#!/usr/bin/env python3
"""Migrate an existing SQLite GeoIP database into empty MariaDB GeoIP tables."""

import argparse
import fcntl
from pathlib import Path

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.SqliteMigration import SqliteMigration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--database-env', type=Path, default=Path(DGeoIp.DATABASE_ENV))
    args = parser.parse_args()
    # Use the same lock as startup and cron. Stop the old HTTP service first.
    with args.source.with_name('download-schedule.download.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        db = DbMgr(args.database_env)
        try:
            counts = SqliteMigration.copy(args.source, db,
                                          progress=lambda count: print(f'Copied {count:,} records.', flush=True))
            print('Verified and committed: ' + ', '.join(f'IPv{v}: {n:,}' for v, n in counts.items()))
        finally:
            db.close()


if __name__ == '__main__':
    main()
