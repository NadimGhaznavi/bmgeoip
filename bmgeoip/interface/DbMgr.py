"""SQLite connection and transaction mechanics, following CMDB's DAL boundary."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3


class DbMgr:
    """Own one connection; create and close it within the worker using it."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path, timeout=30, isolation_level=None)
        self._connection.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()) -> int:
        cursor = self._connection.execute(sql, params)
        try:
            return cursor.rowcount
        finally:
            cursor.close()

    def execute_many(self, sql: str, rows) -> None:
        cursor = self._connection.executemany(sql, rows)
        cursor.close()

    def query(self, sql: str, params=()) -> list[dict]:
        cursor = self._connection.execute(sql, params)
        try:
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    @contextmanager
    def transaction(self):
        """Commit related writes together; roll back every failed import."""
        self.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.execute('COMMIT')
        except BaseException as error:
            try:
                self.execute('ROLLBACK')
            except BaseException:
                error.add_note('Database rollback also failed; discard this connection.')
            raise

    def close(self) -> None:
        self._connection.close()
