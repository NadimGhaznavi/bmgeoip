---
title: BMGeoIP Development
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

For installation, upgrades, and service operations, see the
[server setup guide]({{ site.baseurl }}{% link pages/server.md %}).
Follow the [coding guidelines]({{ site.baseurl }}{% link pages/coding-guidelines.md %})
when changing the project.

Provision a separate development MariaDB database and connection settings file as
described in [server setup]({{ site.baseurl }}{% link pages/server.md %}#database-configuration).
The Python runtime is separate from the GitHub Pages documentation site:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B bmgeoip-server.py --host 127.0.0.1 --port 54300 \
  --state-dir /tmp/bmgeoip-dev --database-env /tmp/bmgeoip-dev.env \
  --zmq-endpoint tcp://127.0.0.1:54301
```

Runtime defaults and installation paths are in `bmgeoip/constants/DBMGeoIP.py`.
`--host` accepts an IPv4 address; `--port` accepts integers from 1 to 65535.
`--zmq-endpoint` overrides the ZMQ bind endpoint; for local development use
`--zmq-endpoint tcp://127.0.0.1:54301`. It is independent of `--host` and `--port`.
Use `--state-dir /tmp/bmgeoip-dev` to keep development CSVs, settings, and progress
separate from service state. Use `--database-env` to select the development database;
`--state-dir` does not change the MariaDB connection settings. The state directory must be writable.
MariaDB integration tests are opt-in: set `BMGEOIP_TEST_DATABASE_ENV` to a private
settings file for an account able to create and drop disposable test databases.
Without it, those tests are skipped. The handler owns HTTP routes, while
`bmgeoip/server/BMGeoIPServer.py` owns startup, shutdown, and worker failure checks. `bmgeoip/zmq/` owns the
message envelope and transport; `bmgeoip/server/LookupHandler.py` dispatches
lookup requests through `GeoIpLookup`. Templates live in
`bmgeoip/server/templates/` and web assets in `bmgeoip/server/static/`.
