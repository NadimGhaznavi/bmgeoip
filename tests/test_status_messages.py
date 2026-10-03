"""Verify retained history and simultaneous writes from separate processes."""

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bmgeoip.interface.StatusMessages import StatusMessages


def record_messages(path, worker):
    history = StatusMessages(path)
    for index in range(20):
        history.append(f'{worker}:{index}')


class StatusMessagesTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'history.json'
        self.history = StatusMessages(self.path)

    def test_retention_source_timestamp_and_independent_reader(self):
        self.assertEqual(self.history.snapshot(), [])
        with patch.object(StatusMessages, 'LIMIT', 3):
            for index in range(5):
                self.history.append(f'Message {index}\nnext line')
        entries = StatusMessages(self.path).snapshot()
        self.assertEqual([entry['message'] for entry in entries],
                         [f'Message {index} next line' for index in (2, 3, 4)])
        self.assertEqual(entries[0]['source'], __name__)
        self.assertIsNotNone(datetime.fromisoformat(entries[0]['timestamp']).tzinfo)

    def test_concurrent_process_writes_preserve_every_message(self):
        with ProcessPoolExecutor(max_workers=3) as workers:
            futures = [workers.submit(record_messages, self.path, worker) for worker in range(3)]
            for future in futures:
                future.result(timeout=10)
        entries = self.history.snapshot()
        self.assertEqual(len(entries), 60)
        self.assertEqual({entry['message'] for entry in entries},
                         {f'{worker}:{index}' for worker in range(3) for index in range(20)})

    def test_write_failure_logs_without_interrupting_caller(self):
        with patch.object(self.history, 'snapshot', side_effect=PermissionError('denied')):
            with self.assertLogs(level='ERROR') as logs:
                self.history.append('Dataset ready.')
        self.assertEqual(logs.records[0].getMessage(), 'Could not record status message')
