import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import coordinator_bootstrap as bootstrap
from app_server_client import RequestRejected, TurnFailed
from project_acpx import Coordinator, CoordinationPending


class Client:
    calls = []
    def __init__(self, *_): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def thread(self, *args): return {'turns': []}
    def request(self, method, params):
        self.calls.append((method, params))
        return {'queuedSubmission': {'id': 'queue-id'}}


class LivenessTests(unittest.TestCase):
    def setUp(self): Client.calls = []

    def controller(self):
        obj = Coordinator.__new__(Coordinator)
        obj.workspace = Path('/tmp').resolve()
        obj.config = {'timeout': 0, 'source': {'type': 'fixture'}}
        obj.active = {}
        obj.state = {'binding': {'transport': 'app_server', 'provider_thread_id': 'thread', 'socket_path': 'socket'},
                     'queue': [{'status': 'waiting_coordinator'}]}
        obj.save = Mock()
        return obj

    def test_prepared_connection_failure_is_safely_submitted_after_recovery(self):
        obj = self.controller()
        with patch('app_server_client.AppServer', side_effect=ConnectionError('offline')):
            with self.assertRaises(CoordinationPending): obj.queue_coordinate('plan')
        self.assertEqual(obj.state['coordinator_request']['status'], 'prepared')
        original_id = obj.state['coordinator_request']['id']
        with patch('app_server_client.AppServer', Client):
            obj.recover_queued_coordination()
            obj.recover_queued_coordination()
        self.assertEqual(len(Client.calls), 1)
        self.assertEqual(Client.calls[0][1]['clientUserMessageId'], original_id)
        self.assertEqual(obj.state['coordinator_request']['status'], 'queued')

    def test_definite_rejection_releases_global_slot_and_caches_terminal_error(self):
        obj = self.controller()
        class Rejected(Client):
            def request(self, *args): raise RequestRejected('unsupported method')
        with patch('app_server_client.AppServer', Rejected):
            with self.assertRaises(TurnFailed): obj.queue_coordinate('plan')
        self.assertNotIn('coordinator_request', obj.state)
        with self.assertRaises(TurnFailed): obj.queue_coordinate('plan')
        obj.recover_queued_coordination()
        self.assertEqual(obj.state['queue'][0]['status'], 'pending')
        with patch('app_server_client.AppServer', Client):
            with self.assertRaises(CoordinationPending): obj.queue_coordinate('different plan')
        self.assertEqual(len(Client.calls), 1)

    def test_definite_rejection_during_prepared_recovery_releases_slot(self):
        obj = self.controller()
        with patch('app_server_client.AppServer', side_effect=ConnectionError('offline')):
            with self.assertRaises(CoordinationPending): obj.queue_coordinate('plan')
        class Rejected(Client):
            def request(self, *args): raise RequestRejected('unsupported method')
        with patch('app_server_client.AppServer', Rejected): obj.recover_queued_coordination()
        self.assertNotIn('coordinator_request', obj.state)
        self.assertEqual(obj.state['queue'][0]['status'], 'pending')
        with self.assertRaises(TurnFailed): obj.queue_coordinate('plan')

    def test_lost_ack_remains_uncertain_and_is_never_resent(self):
        obj = self.controller()
        class LostAck(Client):
            def request(self, method, params):
                self.calls.append((method, params))
                raise ConnectionError('lost ack')
        with patch('app_server_client.AppServer', LostAck):
            with self.assertRaises(CoordinationPending): obj.queue_coordinate('plan')
        with patch('app_server_client.AppServer', Client):
            for _ in range(3): obj.recover_queued_coordination()
        self.assertEqual(len(Client.calls), 1)
        self.assertEqual(obj.state['coordinator_request']['status'], 'submitting')
        self.assertIn('uncertain', obj.state['coordination_error'])

    def test_read_rejection_before_submission_stays_prepared(self):
        obj = self.controller()
        class ReadRejected(Client):
            def thread(self, *args): raise RequestRejected('read denied')
        with patch('app_server_client.AppServer', ReadRejected):
            with self.assertRaises(CoordinationPending): obj.queue_coordinate('plan')
        self.assertEqual(obj.state['coordinator_request']['status'], 'prepared')
        self.assertEqual(Client.calls, [])

    def test_admission_outage_backoff_then_recovers_without_claiming_early(self):
        obj = self.controller()
        obj.state['queue'][0]['status'] = 'pending'
        obj.verify = Mock(side_effect=[ConnectionError('offline'), None])
        with patch('project_acpx.time.monotonic', return_value=100):
            self.assertFalse(obj.admit(0))
            self.assertFalse(obj.admit(0))
        self.assertEqual(obj.verify.call_count, 1)
        self.assertEqual(obj.state['queue'][0]['status'], 'pending')
        self.assertEqual(obj.state['transport_error'], 'offline')
        with patch('project_acpx.time.monotonic', return_value=111):
            self.assertTrue(obj.admit(0))
        self.assertEqual(obj.state['queue'][0]['status'], 'running')
        self.assertIsNone(obj.state['transport_error'])

    def test_identity_mismatch_still_fails_closed(self):
        obj = self.controller()
        obj.verify = Mock(side_effect=ValueError('identity mismatch'))
        with self.assertRaises(ValueError): obj.verify_for_admission()

    def test_run_keeps_polling_after_startup_transport_outage(self):
        obj = self.controller()
        with tempfile.TemporaryDirectory() as tmp:
            obj.workspace = Path(tmp).resolve()
            obj.state['queue'][0]['status'] = 'pending'
            obj.stopped = threading.Event()
            obj.results = queue.Queue()
            obj.max_parallel = 3
            obj.verify = Mock(side_effect=ConnectionError('offline'))
            obj.apply_binding_request = Mock(return_value=False)
            obj.recover_queued_coordination = Mock()
            obj.release_waiting = Mock()
            obj.scan = Mock(side_effect=obj.stopped.set)
            with patch('project_acpx.signal.signal'): obj.run()
            obj.scan.assert_called_once()
            self.assertEqual(obj.state['queue'][0]['status'], 'pending')
            self.assertEqual(obj.state['transport_error'], 'offline')

    def test_same_native_binding_checks_owner_liveness_and_respects_inspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            folder = root / '.project-delegation/github-acpx'
            folder.mkdir(parents=True)
            tid = str(uuid.uuid4())
            scope = dict(workspace=str(root), repository='o/r', project_node_id='P', user_login='o')
            config = folder / 'config.json'
            config.write_text(json.dumps(dict(scope, auto_start_controller=True)))
            (folder / 'state.json').write_text(json.dumps(dict(identity=scope, binding=dict(transport='app_server', provider_thread_id=tid, socket_path='socket'))))
            with patch.object(bootstrap, 'git_context', return_value=(root, 'o/r')), \
                 patch('app_server_client.AppServer', Client), \
                 patch.object(bootstrap.subprocess, 'Popen') as start:
                result = bootstrap.bootstrap(root, root, {'CODEX_THREAD_ID': tid}, config, inspect=True)
                self.assertEqual(result['status'], 'blocked')
                start.assert_not_called()
                result = bootstrap.bootstrap(root, root, {'CODEX_THREAD_ID': tid}, config)
                self.assertEqual(result['status'], 'pending')
                self.assertFalse(result['owner_present'])
                start.assert_called_once()
                with patch.object(bootstrap, 'owner_present', return_value=True):
                    result = bootstrap.bootstrap(root, root, {'CODEX_THREAD_ID': tid}, config)
                self.assertEqual(result['status'], 'active')
                start.assert_called_once()


if __name__ == '__main__': unittest.main()
