import fcntl
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import coordinator_bootstrap as entry


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.root = self.base / 'project'
        self.home.mkdir()
        self.root.mkdir()
        self.folder = self.root / '.project-delegation/github-acpx'
        self.config = self.folder / 'config.json'
        self.scope = dict(workspace=str(self.root), repository='owner/repo', project_node_id='P1', user_login='owner')
        self.write(self.config, self.scope)
        self.thread = str(uuid.UUID(int=1))
        self.env = {'CODEX_THREAD_ID': self.thread}
        self.git = patch.object(entry, 'git_context', return_value=(self.root, 'owner/repo'))
        self.git.start()

    def tearDown(self):
        self.git.stop()
        self.temp.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def run_entry(self, **kwargs):
        return entry.bootstrap(cwd=self.root, home=self.home, environment=self.env, **kwargs)

    def test_local_binding_from_subdirectory(self):
        child = self.root / 'src'
        child.mkdir()
        result = entry.resolve_config(child, self.home)
        self.assertEqual(result['scope'], self.scope)
        self.assertEqual(result['config_path'], str(self.config))

    def test_personal_registry_binding(self):
        self.config.unlink()
        registry = self.home / '.local/share/project-delegation/projects/example/config.json'
        self.write(registry, self.scope)
        self.assertEqual(entry.resolve_config(self.root, self.home)['config_path'], str(registry))

    def test_ambiguous_binding_asks_only_selection(self):
        other = self.home / '.local/share/project-delegation/projects/other/config.json'
        self.write(other, dict(self.scope, project_node_id='P2'))
        result = self.run_entry()
        self.assertEqual(result['status'], 'needs_selection')
        self.assertEqual(len(result['choices']), 2)
        self.assertFalse((self.folder / 'enrollments').exists())

    def test_missing_binding_and_mandatory_fields(self):
        self.write(self.config, dict(workspace=str(self.root), repository='owner/repo'))
        result = self.run_entry()
        self.assertEqual(result['status'], 'needs_configuration')
        self.assertEqual(result['repository'], 'owner/repo')
        self.assertIn('project_node_id', result['missing'][0]['missing'])

    def test_repository_mismatch_and_relative_workspace_refused(self):
        self.write(self.config, dict(self.scope, repository='other/repo'))
        self.assertEqual(self.run_entry()['status'], 'blocked')
        self.write(self.config, dict(self.scope, workspace='.'))
        self.assertEqual(self.run_entry()['status'], 'needs_configuration')

    def test_nested_git_root_cannot_claim_outer_profile(self):
        nested = self.root / 'executor'
        nested.mkdir()
        with patch.object(entry, 'git_context', return_value=(nested, 'owner/repo')):
            result = entry.resolve_config(nested, self.home)
        self.assertEqual(result['status'], 'needs_configuration')

    def test_runtime_identity_missing_does_not_write(self):
        self.env.clear()
        self.assertEqual(self.run_entry()['status'], 'blocked')
        self.assertFalse((self.folder / 'enrollments').exists())

    def test_inspect_is_read_only(self):
        result = self.run_entry(inspect=True)
        self.assertEqual(result['status'], 'registration_needed')
        self.assertTrue(result['first_owner'])
        self.assertFalse((self.folder / 'enrollments').exists())

    def test_registration_pending_reuses_exact_receipt_without_activation(self):
        result = self.run_entry()
        receipt = Path(result['registration'])
        before = receipt.read_bytes()
        again = self.run_entry()
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(again['action'], 'continue_existing_handoff_after_current_turn')
        self.assertEqual(result['registration'], again['registration'])
        self.assertEqual(before, receipt.read_bytes())
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertFalse(result['activation_performed'])
        self.assertFalse((self.folder / 'state.json').exists())

    def test_active_owner_reused_without_enrollment_or_service_action(self):
        self.write(self.folder / 'state.json', dict(identity=self.scope, binding={'provider_thread_id': self.thread}))
        self.write(self.folder / 'provider.json', {'provider_thread_id': self.thread})
        with patch.object(entry, 'enroll', side_effect=AssertionError('must not enroll')):
            result = self.run_entry()
        self.assertEqual(result['status'], 'active')
        self.assertEqual(result['action'], 'reuse_existing_owner')
        self.assertFalse((self.folder / 'enrollments').exists())

    def test_other_owner_preserved_and_lock_reported(self):
        old = dict(identity=self.scope, binding={'provider_thread_id': 'existing-owner'}, queue=[{'status': 'running'}])
        self.write(self.folder / 'state.json', old)
        with open(self.folder / 'controller.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_entry()
        self.assertEqual(result['status'], 'pending')
        self.assertTrue(result['owner_present'])
        self.assertFalse(result['first_owner'])
        self.assertEqual(json.loads((self.folder / 'state.json').read_text()), old)

    def test_state_and_ledger_scope_fail_closed(self):
        self.write(self.config, dict(self.scope, state_directory=str(self.base / 'outside')))
        self.assertEqual(self.run_entry()['status'], 'blocked')
        self.write(self.config, self.scope)
        self.write(self.folder / 'state.json', dict(identity=dict(self.scope, project_node_id='P2')))
        self.assertEqual(self.run_entry()['status'], 'blocked')
        self.write(self.folder / 'state.json', dict(identity=self.scope, binding={'provider_thread_id': self.thread}))
        self.write(self.folder / 'provider.json', {'provider_thread_id': 'different'})
        self.assertEqual(self.run_entry()['status'], 'blocked')

    def test_corrupt_state_and_receipt_never_replaced(self):
        self.write(self.folder / 'state.json', ['not an object'])
        self.assertEqual(self.run_entry()['status'], 'blocked')
        self.write(self.folder / 'state.json', {'binding': {'provider_thread_id': self.thread}})
        self.assertEqual(self.run_entry()['status'], 'blocked')
        (self.folder / 'state.json').unlink()
        receipt = self.folder / 'enrollments' / (self.thread + '.json')
        self.write(receipt, {'scope': dict(self.scope, repository='other/repo')})
        before = receipt.read_bytes()
        self.assertEqual(self.run_entry()['status'], 'blocked')
        self.assertEqual(receipt.read_bytes(), before)
        self.write(receipt, {'scope': self.scope, 'provider_thread_id': self.thread,
                            'identity_source': 'runtime:CODEX_THREAD_ID', 'status': 'adopted'})
        self.assertEqual(self.run_entry()['status'], 'blocked')

    def test_enrollment_permission_failure_is_structured_blocker(self):
        with patch.object(entry, 'enroll', side_effect=PermissionError()):
            self.assertEqual(self.run_entry()['status'], 'blocked')

    def test_natural_trigger_and_rules_live_in_skill(self):
        skill = Path(__file__).resolve().parents[1]
        text = (skill / 'SKILL.md').read_text()
        description = text.split('---', 2)[1]
        self.assertIn('你作为这个项目的 coordinator', description)
        for rule in ('default three', 'claim', 'HTML', 'dependencies', 'CODEX_THREAD_ID'):
            self.assertIn(rule, text)
        procedure = (skill / 'references/manual-coordinator.md').read_text()
        self.assertIn('needs_selection', procedure)
        self.assertIn('needs_configuration', procedure)


if __name__ == '__main__':
    unittest.main()
