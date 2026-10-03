#!/usr/bin/env bash
# Reuse provisioning and deployment while retaining downloaded data and settings.
set -euo pipefail
if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/upgrade.sh\nDeploy BMGeoIP, retaining data and settings; recover missing local MariaDB credentials.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Usage: sudo scripts/upgrade.sh\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

python3 -B - <<'PYTHON'
import fcntl
import grp
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import tempfile

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DatabaseEnvironment import DatabaseEnvironment

installation = Path(DBMGeoIP.BASE_DIR)
if installation.is_symlink() or Path.cwd().resolve() == installation.resolve():
    raise SystemExit('Run upgrade from a separate checkout; installation must not be a symlink.')

path = Path(DGeoIp.DATABASE_ENV)
if path.is_symlink() or path.parent.is_symlink():
    raise SystemExit('Database configuration must not be a symlink.')
path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
# Serialize credential recovery so concurrent upgrades cannot rotate twice.
directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
try:
    fcntl.flock(directory, fcntl.LOCK_EX)
    if path.exists():
        DatabaseEnvironment.read(path)
        print('Existing MariaDB credentials validated and retained.')
    else:
        account = DBMGeoIP.SERVICE_USER
        if account != 'bmgeoip':
            raise SystemExit('Credential recovery requires the bmgeoip service account.')
        try:
            group = grp.getgrnam(account)
        except KeyError:
            subprocess.run(['groupadd', '--system', account], check=True, timeout=30)
            group = grp.getgrnam(account)
        os.chown(path.parent, 0, group.gr_gid)
        os.chmod(path.parent, 0o750)
        password = secrets.token_hex(32)
        digest = hashlib.sha1(hashlib.sha1(password.encode()).digest()).hexdigest().upper()
        sql = f"""
CREATE DATABASE IF NOT EXISTS `bmgeoip` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER IF NOT EXISTS 'bmgeoip'@'localhost' IDENTIFIED BY PASSWORD '*{digest}';
ALTER USER 'bmgeoip'@'localhost' IDENTIFIED VIA mysql_native_password USING '*{digest}';
GRANT SELECT, INSERT, DELETE, UPDATE, CREATE, INDEX ON `bmgeoip`.* TO 'bmgeoip'@'localhost';
SELECT @@socket;
"""
        descriptor, temporary = tempfile.mkstemp(prefix='.database-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'w') as output:
                os.fchown(output.fileno(), 0, group.gr_gid)
                os.fchmod(output.fileno(), 0o640)
                try:
                    result = subprocess.run(
                        ['mariadb', '--no-defaults', '--user=root', '--protocol=socket',
                         '--batch', '--skip-column-names'],
                        input=sql, text=True, capture_output=True, check=True, timeout=30)
                except (OSError, subprocess.SubprocessError):
                    raise SystemExit('MariaDB credential recovery failed. Ensure MariaDB is running '
                                     'and root can connect with mariadb --no-defaults '
                                     '--user=root --protocol=socket.') from None
                socket = result.stdout.strip()
                if not socket.startswith('/') or '\n' in socket or '\r' in socket:
                    raise SystemExit('MariaDB returned an invalid Unix socket path.')
                output.write('DB_HOST=127.0.0.1\nDB_PORT=3306\nDB_NAME=bmgeoip\nDB_USER=bmgeoip\n'
                             f'DB_PASSWORD={password}\nDB_SOCKET={socket}\n')
                output.flush()
                os.fsync(output.fileno())
            # Publish only after SQL succeeds, without overwriting an existing file.
            os.link(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print('Recovered local bmgeoip MariaDB credentials; application password reset.')
finally:
    os.close(directory)
PYTHON

exec ./scripts/install.sh
