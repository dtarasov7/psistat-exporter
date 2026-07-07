# Роль psistat-exporter

Роль устанавливает `psistat-exporter.py` на целевой Linux-сервер и запускает exporter как hardened `systemd` service.

Exporter публикует Linux PSI metrics в формате Prometheus. По умолчанию сервис слушает `0.0.0.0:9104` и отдаёт метрики на `/metrics`.

## Что делает роль

- создаёт системного пользователя и группу;
- устанавливает Python 3;
- копирует exporter в `/opt/psistat-exporter/bin`;
- создаёт каталоги конфигурации, TLS и логов;
- опционально устанавливает TLS certificate/key из local files или HashiCorp Vault;
- разворачивает environment-файл и `systemd` unit;
- включает и запускает сервис;
- применяет максимально строгий hardening unit-файла без выдачи Linux capabilities.

## Переменные

| Переменная | Значение по умолчанию | Описание |
| --- | --- | --- |
| `psistat_exporter_version` | `0.1.0` | Версия exporter, документируется ролью. |
| `psistat_exporter_service_name` | `psistat-exporter` | Имя systemd service. |
| `psistat_exporter_user` | `psistat-exporter` | Пользователь сервиса. |
| `psistat_exporter_group` | `psistat-exporter` | Группа сервиса. |
| `psistat_exporter_manage_user` | `true` | Создавать пользователя ролью. |
| `psistat_exporter_manage_group` | `true` | Создавать группу ролью. |
| `psistat_exporter_install_dir` | `/opt/psistat-exporter` | Базовый каталог установки. |
| `psistat_exporter_bin_dir` | `{{ psistat_exporter_install_dir }}/bin` | Каталог скрипта exporter. |
| `psistat_exporter_config_dir` | `/etc/psistat-exporter` | Каталог конфигурации. |
| `psistat_exporter_log_dir` | `/var/log/psistat-exporter` | Каталог логов, если stdout/stderr перенаправят из journald. |
| `psistat_exporter_log_archive_dir` | `{{ psistat_exporter_log_dir }}/archive` | Каталог архива логов. |
| `psistat_exporter_ssl_dir` | `{{ psistat_exporter_config_dir }}/ssl` | Каталог TLS-файлов. |
| `psistat_exporter_script_name` | `psistat-exporter.py` | Имя устанавливаемого скрипта. |
| `psistat_exporter_source_file` | `{{ role_path }}/files/psistat-exporter.py` | Источник скрипта на controller. |
| `psistat_exporter_python_interpreter` | `/usr/bin/python3` | Python interpreter в unit-файле. |
| `psistat_exporter_packages` | `[python3]` | Пакеты для установки. |
| `psistat_exporter_versionlock_packages` | `[]` | Пакеты для optional dnf versionlock. |
| `psistat_exporter_listen_address` | `0.0.0.0` | Адрес bind. |
| `psistat_exporter_port` | `9104` | HTTP/HTTPS порт. |
| `psistat_exporter_metrics_path` | `/metrics` | Путь metrics endpoint. |
| `psistat_exporter_sample_interval` | `1.0` | Интервал фонового сбора PSI в секундах. |
| `psistat_exporter_event_interval` | `10` | Окно threshold event: `1`, `3`, `10`, `60`, `300`. |
| `psistat_exporter_threshold_pct` | `5` | Порог PSI event, `1..99`. |
| `psistat_exporter_extra_args` | `[]` | Дополнительные аргументы exporter. |
| `psistat_exporter_service_enabled` | `true` | Включать сервис в boot. |
| `psistat_exporter_service_state` | `started` | Состояние сервиса. |
| `psistat_exporter_validate_psi` | `true` | Проверять `/proc/pressure/*` перед запуском. |
| `psistat_exporter_https` | `false` | Включить HTTPS. |
| `psistat_exporter_no_log` | `true` | Скрывать содержимое TLS-файлов в выводе Ansible. |
| `psistat_exporter_hashi_vault_path` | `""` | Путь HashiCorp Vault для cert/key. Пустая строка означает local files. |
| `psistat_exporter_hashi_vault_path_root` | `""` | Путь Vault для root CA. |
| `psistat_exporter_hashi_vault_path_certificates` | `{{ psistat_exporter_hashi_vault_path }}` | Выбранный источник сертификатов. |
| `psistat_exporter_certfile` | `{{ inventory_hostname_short \| lower }}.cer` | Имя certificate file. |
| `psistat_exporter_cerkeyfile` | `{{ inventory_hostname_short \| lower }}.key` | Имя private key file. |
| `psistat_exporter_cacertfile` | `root.cer` | Имя root CA file. |
| `psistat_exporter_local_certs_path` | `./certs/` | Локальный путь к cert/key на controller. |
| `psistat_exporter_certificates` | список | Подготовленный список certificate contents из Vault или local files. |
| `psistat_exporter_tls_cert_path` | `{{ psistat_exporter_ssl_dir }}/{{ psistat_exporter_certfile \| basename }}` | Путь certificate на target. |
| `psistat_exporter_tls_key_path` | `{{ psistat_exporter_ssl_dir }}/{{ psistat_exporter_cerkeyfile \| basename }}` | Путь private key на target. |
| `psistat_exporter_systemd_*` | см. `defaults/main.yml` | Параметры restart policy и hardening. |

## TLS

Для local files:

```yaml
psistat_exporter_https: true
psistat_exporter_local_certs_path: ./certs/
psistat_exporter_certfile: host.cer
psistat_exporter_cerkeyfile: host.key
psistat_exporter_cacertfile: root.cer
```

Для HashiCorp Vault:

```yaml
psistat_exporter_https: true
psistat_exporter_hashi_vault_path: "secret=opensource-{{ project_name }}/data/cert/{{ inventory_hostname_short | lower }}:"
psistat_exporter_hashi_vault_path_root: "secret=opensource-{{ project_name }}/data/cert/root:"
```

Переключение между Vault и local files выполняется только переменными. Task-файлы не содержат логики выбора источника.

## Теги

- `pre-req` - проверки ОС, systemd, настроек, PSI и TLS content;
- `user` - пользователь и группа;
- `install` - пакеты, каталоги, скрипт exporter, optional versionlock;
- `ssl`, `certs` - TLS certificate/key/root CA;
- `config` - environment-файл, systemd unit, запуск сервиса;
- `clean` + `never` - удалить сервис, файлы, каталоги и пользователя.

## Пример inventory

```yaml
all:
  hosts:
    psi01:
      ansible_host: 192.168.1.146
      psistat_exporter_listen_address: "0.0.0.0"
      psistat_exporter_port: 9104
      psistat_exporter_threshold_pct: 5
      psistat_exporter_event_interval: 10
```

## Пример playbook

```yaml
---
- name: Install psistat-exporter
  hosts: psi_exporters
  become: true
  roles:
    - role: psistat-exporter
```

## Hardening systemd

Unit-файл использует:

- `NoNewPrivileges=true`;
- пустые `CapabilityBoundingSet` и `AmbientCapabilities`;
- `ProtectSystem=strict`, `ProtectHome=true`;
- `PrivateTmp=true`, `PrivateDevices=true`, `PrivateMounts=true`;
- `ProtectKernelTunables=true`, `ProtectKernelModules=true`, `ProtectKernelLogs=true`, `ProtectControlGroups=true`;
- `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`;
- `SystemCallFilter=@system-service` и deny-list dangerous syscall groups;
- `ReadOnlyPaths=/proc/pressure`.

Если старый systemd не поддерживает часть директив, systemd обычно пишет warning и игнорирует неизвестные параметры.

## Logrotate

Exporter пишет stdout/stderr в journald через systemd. Файловые логи роль не создаёт, поэтому logrotate не настраивается. Каталог `/var/log/psistat-exporter` создан для случаев, когда оператор перенаправит вывод в файлы вне этой роли.

## Molecule

Сценарий `molecule/default` использует Docker driver и systemd container на `rockylinux:9`.

Проверки:

- service `psistat-exporter` active;
- endpoint `http://127.0.0.1:9104/metrics` отвечает;
- metrics содержат `psistat_info` и `psistat_collection_success`;
- unit содержит ключевые hardening directives.

Запуск:

```bash
cd roles/psistat-exporter
molecule test
```
