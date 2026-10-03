"""GeoIP schema and atomic, bounded-memory CSV imports."""

from pathlib import Path
from ipaddress import ip_address

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.GeoIpSource import GeoIpSource


class GeoIpDb:
    @staticmethod
    def lookup(db: DbMgr, address) -> list[dict[str, str]]:
        """Return every inclusive range match, including nested provider ranges."""
        if not db.query('SELECT records FROM GeoIpImport WHERE version = ?', (address.version,)):
            raise LookupError(f'IPv{address.version} lookup data is not available yet.')
        db.register_function('ip_packed', 1, lambda value: ip_address(value).packed)
        columns = ', '.join(f'"{name}"' for name in DGeoIp.COLUMNS)
        return db.query(f'SELECT {columns} FROM GeoIp WHERE ip_version = ? '
                        'AND ip_packed(start_ip) <= ? AND ip_packed(end_ip) >= ? '
                        'ORDER BY ip_packed(start_ip), ip_packed(end_ip)',
                        (str(address.version), address.packed, address.packed))

    def __init__(self, db: DbMgr) -> None:
        self._db = db
        columns = ', '.join(f'"{name}" TEXT NOT NULL' for name in DGeoIp.COLUMNS)
        db.execute(f'CREATE TABLE IF NOT EXISTS GeoIp ({columns})')
        db.execute('CREATE INDEX IF NOT EXISTS GeoIp_version ON GeoIp (ip_version)')
        db.execute('CREATE TABLE IF NOT EXISTS GeoIpImport '
                   '(version INTEGER PRIMARY KEY, size INTEGER NOT NULL, '
                   'mtime_ns INTEGER NOT NULL, records INTEGER NOT NULL)')

    def current(self, version: int, path: Path) -> int | None:
        stat = path.stat()
        rows = self._db.query('SELECT records FROM GeoIpImport '
                              'WHERE version = ? AND size = ? AND mtime_ns = ?',
                              (version, stat.st_size, stat.st_mtime_ns))
        return rows[0]['records'] if rows else None

    def load(self, version: int, path: Path, progress=None) -> int:
        """Validate all rows and replace only this family in one transaction."""
        stat = path.stat()
        columns = ', '.join(f'"{name}"' for name in DGeoIp.COLUMNS)
        placeholders = ', '.join('?' for _ in DGeoIp.COLUMNS)
        sql = f'INSERT INTO GeoIp ({columns}) VALUES ({placeholders})'
        count, batch = 0, []
        with self._db.transaction():
            self._db.execute('DELETE FROM GeoIp WHERE ip_version = ?', (str(version),))
            for row in GeoIpSource().rows(path, version):
                batch.append(tuple(row[name] for name in DGeoIp.COLUMNS))
                count += 1
                if len(batch) == 1000:
                    self._db.execute_many(sql, batch)
                    batch.clear()
                    if progress:
                        progress(count)
            if batch:
                self._db.execute_many(sql, batch)
            if path.stat().st_mtime_ns != stat.st_mtime_ns or path.stat().st_size != stat.st_size:
                raise ValueError('CSV changed during import; retry with a stable file.')
            self._db.execute('INSERT OR REPLACE INTO GeoIpImport '
                             '(version, size, mtime_ns, records) VALUES (?, ?, ?, ?)',
                             (version, stat.st_size, stat.st_mtime_ns, count))
        if progress:
            progress(count)
        return count
