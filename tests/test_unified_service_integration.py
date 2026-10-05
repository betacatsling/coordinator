"""Offline integration of the unified watcher's two fixed-owner event channels.

Real locks, durable files, bootstrap binding, board normalization, worker state
transitions, and queue reconciliation are exercised. Native/GitHub transports,
worktree creation, and process startup are fixtures; no live services are used.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from app_server_client import RequestRejected
from board_notifier import BoardNotifier
from coordinator_bootstrap import bootstrap
from delegation_service import DelegationService
from executor_notifications import deliver_executor_notifications
import test_board_claim_review as board_fixture


class CycleGate:
    """A stop-event fixture that advances one complete watcher cycle at a time."""
    def __init__(self):
        self.condition = threading.Condition()
        self.stopped = False
        self.finished = False
        self.cycles = 0
        self.permits = 0

    def is_set(self):
        with self.condition:
            return self.stopped

    def wait(self, _interval):
        with self.condition:
            self.cycles += 1
            self.condition.notify_all()
            self.condition.wait_for(lambda: self.stopped or self.permits >= self.cycles)
            return self.stopped

    def advance(self):
        with self.condition:
            self.permits += 1
            self.condition.notify_all()

    def set(self):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()

    def finish(self):
        with self.condition:
            self.finished = True
            self.condition.notify_all()

    def reached(self, count):
        with self.condition:
            return self.condition.wait_for(lambda: self.cycles >= count or self.finished, timeout=5)


class UnifiedServiceIntegrationTests(unittest.TestCase):
    def setUp(self):
        fixture = board_fixture.BoardClaimReviewTests()
        fixture.setUp()
        self.project = copy.deepcopy(fixture.project)
        self.project['items']['nodes'][0]['content'].update(
            number=10, title='Bounded fixture task', url='https://github.com/u/r/issues/10')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / 'config.json'
        self.identity = str(uuid.UUID(int=1))
        self.config = dict(fixture.config, workspace=str(self.root),
                           source={'type': 'fixture'}, app_server_socket='fixture-socket',
                           codex='fixture-codex', node='fixture-node',
                           executor={'enabled': True, 'isolate_worktree': True})
        self.write_config()
        self.sent, self.history, self.thread_reads = [], [], []
        self.client_failure = None
        self.queue_failure = None
        self.board_failure = None
        self.queue_receipt = True
        self.watcher = None
        self.gate = None
        self.worker = None
        self.worker_errors = []
        outer = self

        class NativeClient:
            def __init__(self, *_):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def thread(self, identity, workspace, turns=False):
                outer.assertEqual(identity, outer.identity)
                outer.assertEqual(Path(workspace), outer.root)
                outer.thread_reads.append((identity, turns))
                if outer.client_failure:
                    raise outer.client_failure
                return {'id': identity, 'cwd': str(workspace),
                        'status': {'type': 'active'},
                        'turns': copy.deepcopy(outer.history) if turns else []}

            def request(self, method, params):
                outer.assertEqual(method, 'thread/queue/add')
                outer.assertEqual(params['threadId'], outer.identity)
                outer.sent.append(copy.deepcopy(params))
                if outer.queue_failure:
                    raise outer.queue_failure
                return {'queuedSubmission': {'id': 'queue-' + str(len(outer.sent))}} if outer.queue_receipt else {}

        self.client = NativeClient
        self.dashboard_patch = patch('coordinator_bootstrap.launch_dashboard', return_value={
            'dashboard_url': 'http://127.0.0.1:18766/', 'opened': False,
            'server_started': True, 'notifications': {'status': 'starting'}})
        self.dashboard = self.dashboard_patch.start()
        self.addCleanup(self.dashboard_patch.stop)
        self.bootstrap_result = self.bind()
        self.folder = self.root / '.project-delegation/runtime'
        self.addCleanup(self.stop)

    def write_config(self):
        self.path.write_text(json.dumps(self.config), encoding='utf-8')

    def bind(self, **kwargs):
        return bootstrap(self.path, cwd=self.root, environment={'CODEX_THREAD_ID': self.identity},
                         client_factory=self.client, open_dashboard=False, **kwargs)

    def fetch(self, _):
        if self.board_failure:
            raise self.board_failure
        return copy.deepcopy(self.project)

    def start(self):
        self.worker_errors = []
        self.watcher = BoardNotifier(self.path, client_factory=self.client, fetcher=self.fetch)
        self.gate = CycleGate()
        outer = self

        def run():
            try:
                outer.watcher.watch(interval=10, initialize_current=True,
                                    instance='fixture-service', stop_event=outer.gate)
            except Exception as exc:
                outer.worker_errors.append(exc)
            finally:
                outer.gate.finish()

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self.assertTrue(self.gate.reached(1), 'watcher did not finish first cycle')
        self.assertEqual(self.worker_errors, [])
        return self.watcher

    def cycle(self):
        count = self.gate.cycles + 1
        self.gate.advance()
        self.assertTrue(self.gate.reached(count), 'watcher cycle did not finish')
        return self.read('notifier-service.json')

    def stop(self):
        if self.gate:
            self.gate.set()
        if self.worker:
            self.worker.join(timeout=5)
            self.assertFalse(self.worker.is_alive(), 'watcher did not stop')
            self.worker = None
        if self.watcher:
            self.watcher.close()
            self.watcher = None

    def read(self, name):
        return json.loads((self.folder / name).read_text(encoding='utf-8'))

    def edit(self, text='A new authorized revision'):
        self.project['items']['nodes'][0]['content']['body'] = text

    def seed_job(self, status='verified', *, receipt=True, receipt_status=None, attempt='attempt-1'):
        task = self.watcher.snapshot({})[0]
        job = dict(id='integration-job', task=task, status=status,
                   coordinator_thread_id=self.identity, attempt_id=attempt,
                   worker_pid=None, config_hash=hashlib.sha256(self.path.read_bytes()).hexdigest(),
                   receipt=str(self.folder / 'integration-job.receipt.json'),
                   executor_config=dict(cwd=str(self.root / 'worktree'), base_head='fixture-base',
                                        owned_paths=['result.txt'], bridge_state_root=str(self.root / 'bridge')))
        state = {'scope': self.watcher.scope, 'observations': {}, 'jobs': {job['id']: job}}
        (self.folder / 'jobs.json').write_text(json.dumps(state), encoding='utf-8')
        if receipt:
            evidence = dict(attempt_id=attempt, task_identity={
                key: task[key] for key in ('issue_id', 'revision_hash', 'dispatch_key')},
                workspace=job['executor_config']['cwd'], base_head='fixture-base',
                owned_paths=['result.txt'], bridge_state_root=str(self.root / 'bridge'),
                status=receipt_status or status, thread_id=str(uuid.UUID(int=2)), job_id='native-job')
            Path(job['receipt']).write_text(json.dumps(evidence), encoding='utf-8')
        return job

    def history_for(self, text, status='completed'):
        return {'id': 'turn-' + str(len(self.history)), 'status': status, 'items': [
            {'type': 'userMessage', 'content': [{'type': 'text', 'text': text}]},
            {'type': 'agentMessage', 'phase': 'final_answer', 'text': 'Review is still an explicit coordinator decision'}]}

    def test_bootstrap_baseline_new_board_event_worker_completion_same_owner_review(self):
        self.assertEqual(self.bootstrap_result['status'], 'initialized')
        self.dashboard.assert_called_once()
        self.assertFalse(self.dashboard.call_args.kwargs['auto_open'])
        self.start()
        self.assertEqual(self.watcher.state['baseline']['count'], 1)
        self.assertEqual(self.sent, [])
        self.edit()
        self.assertEqual(self.cycle()['status'], 'running')
        self.assertEqual(len(self.sent), 1)
        self.assertIn('tasks_list', self.sent[0]['input'][0]['text'])
        service = DelegationService(self.path, caller_thread_id=self.identity)
        self.addCleanup(service.close)
        with patch('delegation_service.fetch', side_effect=self.fetch), \
             patch('delegation_service.create', return_value=(self.root / 'worktree', 'fixture-base')), \
             patch.object(service, '_launch'):
            task = service.tasks_list()['tasks'][0]
            started = service.executor_start(task['issue_id'], task['revision_hash'],
                                             'Write the bounded result', ['result.txt'])

        def execute(_brief, config, receipt_path, _node, on_session):
            on_session({'thread_id': str(uuid.UUID(int=2))})
            result = dict(status='verified', attempt_id=config['attempt_id'],
                          task_identity=config['task_identity'], workspace=config['cwd'],
                          base_head=config['base_head'], owned_paths=config['owned_paths'],
                          bridge_state_root=config.get('bridge_state_root'),
                          thread_id=str(uuid.UUID(int=2)), job_id='native-job',
                          checks=[{'returncode': 0}], artifacts=[])
            Path(receipt_path).write_text(json.dumps(result), encoding='utf-8')
            return result

        with patch('delegation_service.fetch', side_effect=self.fetch), \
             patch('delegation_service.execute_assignment', side_effect=execute), \
             patch('delegation_service.deliver_executor_notifications', side_effect=lambda path:
                   deliver_executor_notifications(path, client_factory=self.client)):
            service.run_worker(started['id'], started['attempt_id'])
        self.assertEqual(len(self.sent), 2)
        self.assertEqual({message['threadId'] for message in self.sent}, {self.identity})
        notice = self.sent[1]['input'][0]['text']
        self.assertIn('executor_result', notice)
        self.assertIn('task_finish', notice)
        self.assertIn(started['id'], notice)
        self.assertEqual(service.executor_status(started['id'])['status'], 'verified')
        self.assertNotIn('decision', self.read('jobs.json')['jobs'][started['id']])
        for message in self.sent:
            self.history.append(self.history_for(message['input'][0]['text']))
        self.cycle()
        self.assertEqual(self.watcher.state['outbox'][0]['status'], 'delivered')
        self.assertEqual(next(iter(self.read('jobs.json')['notifications'].values()))['status'], 'delivered')
        self.cycle()
        self.assertEqual(len(self.sent), 2)

    def test_stop_repeated_initialization_and_restart_preserve_baseline_and_dedup(self):
        self.start()
        self.edit()
        self.cycle()
        original_baseline = copy.deepcopy(self.watcher.state['baseline'])
        with self.assertRaises(BlockingIOError):
            BoardNotifier(self.path, client_factory=self.client, fetcher=self.fetch)
        before = (self.folder / 'binding.json').read_bytes()
        self.assertEqual(self.bind()['status'], 'reused')
        self.assertEqual((self.folder / 'binding.json').read_bytes(), before)
        self.stop()
        self.assertEqual(self.read('notifier-service.json')['status'], 'stopped')
        self.start()
        self.assertEqual(self.watcher.state['baseline'], original_baseline)
        self.assertEqual(len(self.sent), 1)
        self.edit('Another revision after restart')
        self.cycle()
        self.assertEqual(len(self.sent), 2)

    def test_board_outage_still_delivers_completion_and_recovers_without_rebaseline(self):
        self.start()
        baseline = copy.deepcopy(self.watcher.state['baseline'])
        self.seed_job()
        self.board_failure = OSError('fixture GitHub outage')
        state = self.cycle()
        self.assertEqual(state['status'], 'degraded')
        self.assertIn('Board observation', state['last_error'])
        self.assertEqual(len(self.sent), 1)
        self.assertIn('Executor event', self.sent[0]['input'][0]['text'])
        self.board_failure = None
        state = self.cycle()
        self.assertEqual(state['status'], 'running')
        self.assertIsNone(state['last_error'])
        self.assertEqual(self.watcher.state['baseline'], baseline)
        self.assertEqual(len(self.sent), 1)

    def test_unavailable_coordinator_preserves_both_prepared_events_until_recovery(self):
        self.start()
        self.edit()
        self.seed_job()
        self.client_failure = RuntimeError('fixture coordinator not loaded')
        state = self.cycle()
        self.assertEqual(state['status'], 'degraded')
        self.assertFalse(state['coordinator_available'])
        self.assertEqual(self.sent, [])
        self.assertEqual(self.watcher.state['outbox'][0]['status'], 'prepared')
        self.assertEqual(next(iter(self.read('jobs.json')['notifications'].values()))['status'], 'prepared')
        self.client_failure = None
        self.assertEqual(self.cycle()['status'], 'running')
        self.assertEqual(len(self.sent), 2)
        self.cycle()
        self.assertEqual(len(self.sent), 2)

    def test_lost_queue_ack_survives_restart_and_reconciles_both_channels(self):
        self.start()
        self.edit()
        self.seed_job()
        self.queue_failure = OSError('fixture lost queue acknowledgement')
        self.assertEqual(self.cycle()['status'], 'degraded')
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.watcher.state['outbox'][0]['status'], 'submitting')
        self.assertEqual(next(iter(self.read('jobs.json')['notifications'].values()))['status'], 'submitting')
        self.stop()
        self.queue_failure = None
        self.start()
        self.assertEqual(len(self.sent), 2)
        self.history = [self.history_for(message['input'][0]['text']) for message in self.sent]
        self.cycle()
        self.assertEqual(self.watcher.state['outbox'][0]['status'], 'delivered')
        self.assertEqual(next(iter(self.read('jobs.json')['notifications'].values()))['status'], 'delivered')
        self.assertEqual(self.read('jobs.json')['jobs']['integration-job']['status'], 'verified')
        self.assertEqual(len(self.sent), 2)

    def test_rejected_notices_are_not_retried_and_new_revision_can_queue(self):
        self.start()
        self.edit()
        self.seed_job()
        self.queue_failure = RequestRejected('fixture native rejection')
        self.cycle()
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.watcher.state['outbox'][0]['status'], 'rejected')
        self.assertEqual(next(iter(self.read('jobs.json')['notifications'].values()))['status'], 'rejected')
        self.queue_failure = None
        self.cycle()
        self.assertEqual(len(self.sent), 2)
        self.edit('A later independent revision')
        self.cycle()
        self.assertEqual(len(self.sent), 3)

    def test_worker_crash_receipt_recovery_queues_review_once(self):
        self.start()
        job = self.seed_job(status='running', receipt_status='verified')
        self.cycle()
        saved = self.read('jobs.json')
        self.assertEqual(saved['jobs'][job['id']]['status'], 'verified')
        self.assertEqual(len(self.sent), 1)
        self.cycle()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(saved['jobs'][job['id']]['attempt_id'], job['attempt_id'])

    def test_worker_crash_without_receipt_requires_original_attempt_recovery(self):
        self.start()
        job = self.seed_job(status='running', receipt=False)
        self.cycle()
        saved = self.read('jobs.json')
        self.assertEqual(saved['jobs'][job['id']]['status'], 'recovery_required')
        event = next(iter(saved['notifications'].values()))
        self.assertEqual(event['kind'], 'recovery_required')
        self.assertEqual(event['attempt_id'], job['attempt_id'])
        self.assertEqual(len(self.sent), 1)

    def test_active_review_failure_reconciles_without_acceptance_or_duplicate_turn(self):
        self.start()
        self.seed_job()
        self.cycle()
        text = self.sent[0]['input'][0]['text']
        self.history = [self.history_for(text, 'inProgress')]
        self.cycle()
        event = next(iter(self.read('jobs.json')['notifications'].values()))
        self.assertEqual(event['turn_status'], 'inProgress')
        self.history[0]['status'] = 'failed'
        self.cycle()
        saved = self.read('jobs.json')
        event = next(iter(saved['notifications'].values()))
        self.assertEqual(event['turn_status'], 'failed')
        self.assertIn('turn_error', event)
        self.assertEqual(saved['jobs']['integration-job']['status'], 'verified')
        self.assertEqual(len(self.sent), 1)

    def test_dashboard_reads_actual_health_both_outboxes_and_stopped_thread(self):
        from web_dashboard import Dashboard
        self.start()
        self.seed_job()
        self.edit()
        self.client_failure = RuntimeError('fixture private error details')
        self.cycle()
        dashboard = Dashboard([self.path])
        project_id = next(iter(dashboard.projects))
        before = {path.name: path.read_bytes() for path in self.folder.iterdir() if path.is_file()}
        blocked = dashboard.detail(project_id)['notifications']
        self.assertFalse(blocked['healthy'])
        self.assertFalse(blocked['coordinator_available'])
        self.assertEqual(blocked['outbox']['prepared'], 2)
        self.assertNotIn('private error details', json.dumps(blocked))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.folder.iterdir() if path.is_file()})
        self.client_failure = None
        self.cycle()
        healthy = dashboard.detail(project_id)['notifications']
        self.assertTrue(healthy['healthy'])
        self.assertTrue(healthy['running'])
        self.assertEqual(healthy['outbox']['queued'], 2)
        self.assertEqual(healthy['baseline']['count'], 1)
        self.stop()
        stopped = dashboard.detail(project_id)['notifications']
        self.assertEqual(stopped['status'], 'stopped')
        self.assertFalse(stopped['healthy'])
        self.assertFalse(stopped['running'])

    def test_config_drift_stops_both_outboxes_before_delivery(self):
        self.start()
        self.edit()
        self.seed_job()
        self.config['board']['view_filter'] = 'changed filter'
        self.write_config()
        state = self.cycle()
        self.assertEqual(state['status'], 'blocked')
        self.assertIn('configuration changed', state['last_error'])
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.worker_errors), 1)

    def test_binding_drift_stops_both_outboxes_without_replacement_owner(self):
        self.start()
        self.edit()
        self.seed_job()
        binding = self.read('binding.json')
        binding['binding']['provider_thread_id'] = str(uuid.UUID(int=3))
        (self.folder / 'binding.json').write_text(json.dumps(binding), encoding='utf-8')
        state = self.cycle()
        self.assertEqual(state['status'], 'blocked')
        self.assertIn('binding changed', state['last_error'])
        self.assertEqual(self.sent, [])
        self.assertEqual({owner for owner, _ in self.thread_reads}, {self.identity})


if __name__ == '__main__':
    unittest.main()
