# Changelog

## 0.1.0 - 2026-07-07

- Added the `psistat-exporter.py` Prometheus exporter for Linux PSI metrics.
- Added short-window PSI averages, kernel long-window gauges, threshold event counters, and exporter health metrics.
- Added `psistat_info{version}` build information metric.
- Added optional HTTPS support.
- Added a Grafana dashboard with datasource, environment, group, instance, resource, and interval filters.
- Added the `psistat-exporter` Ansible role with a hardened systemd unit and Molecule verification.
