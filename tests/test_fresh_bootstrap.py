import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from coordinator_bootstrap import bootstrap


class FreshBootstrapTests(unittest.TestCase):
    def setUp(self):
        launcher = patch('coordinator_bootstrap.launch_dashboard', return_value={'dashboard_url': 'http://127.0.0.1:1234/', 'opened': False, 'server_started': False})
        self.launcher = launcher.start()
        self.addCleanup(launcher.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config.json'
        self.value = {'workspace': str(self.root), 'repository': 'test/repo',
                      'project_node_id': 'P_test', 'user_login': 'tester',
                      'app_server_socket': '/fixture/socket'}
        self.config.write_text(json.dumps(self.value))
        self.identity = str(uuid.uuid4())
        self.env = {'CODEX_THREAD_ID': self.identity}
        self.thread = {'id': self.identity, 'cwd': str(self.root), 'status': {'type': 'active'}}
        outer = self
        class Client:
            def __init__(self, socket): self.socket = socket
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def thread(self, identity, workspace): return outer.thread
        self.client = Client
        self.binding = self.root / '.project-delegation/runtime/binding.json'

    def run_bootstrap(self, **kwargs):
        return bootstrap(self.config, cwd=self.root, environment=self.env,
                         client_factory=self.client, **kwargs)

    def test_init_launches_dashboard_but_status_does_not(self):
        result = self.run_bootstrap()
        self.assertIn('dashboard_url', result)
        self.assertTrue(self.launcher.call_args.kwargs['auto_open'])
        self.launcher.reset_mock()
        self.run_bootstrap(inspect=True)
        self.launcher.assert_not_called()

    def test_no_open_and_config_disable_browser(self):
        self.run_bootstrap(open_dashboard=False)
        self.assertFalse(self.launcher.call_args.kwargs['auto_open'])
        self.value['dashboard'] = {'auto_open': False}
        self.config.write_text(json.dumps(self.value))
        self.run_bootstrap()
        self.assertFalse(self.launcher.call_args.kwargs['auto_open'])

    def test_dashboard_failure_does_not_block_binding(self):
        self.launcher.return_value = {'dashboard_url': None, 'opened': False,
                                      'server_started': False, 'dashboard_warning': 'fixture launch failure'}
        result = self.run_bootstrap()
        self.assertEqual(result['status'], 'initialized')
        self.assertTrue(self.binding.exists())
        self.assertIn('dashboard_warning', result)

    def test_init_and_idempotent_reuse(self):
        self.assertEqual(self.run_bootstrap()['status'], 'initialized')
        before = self.binding.read_bytes()
        self.assertEqual(self.run_bootstrap()['status'], 'reused')
        self.assertEqual(self.binding.read_bytes(), before)
        self.assertEqual(self.run_bootstrap(inspect=True)['status'], 'verified')

    def test_owner_mismatch_never_overwrites(self):
        self.run_bootstrap()
        before = self.binding.read_bytes()
        self.env['CODEX_THREAD_ID'] = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'): self.run_bootstrap()
        self.assertEqual(self.binding.read_bytes(), before)

    def test_scope_mismatch_never_overwrites(self):
        self.run_bootstrap()
        before = self.binding.read_bytes()
        self.value['repository'] = 'different/repo'
        self.config.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'): self.run_bootstrap()
        self.assertEqual(self.binding.read_bytes(), before)

    def test_native_identity_and_cwd_must_match(self):
        for key, value in [('id', str(uuid.uuid4())), ('cwd', '/tmp'), ('status', {'type': 'notLoaded'})]:
            original = self.thread[key]
            self.thread[key] = value
            with self.assertRaisesRegex(ValueError, 'Native thread'): self.run_bootstrap()
            self.assertFalse(self.binding.exists())
            self.thread[key] = original

    def test_missing_runtime_identity_refused(self):
        self.env.clear()
        with self.assertRaisesRegex(ValueError, 'CODEX_THREAD_ID'): self.run_bootstrap()
        self.assertFalse(self.binding.exists())

    def test_existing_context_is_preserved(self):
        previous = self.root / '.project-delegation/github-acpx/state.json'
        previous.parent.mkdir(parents=True)
        previous.write_text('user existing state')
        self.run_bootstrap()
        self.assertEqual(previous.read_text(), 'user existing state')

    def test_unbound_existing_runtime_refused(self):
        self.binding.parent.mkdir(parents=True)
        jobs = self.binding.parent / 'jobs.json'
        jobs.write_text('{"active":true}')
        with self.assertRaisesRegex(ValueError, 'existing data'): self.run_bootstrap()
        self.assertEqual(jobs.read_text(), '{"active":true}')

    def test_state_cannot_reuse_other_directory(self):
        self.value['state_directory'] = str(self.root / '.project-delegation/github-acpx')
        self.config.write_text(json.dumps(self.value))
        with self.assertRaisesRegex(ValueError, 'Fresh state'): self.run_bootstrap()

    def test_binding_initializes_notifier_and_authorizes_service(self):
        from test_board_claim_review import BoardClaimReviewTests
        from board_notifier import BoardNotifier
        from delegation_service import DelegationService
        fixture = BoardClaimReviewTests()
        fixture.setUp()
        self.value.update(fixture.config)
        self.value.update(source={'type': 'fixture'}, executor={
            'enabled': True, 'isolate_worktree': True})
        self.config.write_text(json.dumps(self.value))
        self.run_bootstrap()
        with BoardNotifier(self.config, client_factory=self.client,
                           fetcher=lambda _: fixture.project) as notifier:
            notifier.initialize('current')
            self.assertEqual(notifier.state['outbox'], [])
        with patch.dict('os.environ', self.env):
            service = DelegationService(self.config)
            try:
                service._authorize()
                self.assertEqual(service.owner, self.identity)
            finally:
                service.close()

    def test_stop_does_not_need_loaded_coordinator(self):
        self.run_bootstrap()
        with patch('coordinator_bootstrap.stop_dashboard', return_value={'status': 'stopped'}) as stop:
            self.client = lambda *_: (_ for _ in ()).throw(AssertionError('No native connection for stop'))
            self.assertEqual(self.run_bootstrap(stop=True)['status'], 'stopped')
            stop.assert_called_once()

    def test_status_reports_unavailable_coordinator_without_starting(self):
        self.run_bootstrap()
        self.launcher.reset_mock()
        self.thread['status'] = {'type': 'notLoaded'}
        result = self.run_bootstrap(inspect=True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(result['coordinator_available'])
        self.assertIn('notifications', result)
        self.launcher.assert_not_called()

    def test_status_handles_unavailable_endpoint_without_starting(self):
        self.run_bootstrap()
        self.value.pop('app_server_socket')
        self.value['codex'] = '/fixture/codex'
        self.config.write_text(json.dumps(self.value))
        self.launcher.reset_mock()
        with patch('coordinator_bootstrap.endpoint', side_effect=RuntimeError('No shared daemon')):
            result = self.run_bootstrap(inspect=True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('No shared daemon', result['reason'])
        self.launcher.assert_not_called()

    def test_status_handles_endpoint_timeout(self):
        import subprocess
        self.run_bootstrap()
        self.value.pop('app_server_socket')
        self.value['codex'] = '/fixture/codex'
        self.config.write_text(json.dumps(self.value))
        with patch('coordinator_bootstrap.endpoint', side_effect=subprocess.TimeoutExpired('codex', 15)):
            self.assertEqual(self.run_bootstrap(inspect=True)['status'], 'unavailable')

    def test_status_before_init_has_no_side_effects(self):
        self.assertEqual(self.run_bootstrap(inspect=True)['status'], 'uninitialized')
        self.assertFalse(self.binding.parent.exists())


if __name__ == '__main__': unittest.main()
