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
        if not db.query('SELECT records FROM GeoIpImport WHERE version = %s', (address.version,)):
            raise LookupError(f'IPv{address.version} lookup data is not available yet.')
        # Each range has one smallest enclosing prefix. A matching range must
        # use one of the address's ancestor prefixes; SQL checks the exact bounds.
        keys = [GeoIpDb._prefix_key(address, length)
                for length in range(address.max_prefixlen + 1)]
        placeholders = ', '.join('%s' for _ in keys)
        columns = ', '.join(f'`{name}`' for name in DGeoIp.COLUMNS)
        return db.query(f'SELECT {columns} FROM GeoIp WHERE ip_version = %s '
                        f'AND range_key IN ({placeholders}) '
                        'AND start_packed <= %s AND end_packed >= %s '
                        'ORDER BY start_packed, end_packed',
                        (str(address.version), *keys, address.packed, address.packed))

    @staticmethod
    def _prefix_key(address, length: int) -> bytes:
        host_bits = address.max_prefixlen - length
        network = (int(address) >> host_bits) << host_bits
        return bytes([length]) + network.to_bytes(len(address.packed), 'big')

    @staticmethod
    def _range_values(start: str, end: str) -> tuple[bytes, bytes, bytes]:
        first, last = ip_address(start), ip_address(end)
        length = first.max_prefixlen - (int(first) ^ int(last)).bit_length()
        return GeoIpDb._prefix_key(first, length), first.packed, last.packed

    def __init__(self, db: DbMgr) -> None:
        self._db = db
        columns = ', '.join(f'`{name}` LONGTEXT NOT NULL' for name in DGeoIp.COLUMNS
                            if name != 'ip_version')
        db.execute(f'CREATE TABLE IF NOT EXISTS GeoIp (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, '
                   f'ip_version VARCHAR(1) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, {columns}, '
                   'range_key VARBINARY(17) NOT NULL, start_packed VARBINARY(16) NOT NULL, '
                   'end_packed VARBINARY(16) NOT NULL, INDEX GeoIp_range (ip_version, range_key)) '
                   'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin')
        db.execute('CREATE TABLE IF NOT EXISTS GeoIpImport '
                   '(version INTEGER PRIMARY KEY, size BIGINT NOT NULL, '
                   'mtime_ns BIGINT NOT NULL, records BIGINT NOT NULL) ENGINE=InnoDB')

    def current(self, version: int, path: Path) -> int | None:
        stat = path.stat()
        rows = self._db.query('SELECT records FROM GeoIpImport '
                              'WHERE version = %s AND size = %s AND mtime_ns = %s',
                              (version, stat.st_size, stat.st_mtime_ns))
        return rows[0]['records'] if rows else None

    def load(self, version: int, path: Path, progress=None) -> int:
        """Validate all rows and replace only this family in one transaction."""
        stat = path.stat()
        columns = ', '.join(f'`{name}`' for name in DGeoIp.COLUMNS)
        columns += ', range_key, start_packed, end_packed'
        placeholders = ', '.join('%s' for _ in range(len(DGeoIp.COLUMNS) + 3))
        sql = f'INSERT INTO GeoIp ({columns}) VALUES ({placeholders})'
        count, batch = 0, []
        with self._db.transaction():
            self._db.execute('DELETE FROM GeoIp WHERE ip_version = %s', (str(version),))
            for row in GeoIpSource().rows(path, version):
                batch.append((*[row[name] for name in DGeoIp.COLUMNS],
                              *self._range_values(row['start_ip'], row['end_ip'])))
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
            self._db.execute('INSERT INTO GeoIpImport '
                             '(version, size, mtime_ns, records) VALUES (%s, %s, %s, %s) '
                             'ON DUPLICATE KEY UPDATE size = VALUES(size), mtime_ns = VALUES(mtime_ns), '
                             'records = VALUES(records)', (version, stat.st_size, stat.st_mtime_ns, count))
        if progress:
            progress(count)
        return count
