# psistat-exporter

psistat-exporter это Prometheus exporter для Linux PSI (Pressure Stall Information).
Он читает PSI-данные Linux и публикует их по HTTP или HTTPS в формате Prometheus text exposition.

## Что экспортируется
Linux PSI (Pressure Stall Information) — это подсистема ядра (начиная с 4.20), 
измеряющая время простоя процессов в ожидании ресурсов (CPU, памяти или I/O). 
В отличие от классического load average, PSI показывает не просто нагрузку, 
а то, как сильно нехватка ресурсов (давление) реально тормозит работу приложений

Exporter собирает PSI-данные из:

- `/proc/pressure/cpu`
- `/proc/pressure/io`
- `/proc/pressure/memory`

Для каждого ресурса и типа stall (`some`, `full`) публикуются:

- вычисляемые короткие средние за `1s`, `3s` и `10s`
- предоставляемые ядром средние за `60s` и `300s`
- накопленное время stall с момента загрузки системы

Также exporter ведёт учёт событий:

- настраиваемый порог в процентах
- настраиваемый интервал события: `1`, `3`, `10`, `60` или `300` секунд
- счётчики событий и информация о последнем событии для каждого PSI-потока

## Зачем нужен этот exporter, если есть `node_exporter --collector.pressure`

Если у вас уже запущен `node_exporter` с collector `pressure` и нужны только стандартные сырые PSI-счётчики, этот exporter может быть не нужен.

Этот exporter полезен в тех случаях, когда PSI нужен не просто как источник низкоуровневых counters, а как практический сигнал для диагностики и алертов:

- заранее вычисленные PSI-средние за `1s`, `3s` и `10s`
- прямой экспорт kernel-значений `60s` и `300s`
- детектирование событий по порогу с логикой cooldown
- экспорт счётчиков событий и информации о последнем событии
- сбор PSI, не зависящий от момента scrape со стороны Prometheus

На практике `node_exporter` удобнее для общего host-monitoring, а этот exporter полезнее для целевого анализа PSI и построения алертов по коротким окнам.

Компромиссы:

- этот exporter создаёт больше PSI-series, чем `node_exporter`
- он сфокусирован на PSI для `cpu`, `io` и `memory`
- если запускать оба exporter'а одновременно, часть PSI-сигналов будет дублироваться под разными именами метрик

## Экспортируемые метрики

Основные метрики:

- `psistat_stall_percent{resource,stall,window}`
- `psistat_stalled_seconds_total{resource,stall}`
- `psistat_event_total{resource,stall,window}`
- `psistat_event_last_timestamp_seconds{resource,stall,window}`
- `psistat_event_last_percent{resource,stall,window}`

Служебные метрики exporter'а:

- `psistat_threshold_percent`
- `psistat_event_interval_seconds`
- `psistat_collection_success`
- `psistat_collection_duration_seconds`
- `psistat_collection_timestamp_seconds`
- `psistat_last_error_timestamp_seconds`
- `psistat_last_error_present`

## Требования

- Linux с поддержкой PSI в ядре
- Python 3.8+
- доступ на чтение к `/proc/pressure/*`

Внешние Python-зависимости не требуются.

## Запуск

Запуск с параметрами по умолчанию:

```bash
python3 psistat-exporter.py
```

Endpoint по умолчанию:

```text
http://0.0.0.0:9104/metrics
```

Справка:

```bash
python3 psistat-exporter.py --help
```

Пример с пользовательским портом и настройками событий:

```bash
python3 psistat-exporter.py --port 9204 --event-interval 10 --threshold-pct 5
```

Пример запуска с HTTPS:

```bash
python3 psistat-exporter.py \
  --listen-address 0.0.0.0 \
  --port 9443 \
  --tls-cert-file /etc/ssl/certs/psi-exporter.crt \
  --tls-key-file /etc/ssl/private/psi-exporter.key
```

## Параметры командной строки

```text
usage: psistat-exporter.py [-h] [--listen-address LISTEN_ADDRESS]
                           [--port PORT] [--metrics-path METRICS_PATH]
                           [--sample-interval SAMPLE_INTERVAL]
                           [-i {1,3,10,60,300}] [-t THRESHOLD_PCT]
                           [--tls-cert-file TLS_CERT_FILE]
                           [--tls-key-file TLS_KEY_FILE]
```

Параметры:

- `--listen-address` адрес привязки HTTP, по умолчанию `0.0.0.0`
- `--port` HTTP-порт, по умолчанию `9104`
- `--metrics-path` путь для метрик, по умолчанию `/metrics`
- `--sample-interval` интервал опроса PSI в секундах, по умолчанию `1.0`
- `--event-interval` окно для событий по порогу, одно из `1,3,10,60,300`
- `--threshold-pct` порог в процентах для отслеживания событий, ограничивается диапазоном `1..99`
- `--tls-cert-file` PEM-файл сертификата, включает HTTPS при использовании вместе с `--tls-key-file`
- `--tls-key-file` PEM-файл приватного ключа для HTTPS

## Пример scrape-конфигурации Prometheus

```yaml
scrape_configs:
  - job_name: psi_exporter
    static_configs:
      - targets:
          - 127.0.0.1:9104
```

## Примечания

- Короткие окна (`1s`, `3s`, `10s`) exporter вычисляет сам из накопительных PSI-счётчиков.
- Длинные окна (`60s`, `300s`) читаются напрямую из файлов PSI, которые предоставляет ядро.
- Пока не накоплено достаточно samples, часть коротких окон может отдаваться как `NaN`.
- HTTPS опционален. Если `--tls-cert-file` и `--tls-key-file` не заданы, exporter работает по обычному HTTP.

## Author

**Tarasov Dmitry**
- Email: dtarasov7@gmail.com

## Attribution
Parts of this code were generated with assistance
