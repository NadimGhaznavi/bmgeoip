---
title: BMGeoIP Server Setup
author_profile: true
layout: single
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

## Installation

Requires Python 3.11+, systemd, cron, and a provisioned MariaDB database.

Create `/etc/bmgeoip/database.env` with your connection settings:

    DB_HOST=127.0.0.1
    DB_PORT=3306
    DB_NAME=bmgeoip
    DB_USER=bmgeoip
    DB_PASSWORD=your-private-password

Keep this file private and readable by the `bmgeoip` service account.

From a checkout outside `/opt/prod/bmgeoip`, run:

    sudo apt install python3 python3-venv cron
    sudo scripts/install.sh

The installer deploys the application and enables `bmgeoip-server.service`.

## Access

- Web interface: `http://<server>:54300/`
- ZMQ API: `tcp://<server>:54301`

Both interfaces are unauthenticated and intended for a trusted LAN.

Startup downloads missing IPv4/IPv6 datasets and imports them into MariaDB. Use the web interface to search addresses, monitor progress, and schedule updates.

## Configuration and CMDB

`bmgeoip/constants/DBMGeoIP.py` contains the literal `VERSION` and `CMDB_*`
declarations. `CMDB_NETWORK` supplies the `http` and `zmq` listener defaults.
`CMDB_COMPONENTS` owns the state directory (CSVs, schedules, progress and logs);
`CMDB_DATABASES` declares the default local MariaDB catalog. Database credentials
and custom or remote connections remain in `database.env`. When using a different
local catalog, update the declaration to match it before CMDB discovery.

Installation creates `/opt/prod/bmgeoip/conf/bmgeoip.json` when missing. Reinstall
and upgrade preserve it. Partial overrides inherit undeclared fields:

```json
{
  "network": {
    "http": {"interface": "127.0.0.1", "port": 54310},
    "zmq": {"interface": "127.0.0.1"}
  }
}
```

Interfaces must be IPv4 addresses; ports must be integers from 1 to 65535.
Unknown uses or fields and invalid configuration fail startup and deployment
validation. A missing file uses the declaration defaults. Settings load once per
process. Apply changes with:

```sh
cd /opt/prod/bmgeoip
sudo scripts/restart.sh
```

Restart validates configuration before restarting both listeners. Invocation
arguments `--host`, `--port`, and `--zmq-endpoint` override resolved settings.
Installer health checks use the same settings, translating wildcard binds to
loopback for local requests.

Register `BMGeoIP` in CMDB and re-scan the production host to discover the
release, state component and matching local MariaDB catalog. CMDB network
collection is deferred; the network declaration describes default listeners.

## Maintenance

Run deployment commands from the separate checkout:

    sudo scripts/upgrade.sh
    sudo scripts/uninstall.sh

Upgrade preserves settings and data. It validates and retains an existing
`/etc/bmgeoip/database.env`. If the file is missing, upgrade generates a random
application password, creates the local `bmgeoip` database and account if needed,
resets that account's password, and grants SELECT, INSERT, DELETE, UPDATE, CREATE,
and INDEX on that database. Existing database records are retained.

Credential recovery requires a running local MariaDB server, the `mariadb` client,
and root access through Unix socket authentication. It writes the detected socket
path into the configuration and protects the file with root ownership, the
`bmgeoip` group, and mode `0640`. It changes only the `bmgeoip` application's
password. If recovery fails, upgrade stops before deployment; MariaDB account
changes are not transactional, so rerun after correcting the reported problem.
For a remote or custom database, create the configuration before upgrading.

Uninstall removes local application files and state; MariaDB and database credentials remain.

Check service status and logs:

    systemctl status bmgeoip-server.service
    journalctl -u bmgeoip-server.service -f

## Documentation

- [API reference]({{ site.baseurl }}{% link pages/api.md %})
- [IP address lookup]({{ site.baseurl }}{% link pages/ip-address-lookup.md %})
- [Development guide]({{ site.baseurl }}{% link pages/development.md %})
