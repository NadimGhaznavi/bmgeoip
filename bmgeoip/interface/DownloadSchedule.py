"""Persist download settings and manage the service account's cron entry."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shlex
from tempfile import NamedTemporaryFile

from crontab import CronSlices, CronTab

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.constants.DGeoIp import DGeoIp


class DownloadSchedule:
    COMMENT = "bmgeoip-csv-download"

    def __init__(self, settings: Path = Path(DGeoIp.SCHEDULE_FILE),
                 directory: Path = Path(DGeoIp.DATA_DIR)) -> None:
        self.settings = Path(settings)
        self.directory = Path(directory)

    @staticmethod
    def validate(enabled: bool, expression: str) -> dict:
        if (type(enabled) is not bool or not isinstance(expression, str)
                or len(expression) > 255 or '\n' in expression or '\r' in expression):
            raise ValueError("Provide an enabled flag and a five-field cron expression.")
        expression = ' '.join(expression.split())
        if len(expression.split()) != 5 or not CronSlices.is_valid(expression):
            raise ValueError("Use five cron fields: minute hour day-of-month month day-of-week.")
        return {"enabled": enabled, "expression": expression}

    @contextmanager
    def lock(self):
        # Share a lock with the independent cron runner, including across web processes.
        with self.settings.with_suffix('.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def read(self) -> dict:
        try:
            values = json.loads(self.settings.read_text())
        except FileNotFoundError:
            return {"enabled": False, "expression": DGeoIp.DOWNLOAD_CRON}
        return self.validate(**values)

    def files(self) -> list[dict]:
        files = []
        for version in DGeoIp.VERSIONS:
            path = self.directory / f"ipv{version}.csv"
            try:
                stat = path.stat()
            except FileNotFoundError:
                stat = None
            files.append({"version": version, "path": str(path),
                          "size": stat.st_size if stat else None,
                          "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                          if stat else None})
        return files

    def _write(self, values: dict) -> None:
        with NamedTemporaryFile(mode='w', dir=self.settings.parent, delete=False) as stream:
            candidate = Path(stream.name)
            try:
                json.dump(values, stream)
                stream.flush()
                candidate.replace(self.settings)
            finally:
                candidate.unlink(missing_ok=True)

    def update(self, enabled: bool, expression: str) -> dict:
        values = self.validate(enabled, expression)
        with self.lock():
            previous = self.read()
            tab = CronTab(user=True)
            tab.remove_all(comment=self.COMMENT)
            if enabled:
                command = shlex.join([DBMGeoIP.BASE_DIR + '/.venv/bin/python', '-B',
                                      DBMGeoIP.BASE_DIR + '/bmgeoip-download.py'])
                command += ' >> ' + shlex.quote(str(self.settings.parent / 'download.log')) + ' 2>&1'
                job = tab.new(command=command.replace('%', r'\%'), comment=self.COMMENT)
                job.setall(values['expression'])
            # The runner takes the same lock before reading these settings.
            self._write(values)
            try:
                tab.write()
            except (OSError, RuntimeError):
                self._write(previous)
                raise
        return values
