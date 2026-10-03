"""Verify startup, imports, persisted progress, and refresh failure preservation."""

from io import BytesIO
from ipaddress import ip_address
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from bmgeoip.activity.DataLoader import DataLoader
from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from bmgeoip.interface.GeoIpDb import GeoIpDb
from test_geoip_source import csv_data, zipped


class DataLoaderTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.schedule = DownloadSchedule(self.root / 'schedule.json', self.root / 'data')
        self.loader = DataLoader(self.schedule, self.root / 'geoip.db', self.root / 'status.json')

    def seed(self):
        self.schedule.directory.mkdir(exist_ok=True)
        for version in (4, 6):
            (self.schedule.directory / f'ipv{version}.csv').write_bytes(csv_data(version))

    def query(self, sql, params=()):
        db = DbMgr(self.loader.database)
        try:
            return db.query(sql, params)
        finally:
            db.close()

    def test_first_start_downloads_even_with_schedule_disabled_then_imports(self):
        self.assertFalse(self.schedule.read()['enabled'])
        archives = [BytesIO(zipped(csv_data(version), DGeoIp.MEMBER.format(version=version)))
                    for version in (4, 6)]
        with patch('bmgeoip.interface.GeoIpSource.urlopen', side_effect=archives) as opened:
            self.assertTrue(self.loader.run())
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(self.loader.read()['phase'], 'ready')
        rows = self.query('SELECT * FROM GeoIp ORDER BY ip_version')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['zip'], '00123')
        self.assertEqual(rows[1]['start_ip'], '2606:4700::')
        self.assertEqual(rows[0]['city'], 'É, Example\nCity')
        messages = [entry['message'] for entry in self.loader.status_messages.snapshot()]
        for phase in ('Downloading', 'Extracting', 'Validating', 'Importing'):
            for version in (4, 6):
                self.assertIn(f'{phase} IPv{version} dataset.', messages)

    def test_existing_csvs_import_without_download_and_restart_skips_unchanged(self):
        self.seed()
        with patch('bmgeoip.interface.GeoIpSource.urlopen') as opened:
            self.assertTrue(self.loader.run())
            with patch.object(GeoIpDb, 'load', side_effect=AssertionError('Unchanged CSV reloaded')):
                self.assertTrue(self.loader.run())
            opened.assert_not_called()
        self.assertEqual(len(self.query('SELECT * FROM GeoIpImport')), 2)

    def test_partial_state_downloads_only_missing_family(self):
        self.seed()
        (self.schedule.directory / 'ipv6.csv').unlink()
        archive = BytesIO(zipped(csv_data(6), DGeoIp.MEMBER.format(version=6)))
        with patch('bmgeoip.interface.GeoIpSource.urlopen', return_value=archive) as opened:
            self.assertTrue(self.loader.run())
        opened.assert_called_once_with(DGeoIp.URL.format(version=6), timeout=DGeoIp.DOWNLOAD_TIMEOUT)

    def test_failed_import_rolls_back_deleted_and_inserted_records_and_metadata(self):
        self.seed()
        self.assertTrue(self.loader.run())
        db = DbMgr(self.loader.database, readonly=True)
        try:
            previous = GeoIpDb.lookup(db, ip_address('8.8.8.8'))
        finally:
            db.close()
        path = self.schedule.directory / 'ipv4.csv'
        # A malformed tail must roll back earlier full batches as well as the DELETE.
        data = csv_data(changes={'country': 'Replacement'})
        header, row = data.split(b'\n', 1)
        path.write_bytes(header + b'\n' + row * 1100 + b'4,invalid\n')
        with self.assertLogs(level='ERROR'):
            self.assertFalse(self.loader.run())
        rows = self.query('SELECT country FROM GeoIp WHERE ip_version = ?', ('4',))
        self.assertEqual(rows, [{'country': 'Canada'}])
        self.assertEqual(self.query('SELECT records FROM GeoIpImport WHERE version = 4'), [{'records': 1}])
        db = DbMgr(self.loader.database, readonly=True)
        try:
            self.assertEqual(GeoIpDb.lookup(db, ip_address('8.8.8.8')), previous)
        finally:
            db.close()
        self.assertEqual(self.loader.read()['phase'], 'error')
        self.assertTrue(any('IPv4 dataset failed' in entry['message']
                            for entry in self.loader.status_messages.snapshot()))

    def test_refresh_downloads_and_replaces_records_without_duplicates(self):
        self.seed()
        self.assertTrue(self.loader.run())
        self.schedule._write({'enabled': True, 'expression': '0 3 * * 0'})
        archives = [BytesIO(zipped(csv_data(version, {'country': 'Updated'}),
                                  DGeoIp.MEMBER.format(version=version))) for version in (4, 6)]
        with patch('bmgeoip.interface.GeoIpSource.urlopen', side_effect=archives):
            self.assertTrue(self.loader.run(refresh=True))
        self.assertEqual(self.query('SELECT country FROM GeoIp'),
                         [{'country': 'Updated'}, {'country': 'Updated'}])

    def test_failure_of_one_download_still_imports_the_other_and_preserves_csv(self):
        self.seed()
        self.assertTrue(self.loader.run())
        previous = (self.schedule.directory / 'ipv4.csv').read_bytes()
        self.schedule._write({'enabled': True, 'expression': '0 3 * * 0'})
        archive = BytesIO(zipped(csv_data(6), DGeoIp.MEMBER.format(version=6)))
        with patch('bmgeoip.interface.GeoIpSource.urlopen', side_effect=[OSError('offline'), archive]):
            with self.assertLogs(level='ERROR'):
                self.assertFalse(self.loader.run(refresh=True))
        self.assertEqual((self.schedule.directory / 'ipv4.csv').read_bytes(), previous)
        self.assertEqual(len(self.query('SELECT * FROM GeoIp')), 2)

    def test_progress_reports_transfer_validation_and_import(self):
        self.root.mkdir(exist_ok=True)
        self.loader._report('downloading', 4, 100, 200, force=True)
        status = DataLoader(self.schedule, self.loader.database, self.loader.status).read()
        self.assertEqual(status['completed'], 100)
        self.assertEqual(status['total'], 200)
        self.loader._report('importing', 4, 1000, force=True)
        self.assertEqual(self.loader.read()['phase'], 'importing')

    def test_start_returns_while_download_is_running(self):
        entered, release, finished = Event(), Event(), Event()

        def initialize():
            entered.set()
            release.wait(5)
            finished.set()

        with patch.object(self.loader, 'run', side_effect=initialize):
            try:
                self.loader.start()
                self.assertTrue(entered.wait(2))
                self.assertFalse(finished.is_set())
            finally:
                release.set()
                self.assertTrue(finished.wait(2))


if __name__ == '__main__':
    unittest.main()
