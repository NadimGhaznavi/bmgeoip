---
title: BMGeoIP Server
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

BMGeoIP follows CMDB's standalone HTTP server and systemd installation pattern.
The web interface listens on `0.0.0.0:54300` by default and renders HTML with
Jinja2, with automatic HTML escaping. The dark blue and teal interface follows
CMDB’s header, panels, tables, and schedule controls. It configures cron downloads of the IPv4 and IPv6 CSVs and
shows their paths, modification times, and sizes. GeoIP lookups and ZMQ messaging
are not implemented yet.

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
No database is required for this web server foundation.

Open `http://<server>:54300/`. The interface has no authentication and is
intended for a trusted LAN. Installation does not change firewall rules.

Rerun the installer from an updated checkout to update the service. It stops
an existing service before updating dependencies and files. If installation
fails, fix the reported error and rerun it; automatic rollback is not provided.

## Endpoints and operations

| Endpoint | Behavior |
| --- | --- |
| `/` | CSV download schedule, file paths/status, and project version. |
| `/api/download-schedule` | POST JSON with `enabled` (boolean) and `expression` (five-field cron string); returns the saved `schedule`. |
| `/health` | HTTP 200 with `{"status":"ok","service":"bmgeoip-server"}`. |
| `/ready` | HTTP 200 with `{"status":"ready","service":"bmgeoip-server"}`; indicates web server readiness only, not GeoIP data availability. |
| `/static/style.css` | Web interface stylesheet. |
| `/static/downloads.js` | Schedule form behavior. |
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

## CSV download schedule

Use the Enabled checkbox, enter five cron fields, and click Update. The initial
schedule is disabled; its suggested expression `0 3 * * 0` means Sunday at 03:00
in the server’s local timezone. Cron also supports ranges, lists, and steps.
Disabling and saving removes BMGeoIP’s cron entry without removing unrelated
jobs. The settings persist in `/var/lib/bmgeoip/download-schedule.json` and survive
service restarts and installer updates.

The service account’s cron job runs `/opt/prod/bmgeoip/bmgeoip-download.py` using
the installed virtual environment. It works independently of the HTTP server,
rechecks the saved enabled flag, and skips overlapping invocations. An in-progress
download finishes if the schedule is disabled. Logs append to
`/var/lib/bmgeoip/download.log`.

| Dataset | CSV path |
| --- | --- |
| IPv4 | `/var/lib/bmgeoip/data/ipv4.csv` |
| IPv6 | `/var/lib/bmgeoip/data/ipv6.csv` |

Each family is downloaded and validated independently, so one failure does not
prevent the other family from refreshing. Failed downloads preserve the previous
usable CSV. Reload the webpage to refresh file status; modification times display
in UTC. Provider, path, and default expression settings live in
`bmgeoip/constants/DGeoIp.py`. There is no database import yet.

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
The service uses these defaults. The handler owns HTTP routes, while
`bmgeoip/server/BMGeoIPServer.py` owns startup and shutdown. Templates live in
`bmgeoip/server/templates/` and web assets in `bmgeoip/server/static/`.
