#!/usr/bin/env bash
# Remove the BMGeoIP deployment, state, crontab, and service account.
set -euo pipefail
umask 022
if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/uninstall.sh\nRemove the BMGeoIP service, application, CSVs, settings, logs, crontab, account, and group.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Run scripts/uninstall.sh as root, without arguments.\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 -B - <<'PYTHON'
from pathlib import Path
import grp
import os
import pwd
import shutil
import subprocess
import time

from bmgeoip.constants.DBMGeoIP import DBMGeoIP

application = Path(DBMGeoIP.BASE_DIR)
home = Path(DBMGeoIP.SERVICE_HOME)
if (application != Path('/opt/prod/bmgeoip') or application.is_symlink()
        or application.resolve() != application):
    raise SystemExit('Refusing to remove an unexpected application directory.')
if (home != Path('/var/lib/bmgeoip') or home.is_symlink()
        or home.resolve() != home):
    raise SystemExit('Refusing to remove an unexpected state directory.')
if any(Path.cwd().resolve().is_relative_to(path) for path in (application, home)):
    raise SystemExit('Run uninstall from a separate checkout.')
if DBMGeoIP.SERVICE_UNIT != 'bmgeoip-server.service':
    raise SystemExit('Refusing to remove an unexpected service unit.')
if DBMGeoIP.SERVICE_USER != 'bmgeoip':
    raise SystemExit('Refusing to remove an unexpected service account.')

# Validate the account and read cron before changing the deployment.
account = None
cron_exists = False
try:
    account = pwd.getpwnam(DBMGeoIP.SERVICE_USER)
except KeyError:
    pass
else:
    if account.pw_uid == 0 or Path(account.pw_dir) != home or account.pw_uid == os.getuid():
        raise SystemExit('Refusing to remove an unexpected service account identity.')
    result = subprocess.run(['crontab', '-u', DBMGeoIP.SERVICE_USER, '-l'],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, 'LC_ALL': 'C'})
    if result.returncode != 0:
        if result.returncode != 1 or result.stderr.strip() != 'no crontab for bmgeoip':
            raise SystemExit('Cannot read BMGeoIP crontab: ' + result.stderr.strip())
    else:
        cron_exists = True


def process_command(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(result.returncode, command, result.stdout, result.stderr)
    return result.returncode == 0


def wait_for_processes(uid):
    for attempt in range(20):
        if not process_command(['pgrep', '-u', uid]):
            return True
        time.sleep(0.5)
    return False

unit = Path('/etc/systemd/system') / DBMGeoIP.SERVICE_UNIT
state = subprocess.run(
    ['systemctl', 'show', DBMGeoIP.SERVICE_UNIT, '--property=LoadState', '--value'],
    capture_output=True, text=True, check=True, timeout=30).stdout.strip()
if unit.exists() or unit.is_symlink() or state != 'not-found':
    subprocess.run(['systemctl', 'disable', '--now', DBMGeoIP.SERVICE_UNIT],
                   check=True, timeout=30)
if cron_exists:
    subprocess.run(['crontab', '-u', DBMGeoIP.SERVICE_USER, '-r'], check=True, timeout=30)
if account is not None:
    # Cron downloads run independently of systemd; stop them before deleting state.
    uid = str(account.pw_uid)
    process_command(['pkill', '-TERM', '-u', uid])
    if not wait_for_processes(uid):
        process_command(['pkill', '-KILL', '-u', uid])
        if not wait_for_processes(uid):
            raise SystemExit('BMGeoIP processes are still running; retry uninstall after they exit.')

unit.unlink(missing_ok=True)
overrides = unit.with_name(unit.name + '.d')
if overrides.is_symlink():
    overrides.unlink()
elif overrides.exists():
    shutil.rmtree(overrides)
subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=30)
if account is not None:
    # userdel --remove also cleans the account's mail spool.
    subprocess.run(['userdel', '--remove', DBMGeoIP.SERVICE_USER], check=True, timeout=30)
for path in (application, home):
    if path.exists():
        shutil.rmtree(path)
try:
    grp.getgrnam(DBMGeoIP.SERVICE_USER)
except KeyError:
    pass
else:
    subprocess.run(['groupdel', DBMGeoIP.SERVICE_USER], check=True, timeout=30)
print('Removed BMGeoIP service, application, CSVs, settings, logs, crontab, account, and group.')
PYTHON
