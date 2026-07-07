# psistat-exporter Role

This role installs `psistat-exporter.py` on a target Linux server and runs it as a hardened `systemd` service.

The exporter exposes Linux PSI metrics in Prometheus text format. By default, the service listens on `0.0.0.0:9104` and serves metrics on `/metrics`.

## What The Role Does

- creates a system user and group;
- installs Python 3;
- copies the exporter to `/opt/psistat-exporter/bin`;
- creates configuration, TLS, and log directories;
- optionally installs TLS certificate/key from local files or HashiCorp Vault;
- renders the environment file and `systemd` unit;
- enables and starts the service;
- applies strict systemd hardening without granting Linux capabilities.

## Variables

| Variable | Default | Description |
| --- | --- | --- |
| `psistat_exporter_version` | `0.1.0` | Exporter version documented by the role. |
| `psistat_exporter_service_name` | `psistat-exporter` | systemd service name. |
| `psistat_exporter_user` | `psistat-exporter` | Service user. |
| `psistat_exporter_group` | `psistat-exporter` | Service group. |
| `psistat_exporter_manage_user` | `true` | Create the user. |
| `psistat_exporter_manage_group` | `true` | Create the group. |
| `psistat_exporter_install_dir` | `/opt/psistat-exporter` | Base install directory. |
| `psistat_exporter_bin_dir` | `{{ psistat_exporter_install_dir }}/bin` | Exporter script directory. |
| `psistat_exporter_config_dir` | `/etc/psistat-exporter` | Configuration directory. |
| `psistat_exporter_log_dir` | `/var/log/psistat-exporter` | Log directory if stdout/stderr is redirected from journald. |
| `psistat_exporter_log_archive_dir` | `{{ psistat_exporter_log_dir }}/archive` | Log archive directory. |
| `psistat_exporter_ssl_dir` | `{{ psistat_exporter_config_dir }}/ssl` | TLS files directory. |
| `psistat_exporter_script_name` | `psistat-exporter.py` | Installed script name. |
| `psistat_exporter_source_file` | `{{ role_path }}/files/psistat-exporter.py` | Exporter source file on the controller. |
| `psistat_exporter_python_interpreter` | `/usr/bin/python3` | Python interpreter used in the unit. |
| `psistat_exporter_packages` | `[python3]` | Packages to install. |
| `psistat_exporter_versionlock_packages` | `[]` | Optional packages for dnf versionlock. |
| `psistat_exporter_listen_address` | `0.0.0.0` | Bind address. |
| `psistat_exporter_port` | `9104` | HTTP/HTTPS port. |
| `psistat_exporter_metrics_path` | `/metrics` | Metrics endpoint path. |
| `psistat_exporter_sample_interval` | `1.0` | Background PSI sample interval in seconds. |
| `psistat_exporter_event_interval` | `10` | Threshold event window: `1`, `3`, `10`, `60`, `300`. |
| `psistat_exporter_threshold_pct` | `5` | PSI event threshold, `1..99`. |
| `psistat_exporter_extra_args` | `[]` | Extra exporter arguments. |
| `psistat_exporter_service_enabled` | `true` | Enable the service at boot. |
| `psistat_exporter_service_state` | `started` | Desired service state. |
| `psistat_exporter_validate_psi` | `true` | Validate `/proc/pressure/*` before starting. |
| `psistat_exporter_https` | `false` | Enable HTTPS. |
| `psistat_exporter_no_log` | `true` | Hide TLS file contents from Ansible output. |
| `psistat_exporter_hashi_vault_path` | `""` | HashiCorp Vault path for cert/key. Empty means local files. |
| `psistat_exporter_hashi_vault_path_root` | `""` | Vault path for the root CA. |
| `psistat_exporter_hashi_vault_path_certificates` | `{{ psistat_exporter_hashi_vault_path }}` | Selected certificate source. |
| `psistat_exporter_certfile` | `{{ inventory_hostname_short \| lower }}.cer` | Certificate file name. |
| `psistat_exporter_cerkeyfile` | `{{ inventory_hostname_short \| lower }}.key` | Private key file name. |
| `psistat_exporter_cacertfile` | `root.cer` | Root CA file name. |
| `psistat_exporter_local_certs_path` | `./certs/` | Local certificate path on the controller. |
| `psistat_exporter_certificates` | list | Prepared certificate contents from Vault or local files. |
| `psistat_exporter_tls_cert_path` | `{{ psistat_exporter_ssl_dir }}/{{ psistat_exporter_certfile \| basename }}` | Target certificate path. |
| `psistat_exporter_tls_key_path` | `{{ psistat_exporter_ssl_dir }}/{{ psistat_exporter_cerkeyfile \| basename }}` | Target private key path. |
| `psistat_exporter_systemd_*` | see `defaults/main.yml` | Restart policy and hardening settings. |

## TLS

Local files:

```yaml
psistat_exporter_https: true
psistat_exporter_local_certs_path: ./certs/
psistat_exporter_certfile: host.cer
psistat_exporter_cerkeyfile: host.key
psistat_exporter_cacertfile: root.cer
```

HashiCorp Vault:

```yaml
psistat_exporter_https: true
psistat_exporter_hashi_vault_path: "secret=opensource-{{ project_name }}/data/cert/{{ inventory_hostname_short | lower }}:"
psistat_exporter_hashi_vault_path_root: "secret=opensource-{{ project_name }}/data/cert/root:"
```

Switching between Vault and local files requires variable changes only. Task files do not contain source-selection logic.

## Tags

- `pre-req` - OS, systemd, settings, PSI, and TLS content checks;
- `user` - user and group;
- `install` - packages, directories, exporter script, optional versionlock;
- `ssl`, `certs` - TLS certificate/key/root CA;
- `config` - environment file, systemd unit, service startup;
- `clean` + `never` - remove the service, files, directories, and user.

## Inventory Example

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

## Playbook Example

```yaml
---
- name: Install psistat-exporter
  hosts: psi_exporters
  become: true
  roles:
    - role: psistat-exporter
```

## systemd Hardening

The unit uses:

- `NoNewPrivileges=true`;
- empty `CapabilityBoundingSet` and `AmbientCapabilities`;
- `ProtectSystem=strict`, `ProtectHome=true`;
- `PrivateTmp=true`, `PrivateDevices=true`, `PrivateMounts=true`;
- `ProtectKernelTunables=true`, `ProtectKernelModules=true`, `ProtectKernelLogs=true`, `ProtectControlGroups=true`;
- `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`;
- `SystemCallFilter=@system-service` plus a deny-list for dangerous syscall groups;
- `ReadOnlyPaths=/proc/pressure`.

If an old systemd version does not support some directives, systemd normally logs a warning and ignores unknown settings.

## Logrotate

The exporter writes stdout/stderr to journald through systemd. The role does not create file logs, so it does not configure logrotate. `/var/log/psistat-exporter` is created for operators who redirect output to files outside this role.

## Molecule

The `molecule/default` scenario uses the Docker driver and a systemd container based on `rockylinux:9`.

Checks:

- service `psistat-exporter` is active;
- endpoint `http://127.0.0.1:9104/metrics` responds;
- metrics contain `psistat_info` and `psistat_collection_success`;
- the unit contains key hardening directives.

Run:

```bash
cd roles/psistat-exporter
molecule test
```
