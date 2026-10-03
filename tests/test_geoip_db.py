"""Verify indexed SQL matches and atomic upgrades of legacy GeoIP records."""

from ipaddress import ip_address
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from database_support import database_settings
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
        self.db = DbMgr(database_settings(self, self.root / 'database.env'))
        self.addCleanup(self.db.close)

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
                plans.extend(query('EXPLAIN ' + sql, params))
            return query(sql, params)

        with patch.object(self.db, 'query', side_effect=inspect):
            GeoIpDb.lookup(self.db, ip_address('8.8.8.8'))
        self.assertTrue(any(row['key'] == 'GeoIp_range' and row['type'] == 'range'
                            for row in plans), plans)


if __name__ == '__main__':
    unittest.main()
