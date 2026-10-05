"""Read-only watcher health; PID existence alone is not successful polling."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from notifier_status import SERVICE, evaluate_status, service_status


class NotificationStatusTests(unittest.TestCase):
    def setUp(self):
        self.scope = {'workspace': '/fixture', 'repository': 'u/r', 'project_node_id': 'P', 'user_login': 'u'}
        self.now = time.time()
        self.state = {'service': SERVICE, 'scope': self.scope, 'owner': 'T', 'config_signature': 'C',
                      'pid': os.getpid(), 'interval': 10, 'status': 'running', 'initialized': True,
                      'coordinator_available': True, 'heartbeat_at': self.now, 'last_success_at': self.now}

    def status(self):
        return evaluate_status(self.state, self.scope, 'T', 'C', now=self.now)

    def test_fresh_success_is_healthy(self):
        self.assertTrue(self.status()['healthy'])

    def test_pid_alone_never_proves_health(self):
        self.state.pop('last_success_at')
        self.assertFalse(self.status()['healthy'])
        self.state['last_success_at'] = self.now - 100
        self.assertFalse(self.status()['healthy'])

    def test_stale_heartbeat_erases_availability(self):
        self.state['heartbeat_at'] = self.now - 100
        self.assertEqual(self.status()['status'], 'stale')
        self.assertIsNone(self.status()['coordinator_available'])

    def test_dead_process_erases_availability(self):
        with patch('notifier_status.process_alive', return_value=False):
            self.assertEqual(self.status()['status'], 'stopped')
            self.assertFalse(self.status()['running'])
            self.assertIsNone(self.status()['coordinator_available'])

    def test_mismatch_fails_closed(self):
        self.state['owner'] = 'other'
        self.assertEqual(self.status()['status'], 'blocked')
        self.assertFalse(self.status()['healthy'])
        self.assertFalse(self.status()['running'])

    def test_failed_watcher_inside_live_http_process_is_not_running(self):
        self.state['status'] = 'blocked'
        self.assertFalse(self.status()['running'])
        self.assertFalse(self.status()['healthy'])

    def test_read_status_never_creates_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'missing'
            self.assertEqual(service_status(path, self.scope, 'T', 'C')['status'], 'not_running')
            self.assertFalse(path.exists())

    def test_corrupt_status_fails_closed_readonly(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'notifier-service.json'
            path.write_text('{broken')
            before = path.read_bytes()
            self.assertEqual(service_status(path.parent, self.scope, 'T', 'C')['status'], 'blocked')
            self.assertEqual(path.read_bytes(), before)
