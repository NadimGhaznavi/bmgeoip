#!/usr/bin/env bash
# Provision the BMGeoIP service account and deploy the web server.
set -euo pipefail
umask 022

if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/install.sh\nInstall and start the BMGeoIP web server on port 54300.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Run scripts/install.sh as root, without arguments.\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v systemctl >/dev/null
command -v systemd-analyze >/dev/null
command -v crontab >/dev/null

settings_output=$(python3 -B - <<'PY'
from pathlib import Path
import sys
import ensurepip
import venv
from bmgeoip.constants.DBMGeoIP import DBMGeoIP

if sys.version_info < (3, 11):
    raise SystemExit('BMGeoIP requires Python 3.11 or later.')
installation = Path(DBMGeoIP.BASE_DIR)
if installation.is_symlink() or Path.cwd().resolve() == installation.resolve():
    raise SystemExit('Run installation from a separate checkout; installation must not be a symlink.')
print(DBMGeoIP.BASE_DIR)
print(DBMGeoIP.SERVICE_USER)
print(DBMGeoIP.SERVICE_HOME)
print(DBMGeoIP.SERVICE_UNIT)
PY
)
mapfile -t settings <<< "$settings_output"
install_dir=${settings[0]}
account=${settings[1]}
account_home=${settings[2]}
unit=${settings[3]}

getent group "$account" >/dev/null || groupadd --system "$account"
getent passwd "$account" >/dev/null || useradd --system --gid "$account" \
    --no-create-home --home-dir "$account_home" --shell /usr/sbin/nologin "$account"
install -d -m 755 -- "$install_dir"

if [[ -e /etc/systemd/system/$unit ]]; then
    systemctl stop "$unit"
fi
if [[ ! -x $install_dir/.venv/bin/python ]]; then
    python3 -m venv "$install_dir/.venv"
fi
"$install_dir/.venv/bin/python" -m pip install -r requirements.txt
"$install_dir/.venv/bin/python" -B -m unittest discover -s tests -v

python3 -B - <<'PY'
from pathlib import Path
import shutil
from bmgeoip.constants.DBMGeoIP import DBMGeoIP

destination = Path(DBMGeoIP.BASE_DIR)
shutil.copytree('bmgeoip', destination / 'bmgeoip', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copytree('pages/images', destination / 'pages/images', dirs_exist_ok=True)
for name in ('bmgeoip-server.py', 'bmgeoip-download.py', 'requirements.txt'):
    shutil.copy2(name, destination / name)
template = Path('systemd', DBMGeoIP.SERVICE_UNIT).read_text()
unit = template.replace('@APP@', DBMGeoIP.BASE_DIR).replace('@USER@', DBMGeoIP.SERVICE_USER)
target = Path('/etc/systemd/system', DBMGeoIP.SERVICE_UNIT)
target.write_text(unit)
target.chmod(0o644)
PY

systemd-analyze verify "/etc/systemd/system/$unit"
systemctl daemon-reload
systemctl enable --now cron.service
systemctl enable --now "$unit"

python3 -B - <<'PY'
import json
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from bmgeoip.constants.DBMGeoIP import DBMGeoIP

opener = build_opener(ProxyHandler({}))
for endpoint, expected in (('health', 'ok'), ('ready', 'ready')):
    for attempt in range(30):
        try:
            with opener.open(f'http://127.0.0.1:{DBMGeoIP.PORT}/{endpoint}', timeout=1) as response:
                if response.status == 200 and json.load(response) == {
                    'status': expected, 'service': 'bmgeoip-server'
                }:
                    break
        except (URLError, TimeoutError):
            pass
        time.sleep(1)
    else:
        raise SystemExit('Health check failed; inspect journalctl -u ' + DBMGeoIP.SERVICE_UNIT)
with opener.open(f'http://127.0.0.1:{DBMGeoIP.PORT}/', timeout=5) as response:
    if response.status != 200 or b'Bear &amp; Moose GeoIP' not in response.read():
        raise SystemExit('Web interface check failed.')
print(f'BMGeoIP server listening on port: {DBMGeoIP.PORT}')
PY
