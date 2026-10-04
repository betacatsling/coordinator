import copy
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import adopt_coordinator as adopt


class FirstOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / '.project-delegation/github-acpx'
        self.enroll = self.folder / 'enrollments'
        self.enroll.mkdir(parents=True)
        self.config_path = self.root / 'config.json'
        self.config = dict(workspace=str(self.root), project_node_id='P1', repository='owner/repo',
                           user_login='owner', node='/explicit/node', adapter='/explicit/adapter',
                           acpx='/explicit/acpx', codex='/explicit/codex', source={'type': 'github'})
        self.config_path.write_text(json.dumps(self.config))
        self.provider = str(uuid.UUID(int=1))
        self.ledger = self.enroll / 'verified/provider.json'
        self.ledger.parent.mkdir()
        self.ledger.write_text(json.dumps({'creation': 'bound', 'provider_thread_id': self.provider}))
        self.name = 'project-' + hashlib.sha256(b'P1').hexdigest()[:20]
        agent = shlex.join([sys.executable, str(Path(adopt.__file__).with_name('acp_identity_guard.py').resolve()),
                            '--ledger', str(self.ledger), '--node', self.config['node'], '--adapter', self.config['adapter']])
        self.receipt = dict(scope={key: self.config[key] for key in ('workspace', 'project_node_id', 'repository', 'user_login')},
                            identity_source='runtime:CODEX_THREAD_ID', provider_thread_id=self.provider,
                            verification=dict(provider_thread_id=self.provider, acpx_session_id=self.provider,
                                acpx_record_id='record', session_name=self.name, provider_ledger=str(self.ledger),
                                agent_command=agent, verified_at=time.time(),
                                turns=[dict(provider_thread_id=self.provider, stop_reason='end_turn', nonce_matches=True)] * 2))
        self.registration = self.enroll / (self.provider + '.json')
        self.registration.write_text(json.dumps(self.receipt))
        self.meta = {'acpxRecordId': 'record', 'acpSessionId': self.provider, 'closed': False}
        self.task = {'issue_id': 'I1', 'revision_hash': 'version1'}

    def tearDown(self):
        self.temp.cleanup()

    def activate(self):
        with patch.object(adopt, 'command', return_value=[self.meta]) as cmd, \
                patch('project_acpx.fetch', return_value={'id': 'P1'}) as fetch, \
                patch('github_project_inputs.normalize_project', return_value=[self.task]):
            result = adopt.commit(self.config_path, self.registration, first_owner=True)
            self.assertEqual(cmd.call_args.args[2], ['sessions', 'show', self.name])
            self.assertEqual(fetch.call_count, 1)
            return result

    def test_no_state_first_owner_baselines_without_prompt_or_native_new(self):
        result = self.activate()
        state = json.loads((self.folder / 'state.json').read_text())
        self.assertEqual(state['binding']['provider_thread_id'], self.provider)
        self.assertEqual(state['queue'][0]['status'], 'baseline')
        self.assertEqual(state['initialization'], 'completed')
        self.assertFalse(result['controller_started'])
        for path in (self.config_path, self.folder / 'state.json', self.registration):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_existing_queue_and_old_files_preserved(self):
        pending = {'task': {'issue_id': 'I2', 'revision_hash': 'v2'}, 'status': 'pending'}
        (self.folder / 'state.json').write_text(json.dumps({'queue': [pending], 'result_comment_ids': ['C1']}))
        old_ledger = self.folder / 'provider-old.json'
        old_ledger.write_text('keep exactly')
        self.activate()
        state = json.loads((self.folder / 'state.json').read_text())
        self.assertEqual(state['queue'][0], pending)
        self.assertEqual(state['result_comment_ids'], ['C1'])
        self.assertEqual(old_ledger.read_text(), 'keep exactly')

    def test_first_owner_cannot_replace_existing_or_running(self):
        for state in ({'binding': {'provider_thread_id': 'old'}},
                      {'queue': [{'status': 'running'}]}):
            (self.folder / 'state.json').write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                self.activate()

    def test_lock_excludes_second_owner(self):
        with open(self.folder / 'controller.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.activate()

    def test_stale_future_wrong_guard_and_wrong_meta_fail_before_writes(self):
        for key, value in [('verified_at', time.time() - 901), ('verified_at', time.time() + 60),
                           ('agent_command', '/untrusted/command'), ('provider_thread_id', 'other')]:
            altered = copy.deepcopy(self.receipt)
            altered['verification'][key] = value
            self.registration.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                self.activate()
            self.assertFalse((self.folder / 'state.json').exists())
        self.registration.write_text(json.dumps(self.receipt))
        self.meta['acpSessionId'] = 'wrong'
        with self.assertRaises(RuntimeError):
            self.activate()

    def test_ordinary_handoff_still_requires_expected_owner(self):
        with self.assertRaises(ValueError):
            adopt.commit(self.config_path, self.registration)
        with self.assertRaises(ValueError):
            adopt.commit(self.config_path, self.registration, expected_old='old', first_owner=True)

    def test_ordinary_handoff_preserves_baseline_without_refetch(self):
        queue = [{'task': self.task, 'status': 'baseline'}]
        state = {'identity': dict(self.receipt['scope'], agent_command='previous-guard'),
                 'binding': {'provider_thread_id': 'old'}, 'queue': queue, 'baseline_at': 123}
        (self.folder / 'state.json').write_text(json.dumps(state))
        with patch.object(adopt, 'command', return_value=[self.meta]), \
                patch('project_acpx.fetch') as fetch:
            adopt.commit(self.config_path, self.registration, expected_old='old')
            fetch.assert_not_called()
        updated = json.loads((self.folder / 'state.json').read_text())
        self.assertEqual(updated['queue'], queue)
        self.assertEqual(updated['baseline_at'], 123)

    def test_first_owner_read_failure_has_no_binding_writes(self):
        original = self.config_path.read_text()
        with patch.object(adopt, 'command', return_value=[self.meta]), \
                patch('project_acpx.fetch', side_effect=RuntimeError('API unavailable')):
            with self.assertRaises(RuntimeError):
                adopt.commit(self.config_path, self.registration, first_owner=True)
        self.assertFalse((self.folder / 'state.json').exists())
        self.assertEqual(self.config_path.read_text(), original)


if __name__ == '__main__':
    unittest.main()
