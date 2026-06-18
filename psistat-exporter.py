#!/usr/bin/env python3
"""
Prometheus exporter for Linux Pressure Stall Information (PSI).
Prometheus exporter для Linux Pressure Stall Information (PSI).

The exporter exposes:
Экспортер публикует:
    - 1s, 3s, 10s calculated running averages
    - вычисляемые средние за 1s, 3s, 10s
    - 60s, 300s kernel-provided averages
    - средние avg60 и avg300, предоставляемые ядром
    - optional threshold event tracking for one selected interval
    - опциональный учет событий по порогу для выбранного интервала
"""

import argparse
import math
import re
import signal
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace


SAMPLES = 11
WINDOWS = (1, 3, 10, 60, 300)
SHORT_WINDOWS = (1, 3, 10)
PRESSURE_GROUPS = ("cpu", "io", "memory")
STALL_TYPES = ("full", "some")

# The kernel PSI files expose avg60/avg300 directly; shorter windows are computed locally.
# Файлы PSI ядра отдают avg60/avg300 напрямую; более короткие окна вычисляются локально.
PATTERN = re.compile(
    r"^(\S+)\b.*\bavg60=(\d+\.\d+)\b.*\bavg300=(\d+\.\d+)\b.*\btotal=(\d+)$"
)


def make_series():
    """Create storage for one PSI resource/stall stream.

    EN: Keeps recent cumulative counters, kernel averages, and the latest total.
    RU: Хранит последние накопительные счетчики, средние ядра и последний total.

    Returns:
        SimpleNamespace: Mutable fields `micros`, `avgs`, and `total`.
    """
    return SimpleNamespace(micros=[], avgs={60: math.nan, 300: math.nan}, total=0)


def format_prom_value(value):
    """Render a value for Prometheus text exposition.

    EN: Converts `NaN` floats to the literal accepted by Prometheus.
    RU: Преобразует float `NaN` в литерал, который принимает Prometheus.

    Args:
        value (object): Numeric or string-like value to render.

    Returns:
        str: Prometheus-compatible value text.
    """
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    return f"{value}"


def prom_labels(**labels):
    """Format metric labels for Prometheus exposition.

    EN: Escapes label values according to the Prometheus text format.
    RU: Экранирует значения меток по правилам Prometheus text format.

    Args:
        **labels (object): Label names and values.

    Returns:
        str: Label block such as `{resource="cpu",window="10s"}`.
    """
    parts = []
    for key, value in labels.items():
        # Prometheus requires backslash, newline, and quote escaping in label values.
        # Prometheus требует экранировать backslash, newline и кавычки в значениях меток.
        escaped = (
            str(value)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace('"', '\\"')
        )
        parts.append(f'{key}="{escaped}"')
    return "{" + ",".join(parts) + "}"


def enable_tls(server, cert_file, key_file):
    """Wrap the HTTP server socket with TLS.

    EN: Loads the certificate pair and replaces the server socket with an SSL socket.
    RU: Загружает пару certificate/key и заменяет сокет сервера на SSL socket.

    Args:
        server (ThreadingHTTPServer): Server whose socket must be wrapped.
        cert_file (str): Path to a PEM certificate file.
        key_file (str): Path to a PEM private key file.

    Returns:
        None: The server is modified in place.

    Raises:
        OSError: Certificate or key file cannot be read.
        ssl.SSLError: Certificate or key content is invalid.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)


class PressureGroup:
    """Read one `/proc/pressure/<group>` file into shared PSI storage.

    EN: Owns one open file handle and updates resource/stall sample series.
    RU: Владеет одним открытым file handle и обновляет серии resource/stall.
    """

    def __init__(self, tag, stats):
        """Initialize a PSI pressure group reader.

        EN: Opens `/proc/pressure/<tag>` immediately so startup fails on bad access.
        RU: Сразу открывает `/proc/pressure/<tag>`, чтобы ошибка доступа была видна при старте.

        Args:
            tag (str): PSI resource name, for example `cpu`, `io`, or `memory`.
            stats (dict[str, SimpleNamespace]): Shared collector storage keyed by `resource.stall`.

        Returns:
            None: Initializes instance state.

        Raises:
            FileNotFoundError: The PSI file does not exist.
            PermissionError: The PSI file cannot be read by this process.
            OSError: Opening the PSI file fails for another reason.
        """
        self.tag = tag
        self.stats = stats
        self.fullpath = "/proc/pressure/" + tag
        self.handle = open(self.fullpath, encoding="utf-8")

    def add_sample(self):
        """Read and parse the current PSI group document.

        EN: Updates cumulative counters, kernel averages, and placeholder samples for absent stall types.
        RU: Обновляет накопительные счетчики, средние ядра и placeholder samples для отсутствующих stall types.

        Returns:
            None: Mutates the shared `stats` mapping.

        Raises:
            OSError: Seeking or reading the PSI file fails.
        """
        self.handle.seek(0)
        document = self.handle.read()
        seen = set()
        for line in document.splitlines():
            match = PATTERN.match(line)
            if not match:
                continue
            stall_type, avg60, avg300, micro = match.groups()
            if stall_type not in STALL_TYPES:
                continue
            key = f"{self.tag}.{stall_type}"
            series = self.stats.get(key)
            if series is None:
                series = self.stats[key] = make_series()
            series.micros.insert(0, int(micro))
            del series.micros[SAMPLES:]
            series.avgs[60] = float(avg60)
            series.avgs[300] = float(avg300)
            series.total = int(micro)
            seen.add(stall_type)

        # Some kernels/resources omit unsupported stall rows, for example `cpu full`.
        # Некоторые kernels/resources не отдают неподдерживаемые строки, например `cpu full`.
        # Keep sample arrays aligned with `monos` by repeating the last known total.
        # Держим sample arrays выровненными с `monos`, повторяя последний известный total.
        missing = set(STALL_TYPES) - seen
        for stall_type in missing:
            key = f"{self.tag}.{stall_type}"
            series = self.stats.get(key)
            if series is None:
                series = self.stats[key] = make_series()
            series.micros.insert(0, series.total)
            del series.micros[SAMPLES:]

    def close(self):
        """Close the PSI file handle.

        EN: Releases the open `/proc/pressure/<group>` descriptor.
        RU: Освобождает открытый дескриптор `/proc/pressure/<group>`.

        Returns:
            None: The handle is closed in place.

        Raises:
            OSError: Closing the handle fails.
        """
        self.handle.close()


class PsiCollector:
    """Collect PSI samples in the background and render metrics snapshots.

    EN: Coordinates file readers, rolling sample history, threshold events, and health metrics.
    RU: Координирует readers, rolling sample history, threshold events и служебные метрики.
    """

    def __init__(self, sample_interval, threshold_pct, event_interval):
        """Initialize collector state and PSI file readers.

        EN: Pre-allocates all resource/stall streams so metrics remain stable across scrapes.
        RU: Заранее создает все resource/stall streams, чтобы metrics были стабильны между scrape.

        Args:
            sample_interval (float): Seconds between background collection cycles.
            threshold_pct (int): Event threshold percentage clamped by argument parsing.
            event_interval (int): Averaging window used for threshold event detection.

        Returns:
            None: Initializes instance state.

        Raises:
            OSError: Opening any `/proc/pressure/*` file fails.
        """
        self.sample_interval = sample_interval
        self.threshold_pct = threshold_pct
        self.event_interval = event_interval
        self.stats = {
            f"{group}.{stall_type}": make_series()
            for group in PRESSURE_GROUPS
            for stall_type in STALL_TYPES
        }
        self.event_counts = {key: 0 for key in self.stats}
        self.event_last_timestamp = {key: math.nan for key in self.stats}
        self.event_last_percent = {key: math.nan for key in self.stats}
        self.event_floor = {}
        self.monos = []
        self.last_collection_timestamp = math.nan
        self.last_collection_duration_seconds = math.nan
        self.last_error_timestamp = math.nan
        self.last_error_message = ""
        self.collection_success = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._groups = [PressureGroup(tag, self.stats) for tag in PRESSURE_GROUPS]

    def start(self):
        """Start the background collection thread.

        EN: Performs one synchronous collection before the first HTTP scrape can arrive.
        RU: Выполняет один синхронный сбор до первого возможного HTTP scrape.

        Returns:
            None: Starts a daemon thread.
        """
        self.collect_once()
        self._thread = threading.Thread(target=self._run, name="psi-collector", daemon=True)
        self._thread.start()

    def stop(self):
        """Stop collection and close PSI file handles.

        EN: Signals the thread, waits briefly, and releases all readers.
        RU: Посылает thread сигнал остановки, коротко ждет и освобождает все readers.

        Returns:
            None: Mutates collector lifecycle state.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.sample_interval + 1.0)
        for group in self._groups:
            group.close()

    def _run(self):
        """Run the fixed-interval collector loop.

        EN: Uses monotonic time so wall-clock jumps do not move the sampling cadence.
        RU: Использует monotonic time, чтобы скачки системного времени не сбивали ритм опроса.

        Returns:
            None: Exits when `_stop_event` is set.
        """
        next_tick = time.monotonic()
        while not self._stop_event.is_set():
            next_tick += self.sample_interval
            wait_time = max(0.0, next_tick - time.monotonic())
            if self._stop_event.wait(wait_time):
                return
            self.collect_once()

    def collect_once(self):
        """Collect one full PSI sample set.

        EN: Reads every pressure group, trims invalid history, updates health, and detects events.
        RU: Читает все pressure groups, обрезает некорректную историю, обновляет health и обнаруживает события.

        Returns:
            None: Stores results internally.
        """
        started = time.monotonic()
        now = time.time()

        try:
            with self._lock:
                for group in self._groups:
                    group.add_sample()
                mono_ns = time.monotonic_ns()
                self.monos.insert(0, mono_ns)
                del self.monos[SAMPLES:]
                # A late collection would distort short-window percentages, so discard older history.
                # Запоздавший сбор исказил бы короткие проценты, поэтому старая history отбрасывается.
                valid_count = self._count_valid_samples_locked()
                del self.monos[valid_count:]
                for series in self.stats.values():
                    del series.micros[valid_count:]

                self.last_collection_timestamp = now
                self.last_collection_duration_seconds = time.monotonic() - started
                self.collection_success = 1
                self.last_error_message = ""
                self._update_events_locked(now, valid_count)
        except Exception as exc:
            with self._lock:
                self.last_collection_duration_seconds = time.monotonic() - started
                self.last_error_timestamp = now
                self.last_error_message = str(exc)
                self.collection_success = 0
            print(f"psi collection failed: {exc}", file=sys.stderr)

    def _count_valid_samples_locked(self):
        """Count samples whose collection gaps are acceptable.

        EN: The caller must hold `_lock`; counting stops at the first gap above 1.25 seconds.
        RU: Вызывающий код должен держать `_lock`; подсчет останавливается на первом gap больше 1.25 seconds.

        Returns:
            int: Number of newest samples usable for short-window calculations.
        """
        count = 1
        for idx in range(0, len(self.monos) - 1):
            delta_ns = self.monos[idx] - self.monos[idx + 1]
            if delta_ns > 1_250_000_000:
                break
            count += 1
        return count

    def _calculate_pct_locked(self, key, window, valid_count):
        """Calculate PSI percentage for one stream and window.

        EN: Short windows are derived from cumulative counters; long windows use kernel averages.
        RU: Короткие окна вычисляются из накопительных counters; длинные берутся из kernel averages.

        Args:
            key (str): Stream key in `resource.stall` format.
            window (int): Averaging window in seconds.
            valid_count (int): Number of aligned samples considered valid.

        Returns:
            float: Stall percentage, or `math.nan` until enough samples exist.
        """
        series = self.stats[key]
        micros = series.micros
        if window in SHORT_WINDOWS:
            if valid_count <= window or len(micros) <= window:
                return math.nan
            delta_micros = micros[0] - micros[window]
            delta_monos = self.monos[0] - self.monos[window]
            if delta_monos <= 0:
                return 0.0
            # PSI totals are microseconds, monotonic timestamps are nanoseconds:
            # percent = (delta_us * 1000 ns/us) / delta_ns * 100.
            # PSI totals в microseconds, monotonic timestamps в nanoseconds:
            # percent = (delta_us * 1000 ns/us) / delta_ns * 100.
            return 100.0 * 1000.0 * delta_micros / delta_monos
        return series.avgs[window]

    def _update_events_locked(self, now, valid_count):
        """Track threshold events for the configured interval.

        EN: Counts at most one event per stream during each event interval cooldown.
        RU: Считает не больше одного события на stream за время cooldown event interval.

        Args:
            now (float): Current Unix timestamp in seconds.
            valid_count (int): Number of aligned samples considered valid.

        Returns:
            None: Updates event counters and last-event fields.
        """
        for key in self.stats:
            pct = self._calculate_pct_locked(key, self.event_interval, valid_count)
            if math.isnan(pct):
                continue
            floor_key = f"{key}.{self.event_interval}"
            floor = self.event_floor.get(floor_key, 0.0)
            # Round before comparing so event decisions match the visible metric precision.
            # Округляем перед сравнением, чтобы решение по событию совпадало с видимой precision metric.
            if round(pct, 2) < self.threshold_pct or now < floor:
                continue
            self.event_counts[key] += 1
            self.event_last_timestamp[key] = now
            self.event_last_percent[key] = pct
            self.event_floor[floor_key] = now + self.event_interval

    def render_metrics(self):
        """Render a consistent Prometheus metrics snapshot.

        EN: Holds the collector lock while values are calculated and formatted.
        RU: Держит lock collector'а, пока значения вычисляются и форматируются.

        Returns:
            str: Complete Prometheus text exposition payload ending with a newline.
        """
        with self._lock:
            valid_count = self._count_valid_samples_locked()
            lines = [
                "# HELP psistat_stall_percent PSI stalled time as a percentage for each resource, stall type, and averaging window.",
                "# TYPE psistat_stall_percent gauge",
            ]

            for key in self.stats:
                resource, stall_type = key.split(".")
                for window in WINDOWS:
                    pct = self._calculate_pct_locked(key, window, valid_count)
                    lines.append(
                        "psistat_stall_percent"
                        + prom_labels(resource=resource, stall=stall_type, window=f"{window}s")
                        + " "
                        + format_prom_value(pct)
                    )

            lines.extend(
                [
                    "# HELP psistat_stalled_seconds_total Total stalled time reported by the kernel since boot.",
                    "# TYPE psistat_stalled_seconds_total counter",
                ]
            )
            for key, series in self.stats.items():
                resource, stall_type = key.split(".")
                stalled_seconds = series.total / 1_000_000.0
                lines.append(
                    "psistat_stalled_seconds_total"
                    + prom_labels(resource=resource, stall=stall_type)
                    + " "
                    + format_prom_value(stalled_seconds)
                )

            lines.extend(
                [
                    "# HELP psistat_threshold_percent Configured threshold used for event detection.",
                    "# TYPE psistat_threshold_percent gauge",
                    f"psistat_threshold_percent {format_prom_value(float(self.threshold_pct))}",
                    "# HELP psistat_event_interval_seconds Configured averaging interval used for event detection.",
                    "# TYPE psistat_event_interval_seconds gauge",
                    f"psistat_event_interval_seconds {format_prom_value(float(self.event_interval))}",
                    "# HELP psistat_event_total Number of threshold events detected by the exporter.",
                    "# TYPE psistat_event_total counter",
                ]
            )
            for key, count in self.event_counts.items():
                resource, stall_type = key.split(".")
                lines.append(
                    "psistat_event_total"
                    + prom_labels(
                        resource=resource,
                        stall=stall_type,
                        window=f"{self.event_interval}s",
                    )
                    + f" {count}"
                )

            lines.extend(
                [
                    "# HELP psistat_event_last_timestamp_seconds Unix timestamp of the most recent threshold event.",
                    "# TYPE psistat_event_last_timestamp_seconds gauge",
                ]
            )
            for key, timestamp in self.event_last_timestamp.items():
                resource, stall_type = key.split(".")
                lines.append(
                    "psistat_event_last_timestamp_seconds"
                    + prom_labels(
                        resource=resource,
                        stall=stall_type,
                        window=f"{self.event_interval}s",
                    )
                    + " "
                    + format_prom_value(timestamp)
                )

            lines.extend(
                [
                    "# HELP psistat_event_last_percent PSI percentage of the most recent threshold event.",
                    "# TYPE psistat_event_last_percent gauge",
                ]
            )
            for key, pct in self.event_last_percent.items():
                resource, stall_type = key.split(".")
                lines.append(
                    "psistat_event_last_percent"
                    + prom_labels(
                        resource=resource,
                        stall=stall_type,
                        window=f"{self.event_interval}s",
                    )
                    + " "
                    + format_prom_value(pct)
                )

            error_present = 1.0 if self.last_error_message else 0.0
            lines.extend(
                [
                    "# HELP psistat_collection_success Whether the most recent background collection succeeded.",
                    "# TYPE psistat_collection_success gauge",
                    f"psistat_collection_success {self.collection_success}",
                    "# HELP psistat_collection_duration_seconds Duration of the most recent collection cycle.",
                    "# TYPE psistat_collection_duration_seconds gauge",
                    f"psistat_collection_duration_seconds {format_prom_value(self.last_collection_duration_seconds)}",
                    "# HELP psistat_collection_timestamp_seconds Unix timestamp of the most recent collection cycle.",
                    "# TYPE psistat_collection_timestamp_seconds gauge",
                    f"psistat_collection_timestamp_seconds {format_prom_value(self.last_collection_timestamp)}",
                    "# HELP psistat_last_error_timestamp_seconds Unix timestamp of the most recent collection error.",
                    "# TYPE psistat_last_error_timestamp_seconds gauge",
                    f"psistat_last_error_timestamp_seconds {format_prom_value(self.last_error_timestamp)}",
                    "# HELP psistat_last_error_present Whether the exporter has recorded a collection error.",
                    "# TYPE psistat_last_error_present gauge",
                    f"psistat_last_error_present {format_prom_value(error_present)}",
                ]
            )
            return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    """Serve exporter HTTP responses.

    EN: Returns a small landing response, Prometheus metrics, or 404 for other paths.
    RU: Отдает короткий landing response, Prometheus metrics или 404 для других paths.
    """

    collector = None
    metrics_path = "/metrics"

    def do_GET(self):  # noqa: N802 - stdlib handler signature
        """Handle HTTP GET requests.

        EN: Writes responses directly to the socket managed by `BaseHTTPRequestHandler`.
        RU: Пишет ответы напрямую в socket, которым управляет `BaseHTTPRequestHandler`.

        Returns:
            None: Sends the HTTP response as a side effect.
        """
        if self.path == "/" or self.path == "":
            payload = (
                "psistat exporter\n"
                f"metrics: {self.metrics_path}\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # Prometheus should scrape only the configured metrics path; every other path is explicit 404.
        # Prometheus должен читать только настроенный metrics path; любой другой path получает явный 404.
        if self.path != self.metrics_path:
            self.send_error(404)
            return

        payload = self.collector.render_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        """Log HTTP access lines to stderr.

        EN: Keeps the stdlib log format while routing logs to the process stderr.
        RU: Сохраняет stdlib log format и направляет logs в stderr процесса.

        Args:
            fmt (str): Format string from `BaseHTTPRequestHandler`.
            *args (object): Values interpolated into `fmt`.

        Returns:
            None: Writes one access log line.
        """
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), fmt % args)
        )


def parse_args():
    """Parse and validate CLI options.

    EN: Applies defaults, clamps the event threshold, and validates coupled TLS options.
    RU: Применяет defaults, ограничивает event threshold и проверяет связанные TLS options.

    Returns:
        argparse.Namespace: Validated command-line configuration.

    Raises:
        SystemExit: `argparse` exits after invalid input or `--help`.
    """
    parser = argparse.ArgumentParser(
        description="Export Linux PSI metrics in Prometheus format."
    )
    parser.add_argument(
        "--listen-address",
        default="0.0.0.0",
        help="address to bind HTTP server [default: %(default)s]",
    )
    parser.add_argument(
        "--port",
        default=9104,
        type=int,
        help="HTTP port to listen on [default: %(default)s]",
    )
    parser.add_argument(
        "--metrics-path",
        default="/metrics",
        help="HTTP path for Prometheus metrics [default: %(default)s]",
    )
    parser.add_argument(
        "--sample-interval",
        default=1.0,
        type=float,
        help="background PSI sample interval in seconds [default: %(default)s]",
    )
    parser.add_argument(
        "-i",
        "--event-interval",
        default=10,
        type=int,
        choices=WINDOWS,
        help="average interval used for threshold event tracking",
    )
    parser.add_argument(
        "-t",
        "--threshold-pct",
        default=5,
        type=int,
        help="event threshold percent [1-99, default: %(default)s]",
    )
    parser.add_argument(
        "--tls-cert-file",
        help="enable HTTPS using this PEM certificate file",
    )
    parser.add_argument(
        "--tls-key-file",
        help="PEM private key file for HTTPS",
    )
    args = parser.parse_args()

    # Keep the runtime path simple by normalizing user input once at startup.
    # Упрощаем runtime path, нормализуя пользовательский ввод один раз при старте.
    args.threshold_pct = min(max(args.threshold_pct, 1), 99)
    if args.sample_interval <= 0:
        parser.error("--sample-interval must be > 0")
    if not args.metrics_path.startswith("/"):
        parser.error("--metrics-path must start with '/'")
    if bool(args.tls_cert_file) != bool(args.tls_key_file):
        parser.error("--tls-cert-file and --tls-key-file must be provided together")
    return args


def main():
    """Run the PSI exporter process.

    EN: Starts collection, configures HTTP/HTTPS serving, and performs graceful shutdown.
    RU: Запускает collection, настраивает HTTP/HTTPS serving и выполняет graceful shutdown.

    Returns:
        None: Runs until the HTTP server stops.
    """
    args = parse_args()
    collector = PsiCollector(
        sample_interval=args.sample_interval,
        threshold_pct=args.threshold_pct,
        event_interval=args.event_interval,
    )
    collector.start()

    MetricsHandler.collector = collector
    MetricsHandler.metrics_path = args.metrics_path
    server = ThreadingHTTPServer((args.listen_address, args.port), MetricsHandler)
    scheme = "http"
    if args.tls_cert_file:
        enable_tls(server, args.tls_cert_file, args.tls_key_file)
        scheme = "https"

    def shutdown_handler(signum, _frame):
        """Request graceful server shutdown after SIGINT or SIGTERM.

        EN: Runs `server.shutdown()` outside the signal handler stack to avoid blocking it.
        RU: Запускает `server.shutdown()` вне signal handler stack, чтобы не блокировать его.

        Args:
            signum (int): Received signal number.
            _frame (frame): Current stack frame provided by `signal`.

        Returns:
            None: Schedules the shutdown.
        """
        print(f"received signal {signum}, shutting down", file=sys.stderr)
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, shutdown_handler)

    print(
        f"listening on {scheme}://{args.listen_address}:{args.port}{args.metrics_path}",
        file=sys.stderr,
    )

    try:
        server.serve_forever()
    finally:
        server.server_close()
        collector.stop()


if __name__ == "__main__":
    main()
