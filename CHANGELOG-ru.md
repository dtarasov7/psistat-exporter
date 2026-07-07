# История изменений

## 0.1.0 - 2026-07-07

- Добавлен Prometheus exporter `psistat-exporter.py` для Linux PSI metrics.
- Добавлены короткие PSI-средние, длинные kernel-окна, счётчики threshold events и служебные метрики exporter'а.
- Добавлена информационная метрика `psistat_info{version}`.
- Добавлена опциональная поддержка HTTPS.
- Добавлен Grafana dashboard с фильтрами datasource, env, group, instance, resource и interval.
- Добавлена Ansible-роль `psistat-exporter` с hardened systemd unit и Molecule-проверкой.
