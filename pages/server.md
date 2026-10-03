---
title: BMGeoIP Server
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

BMGeoIP follows CMDB's standalone HTTP server and systemd installation pattern.
The web interface listens on `0.0.0.0:54300` by default and renders HTML with
Jinja2, with automatic HTML escaping. The dark blue and teal interface follows
CMDB’s header, panels, tables, and schedule controls. It configures cron downloads of the IPv4 and IPv6 CSVs and
shows their paths, modification times, sizes, and live download/import progress.
A scrolling Status Messages box at the bottom follows CMDB’s Timestamp, Source,
and Message columns.
Startup fills missing CSVs and imports both IP families into SQLite. The IP Address
Lookup form searches those records and displays raw JSON in a nested Lookup Results
box. ZMQ messaging is not implemented yet.

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
Jinja2 and python-crontab in `/opt/prod/bmgeoip/.venv`. It runs the Python tests,
verifies the systemd unit, enables `bmgeoip-server.service` at boot, starts it, and checks
the health endpoints and rendered home page. It also enables the Debian/Ubuntu
`cron.service`. The process runs as `bmgeoip` with a private temporary directory
and a read-only system filesystem, except for its state directory and the cron
spool. `StateDirectory=bmgeoip` creates `/var/lib/bmgeoip`. The systemd unit
allows the setgid `crontab` helper, following CMDB’s service configuration.
SQLite is included with Python; no separate database service is required.

Open `http://<server>:54300/`. The interface has no authentication and is
intended for a trusted LAN. Installation does not change firewall rules.

## Upgrade and uninstall

From an updated checkout separate from `/opt/prod/bmgeoip`, run:

```sh
sudo scripts/upgrade.sh
```

The upgrade script reuses the installer and preserves downloaded CSVs, download
settings, the SQLite database, logs, and the existing cron schedule. It stops
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
the SQLite database, progress status, and logs, and removes the `bmgeoip` Linux
account and group. Shared system packages and the cron service remain
available for other applications. Repeated uninstallation handles an absent
deployment or account; failures stop the script so the reported problem can be
fixed before retrying. Reinstallation starts with fresh state.

## Endpoints and operations

| Endpoint | Behavior |
| --- | --- |
| `/` | CSV download schedule, file paths/status, IP address lookup, and project version. |
| `/api/lookup?ip=8.8.8.8` | GET/HEAD JSON with normalized `ip`, numeric `ip_version`, and a `results` array of matching provider records. |
| `/api/download-schedule` | POST JSON with `enabled` (boolean) and `expression` (five-field cron string); returns the saved `schedule`. |
| `/status-messages` | GET/HEAD JSON history with `timestamp`, `source`, and `message` fields. |
| `/api/data-status` | GET/HEAD JSON progress: `phase`, `version`, `completed`, `total`, and `message`. |
| `/health` | HTTP 200 with `{"status":"ok","service":"bmgeoip-server"}`. |
| `/ready` | HTTP 200 with `{"status":"ready","service":"bmgeoip-server"}`; indicates web server readiness only, not GeoIP data availability. |
| `/static/style.css` | Web interface stylesheet. |
| `/static/downloads.js` | Schedule form behavior. |
| `/static/lookup.js` | IP lookup form and raw response display. |
| `/static/status_messages.js` | Live status history polling. |
| `/pages/images/bmgeoip.png` | Project logo. |

GET and HEAD are supported on page, asset, and health routes. Schedule POSTs
require `Content-Type: application/json` and a body of at most 4096 bytes. Invalid
settings return HTTP 400, cross-origin saves return HTTP 403, and storage or cron
failures return HTTP 503. Settings are restored if writing the crontab fails.
Unknown paths return HTTP 404 with
`{"error":"Not found."}`. Requests have a ten-second socket timeout.
SIGTERM and Ctrl-C stop the server cleanly; systemd restarts failed processes.

```sh
systemctl status bmgeoip-server.service
journalctl -u bmgeoip-server.service -f
curl -i http://127.0.0.1:54300/health
curl -i http://127.0.0.1:54300/ready
sudo systemctl restart bmgeoip-server.service
```

## IP address lookup

Enter one IPv4 or IPv6 address and click Look Up. The form sits between CSV Data
Files and Status Messages. Lookup Results shows the complete JSON response,
including all fourteen original provider fields as strings. Matching ranges include
both endpoints; overlapping or nested ranges return every matching record ordered
by their numeric start and end addresses. An empty `results` array means the loaded
family contains no matching range, including addresses absent from the provider data.

`GET /api/lookup?ip=8.8.8.8` accepts exactly one `ip` parameter, trims surrounding
whitespace, and normalizes the address in the response. Hostnames, CIDR prefixes,
IPv6 zone IDs, duplicate parameters, and extra parameters return HTTP 400 with an
`error` message. A missing database, an unimported family, or an unavailable
database returns HTTP 503 with an `error` message. The form shows these raw error
responses too. Without JavaScript, submitting opens the JSON endpoint directly.

Each request opens and closes its own read-only database connection. Lookups scan
the requested family's ranges using numeric address comparisons; response time
depends on dataset size. Committed records remain usable after a failed refresh.

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

Validated records are stored in `/var/lib/bmgeoip/geoip.sqlite3`. Each family is
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

## Development

The Python runtime is separate from the GitHub Pages documentation site:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B bmgeoip-server.py --host 127.0.0.1 --port 54300
```

Runtime defaults and installation paths are in `bmgeoip/constants/DBMGeoIP.py`.
`--host` accepts an IPv4 address; `--port` accepts integers from 1 to 65535.
Use `--state-dir /tmp/bmgeoip-dev` to keep development CSVs, settings, progress,
and the database separate from service state. The state directory must be writable.
The service uses these defaults. The handler owns HTTP routes, while
`bmgeoip/server/BMGeoIPServer.py` owns startup and shutdown. Templates live in
`bmgeoip/server/templates/` and web assets in `bmgeoip/server/static/`.
