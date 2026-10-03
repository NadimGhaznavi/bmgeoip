"""Verify destructive uninstall behavior without touching the host deployment."""

from contextlib import ExitStack
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from bmgeoip.constants.DBMGeoIP import DBMGeoIP


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/uninstall.sh'
SOURCE = SCRIPT.read_text().split("<<'PYTHON'\n", 1)[1].rsplit('\nPYTHON', 1)[0]


class UninstallTests(unittest.TestCase):
    def run_uninstall(self, *, installed=True, cron=True, failure=None, lingering=False):
        events = []
        killed = False

        def run(command, **kwargs):
            nonlocal killed
            events.append(command)
            if failure and command[0] == failure:
                raise subprocess.CalledProcessError(2, command)
            code = 0
            output = ''
            error = ''
            if command[0] == 'crontab' and command[-1] == '-l':
                code = 0 if cron else 1
                error = '' if cron else 'no crontab for bmgeoip\n'
            if command[0] == 'systemctl' and command[1] == 'show':
                output = 'loaded' if installed else 'not-found'
            if command[0] == 'pkill' and command[1] == '-KILL':
                killed = True
            if command[0] == 'pgrep':
                code = 0 if lingering and not killed else 1
            return subprocess.CompletedProcess(command, code, stdout=output, stderr=error)

        with ExitStack() as stack:
            stack.enter_context(patch('subprocess.run', side_effect=run))
            stack.enter_context(patch('pathlib.Path.is_symlink', return_value=False))
            stack.enter_context(patch('pathlib.Path.exists', return_value=installed))
            stack.enter_context(patch('os.getuid', return_value=0))
            stack.enter_context(patch('pwd.getpwnam', return_value=SimpleNamespace(
                pw_uid=987, pw_dir='/var/lib/bmgeoip'), side_effect=None if installed else KeyError))
            stack.enter_context(patch('grp.getgrnam', side_effect=None if installed else KeyError))
            stack.enter_context(patch('time.sleep'))
            unlink = stack.enter_context(patch('pathlib.Path.unlink', autospec=True))
            remove = stack.enter_context(patch('shutil.rmtree'))
            stack.enter_context(patch('builtins.print'))
            if failure:
                with self.assertRaises(subprocess.CalledProcessError):
                    exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
            else:
                exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
        return events, unlink, remove

    def test_removes_service_state_crontab_account_and_group(self):
        events, unlink, remove = self.run_uninstall()
        self.assertEqual(events, [
            ['crontab', '-u', 'bmgeoip', '-l'],
            ['systemctl', 'show', 'bmgeoip-server.service', '--property=LoadState', '--value'],
            ['systemctl', 'disable', '--now', 'bmgeoip-server.service'],
            ['crontab', '-u', 'bmgeoip', '-r'],
            ['pkill', '-TERM', '-u', '987'],
            ['pgrep', '-u', '987'],
            ['systemctl', 'daemon-reload'],
            ['userdel', '--remove', 'bmgeoip'],
            ['groupdel', 'bmgeoip'],
        ])
        unlink.assert_called_once_with(Path('/etc/systemd/system/bmgeoip-server.service'),
                                       missing_ok=True)
        self.assertEqual(remove.call_args_list, [
            call(Path('/etc/systemd/system/bmgeoip-server.service.d')),
            call(Path('/opt/prod/bmgeoip')),
            call(Path('/var/lib/bmgeoip')),
        ])

    def test_repeat_uninstall_with_missing_deployment_and_account(self):
        events, _, remove = self.run_uninstall(installed=False)
        self.assertEqual([command[0] for command in events], ['systemctl', 'systemctl'])
        remove.assert_not_called()

    def test_account_without_crontab_is_still_removed(self):
        events, _, _ = self.run_uninstall(cron=False)
        self.assertNotIn(['crontab', '-u', 'bmgeoip', '-r'], events)
        self.assertIn(['userdel', '--remove', 'bmgeoip'], events)

    def test_cron_or_service_failure_prevents_file_and_account_removal(self):
        for failure in ('crontab', 'systemctl', 'pkill'):
            with self.subTest(failure=failure):
                events, unlink, remove = self.run_uninstall(failure=failure)
                unlink.assert_not_called()
                remove.assert_not_called()
                self.assertFalse(any(command[0] == 'userdel' for command in events))

    def test_download_that_ignores_term_is_killed_before_account_removal(self):
        events, _, _ = self.run_uninstall(lingering=True)
        kill = events.index(['pkill', '-KILL', '-u', '987'])
        delete = events.index(['userdel', '--remove', 'bmgeoip'])
        self.assertLess(kill, delete)
        self.assertEqual(events[kill + 1], ['pgrep', '-u', '987'])

    def test_unsafe_paths_and_identity_are_rejected_before_commands(self):
        for attribute, value in (('BASE_DIR', '/opt/prod'), ('SERVICE_HOME', '/var/lib'),
                                 ('SERVICE_UNIT', '../other.service'), ('SERVICE_USER', 'root')):
            with self.subTest(attribute=attribute), patch.object(DBMGeoIP, attribute, value), \
                    patch('subprocess.run') as run:
                with self.assertRaises(SystemExit):
                    exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
                run.assert_not_called()

    def test_symlink_or_installed_checkout_is_rejected_before_commands(self):
        for mock in (patch('pathlib.Path.is_symlink', return_value=True),
                     patch('pathlib.Path.cwd', return_value=Path('/opt/prod/bmgeoip'))):
            with mock, patch('subprocess.run') as run:
                with self.assertRaises(SystemExit):
                    exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
                run.assert_not_called()

    def test_root_or_unexpected_account_home_is_rejected_before_commands(self):
        for uid, home in ((0, '/var/lib/bmgeoip'), (987, '/home/other')):
            with patch('pwd.getpwnam', return_value=SimpleNamespace(pw_uid=uid, pw_dir=home)), \
                    patch('subprocess.run') as run:
                with self.assertRaises(SystemExit):
                    exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
