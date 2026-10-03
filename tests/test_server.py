"""Verify HTTP contracts, Jinja2 rendering, and service shutdown."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import select
import subprocess
import sys
from threading import Thread
import unittest
from unittest.mock import patch

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.server.BMGeoIPHandler import BMGeoIPHandler


ROOT = Path(__file__).resolve().parents[1]


class HTTPTests(unittest.TestCase):
    def setUp(self):
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
        self.assertIn(b'/var/lib/bmgeoip/data/ipv4.csv', body)
        self.assertIn(b'/var/lib/bmgeoip/data/ipv6.csv', body)
        for path, content_type in (('/static/style.css', 'text/css; charset=utf-8'),
                                   ('/pages/images/bmgeoip.png', 'image/png'),
                                   ('/static/downloads.js', 'text/javascript; charset=utf-8')):
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

    def test_schedule_save_and_failure_responses(self):
        values = {'enabled': True, 'expression': '0 3 * * 0'}
        with patch('bmgeoip.server.BMGeoIPHandler.DownloadSchedule') as scheduler:
            scheduler.return_value.update.return_value = values
            status, _, body = self.request('/api/download-schedule', 'POST', json.dumps(values),
                                            {'Content-Type': 'application/json'})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {'schedule': values})
            scheduler.return_value.update.assert_called_once_with(**values)
            scheduler.return_value.update.side_effect = ValueError('Invalid cron')
            self.assertEqual(self.request('/api/download-schedule', 'POST', json.dumps(values),
                                         {'Content-Type': 'application/json'})[0], 400)
            scheduler.return_value.update.side_effect = OSError('denied')
            with self.assertLogs(level='ERROR') as logs:
                self.assertEqual(self.request('/api/download-schedule', 'POST', json.dumps(values),
                                             {'Content-Type': 'application/json'})[0], 503)
            self.assertEqual(logs.records[0].getMessage(), 'Could not save CSV download schedule')
            self.assertIsInstance(logs.records[0].exc_info[1], OSError)

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
        # Reserve a free port and release it immediately before startup.
        with ThreadingHTTPServer(('127.0.0.1', 0), BMGeoIPHandler) as reservation:
            port = reservation.server_port
        process = subprocess.Popen(
            [sys.executable, '-B', str(ROOT / 'bmgeoip-server.py'),
             '--host', '127.0.0.1', '--port', str(port)],
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
            process.terminate()
            output, errors = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, errors.decode())
            self.assertNotIn(b'Traceback', errors)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
