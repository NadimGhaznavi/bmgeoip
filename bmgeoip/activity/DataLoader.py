"""Coordinate startup and scheduled downloads, imports, and shared progress."""

import csv
import fcntl
import json
import logging
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile
from threading import Thread
from time import monotonic
from zipfile import BadZipFile

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from bmgeoip.interface.GeoIpDb import GeoIpDb
from bmgeoip.interface.GeoIpSource import GeoIpSource


class DataLoader:
    def __init__(self, schedule=None, database: Path = Path(DGeoIp.DATABASE_FILE),
                 status: Path = Path(DGeoIp.STATUS_FILE)) -> None:
        self.schedule = schedule if schedule is not None else DownloadSchedule()
        self.database = Path(database)
        self.status = Path(status)
        self._last_update = 0.0
        self._phase = None

    def read(self) -> dict:
        try:
            return json.loads(self.status.read_text())
        except FileNotFoundError:
            return {'phase': 'waiting', 'version': None, 'completed': 0,
                    'total': None, 'message': 'Waiting for dataset initialization.'}

    def _report(self, phase, version=None, completed=0, total=None, message='', force=False):
        now = monotonic()
        if not force and phase == self._phase and now - self._last_update < 0.5:
            return
        self._phase, self._last_update = phase, now
        values = dict(phase=phase, version=version, completed=completed,
                      total=total, message=message)
        with NamedTemporaryFile(mode='w', dir=self.status.parent, delete=False) as stream:
            candidate = Path(stream.name)
            try:
                json.dump(values, stream)
                stream.flush()
                candidate.replace(self.status)
            finally:
                candidate.unlink(missing_ok=True)

    def run(self, *, refresh=False) -> bool:
        """Fill missing families at startup, or refresh both when cron is enabled."""
        self.schedule.settings.parent.mkdir(parents=True, exist_ok=True)
        with self.schedule.settings.with_suffix('.download.lock').open('a') as stream:
            # Startup waits for any existing cron job; cron skips overlapping work.
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if refresh else 0))
            except BlockingIOError:
                return True
            if refresh:
                with self.schedule.lock():
                    if not self.schedule.read()['enabled']:
                        return True
            self.schedule.directory.mkdir(parents=True, exist_ok=True)
            self.database.parent.mkdir(parents=True, exist_ok=True)
            self.status.parent.mkdir(parents=True, exist_ok=True)
            self._report('checking', message='Checking GeoIP datasets.', force=True)
            db = None
            errors = []
            counts = {}
            try:
                db = DbMgr(self.database)
                records = GeoIpDb(db)
                source = GeoIpSource()
                for version in DGeoIp.VERSIONS:
                    try:
                        path = self.schedule.directory / f'ipv{version}.csv'
                        if refresh or not path.is_file():
                            self._report('downloading', version, force=True)
                            source.download(version, path, progress=lambda phase, done, total:
                                            self._report(phase, version, done, total))
                        count = records.current(version, path)
                        if count is None:
                            self._report('importing', version, force=True)
                            count = records.load(version, path, progress=lambda done:
                                                 self._report('importing', version, done))
                        counts[version] = count
                        logging.info('IPv%s dataset ready: %s records.', version, count)
                    except (OSError, ValueError, csv.Error, BadZipFile, KeyError, sqlite3.Error):
                        logging.exception('IPv%s dataset initialization failed.', version)
                        errors.append(f'IPv{version} failed. Check the service log and restart to retry.')
                message = ' '.join(errors) if errors else 'Both datasets loaded. ' + ', '.join(
                    f'IPv{version}: {count:,} records' for version, count in counts.items()) + '.'
                self._report('error' if errors else 'ready', message=message, force=True)
                return not errors
            except (OSError, sqlite3.Error):
                logging.exception('GeoIP database initialization failed.')
                self._report('error', message='Database initialization failed. Check the service log.', force=True)
                return False
            finally:
                if db is not None:
                    db.close()

    def start(self) -> None:
        """Run initialization without delaying the HTTP listener."""
        def initialize():
            try:
                self.run()
            except (OSError, ValueError):
                logging.exception('Could not initialize GeoIP datasets or write progress.')

        Thread(target=initialize, name='geoip-data-loader', daemon=True).start()
