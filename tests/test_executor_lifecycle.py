"""Offline lifecycle contracts: no model, network, or user repository mutation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from mcp_executor import execute_assignment, resume_assignment, recover_assignment, task_identity, ExecutorRecoveryRequired
from issue_worktree import create, resume, git, inspect, validate_paths


class FakeMCP:
    calls = []
    state = 'completed'
    result_thread = 'native-1'
    fail_submit = False
    native_cwd = None
    native_status = 'notLoaded'

    def __init__(self, *args):
        pass

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name in {'codex-start', 'codex-reply-start'}:
            if self.fail_submit:
                raise OSError('lost submission response')
            return {'jobId': 'job-1', 'threadId': 'native-1'}
        if name == 'codex-thread-read':
            return {'thread': {'cwd': self.native_cwd, 'status': {'type': self.native_status}}}
        if name == 'codex-status':
            return {'state': self.state, 'threadId': 'native-1', 'cursor': 1}
        if name == 'codex-result':
            return {'threadId': self.result_thread, 'text': 'An executor claim, not test evidence'}
        raise AssertionError(name)

    def close(self):
        pass


class ExecutorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        (self.workspace / 'owned.txt').write_text('artifact')
        self.task = {'issue_id': 'I', 'revision_hash': 'R', 'dispatch_key': 'D'}
        self.config = {'cwd': str(self.workspace), 'owned_paths': ['owned.txt'],
                       'checks': [[sys.executable, '-c', 'print("actual check")']],
                       'bridge_state_root': str(self.root / 'bridge'), 'server': 'fixture',
                       'task_identity': task_identity(self.task)}
        self.receipt = self.root / 'receipt.json'
        FakeMCP.calls = []
        FakeMCP.state = 'completed'
        FakeMCP.result_thread = 'native-1'
        FakeMCP.fail_submit = False
        FakeMCP.native_cwd = str(self.workspace)
        FakeMCP.native_status = 'notLoaded'
        self.patch = patch('mcp_executor.MCP', FakeMCP)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def run_first(self):
        return execute_assignment('fixture', self.config, self.receipt, 'unused')

    def test_actual_checks_and_explicit_resume_keep_identity_and_history(self):
        first = self.run_first()
        self.assertEqual(first['status'], 'verified')
        self.assertEqual(first['checks'][0]['stdout'], 'actual check\n')
        resumed = resume_assignment('correct rejection', self.config, self.receipt, 'unused')
        self.assertEqual(resumed['thread_id'], first['thread_id'])
        self.assertEqual(resumed['workspace'], first['workspace'])
        self.assertEqual(resumed['previous_turns'][0]['artifacts'], first['artifacts'])
        starts = [name for name, _ in FakeMCP.calls if name.endswith('start')]
        self.assertEqual(starts, ['codex-start', 'codex-reply-start'])

    def test_existing_receipt_is_not_overwritten(self):
        self.run_first()
        before = self.receipt.read_bytes()
        with self.assertRaises(ExecutorRecoveryRequired):
            self.run_first()
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_cross_task_revision_dispatch_workspace_and_scope_rejected(self):
        self.run_first()
        before = self.receipt.read_bytes()
        for key in ['issue_id', 'revision_hash', 'dispatch_key']:
            config = copy.deepcopy(self.config)
            config['task_identity'][key] = 'other'
            with self.assertRaises(ValueError):
                resume_assignment('wrong', config, self.receipt, 'unused')
        for key, value in [('owned_paths', ['different']), ('base_head', 'new-head'),
                           ('bridge_state_root', str(self.root / 'different'))]:
            with self.assertRaises(ValueError):
                resume_assignment('wrong', dict(self.config, **{key: value}), self.receipt, 'unused')
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_waiting_approval_recovery_observes_original_job(self):
        FakeMCP.state = 'waiting_for_input'
        with self.assertRaises(ExecutorRecoveryRequired):
            self.run_first()
        first = json.loads(self.receipt.read_text())
        self.assertEqual(first['status'], 'waiting_for_input')
        with self.assertRaises(ExecutorRecoveryRequired):
            resume_assignment('duplicate', self.config, self.receipt, 'unused')
        FakeMCP.state = 'completed'
        result = recover_assignment(self.config, self.receipt, 'unused')
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(sum(name.endswith('start') for name, _ in FakeMCP.calls), 1)

    def test_deadline_preserves_running_job_for_recovery(self):
        self.config['timeout'] = 0
        with self.assertRaises(ExecutorRecoveryRequired):
            self.run_first()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['status'], 'recovery_required')
        self.assertEqual(receipt['job_id'], 'job-1')
        self.config['timeout'] = 10
        self.assertEqual(recover_assignment(self.config, self.receipt, 'unused')['status'], 'verified')
        self.assertEqual(sum(name.endswith('start') for name, _ in FakeMCP.calls), 1)

    def test_confirmed_failed_turn_can_resume_same_native_thread(self):
        FakeMCP.state = 'failed'
        with self.assertRaises(RuntimeError):
            self.run_first()
        self.assertEqual(json.loads(self.receipt.read_text())['status'], 'failed')
        FakeMCP.state = 'completed'
        result = resume_assignment('repair', self.config, self.receipt, 'unused')
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['previous_turns'][0]['status'], 'failed')

    def test_native_identity_change_never_overwrites_original(self):
        FakeMCP.result_thread = 'wrong'
        with self.assertRaises(ExecutorRecoveryRequired):
            self.run_first()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['thread_id'], 'native-1')
        self.assertEqual(receipt['status'], 'recovery_required')

    def test_unknown_resume_submission_cannot_poll_previous_turn(self):
        self.run_first()
        FakeMCP.fail_submit = True
        with self.assertRaises(OSError):
            resume_assignment('fix', self.config, self.receipt, 'unused')
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['thread_id'], 'native-1')
        self.assertNotIn('job_id', receipt)
        with self.assertRaises(ExecutorRecoveryRequired):
            recover_assignment(self.config, self.receipt, 'unused')

    def test_resume_checks_native_workspace_before_submission(self):
        self.run_first()
        FakeMCP.native_cwd = str(self.root)
        with self.assertRaises(ExecutorRecoveryRequired):
            resume_assignment('wrong workspace', self.config, self.receipt, 'unused')
        self.assertEqual(sum(name.endswith('start') for name, _ in FakeMCP.calls), 1)
        self.assertEqual(json.loads(self.receipt.read_text())['thread_id'], 'native-1')

    def test_failed_checks_and_missing_executable_are_evidence(self):
        self.config['checks'] = [[sys.executable, '-c', 'print("failed evidence");raise SystemExit(3)'], ['/nonexistent-fixture-command']]
        result = self.run_first()
        self.assertEqual(result['status'], 'checks_failed')
        self.assertEqual(result['checks'][0]['returncode'], 3)
        self.assertIn('failed evidence', result['checks'][0]['stdout'])
        self.assertIsNone(result['checks'][1]['returncode'])

    def test_verification_error_preserves_executor(self):
        (self.workspace / 'owned.txt').unlink()
        with self.assertRaises(RuntimeError):
            self.run_first()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt['status'], 'verification_failed')
        self.assertEqual(receipt['thread_id'], 'native-1')
        self.assertEqual(receipt['checks'][0]['returncode'], 0)

    def test_corrupt_receipt_and_invalid_checks_fail_before_mcp(self):
        self.receipt.write_text('not JSON')
        with self.assertRaises(ValueError):
            resume_assignment('fix', self.config, self.receipt, 'unused')
        self.assertEqual(self.receipt.read_text(), 'not JSON')
        self.receipt.unlink()
        self.config['checks'] = ['a shell command']
        with self.assertRaises(ValueError):
            self.run_first()
        self.assertFalse(FakeMCP.calls)


class WorktreeRecoveryTests(unittest.TestCase):
    def test_scoped_worktree_recovery_and_ignored_scope_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'repo'
            repo.mkdir()
            git(repo, 'init')
            git(repo, 'config', 'user.name', 'Fixture')
            git(repo, 'config', 'user.email', 'fixture@example.invalid')
            (repo / 'owned.txt').write_text('original')
            (repo / '.gitignore').write_text('hidden.txt\n')
            git(repo, 'add', '.')
            git(repo, 'commit', '-m', 'fixture')
            task = {'issue_id': 'I', 'revision_hash': 'R', 'dispatch_key': 'D'}
            work, head = create(repo, task, root / 'state', ['owned.txt'])
            (work / 'owned.txt').write_text('progress')
            receipt = {'task_identity': task_identity(task), 'workspace': str(work), 'base_head': head, 'owned_paths': ['owned.txt']}
            self.assertEqual(resume(repo, task, root / 'state', ['owned.txt'], receipt), (work, head))
            self.assertEqual((work / 'owned.txt').read_text(), 'progress')
            with self.assertRaises(ValueError):
                create(repo, task, root / 'state', ['owned.txt'])
            with self.assertRaises(ValueError):
                resume(repo, task, root / 'state', ['owned.txt'], dict(receipt, base_head='wrong'))
            (work / 'hidden.txt').write_text('ignored but out of scope')
            with self.assertRaises(ValueError):
                inspect(work, ['owned.txt'])
            for invalid in [[None], [42], ['.git']]:
                with self.assertRaises(ValueError):
                    validate_paths(invalid)


if __name__ == '__main__':
    unittest.main()
