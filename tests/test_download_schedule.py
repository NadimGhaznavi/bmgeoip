"""Exercise scheduling and dispatch without touching system cron or the provider."""

import fcntl
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crontab import CronTab

from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from bmgeoip.interface.DownloadRunner import run


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.schedule = DownloadSchedule(root / 'schedule.json', root / 'data')
        self.tab = CronTab(tab='15 2 * * * /other # unrelated\n')
        self.tab.write = unittest.mock.Mock()
        cron = patch('bmgeoip.interface.DownloadSchedule.CronTab', return_value=self.tab)
        cron.start()
        self.addCleanup(cron.stop)

    def test_update_persists_replaces_and_disables_only_owned_job(self):
        self.assertFalse(self.schedule.read()['enabled'])
        for expression in ('0 3 * * 0', '30 4 * * 1-5'):
            saved = self.schedule.update(True, expression)
            self.assertEqual(DownloadSchedule(self.schedule.settings).read(), saved)
            jobs = list(self.tab.find_comment(self.schedule.COMMENT))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(str(jobs[0].slices), expression)
            self.assertIn('/bmgeoip-download.py', jobs[0].command)
        self.schedule.update(False, '30 4 * * 1-5')
        self.assertFalse(self.schedule.read()['enabled'])
        self.assertEqual(len(list(self.tab.find_comment(self.schedule.COMMENT))), 0)
        self.assertEqual(len(list(self.tab.find_comment('unrelated'))), 1)

    def test_invalid_settings_do_not_write(self):
        for enabled, expression in ((1, '0 3 * * 0'), (True, '@daily'), (True, '60 3 * * 0'),
                                    (True, '0 3 * * 0\n'), (True, '0 3 * * 0 /command'),
                                    (True, None)):
            with self.assertRaises(ValueError):
                self.schedule.update(enabled, expression)
        self.tab.write.assert_not_called()
        self.assertFalse(self.schedule.settings.exists())

    def test_cron_failure_restores_previous_settings(self):
        self.schedule.update(False, '0 3 * * 0')
        self.tab.write.side_effect = OSError('denied')
        with self.assertRaises(OSError):
            self.schedule.update(True, '30 4 * * 1-5')
        self.assertEqual(self.schedule.read(), {'enabled': False, 'expression': '0 3 * * 0'})

    def test_file_paths_and_missing_or_existing_status(self):
        self.schedule.directory.mkdir()
        (self.schedule.directory / 'ipv4.csv').write_text('example')
        files = self.schedule.files()
        self.assertEqual(files[0]['size'], 7)
        self.assertTrue(files[0]['modified'].endswith('+00:00'))
        self.assertEqual(files[1]['path'], str(self.schedule.directory / 'ipv6.csv'))
        self.assertIsNone(files[1]['modified'])

    def test_dispatch_rechecks_enabled_and_attempts_both_families(self):
        with patch('bmgeoip.interface.DownloadRunner.DownloadSchedule', return_value=self.schedule), \
                patch('bmgeoip.interface.DownloadRunner.GeoIpSource') as source:
            self.assertTrue(run())
            source.assert_not_called()
            self.schedule.update(True, '0 3 * * 0')
            source.return_value.download.side_effect = [OSError('offline'), None]
            self.assertFalse(run())
            self.assertEqual(source.return_value.download.call_args_list,
                             [unittest.mock.call(4, self.schedule.directory / 'ipv4.csv'),
                              unittest.mock.call(6, self.schedule.directory / 'ipv6.csv')])

    def test_overlapping_dispatch_skips_download(self):
        self.schedule.update(True, '0 3 * * 0')
        with self.schedule.settings.with_suffix('.download.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('bmgeoip.interface.DownloadRunner.DownloadSchedule', return_value=self.schedule), \
                    patch('bmgeoip.interface.DownloadRunner.GeoIpSource') as source:
                self.assertTrue(run())
                source.assert_not_called()


if __name__ == '__main__':
    unittest.main()
