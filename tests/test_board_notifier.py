"""Notifier-only intake, durable delivery and fixed-native identity regressions."""
import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from app_server_client import RequestRejected
from board_notifier import BoardNotifier
import test_board_claim_review as board_fixture


class Client:
    sent = []
    turns = []
    failure = None
    status = 'active'
    def __init__(self, *_): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def thread(self, identity, workspace, turns=False):
        if self.status == 'notLoaded': raise RuntimeError('unloaded')
        return {'id': identity, 'cwd': str(workspace), 'status': {'type': self.status}, 'turns': self.turns if turns else []}
    def request(self, method, params):
        assert method == 'thread/queue/add'
        self.sent.append(params)
        if self.failure: raise self.failure
        return {'queuedSubmission': {'id': 'Q'}}


class NotifierTests(unittest.TestCase):
    def setUp(self):
        base = board_fixture.BoardClaimReviewTests(); base.setUp()
        self.project = copy.deepcopy(base.project)
        self.project['items']['nodes'][0]['content'].update(number=10, url='https://github.com/u/r/issues/10')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = dict(base.config, workspace=str(self.root), source={'type': 'fixture'},
                           app_server_socket='socket', delegation={'enabled': True})
        self.config_path = self.root / 'config.json'; self.write_config()
        self.identity = str(uuid.UUID(int=1))
        folder = self.root / '.project-delegation/github-acpx/enrollments'; folder.mkdir(parents=True)
        self.registration = folder / (self.identity + '.json')
        self.receipt = {'provider_thread_id': self.identity, 'identity_source': 'runtime:CODEX_THREAD_ID',
                        'scope': dict(workspace=str(self.root), repository='u/r', project_node_id='P', user_login='u')}
        self.registration.write_text(json.dumps(self.receipt))
        Client.sent = []; Client.turns = []; Client.failure = None; Client.status = 'active'
    def write_config(self): self.config_path.write_text(json.dumps(self.config))
    def notifier(self): return BoardNotifier(self.config_path, client_factory=Client, fetcher=lambda _: copy.deepcopy(self.project))
    def initialize(self):
        obj = self.notifier(); self.addCleanup(obj.close); obj.initialize(self.registration, 'current'); return obj
    def edit(self, body='new task'): self.project['items']['nodes'][0]['content']['body'] = body
    def change_status(self, status): self.project['items']['nodes'][0]['fieldValues']['nodes'][0]['optionId'] = status
    def test_explicit_baseline_no_historical_replay(self):
        with self.notifier() as obj:
            with self.assertRaises(ValueError): obj.once()
            with self.assertRaises(ValueError): obj.initialize(self.registration, None)
            obj.initialize(self.registration, 'current'); obj.once()
            self.assertEqual(obj.state['outbox'], []); self.assertEqual(Client.sent, [])
            with self.assertRaises(ValueError): obj.initialize(self.registration, 'current')
    def test_change_queue_busy_fixed_thread_and_restart_dedup(self):
        obj = self.initialize(); self.edit(); obj.once(); obj.once()
        self.assertEqual(len(Client.sent), 1)
        self.assertEqual(Client.sent[0]['threadId'], self.identity)
        text = Client.sent[0]['input'][0]['text']
        self.assertIn('u/r#10', text); self.assertIn('tasks_list', text); self.assertNotIn('ONLY JSON', text)
        obj.close()
        with self.notifier() as second: second.once(); self.assertEqual(len(Client.sent), 1)
    def test_generation_survives_leave_and_return(self):
        obj = self.initialize(); self.edit(); obj.once()
        self.change_status('doing'); obj.once(); self.change_status('todo'); obj.once()
        self.assertEqual(len(Client.sent), 2)
        self.assertEqual([e['task']['ready_generation'] for e in obj.state['outbox']], [1, 2])
    def test_uncertain_not_resent_new_revisions_preserved(self):
        obj = self.initialize(); self.edit(); Client.failure = OSError('lost ack')
        with self.assertRaises(OSError): obj.once()
        self.assertEqual(obj.state['outbox'][0]['status'], 'submitting')
        Client.failure = None; self.edit('later revision'); obj.once()
        self.assertEqual(len(Client.sent), 2)
        self.assertEqual([e['status'] for e in obj.state['outbox']], ['submitting', 'queued'])
    def test_exact_text_reconciles_active_and_failed_delivery(self):
        for status in ['inProgress', 'failed', 'completed']:
            with self.subTest(status=status):
                obj = self.initialize(); self.edit(status); Client.failure = OSError('lost ack')
                with self.assertRaises(OSError): obj.once()
                entry = obj.state['outbox'][-1]; Client.failure = None
                Client.turns = [{'id': 'T', 'status': status, 'items': [
                    {'type': 'userMessage', 'content': [{'type': 'text', 'text': entry['text']}]},
                    {'type': 'agentMessage', 'phase': 'final_answer', 'text': 'done'}]}]
                obj.deliver(); self.assertEqual(entry['status'], 'delivered'); obj.close()
                obj.path.unlink()
    def test_unrelated_assistant_text_is_not_delivery(self):
        obj = self.initialize(); self.edit(); obj.once(); entry = obj.state['outbox'][0]
        entry['status'] = 'submitting'; obj.save()
        Client.turns = [{'status': 'completed', 'items': [{'type': 'agentMessage', 'text': entry['text']}]}]
        obj.deliver(); self.assertEqual(entry['status'], 'submitting'); self.assertEqual(len(Client.sent), 1)
    def test_definite_rejection_not_retried_or_blocking_next_version(self):
        obj = self.initialize(); self.edit(); Client.failure = RequestRejected('denied'); obj.once()
        self.assertEqual(obj.state['outbox'][0]['status'], 'rejected')
        Client.failure = None; obj.once(); self.assertEqual(len(Client.sent), 1)
        self.edit('version 3'); obj.once(); self.assertEqual(len(Client.sent), 2)
    def test_known_unsent_outage_recovers_once(self):
        obj = self.initialize(); self.edit(); Client.status = 'notLoaded'
        with self.assertRaises(RuntimeError): obj.once()
        self.assertEqual(obj.state['outbox'][0]['status'], 'prepared')
        Client.status = 'idle'; obj.once(); obj.once(); self.assertEqual(len(Client.sent), 1)
    def test_scope_mismatch_rejected_on_init_and_restart(self):
        self.receipt['scope']['user_login'] = 'other'; self.registration.write_text(json.dumps(self.receipt))
        with self.notifier() as obj:
            with self.assertRaises(ValueError): obj.initialize(self.registration, 'current')
        self.receipt['scope']['user_login'] = 'u'; self.registration.write_text(json.dumps(self.receipt))
        obj = self.initialize(); obj.close(); self.config['repository'] = 'other/repo'; self.write_config()
        with self.assertRaises(ValueError): self.notifier()
    def test_singleton_uses_legacy_controller_lock(self):
        obj = self.initialize()
        with self.assertRaises(BlockingIOError): self.notifier()
        self.assertEqual(Path(obj.lock.name), self.root / '.project-delegation/github-acpx/controller.lock')
    def test_cross_process_shared_service_lock_and_exclusive_legacy_lock(self):
        obj = self.initialize()
        probe = ('import fcntl,sys; f=open(sys.argv[1],"a"); '
                 'fcntl.flock(f, int(sys.argv[2]) | fcntl.LOCK_NB)')
        import fcntl
        shared = subprocess.run([sys.executable, '-c', probe, obj.lock.name, str(fcntl.LOCK_SH)], capture_output=True)
        exclusive = subprocess.run([sys.executable, '-c', probe, obj.lock.name, str(fcntl.LOCK_EX)], capture_output=True)
        singleton = subprocess.run([sys.executable, '-c', probe, obj.notifier_lock.name, str(fcntl.LOCK_EX)], capture_output=True)
        self.assertEqual(shared.returncode, 0)
        self.assertNotEqual(exclusive.returncode, 0)
        self.assertNotEqual(singleton.returncode, 0)
        lock_path = obj.lock.name; obj.close()
        released = subprocess.run([sys.executable, '-c', probe, lock_path, str(fcntl.LOCK_EX)], capture_output=True)
        self.assertEqual(released.returncode, 0)
    def test_invalid_snapshot_does_not_advance_observations(self):
        obj = self.initialize(); before = copy.deepcopy(obj.state)
        self.project['views']['nodes'][0]['filter'] = 'broadened'
        with self.assertRaises(ValueError): obj.once()
        self.assertEqual(obj.state, before)
    def test_enable_and_separate_state_required(self):
        self.config['delegation']['enabled'] = False; self.write_config()
        with self.assertRaises(ValueError): self.notifier()
        self.config['delegation']['enabled'] = True
        self.config['notifier_state_directory'] = str(self.root / '.project-delegation/github-acpx'); self.write_config()
        with self.assertRaises(ValueError): self.notifier()
    def test_legacy_state_is_never_migrated_or_changed(self):
        legacy = self.root / '.project-delegation/github-acpx/state.json'
        original = '{"binding":{"provider_thread_id":"old"},"queue":[{"status":"running"}]}'
        legacy.write_text(original)
        obj = self.initialize(); obj.once()
        self.assertEqual(legacy.read_text(), original)
        self.assertEqual(obj.state['outbox'], [])
    def test_rejected_and_uncertain_survive_process_restart(self):
        obj = self.initialize(); self.edit(); Client.failure = RequestRejected('denied'); obj.once()
        self.edit('second'); Client.failure = OSError('lost acknowledgement')
        with self.assertRaises(OSError): obj.once()
        obj.close(); Client.failure = None
        with self.notifier() as recovered:
            recovered.once()
            self.assertEqual([e['status'] for e in recovered.state['outbox']], ['rejected', 'submitting'])
            self.assertEqual(len(Client.sent), 2)
    def test_removal_and_readdition_preserve_new_generation(self):
        obj = self.initialize(); card = self.project['items']['nodes'].pop(); obj.once()
        self.project['items']['nodes'].append(card); obj.once()
        self.assertEqual(obj.state['outbox'][0]['task']['ready_generation'], 2)
    def test_only_user_input_changes_notify(self):
        obj = self.initialize(); comments = self.project['items']['nodes'][0]['content']['comments']['nodes']
        comments.append({'id': 'foreign', 'body': 'do something else', 'author': {'login': 'someone'}})
        obj.once(); self.assertEqual(Client.sent, [])
        comments.append({'id': 'owned', 'body': 'refine acceptance', 'author': {'login': 'u'}})
        obj.once(); self.assertEqual(len(Client.sent), 1)
    def test_own_workflow_comments_do_not_change_notifier_or_service_revision(self):
        from delegation_service import DelegationService
        from github_writeback import marker_prefix
        obj = self.initialize()
        original = obj.snapshot({})[0]['revision_hash']
        comments = self.project['items']['nodes'][0]['content']['comments']['nodes']
        for kind in ['claim', 'result']:
            comments.append({'id': kind, 'body': marker_prefix(self.config, 'I', kind) + 'a' * 64 + ' --> managed output',
                             'author': {'login': 'u'}})
        comments.append({'id': 'deleted-author', 'body': 'deleted user comment', 'author': None})
        service = DelegationService.__new__(DelegationService); service.config = self.config
        with patch('delegation_service.fetch', return_value=copy.deepcopy(self.project)):
            _, current, _ = service._source({'observations': {}})
        self.assertEqual(obj.snapshot({})[0]['revision_hash'], current[0]['revision_hash'])
        self.assertEqual(current[0]['revision_hash'], original)
        obj.once(); self.assertEqual(Client.sent, [])
        # A marker for another issue is not this issue's managed output.
        comments.append({'id': 'different-scope', 'body': marker_prefix(self.config, 'OTHER', 'claim') + 'b' * 64 + ' --> input',
                         'author': {'login': 'u'}})
        self.assertNotEqual(obj.snapshot({})[0]['revision_hash'], original)
        obj.once(); self.assertEqual(len(Client.sent), 1)
    def test_duplicate_exact_turns_fail_closed(self):
        obj = self.initialize(); self.edit(); obj.once(); entry = obj.state['outbox'][0]
        turn = {'items': [{'type': 'userMessage', 'content': [{'type': 'text', 'text': entry['text']}]}]}
        Client.turns = [turn, turn]
        with self.assertRaises(RuntimeError): obj.deliver()
        self.assertEqual(entry['status'], 'queued'); self.assertEqual(len(Client.sent), 1)


if __name__ == '__main__': unittest.main()
