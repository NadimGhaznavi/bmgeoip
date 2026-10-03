"""Verify indexed SQL matches and atomic upgrades of legacy GeoIP records."""

from ipaddress import ip_address
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.GeoIpDb import GeoIpDb
from bmgeoip.interface.GeoIpSource import GeoIpSource
from test_geoip_source import csv_data


class GeoIpDbTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = DbMgr(self.root / 'geoip.db')
        self.addCleanup(self.db.close)

    def legacy(self):
        columns = ', '.join(f'"{name}" TEXT NOT NULL' for name in DGeoIp.COLUMNS)
        self.db.execute(f'CREATE TABLE GeoIp ({columns})')
        self.db.execute('CREATE TABLE GeoIpImport (version INTEGER PRIMARY KEY, '
                        'size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, records INTEGER NOT NULL)')
        for version in (4, 6):
            path = self.root / f'ipv{version}.csv'
            path.write_bytes(csv_data(version))
            row = next(GeoIpSource().rows(path, version))
            placeholders = ', '.join('?' for _ in DGeoIp.COLUMNS)
            self.db.execute(f'INSERT INTO GeoIp VALUES ({placeholders})', tuple(row.values()))
            stat = path.stat()
            self.db.execute('INSERT INTO GeoIpImport VALUES (?, ?, ?, ?)',
                            (version, stat.st_size, stat.st_mtime_ns, 1))

    def test_upgrade_preserves_provider_fields_metadata_and_restart(self):
        self.legacy()
        original = self.db.query('SELECT * FROM GeoIp')
        metadata = self.db.query('SELECT * FROM GeoIpImport')
        records = GeoIpDb(self.db)
        for version, address in ((4, '8.8.8.8'), (6, '2606:4700::8')):
            self.assertEqual(GeoIpDb.lookup(self.db, ip_address(address)), [original[0 if version == 4 else 1]])
            self.assertEqual(records.current(version, self.root / f'ipv{version}.csv'), 1)
        self.assertEqual(self.db.query('SELECT * FROM GeoIpImport'), metadata)
        with patch.object(GeoIpDb, '_range_values', side_effect=AssertionError('Index rebuilt')):
            GeoIpDb(self.db)

    def test_failed_upgrade_rolls_back_schema_and_retries(self):
        self.legacy()
        original = self.db.query('SELECT * FROM GeoIp')
        with patch.object(GeoIpDb, '_range_values', side_effect=ValueError('interrupted')):
            with self.assertRaises(ValueError):
                GeoIpDb(self.db)
        self.assertEqual(self.db.query('SELECT * FROM GeoIp'), original)
        self.assertEqual(len(self.db.query('PRAGMA table_info(GeoIp)')), 14)
        GeoIpDb(self.db)
        self.assertEqual(GeoIpDb.lookup(self.db, ip_address('8.8.8.8')), [original[0]])

    def test_sql_bounds_overlaps_full_ranges_and_numeric_order_for_both_families(self):
        records = GeoIpDb(self.db)
        random = Random(12)
        for version, base in ((4, int(ip_address('185.199.108.0'))),
                              (6, int(ip_address('2001:db8::')))):
            bits = 32 if version == 4 else 128
            # Unaligned, overlapping, nested, singleton, and full-family ranges.
            ranges = [(0, (1 << bits) - 1), (base + 7, base + 18),
                      (base + 8, base + 8), (base + 10, base + 31)]
            ranges += [(base + start, base + end) for start, end in
                       (sorted(random.sample(range(256), 2)) for _ in range(80))]

            def address(value):
                return ip_address(value.to_bytes(bits // 8, 'big'))

            data = csv_data(version, {'start_ip': str(address(ranges[0][0])),
                                      'end_ip': str(address(ranges[0][1]))})
            for start, end in ranges[1:]:
                data += csv_data(version, {'start_ip': str(address(start)),
                                           'end_ip': str(address(end))}).split(b'\n', 1)[1]
            path = self.root / f'ipv{version}.csv'
            path.write_bytes(data)
            records.load(version, path)
            for target in [0, (1 << bits) - 1, base - 1, base + 256, *range(base, base + 256)]:
                result = GeoIpDb.lookup(self.db, address(target))
                expected = sorted((start, end) for start, end in ranges if start <= target <= end)
                self.assertEqual([(int(ip_address(row['start_ip'])), int(ip_address(row['end_ip'])))
                                  for row in result], expected)
                self.assertTrue(all(len(row) == 14 and row['zip'] == '00123' for row in result))

    def test_lookup_query_uses_prefix_index(self):
        records = GeoIpDb(self.db)
        path = self.root / 'ipv4.csv'
        path.write_bytes(csv_data())
        records.load(4, path)
        query = self.db.query
        plans = []

        def inspect(sql, params=()):
            if 'range_key IN' in sql:
                plans.extend(query('EXPLAIN QUERY PLAN ' + sql, params))
            return query(sql, params)

        with patch.object(self.db, 'query', side_effect=inspect):
            GeoIpDb.lookup(self.db, ip_address('8.8.8.8'))
        self.assertTrue(any('SEARCH GeoIp USING INDEX GeoIp_range' in row['detail']
                            for row in plans), plans)
        self.assertFalse(any('SCAN GeoIp' in row['detail'] for row in plans), plans)


if __name__ == '__main__':
    unittest.main()
