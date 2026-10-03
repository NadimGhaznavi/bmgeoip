"""MariaDB connection, bound queries, and transaction mechanics."""

from contextlib import contextmanager
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DatabaseEnvironment import DatabaseEnvironment


class DbMgr:
    """Own one connection; create and close it within the worker using it."""

    def __init__(self, settings: Path = Path(DGeoIp.DATABASE_ENV), *, readonly=False) -> None:
        values = DatabaseEnvironment.read(settings)
        self._connection = pymysql.connect(
            host=values['DB_HOST'], port=int(values['DB_PORT']),
            user=values['DB_USER'], password=values['DB_PASSWORD'], database=values['DB_NAME'],
            unix_socket=values.get('DB_SOCKET'), charset='utf8mb4', cursorclass=DictCursor,
            autocommit=True, connect_timeout=10, read_timeout=30, write_timeout=30,
            sql_mode='STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION',
        )
        if readonly:
            try:
                self.execute('SET SESSION TRANSACTION READ ONLY')
            except BaseException:
                self.close()
                raise

    def execute(self, sql: str, params=()) -> int:
        with self._connection.cursor() as cursor:
            return cursor.execute(sql, params)

    def execute_many(self, sql: str, rows) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(sql, rows)

    def query(self, sql: str, params=()) -> list[dict]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    @contextmanager
    def transaction(self):
        """Commit related writes together; keep DDL outside transactions."""
        self._connection.begin()
        try:
            yield
            self._connection.commit()
        except BaseException as error:
            try:
                self._connection.rollback()
            except BaseException:
                error.add_note('Database rollback also failed; discard this connection.')
            raise

    def close(self) -> None:
        self._connection.close()
