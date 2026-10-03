"""Share a bounded status history between the HTTP server and cron workers."""

from datetime import datetime, timezone
import fcntl
import json
import logging
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

from bmgeoip.constants.DBMGeoIP import DBMGeoIP


class StatusMessages:
    LIMIT = 1000

    def __init__(self, path: Path = Path(DBMGeoIP.SERVICE_HOME) / 'status-messages.json') -> None:
        self.path = Path(path)

    def snapshot(self) -> list[dict[str, str]]:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return []

    def append(self, message: str) -> None:
        """Record a line and its calling module without interrupting service work."""
        entry = {'timestamp': datetime.now(timezone.utc).isoformat(),
                 'source': sys._getframe(1).f_globals['__name__'],
                 'message': ' '.join(message.splitlines())}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix('.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                messages = (self.snapshot() + [entry])[-self.LIMIT:]
                with NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as stream:
                    candidate = Path(stream.name)
                    try:
                        json.dump(messages, stream)
                        stream.flush()
                        candidate.replace(self.path)
                    finally:
                        candidate.unlink(missing_ok=True)
        except (OSError, ValueError):
            logging.exception('Could not record status message')
