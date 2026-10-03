"""Verify HTTP contracts, Jinja2 rendering, and service shutdown."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import select
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.server.BMGeoIPHandler import BMGeoIPHandler
from bmgeoip.activity.DataLoader import DataLoader
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from bmgeoip.interface.StatusMessages import StatusMessages
from test_geoip_source import csv_data
from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.GeoIpDb import GeoIpDb


ROOT = Path(__file__).resolve().parents[1]


class HTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.messages = StatusMessages(Path(temporary.name) / 'messages.json')
        messages_patch = patch('bmgeoip.server.BMGeoIPHandler.StatusMessages', return_value=self.messages)
        messages_patch.start()
        self.addCleanup(messages_patch.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), BMGeoIPHandler)
        self.thread = Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def request(self, path, method='GET', body=None, headers=None):
        connection = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_health_and_readiness_describe_web_service(self):
        for path, expected in (('/health', 'ok'), ('/ready', 'ready')):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], 'application/json')
            self.assertEqual(json.loads(body), {'status': expected, 'service': 'bmgeoip-server'})

    def test_home_uses_jinja2_autoescaping_and_serves_assets(self):
        with patch.object(DBMGeoIP, 'VERSION', '<script>test</script>'):
            status, headers, body = self.request('/?view=status')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/html; charset=utf-8')
        self.assertIn(b'&lt;script&gt;test&lt;/script&gt;', body)
        self.assertNotIn(b'{{', body)
        self.assertIn(b'CSV Download Schedule', body)
        self.assertIn(b'Status Messages', body)
        self.assertLess(body.index(b'CSV Data Files'), body.index(b'IP Address Lookup'))
        self.assertLess(body.index(b'Lookup Results'), body.index(b'Status Messages'))
        self.assertIn(b'<th scope="col">Timestamp</th><th scope="col">Source</th><th scope="col">Message</th>', body)
        self.assertIn(b'/var/lib/bmgeoip/data/ipv4.csv', body)
        self.assertIn(b'/var/lib/bmgeoip/data/ipv6.csv', body)
        for path, content_type in (('/static/style.css', 'text/css; charset=utf-8'),
                                   ('/pages/images/bmgeoip.png', 'image/png'),
                                   ('/static/downloads.js', 'text/javascript; charset=utf-8'),
                                   ('/static/lookup.js', 'text/javascript; charset=utf-8'),
                                   ('/static/status_messages.js', 'text/javascript; charset=utf-8')):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], content_type)
            self.assertGreater(len(body), 0)

    def test_head_preserves_headers_without_body(self):
        for path in ('/', '/health', '/ready', '/static/style.css', '/missing'):
            status, headers, body = self.request(path)
            head_status, head_headers, head_body = self.request(path, 'HEAD')
            self.assertEqual(head_status, status)
            self.assertEqual(head_headers['Content-Length'], str(len(body)))
            self.assertEqual(head_headers['Content-Type'], headers['Content-Type'])
            self.assertEqual(head_body, b'')

    def test_unknown_paths_cannot_read_files(self):
        for path in ('/missing', '/static/../../requirements.txt', '/pages/images/../coding-guidelines.md'):
            status, headers, body = self.request(path)
            self.assertEqual(status, 404)
            self.assertEqual(json.loads(body), {'error': 'Not found.'})

    def test_data_status_reads_shared_progress_and_handles_storage_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            loader = DataLoader(DownloadSchedule(root / 'schedule.json', root / 'data'),
                                root / 'geoip.db', root / 'status.json')
            self.server.data_loader = loader
            self.assertEqual(json.loads(self.request('/api/data-status')[2])['phase'], 'waiting')
            loader._report('downloading', 6, 1024, 2048, force=True)
            status, _, body = self.request('/api/data-status')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), loader.read())
            self.assertEqual(self.request('/api/data-status', 'HEAD')[2], b'')
            loader.status.write_text('{broken')
            with self.assertLogs(level='ERROR'):
                self.assertEqual(self.request('/api/data-status')[0], 503)

    def test_schedule_save_and_failure_responses(self):
        values = {'enabled': True, 'expression': '0 3 * * 0'}
        with patch('bmgeoip.server.BMGeoIPHandler.DownloadSchedule') as scheduler:
            scheduler.return_value.update.return_value = values
            status, _, body = self.request('/api/download-schedule', 'POST', json.dumps(values),
                                            {'Content-Type': 'application/json'})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {'schedule': values})
            scheduler.return_value.update.assert_called_once_with(**values)
            self.assertIn('CSV download schedule saved: enabled; 0 3 * * 0.',
                          [entry['message'] for entry in self.messages.snapshot()])
            scheduler.return_value.update.side_effect = ValueError('Invalid cron')
            self.assertEqual(self.request('/api/download-schedule', 'POST', json.dumps(values),
                                         {'Content-Type': 'application/json'})[0], 400)
            scheduler.return_value.update.side_effect = OSError('denied')
            with self.assertLogs(level='ERROR') as logs:
                self.assertEqual(self.request('/api/download-schedule', 'POST', json.dumps(values),
                                             {'Content-Type': 'application/json'})[0], 503)
            self.assertEqual(logs.records[0].getMessage(), 'Could not save CSV download schedule')
            self.assertIsInstance(logs.records[0].exc_info[1], OSError)
            self.assertIn('Could not save CSV download schedule.', self.messages.snapshot()[-1]['message'])

    def test_lookup_results_boundaries_nested_ranges_and_failures(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            loader = DataLoader(DownloadSchedule(root / 'schedule.json', root / 'data'),
                                root / 'geoip.db', root / 'status.json')
            self.server.data_loader = loader
            with self.assertLogs(level='ERROR'):
                self.assertEqual(self.request('/api/lookup?ip=8.8.8.8')[0], 503)
            self.assertFalse(loader.database.exists())
            db = DbMgr(loader.database)
            try:
                records = GeoIpDb(db)
                self.assertEqual(self.request('/api/lookup?ip=8.8.8.8')[0], 503)
                for version in (4, 6):
                    path = root / f'ipv{version}.csv'
                    path.write_bytes(csv_data(version))
                    records.load(version, path)
                for address in ('8.8.8.0', '8.8.8.255', '2606:4700::',
                                '2606:4700::ff', '2606:4700:0:0:0:0:0:8'):
                    status, _, body = self.request('/api/lookup?ip=' + address)
                    self.assertEqual(status, 200)
                    result = json.loads(body)
                    self.assertEqual(result['results'][0]['zip'], '00123')
                    self.assertEqual(result['results'][0]['city'], 'É, Example\nCity')
                    self.assertEqual(len(result['results'][0]), 14)
                for address in ('8.8.7.255', '8.8.9.0', '2606:4700::100', '127.0.0.1'):
                    status, _, body = self.request('/api/lookup?ip=' + address)
                    self.assertEqual(status, 200)
                    self.assertEqual(json.loads(body)['results'], [])
                db.execute('INSERT INTO GeoIp SELECT ip_version, ?, ?, continent, country_code, '
                           'country, state, city, zip, timezone, latitude, longitude, accuracy, source '
                           'FROM GeoIp WHERE ip_version = ?', ('8.8.8.8', '8.8.8.8', '4'))
                self.assertEqual(len(json.loads(self.request('/api/lookup?ip=8.8.8.8')[2])['results']), 2)
                self.assertEqual(self.request('/api/lookup?ip=8.8.8.8', 'HEAD')[2], b'')
            finally:
                db.close()

    def test_invalid_lookup_requests_do_not_open_database(self):
        with patch('bmgeoip.interface.GeoIpLookup.DbMgr') as db:
            for query in ('', '?ip=', '?ip=example.com', '?ip=8.8.8.8/24', '?ip=fe80::1%25eth0',
                          '?ip=8.8.8.8&ip=1.1.1.1', '?ip=8.8.8.8&extra=true',
                          '?ip=999.1.1.1', '?ip=' + 'a' * 46):
                status, _, body = self.request('/api/lookup' + query)
                self.assertEqual(status, 400)
                self.assertIn('error', json.loads(body))
            db.assert_not_called()

    def test_status_history_and_storage_failure(self):
        self.assertEqual(json.loads(self.request('/status-messages')[2]), [])
        self.messages.append('<script>example</script>')
        status, headers, body = self.request('/status-messages')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(json.loads(body), self.messages.snapshot())
        self.assertEqual(self.request('/status-messages', 'HEAD')[2], b'')
        self.messages.path.write_text('{broken')
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.request('/status-messages')[0], 503)

    def test_invalid_schedule_requests_never_reach_scheduler(self):
        with patch('bmgeoip.server.BMGeoIPHandler.DownloadSchedule') as scheduler:
            for body in ('{', '[]', '{}', '{"enabled":true}', 'x' * 4097):
                self.assertEqual(self.request('/api/download-schedule', 'POST', body,
                                             {'Content-Type': 'application/json'})[0], 400)
            self.assertEqual(self.request('/api/download-schedule', 'POST', '{}',
                                         {'Content-Type': 'application/x-www-form-urlencoded'})[0], 400)
            self.assertEqual(self.request('/api/download-schedule', 'POST', '{}',
                                         {'Content-Type': 'application/json',
                                          'Origin': 'https://other.example'})[0], 403)
            self.assertEqual(self.request('/missing', 'POST', '{}')[0], 404)
            scheduler.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def test_invalid_listener_configuration_fails_before_startup(self):
        for args in (['--port', '0'], ['--port', '65536'], ['--port', 'abc'],
                     ['--host', 'invalid'], ['--host', '::1']):
            result = subprocess.run([sys.executable, '-B', str(ROOT / 'bmgeoip-server.py'), *args],
                                    capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b'error:', result.stderr)

    def test_sigterm_exits_cleanly(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = Path(temporary.name)
        (state / 'data').mkdir()
        for version in (4, 6):
            (state / 'data' / f'ipv{version}.csv').write_bytes(csv_data(version))
        # Reserve a free port and release it immediately before startup.
        with ThreadingHTTPServer(('127.0.0.1', 0), BMGeoIPHandler) as reservation:
            port = reservation.server_port
        process = subprocess.Popen(
            [sys.executable, '-B', str(ROOT / 'bmgeoip-server.py'),
             '--host', '127.0.0.1', '--port', str(port), '--state-dir', str(state)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'Server did not start.')
            self.assertIn(f'http://127.0.0.1:{port}/'.encode(), process.stdout.readline())
            connection = HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                connection.request('GET', '/health')
                self.assertEqual(connection.getresponse().status, 200)
            finally:
                connection.close()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                connection = HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    connection.request('GET', '/api/data-status')
                    result = json.loads(connection.getresponse().read())
                finally:
                    connection.close()
                if result['phase'] == 'ready':
                    break
                time.sleep(0.05)
            self.assertEqual(result['phase'], 'ready')
            self.assertTrue((state / 'geoip.sqlite3').is_file())
            messages = StatusMessages(state / 'status-messages.json').snapshot()
            self.assertTrue(any('HTTP listener ready' in entry['message'] for entry in messages))
            self.assertTrue(any('Both datasets loaded' in entry['message'] for entry in messages))
            process.terminate()
            output, errors = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, errors.decode())
            self.assertNotIn(b'Traceback', errors)
            self.assertEqual(StatusMessages(state / 'status-messages.json').snapshot()[-1]['message'],
                             'HTTP server stopping.')
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
