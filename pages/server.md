---
title: BMGeoIP Server Setup
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

For local development and code checks, see the
[development guide]({{ site.baseurl }}{% link pages/development.md %}).

BMGeoIP follows CMDB's standalone HTTP server and systemd installation pattern.
The web interface listens on `0.0.0.0:54300` by default and renders HTML with
Jinja2, with automatic HTML escaping. The dark blue and teal interface follows
CMDB’s header, panels, tables, and schedule controls. It configures cron downloads of the IPv4 and IPv6 CSVs and
shows their paths, modification times, sizes, and live download/import progress.
A scrolling Status Messages box at the bottom follows CMDB’s Timestamp, Source,
and Message columns.
Startup fills missing CSVs and imports both IP families into MariaDB. The IP Address
Lookup form searches those records and displays raw JSON in a nested Lookup Results
box. For lookup behavior and request formats, see
[IP address lookup]({{ site.baseurl }}{% link pages/ip-address-lookup.md %}) and the
[BMGeoIP API]({{ site.baseurl }}{% link pages/api.md %}).

## Database configuration

Provision a MariaDB database using `utf8mb4` and a database account with SELECT,
INSERT, DELETE, UPDATE, CREATE, and INDEX privileges on that database. Startup
creates the `GeoIp` and `GeoIpImport` InnoDB tables. BMGeoIP uses PyMySQL for
connections; no SQLite database is used for live lookups or imports.

Create `/etc/bmgeoip/database.env` before installation. The following values are
examples; replace them with the actual connection settings and a private password:

```text
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=bmgeoip
DB_USER=bmgeoip
DB_PASSWORD=replace-with-private-password
```

The five keys above are required. `DB_SOCKET` is the only optional key and selects
a Unix socket. The file is parsed as plain `KEY=value` data, with blank lines and
lines beginning with `#` ignored. Do not add shell quoting, `export`, duplicate keys,
or additional keys. Make it readable by the `bmgeoip` service account and keep it
private, for example with root ownership, the `bmgeoip` group, and mode `0640`
once that account exists. Restrict `/etc/bmgeoip` appropriately as well.

`--database-env` overrides this path for the server and standalone download runner.
Generated cron entries use the default path; the server's override is not passed
into those entries. `--state-dir` changes CSV and status/settings paths, independently
of the selected MariaDB database.

For a legacy SQLite deployment, stop the old service and dataset jobs, provision
MariaDB, and run this from the updated checkout's virtual environment before
starting the new service:

```sh
.venv/bin/python -B bmgeoip-migrate.py /var/lib/bmgeoip/geoip.sqlite3 --database-env /etc/bmgeoip/database.env
```

The migration requires empty destination GeoIP tables, retains the SQLite source,
and verifies provider text, binary range keys, record counts, and import metadata
before committing both families together. Failure rolls back the copied records.
The installer does not run or deploy this migration command. Alternatively, let
startup import the retained CSVs into MariaDB; this rebuilds data rather than copying
the legacy database.

## Installation

Use Python 3.11 or later with virtual-environment support and systemd. On
Debian/Ubuntu, install the prerequisites:

```sh
sudo apt install python3 python3-venv cron
```

From a checkout separate from `/opt/prod/bmgeoip`, run:

```sh
sudo scripts/install.sh
```

The installer creates the `bmgeoip` system account with a `nologin` shell,
copies application files and the logo to `/opt/prod/bmgeoip`, and installs
Jinja2, python-crontab, pyzmq, and PyMySQL in `/opt/prod/bmgeoip/.venv`. It runs the Python tests,
verifies the systemd unit, enables `bmgeoip-server.service` at boot, starts it, and checks
the health endpoints and rendered home page. It also enables the Debian/Ubuntu
`cron.service`. The process runs as `bmgeoip` with a private temporary directory
and a read-only system filesystem, except for its state directory and the cron
spool. `StateDirectory=bmgeoip` creates `/var/lib/bmgeoip`. The systemd unit
allows the setgid `crontab` helper, following CMDB’s service configuration.
MariaDB must be provisioned separately before starting the service; the installer
does not create the database, database user, or connection settings. See
[database configuration](#database-configuration).

Open `http://<server>:54300/`. The interface has no authentication and is
intended for a trusted LAN. The BMGeoIP ZMQ API binds to
`tcp://0.0.0.0:54301` and also has no authentication. Installation does not
change firewall rules.

## Upgrade and uninstall

From an updated checkout separate from `/opt/prod/bmgeoip`, run:

```sh
sudo scripts/upgrade.sh
```

The upgrade script reuses the installer and preserves downloaded CSVs, download
settings, logs, and the existing cron schedule. It leaves the external MariaDB
database and `/etc/bmgeoip/database.env` in place. It stops
an existing service before updating dependencies and files. If installation
fails, fix the reported error and rerun it; automatic rollback is not provided.

To remove the deployment, run from the separate checkout:

```sh
sudo scripts/uninstall.sh
```

Uninstallation stops and disables `bmgeoip-server.service`, removes its unit and
overrides, deletes the service account's entire crontab, and terminates remaining
processes owned by that account, including CSV downloads. It deletes
`/opt/prod/bmgeoip` and `/var/lib/bmgeoip`, including all downloaded CSVs, settings,
any legacy SQLite file, progress status, and logs, and removes the `bmgeoip` Linux
account and group. Shared system packages and the cron service remain
available for other applications. The external MariaDB database, database account,
and `/etc/bmgeoip/database.env` are not removed by the uninstall script.
Repeated uninstallation handles an absent
deployment or account; failures stop the script so the reported problem can be
fixed before retrying. Reinstallation starts with fresh local files but can reuse
the retained MariaDB records.

## Endpoints and operations

For HTTP lookup, schedule, status, and health contracts, including request formats
and errors, see the [BMGeoIP API reference]({{ site.baseurl }}{% link pages/api.md %}).
The home page is `/`; it serves the CSV schedule, file status, lookup form, and
project version. Styles and scripts are served under `/static/`, and the logo is
`/pages/images/bmgeoip.png`. Page and asset routes accept GET and HEAD.
SIGTERM and Ctrl-C stop the server cleanly; systemd restarts failed processes.

```sh
systemctl status bmgeoip-server.service
journalctl -u bmgeoip-server.service -f
curl -i http://127.0.0.1:54300/health
curl -i http://127.0.0.1:54300/ready
sudo systemctl restart bmgeoip-server.service
```

## Status messages

The bottom panel refreshes every two seconds, showing timestamps in the browser’s
local timezone and the Python module that produced each message. It follows new
messages when scrolled to the bottom; scrolling up keeps earlier messages visible.
Messages cover listener startup and shutdown, saved download schedules, worker lock
waits, skipped cron runs, database initialization, download/extraction/validation/import
phases, unchanged CSVs, record counts, and failures. Transfer and record progress
continue in the Dataset Status panel without adding a history row for every batch.

The newest 1,000 messages persist in `/var/lib/bmgeoip/status-messages.json`, surviving
restarts and including the independent cron runner. Writers share a file lock and
replace the history atomically. A history-write failure is logged without stopping
dataset work. Detailed exceptions remain in the service journal or `download.log`.
`--state-dir` places this history beside the selected schedule settings.

## CSV download schedule

At startup a background worker downloads each missing `ipv4.csv` or `ipv6.csv`,
even when scheduled downloads are disabled. Existing CSVs are imported without
downloading them again. The HTTP listener remains available during this process.
The Dataset Status panel polls every two seconds and shows the current family
and phase: checking, downloading, extracting, validating, importing, ready, or error.
Downloads show transferred bytes and a determinate bar when the provider supplies
the archive size; other phases use an indeterminate bar. Validation and import
show record counts. Failures identify the family and direct users to service logs;
restart the service to retry startup work.

Validated records are stored in the configured MariaDB database. Each family is
replaced in a transaction, preserving its previous records if validation or import
fails. All fourteen provider fields are retained as text. Committed file size and
nanosecond modification time allow restarts to skip imports of unchanged CSVs.
Progress persists in `/var/lib/bmgeoip/data-status.json` so the web page can also
show the independent cron runner's work. Startup and cron share a lock: startup
waits for an existing job, and overlapping cron invocations skip work. Interrupting
an import rolls back its uncommitted changes; startup resumes from the saved CSV.

Use the Enabled checkbox, enter five cron fields, and click Update. The initial
schedule is disabled; its suggested expression `0 3 * * 0` means Sunday at 03:00
in the server’s local timezone. Cron also supports ranges, lists, and steps.
Disabling and saving removes BMGeoIP’s cron entry without removing unrelated
jobs. The settings persist in `/var/lib/bmgeoip/download-schedule.json` and survive
service restarts and installer updates.

The service account’s cron job runs `/opt/prod/bmgeoip/bmgeoip-download.py` using
the installed virtual environment. It works independently of the HTTP server,
rechecks the saved enabled flag, downloads and imports both families, and skips
overlapping invocations. An in-progress
download finishes if the schedule is disabled. Logs append to
`/var/lib/bmgeoip/download.log`.

| Dataset | CSV path |
| --- | --- |
| IPv4 | `/var/lib/bmgeoip/data/ipv4.csv` |
| IPv6 | `/var/lib/bmgeoip/data/ipv6.csv` |

Each family is downloaded and validated independently, so one failure does not
prevent the other family from refreshing. Failed downloads preserve the previous
usable CSV and database records. Reload the webpage to refresh file status; modification times display
in UTC. Provider, path, and default expression settings live in
`bmgeoip/constants/DGeoIp.py`.

```sh
sudo crontab -u bmgeoip -l
tail -n 50 /var/lib/bmgeoip/download.log
```
