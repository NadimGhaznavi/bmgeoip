"""Download both CSV families without overlapping another cron invocation."""

import fcntl
import csv
import logging
from zipfile import BadZipFile

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from bmgeoip.interface.GeoIpSource import GeoIpSource


def run() -> bool:
    schedule = DownloadSchedule()
    with schedule.settings.with_suffix('.download.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        with schedule.lock():
            if not schedule.read()['enabled']:
                return True
        schedule.directory.mkdir(parents=True, exist_ok=True)
        source = GeoIpSource()
        success = True
        for version in DGeoIp.VERSIONS:
            try:
                source.download(version, schedule.directory / f'ipv{version}.csv')
                logging.info('Downloaded IPv%s CSV.', version)
            except (OSError, ValueError, csv.Error, BadZipFile, KeyError, RuntimeError):
                # Independent families: keep the last usable CSV and attempt the other.
                logging.exception('IPv%s CSV download failed.', version)
                success = False
        return success
