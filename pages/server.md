---
title: BMGeoIP Server
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

BMGeoIP follows CMDB's standalone HTTP server and systemd installation pattern.
The web interface listens on `0.0.0.0:54300` by default and renders HTML with
Jinja2, with automatic HTML escaping. The current server shows service status
and the project version. GeoIP lookups, ZMQ messaging, and scheduled dataset
refreshes are not implemented yet.

## Installation

Use Python 3.11 or later with virtual-environment support and systemd. On
Debian/Ubuntu, install the prerequisites:

```sh
sudo apt install python3 python3-venv
```

From a checkout separate from `/opt/prod/bmgeoip`, run:

```sh
sudo scripts/install.sh
```

The installer creates the `bmgeoip` system account with a `nologin` shell,
copies application files and the logo to `/opt/prod/bmgeoip`, and installs
Jinja2 in `/opt/prod/bmgeoip/.venv`. It runs the Python tests, verifies the
systemd unit, enables `bmgeoip-server.service` at boot, starts it, and checks
the health endpoints and rendered home page. The process runs as `bmgeoip`
with a read-only system filesystem and a private temporary directory.
No database is required for this web server foundation.

Open `http://<server>:54300/`. The interface has no authentication and is
intended for a trusted LAN. Installation does not change firewall rules.

Rerun the installer from an updated checkout to update the service. It stops
an existing service before updating dependencies and files. If installation
fails, fix the reported error and rerun it; automatic rollback is not provided.

## Endpoints and operations

| Endpoint | Behavior |
| --- | --- |
| `/` | Jinja2 service status page and project version. |
| `/health` | HTTP 200 with `{"status":"ok","service":"bmgeoip-server"}`. |
| `/ready` | HTTP 200 with `{"status":"ready","service":"bmgeoip-server"}`; indicates web server readiness only, not GeoIP data availability. |
| `/static/style.css` | Web interface stylesheet. |
| `/pages/images/bmgeoip.png` | Project logo. |

GET and HEAD are supported. Unknown paths return HTTP 404 with
`{"error":"Not found."}`. Requests have a ten-second socket timeout.
SIGTERM and Ctrl-C stop the server cleanly; systemd restarts failed processes.

```sh
systemctl status bmgeoip-server.service
journalctl -u bmgeoip-server.service -f
curl -i http://127.0.0.1:54300/health
curl -i http://127.0.0.1:54300/ready
sudo systemctl restart bmgeoip-server.service
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
