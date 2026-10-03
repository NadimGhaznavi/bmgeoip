"""Verify ZMQ lookup contracts, worker ownership, and transport lifecycle."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from database_support import database_settings
from unittest.mock import Mock, patch

import zmq

from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.GeoIpDb import GeoIpDb
from bmgeoip.interface.GeoIpLookup import GeoIpLookup
from bmgeoip.server.LookupHandler import LookupHandler
from bmgeoip.zmq.ZMQMsg import ZMQMsg
from bmgeoip.zmq.ZMQServer import ZMQServer
from test_geoip_source import csv_data


class ZMQTests(unittest.TestCase):
    def request(self, endpoint, frames):
        with zmq.Context() as context, context.socket(zmq.REQ) as socket:
            socket.setsockopt(zmq.LINGER, 0)
            socket.setsockopt(zmq.SNDTIMEO, 2000)
            socket.setsockopt(zmq.RCVTIMEO, 2000)
            socket.connect(endpoint)
            socket.send_multipart(frames)
            return ZMQMsg.from_json(socket.recv())

    def lookup(self, endpoint, address):
        return self.request(endpoint, [ZMQMsg('test', 'lookup', 'bmgeoip', {'ip': address}).to_json()])

    def test_lookup_families_refresh_rollback_and_missing_data(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = database_settings(self, root / 'database.env')
            with ZMQServer('tcp://127.0.0.1:*', LookupHandler(GeoIpLookup(database))) as worker:
                with self.assertLogs(level='ERROR'):
                    self.assertEqual(self.lookup(worker.endpoint, '8.8.8.8').payload['error']['code'], 'data_unavailable')
                db = DbMgr(database)
                try:
                    records = GeoIpDb(db)
                    self.assertEqual(self.lookup(worker.endpoint, '8.8.8.8').payload['error']['code'], 'data_unavailable')
                    for version in (4, 6):
                        path = root / f'ipv{version}.csv'
                        path.write_bytes(csv_data(version))
                        records.load(version, path)
                    for address in ('8.8.8.0', '8.8.8.255', '2606:4700::', '2606:4700::ff'):
                        reply = self.lookup(worker.endpoint, address)
                        self.assertEqual((reply.sender, reply.target, reply.method), ('bmgeoip', 'test', 'lookup'))
                        self.assertEqual(reply.payload['status'], 'ok')
                        self.assertEqual(reply.payload['results'][0]['zip'], '00123')
                        self.assertEqual(reply.payload['results'][0]['city'], 'É, Example\nCity')
                        self.assertEqual(len(reply.payload['results'][0]), 14)
                    self.assertEqual(self.lookup(worker.endpoint, '127.0.0.1').payload['results'], [])
                    self.assertEqual(self.lookup(worker.endpoint, ' 2606:4700:0:0:0:0:0:8 ').payload['ip'], '2606:4700::8')
                    path = root / 'ipv4.csv'
                    path.write_bytes(csv_data(changes={'city': 'Refreshed'}))
                    records.load(4, path)
                    self.assertEqual(self.lookup(worker.endpoint, '8.8.8.8').payload['results'][0]['city'], 'Refreshed')
                    path.write_bytes(csv_data() + b'malformed,tail\n')
                    with self.assertRaises(ValueError):
                        records.load(4, path)
                    self.assertEqual(self.lookup(worker.endpoint, '8.8.8.8').payload['results'][0]['city'], 'Refreshed')
                finally:
                    db.close()
            self.assertFalse(worker._thread.is_alive())
            with ZMQServer(worker.endpoint, LookupHandler(GeoIpLookup(database))) as restarted:
                self.assertEqual(self.lookup(restarted.endpoint, '8.8.8.8').payload['status'], 'ok')

    def test_invalid_messages_do_not_open_database_or_break_listener(self):
        with patch('bmgeoip.interface.GeoIpLookup.DbMgr') as db:
            with ZMQServer('tcp://127.0.0.1:*', LookupHandler(GeoIpLookup())) as worker:
                frames = [[b'{'], [b'\xff'], [b'[]'], [b'{}'], [b'{}', b'{}']]
                messages = [ZMQMsg('test', 'unknown'), ZMQMsg('test', 'lookup', 'other')]
                for value in (None, 123, [], {}, '', 'hostname', '8.8.8.8/24', 'fe80::1%eth0'):
                    messages.append(ZMQMsg('test', 'lookup', payload={'ip': value}))
                messages.extend([ZMQMsg('test', 'lookup'),
                                 ZMQMsg('test', 'lookup', payload={'ip': '8.8.8.8', 'extra': True})])
                frames.extend([message.to_json()] for message in messages)
                for data in frames:
                    self.assertEqual(self.request(worker.endpoint, data).payload['error']['code'], 'invalid_request')
                db.assert_not_called()

    def test_bind_failure_and_internal_failure_surface(self):
        with ZMQServer('tcp://127.0.0.1:*', Mock()) as worker:
            with self.assertRaises(zmq.ZMQError):
                with ZMQServer(worker.endpoint, Mock()):
                    self.fail('Bind should fail.')
        handler = Mock(side_effect=RuntimeError('programming error'))
        with self.assertRaisesRegex(RuntimeError, 'programming error'):
            with ZMQServer('tcp://127.0.0.1:*', handler) as worker:
                with self.assertRaises(zmq.Again):
                    self.lookup(worker.endpoint, '8.8.8.8')
                with self.assertRaisesRegex(RuntimeError, 'programming error'):
                    worker.check()
        self.assertFalse(worker._thread.is_alive())

    def test_envelope_version_and_fields(self):
        data = ZMQMsg('test', 'lookup').to_dict()
        for version in (True, 2, '1'):
            with self.assertRaises(ValueError):
                ZMQMsg.from_dict({**data, 'protocol_version': version})
        for field, value in (('sender', ''), ('method', None), ('payload', []), ('target', 3)):
            with self.assertRaises((ValueError, TypeError)):
                ZMQMsg.from_dict({**data, field: value})
