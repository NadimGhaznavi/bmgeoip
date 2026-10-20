"""Verify CMDB defaults, production overrides and deployment validation."""

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.interface.Configuration import Configuration
from bmgeoip.interface.Network import Network
from bmgeoip.server.BMGeoIPServer import main


ROOT = Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / DBMGeoIP.CONFIG_FILE
        setting = patch.object(DBMGeoIP, 'BASE_DIR', str(self.root))
        setting.start()
        self.addCleanup(setting.stop)
        Network._bindings.cache_clear()
        self.addCleanup(Network._bindings.cache_clear)

    def write(self, values):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(values))

    def test_defaults_follow_declaration_by_use_and_local_destinations(self):
        defaults = (('zmq', '192.0.2.5', 19001), ('http', '0.0.0.0', 19000))
        with patch.object(DBMGeoIP, 'CMDB_NETWORK', defaults):
            self.assertEqual(Network.binding('http'), ('0.0.0.0', 19000))
            self.assertEqual(Network.destination('http'), ('127.0.0.1', 19000))
            self.assertEqual(Network.destination('zmq'), ('192.0.2.5', 19001))

    def test_partial_overrides_and_process_cache(self):
        default_host, default_port = Network.binding('zmq')
        Network._bindings.cache_clear()
        self.write({'network': {'http': {'port': 19000}, 'zmq': {'interface': '127.0.0.2'}}})
        self.assertEqual(Network.binding('http'), ('0.0.0.0', 19000))
        self.assertEqual(Network.binding('zmq'), ('127.0.0.2', default_port))
        self.write({'network': {'zmq': {'port': 19001}}})
        self.assertEqual(Network.binding('zmq'), ('127.0.0.2', default_port))
        Network._bindings.cache_clear()
        self.assertEqual(Network.binding('zmq'), (default_host, 19001))

    def test_invalid_files_identify_path_and_never_fall_back(self):
        invalid = ['{', '[]', '{"unknown": {}}', '{"network": []}',
                   '{"network":{"unknown":{}}}', '{"network":{"http":{"host":"127.0.0.1"}}}']
        for value in ('localhost', '::1', '999.1.1.1', 123, None):
            invalid.append(json.dumps({'network': {'zmq': {'interface': value}}}))
        for value in (True, False, 0, 65536, '19000', 1.5, None):
            invalid.append(json.dumps({'network': {'http': {'port': value}}}))
        self.path.parent.mkdir()
        for value in invalid:
            with self.subTest(value=value):
                self.path.write_text(value)
                with self.assertRaisesRegex(ValueError, str(self.path)):
                    Network.binding('http')

    def test_install_generates_readable_defaults_and_preserves_existing_files(self):
        Configuration.install()
        expected = {'network': {use: {'interface': host, 'port': port}
                                for use, host, port in DBMGeoIP.CMDB_NETWORK}}
        self.assertEqual(json.loads(self.path.read_text()), expected)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        self.write({'network': {'http': {'port': 19000}}})
        original = self.path.read_bytes()
        Configuration.install()
        self.assertEqual(self.path.read_bytes(), original)
        self.path.write_text('{broken')
        with self.assertRaises(ValueError):
            Configuration.install()
        self.assertEqual(self.path.read_text(), '{broken')

    def test_startup_resolves_both_listeners_and_cli_precedence(self):
        defaults = (('zmq', '127.0.0.2', 19001), ('http', '127.0.0.3', 19000))
        for overrides, arguments, http, endpoint in (
                ({}, [], ('127.0.0.3', 19000), 'tcp://127.0.0.2:19001'),
                ({'http': {'port': 19002}, 'zmq': {'port': 19003}}, [],
                 ('127.0.0.3', 19002), 'tcp://127.0.0.2:19003'),
                ({'http': {'port': 19002}, 'zmq': {'port': 19003}},
                 ['--host', '127.0.0.4', '--port', '19004', '--zmq-endpoint', 'tcp://127.0.0.5:*'],
                 ('127.0.0.4', 19004), 'tcp://127.0.0.5:*')):
            Network._bindings.cache_clear()
            self.write({'network': overrides})
            with self.subTest(arguments=arguments), patch.object(DBMGeoIP, 'CMDB_NETWORK', defaults), \
                    patch('sys.argv', ['bmgeoip-server.py', *arguments]), \
                    patch('bmgeoip.server.BMGeoIPServer.BMGeoIPServer') as server, \
                    patch('bmgeoip.server.BMGeoIPServer.ZMQServer', side_effect=RuntimeError('stop')) as zmq:
                with self.assertRaisesRegex(RuntimeError, 'stop'):
                    main()
                self.assertEqual(server.call_args.args[0], http)
                self.assertEqual(zmq.call_args.args[0], endpoint)

    def test_installer_health_checks_follow_resolved_destination(self):
        self.write({'network': {'http': {'interface': '127.0.0.2', 'port': 19000}}})
        source = (ROOT / 'scripts/install.sh').read_text().split("<<'PY'\n")[-1].rsplit('\nPY', 1)[0]
        with patch('urllib.request.build_opener') as opener, patch('builtins.print'):
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b'Bear &amp; Moose GeoIP'
            with patch('json.load', side_effect=[{'status': status, 'service': 'bmgeoip-server'}
                                                for status in ('ok', 'ready')]):
                exec(compile(source, 'install-health-check', 'exec'), {})
            self.assertEqual([call.args[0] for call in opener.return_value.open.call_args_list],
                             ['http://127.0.0.2:19000/health', 'http://127.0.0.2:19000/ready',
                              'http://127.0.0.2:19000/'])

    def test_invalid_configuration_prevents_startup_even_with_cli_overrides(self):
        self.write({'network': {'zmq': {'port': False}}})
        with patch('sys.argv', ['bmgeoip-server.py', '--zmq-endpoint', 'tcp://127.0.0.1:*']), \
                patch('bmgeoip.server.BMGeoIPServer.BMGeoIPServer') as server, \
                redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 2)
            self.assertIn(str(self.path), errors.getvalue())
            server.assert_not_called()

    def test_restart_validates_before_systemctl(self):
        source = (ROOT / 'scripts/restart.sh').read_text()
        # Exercise the shell ordering with fake executables, without restarting services.
        executable = self.root / 'bin'
        executable.mkdir()
        marker = self.root / 'restarted'
        python = executable / 'python3'
        python.write_text('#!/bin/sh\nexit 1\n')
        systemctl = executable / 'systemctl'
        systemctl.write_text(f'#!/bin/sh\ntouch {marker}\n')
        for command in (python, systemctl):
            command.chmod(0o755)
        source = source.replace('[[ $# == 0 && $EUID == 0 ]]', '[[ $# == 0 ]]')
        source = source.replace('cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."', '')
        result = subprocess.run(['/bin/bash', '-c', source],
                                env={'PATH': str(executable) + ':/usr/bin:/bin'},
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
