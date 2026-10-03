"""Check credential recovery using temporary files and a mocked MariaDB client."""

from contextlib import ExitStack
import hashlib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DatabaseEnvironment import DatabaseEnvironment


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/upgrade.sh'
SOURCE = SCRIPT.read_text().split("<<'PYTHON'\n", 1)[1].rsplit('\nPYTHON', 1)[0]


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'config/database.env'

    def run_recovery(self, *, failure=None, socket='/run/mysqld/mysqld.sock\n', group_exists=True):
        with ExitStack() as stack:
            stack.enter_context(patch.object(DGeoIp, 'DATABASE_ENV', str(self.path)))
            group = SimpleNamespace(gr_gid=123)
            stack.enter_context(patch('grp.getgrnam', side_effect=
                                      [group] if group_exists else [KeyError(), group]))
            chown = stack.enter_context(patch('os.chown'))
            fchown = stack.enter_context(patch('os.fchown'))
            run = stack.enter_context(patch('subprocess.run', side_effect=failure,
                return_value=subprocess.CompletedProcess([], 0, stdout=socket)))
            stack.enter_context(patch('builtins.print'))
            exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
        return run, chown, fchown

    def test_missing_credentials_reset_application_password_and_grant_access(self):
        run, chown, fchown = self.run_recovery()
        values = DatabaseEnvironment.read(self.path)
        self.assertEqual(values['DB_NAME'], 'bmgeoip')
        self.assertEqual(values['DB_USER'], 'bmgeoip')
        self.assertEqual(values['DB_SOCKET'], '/run/mysqld/mysqld.sock')
        password = values['DB_PASSWORD']
        self.assertEqual(len(password), 64)
        int(password, 16)
        digest = hashlib.sha1(hashlib.sha1(password.encode()).digest()).hexdigest().upper()
        command = run.call_args.args[0]
        sql = run.call_args.kwargs['input']
        self.assertEqual(command, ['mariadb', '--no-defaults', '--user=root',
                                  '--protocol=socket', '--batch', '--skip-column-names'])
        self.assertIn('CREATE DATABASE IF NOT EXISTS `bmgeoip`', sql)
        self.assertIn("CREATE USER IF NOT EXISTS 'bmgeoip'@'localhost'", sql)
        self.assertIn(f"ALTER USER 'bmgeoip'@'localhost' IDENTIFIED VIA "
                      f"mysql_native_password USING '*{digest}'", sql)
        self.assertIn('GRANT SELECT, INSERT, DELETE, UPDATE, CREATE, INDEX ON `bmgeoip`.*', sql)
        self.assertNotIn(password, sql)
        self.assertNotIn('DROP ', sql)
        self.assertNotIn("ALTER USER 'root'", sql)
        self.assertTrue(run.call_args.kwargs['check'])
        self.assertEqual(run.call_args.kwargs['timeout'], 30)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o750)
        chown.assert_called_once_with(self.path.parent, 0, 123)
        self.assertEqual(fchown.call_args.args[1:], (0, 123))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_existing_custom_credentials_preserved_without_database_commands(self):
        self.path.parent.mkdir()
        original = ('DB_HOST=database.example\nDB_PORT=3307\nDB_NAME=custom\n'
                    'DB_USER=custom\nDB_PASSWORD=existing-password\n')
        self.path.write_text(original)
        self.path.chmod(0o600)
        run, chown, fchown = self.run_recovery()
        run.assert_not_called()
        chown.assert_not_called()
        fchown.assert_not_called()
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_invalid_existing_credentials_are_not_replaced(self):
        self.path.parent.mkdir()
        self.path.write_text('DB_HOST=localhost\n')
        with self.assertRaises(ValueError):
            self.run_recovery()
        self.assertEqual(self.path.read_text(), 'DB_HOST=localhost\n')

    def test_failures_do_not_publish_credentials_and_allow_retry(self):
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired('mariadb', 30),
                        subprocess.CalledProcessError(1, 'mariadb', stderr='private SQL')):
            with self.subTest(failure=type(failure).__name__):
                with self.assertRaises(SystemExit) as error:
                    self.run_recovery(failure=failure)
                self.assertNotIn('private SQL', str(error.exception))
                self.assertFalse(self.path.exists())
                self.assertEqual(list(self.path.parent.iterdir()), [])
        self.run_recovery()
        self.assertTrue(self.path.is_file())

    def test_creates_missing_service_group(self):
        run, _, _ = self.run_recovery(group_exists=False)
        self.assertEqual(run.call_args_list[0].args[0], ['groupadd', '--system', 'bmgeoip'])
        self.assertEqual(run.call_count, 2)

    def test_invalid_socket_does_not_publish_credentials(self):
        for socket in ('', 'relative.sock', '/tmp/db.sock\nother-row'):
            with self.subTest(socket=socket), self.assertRaises(SystemExit):
                self.run_recovery(socket=socket)
            self.assertFalse(self.path.exists())

    def test_symlink_configuration_is_rejected(self):
        self.path.parent.mkdir()
        destination = self.root / 'elsewhere'
        self.path.symlink_to(destination)
        with self.assertRaises(SystemExit), patch('subprocess.run') as run:
            self.run_recovery()
        run.assert_not_called()
        self.assertFalse(destination.exists())

    def test_installed_checkout_rejected_before_database_commands(self):
        with patch('pathlib.Path.cwd', return_value=Path('/opt/prod/bmgeoip')), \
                self.assertRaises(SystemExit), patch('subprocess.run') as run:
            self.run_recovery()
        run.assert_not_called()
        self.assertFalse(self.path.parent.exists())


if __name__ == '__main__':
    unittest.main()
