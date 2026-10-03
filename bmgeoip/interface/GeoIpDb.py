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
        # Each range has one smallest enclosing prefix. A matching range must
        # use one of the address's ancestor prefixes; SQL checks the exact bounds.
        keys = [GeoIpDb._prefix_key(address, length)
                for length in range(address.max_prefixlen + 1)]
        placeholders = ', '.join('?' for _ in keys)
        columns = ', '.join(f'"{name}"' for name in DGeoIp.COLUMNS)
        return db.query(f'SELECT {columns} FROM GeoIp WHERE ip_version = ? '
                        f'AND range_key IN ({placeholders}) '
                        'AND start_packed <= ? AND end_packed >= ? '
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
        columns = ', '.join(f'"{name}" TEXT NOT NULL' for name in DGeoIp.COLUMNS)
        db.execute(f'CREATE TABLE IF NOT EXISTS GeoIp ({columns}, '
                   'range_key BLOB NOT NULL, start_packed BLOB NOT NULL, end_packed BLOB NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS GeoIp_version ON GeoIp (ip_version)')
        db.execute('CREATE TABLE IF NOT EXISTS GeoIpImport '
                   '(version INTEGER PRIMARY KEY, size INTEGER NOT NULL, '
                   'mtime_ns INTEGER NOT NULL, records INTEGER NOT NULL)')
        self._upgrade_ranges()

    def _upgrade_ranges(self) -> None:
        """Backfill legacy records in bounded batches, atomically with the schema."""
        if self._db.query("SELECT name FROM sqlite_master WHERE type = 'index' "
                          "AND name = 'GeoIp_range'"):
            return
        with self._db.transaction():
            columns = {row['name'] for row in self._db.query('PRAGMA table_info(GeoIp)')}
            for name in ('range_key', 'start_packed', 'end_packed'):
                if name not in columns:
                    self._db.execute(f'ALTER TABLE GeoIp ADD COLUMN {name} BLOB')
            last_id = 0
            while True:
                rows = self._db.query('SELECT rowid, start_ip, end_ip FROM GeoIp '
                                      'WHERE rowid > ? ORDER BY rowid LIMIT 1000', (last_id,))
                if not rows:
                    break
                self._db.execute_many('UPDATE GeoIp SET range_key = ?, start_packed = ?, '
                                       'end_packed = ? WHERE rowid = ?',
                                       [(*self._range_values(row['start_ip'], row['end_ip']), row['rowid'])
                                        for row in rows])
                last_id = rows[-1]['rowid']
            self._db.execute('CREATE INDEX GeoIp_range ON GeoIp (ip_version, range_key)')

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
        columns += ', range_key, start_packed, end_packed'
        placeholders = ', '.join('?' for _ in range(len(DGeoIp.COLUMNS) + 3))
        sql = f'INSERT INTO GeoIp ({columns}) VALUES ({placeholders})'
        count, batch = 0, []
        with self._db.transaction():
            self._db.execute('DELETE FROM GeoIp WHERE ip_version = ?', (str(version),))
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
            self._db.execute('INSERT OR REPLACE INTO GeoIpImport '
                             '(version, size, mtime_ns, records) VALUES (?, ?, ?, ?)',
                             (version, stat.st_size, stat.st_mtime_ns, count))
        if progress:
            progress(count)
        return count
