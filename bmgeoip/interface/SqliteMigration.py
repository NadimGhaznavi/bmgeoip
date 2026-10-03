"""Copy a stable SQLite snapshot into empty MariaDB GeoIP tables."""

from contextlib import closing
from hashlib import sha256
from ipaddress import ip_address
import json
from pathlib import Path
import sqlite3

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.GeoIpDb import GeoIpDb


class SqliteMigration:
    @staticmethod
    def _digest(digest, values):
        digest.update(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        digest.update(b'\n')

    @staticmethod
    def copy(source: Path, db, progress=None) -> dict[int, int]:
        """Retain the source and commit both families only after full verification."""
        GeoIpDb(db)
        columns = ', '.join(f'`{name}`' for name in DGeoIp.COLUMNS)
        placeholders = ', '.join('%s' for _ in range(len(DGeoIp.COLUMNS) + 3))
        insert = (f'INSERT INTO GeoIp ({columns}, range_key, start_packed, end_packed) '
                  f'VALUES ({placeholders})')
        with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as old:
            old.row_factory = sqlite3.Row
            old.execute('BEGIN')
            metadata = [dict(row) for row in old.execute('SELECT * FROM GeoIpImport ORDER BY version')]
            counts = {row['version']: 0 for row in metadata}
            if not counts or any(version not in DGeoIp.VERSIONS for version in counts):
                raise ValueError('SQLite import metadata is missing or invalid.')
            expected = sha256()
            with db.transaction():
                if db.query('SELECT id FROM GeoIp LIMIT 1') or db.query('SELECT version FROM GeoIpImport LIMIT 1'):
                    raise ValueError('Migration requires empty MariaDB GeoIP tables; existing data was retained.')
                with closing(old.execute(f'SELECT {columns} FROM GeoIp ORDER BY rowid')) as cursor:
                    while rows := cursor.fetchmany(1000):
                        batch = []
                        for row in rows:
                            values = [row[name] for name in DGeoIp.COLUMNS]
                            if any(not isinstance(value, str) for value in values):
                                raise ValueError('SQLite provider fields must be text.')
                            version = int(row['ip_version'])
                            first, last = ip_address(row['start_ip']), ip_address(row['end_ip'])
                            if (version not in counts or row['ip_version'] != str(version)
                                    or first.version != version or last.version != version or first > last):
                                raise ValueError('Invalid SQLite GeoIP range or missing import metadata.')
                            batch.append((*values, *GeoIpDb._range_values(row['start_ip'], row['end_ip'])))
                            SqliteMigration._digest(expected, values)
                            counts[version] += 1
                        db.execute_many(insert, batch)
                        if progress:
                            progress(sum(counts.values()))
                for row in metadata:
                    if row['records'] != counts[row['version']] or counts[row['version']] == 0:
                        raise ValueError('SQLite record count does not match committed import metadata.')
                    db.execute('INSERT INTO GeoIpImport (version, size, mtime_ns, records) '
                               'VALUES (%s, %s, %s, %s)',
                               tuple(row[name] for name in ('version', 'size', 'mtime_ns', 'records')))
                actual, last_id = sha256(), 0
                while rows := db.query(f'SELECT id, {columns}, range_key, start_packed, end_packed '
                                       'FROM GeoIp WHERE id > %s ORDER BY id LIMIT 1000', (last_id,)):
                    for row in rows:
                        SqliteMigration._digest(actual, [row[name] for name in DGeoIp.COLUMNS])
                        if tuple(row[name] for name in ('range_key', 'start_packed', 'end_packed')) != \
                                GeoIpDb._range_values(row['start_ip'], row['end_ip']):
                            raise ValueError('MariaDB range verification failed.')
                    last_id = rows[-1]['id']
                if actual.digest() != expected.digest():
                    raise ValueError('MariaDB provider-field verification failed.')
                if db.query('SELECT * FROM GeoIpImport ORDER BY version') != metadata:
                    raise ValueError('MariaDB import metadata verification failed.')
            return counts
