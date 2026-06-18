# psistat-exporter

`psistat-exporter.py` is a Prometheus exporter for Linux PSI (Pressure Stall Information).
It reads Linux PSI data and exposes it over HTTP or HTTPS in Prometheus text format.

## What It Exports

The exporter collects PSI data from:

- `/proc/pressure/cpu`
- `/proc/pressure/io`
- `/proc/pressure/memory`

For each resource and stall type (`some`, `full`) it publishes:

- calculated short-window averages for `1s`, `3s`, and `10s`
- kernel-provided averages for `60s` and `300s`
- cumulative stalled time since boot

It also tracks threshold events:

- configurable threshold percentage
- configurable event interval: `1`, `3`, `10`, `60`, or `300` seconds
- event counters and last event details per PSI stream

## Why Use This Exporter If `node_exporter --collector.pressure` Exists

If you already run `node_exporter` with the `pressure` collector and only need standard raw PSI counters, this exporter may be unnecessary.

This exporter is useful when you need PSI as an operational signal rather than only as a low-level counter source:

- precomputed `1s`, `3s`, and `10s` PSI averages
- direct `60s` and `300s` PSI gauges from the kernel
- threshold event detection with cooldown logic
- exported event counters and last-event details
- PSI sampling that is independent of Prometheus scrape timing

In practice, `node_exporter` pressure metrics are better for broad host monitoring, while this exporter is better for focused PSI troubleshooting and alerting.

Trade-offs:

- this exporter creates more PSI time series than `node_exporter`
- it is focused on `cpu`, `io`, and `memory` PSI
- if you run both exporters, some underlying PSI signals will be duplicated under different metric names

## Exported Metrics

Main metrics:

- `psistat_stall_percent{resource,stall,window}`
- `psistat_stalled_seconds_total{resource,stall}`
- `psistat_event_total{resource,stall,window}`
- `psistat_event_last_timestamp_seconds{resource,stall,window}`
- `psistat_event_last_percent{resource,stall,window}`

Exporter health/configuration metrics:

- `psistat_threshold_percent`
- `psistat_event_interval_seconds`
- `psistat_collection_success`
- `psistat_collection_duration_seconds`
- `psistat_collection_timestamp_seconds`
- `psistat_last_error_timestamp_seconds`
- `psistat_last_error_present`

## Requirements

- Linux with PSI enabled in the kernel
- Python 3.8+
- readable `/proc/pressure/*`

No external Python packages are required.

## Usage

Run with defaults:

```bash
python3 psistat-exporter.py
```

Default endpoint:

```text
http://0.0.0.0:9104/metrics
```

Help:

```bash
python3 psistat-exporter.py --help
```

Example with custom port and event settings:

```bash
python3 psistat-exporter.py --port 9204 --event-interval 10 --threshold-pct 5
```

Example with HTTPS enabled:

```bash
python3 psistat-exporter.py \
  --listen-address 0.0.0.0 \
  --port 9443 \
  --tls-cert-file /etc/ssl/certs/psi-exporter.crt \
  --tls-key-file /etc/ssl/private/psi-exporter.key
```

## Command-Line Options

```text
usage: psistat-exporter.py [-h] [--listen-address LISTEN_ADDRESS]
                           [--port PORT] [--metrics-path METRICS_PATH]
                           [--sample-interval SAMPLE_INTERVAL]
                           [-i {1,3,10,60,300}] [-t THRESHOLD_PCT]
                           [--tls-cert-file TLS_CERT_FILE]
                           [--tls-key-file TLS_KEY_FILE]
```

Options:

- `--listen-address` HTTP bind address, default `0.0.0.0`
- `--port` HTTP port, default `9104`
- `--metrics-path` metrics path, default `/metrics`
- `--sample-interval` PSI sampling interval in seconds, default `1.0`
- `--event-interval` threshold event window, one of `1,3,10,60,300`
- `--threshold-pct` threshold percentage for event tracking, clamped to `1..99`
- `--tls-cert-file` PEM certificate file, enables HTTPS when used together with `--tls-key-file`
- `--tls-key-file` PEM private key file for HTTPS

## Prometheus Scrape Example

```yaml
scrape_configs:
  - job_name: psi_exporter
    static_configs:
      - targets:
          - 127.0.0.1:9104
```

## Notes

- Short-window metrics (`1s`, `3s`, `10s`) are computed by the exporter from cumulative PSI counters.
- Long-window metrics (`60s`, `300s`) are read directly from the kernel PSI files.
- Until enough samples are collected, some short-window values may be exposed as `NaN`.
- HTTPS is optional. If `--tls-cert-file` and `--tls-key-file` are not set, the exporter serves plain HTTP.

## Author

**Tarasov Dmitry**
- Email: dtarasov7@gmail.com

## Attribution
Parts of this code were generated with assistance
