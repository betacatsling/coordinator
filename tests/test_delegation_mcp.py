"""Offline coordinator-driven delegation, real stdio/worker/worktree integration."""
import io
import fcntl
import json
import os
import select
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from delegation_service import DelegationService
from delegation_mcp import dispatch, serve, RequestService
from issue_worktree import git, create
from mcp_executor import _verify, validated_receipt, task_identity
from platform_support import process_alive

BRIDGE = r'''
import json, os, re, sys, uuid
from pathlib import Path
thread = str(uuid.uuid5(uuid.NAMESPACE_URL, os.getcwd()))
for line in sys.stdin:
    m=json.loads(line)
    if 'id' not in m: continue
    if m['method']=='initialize': result={'protocolVersion':'2025-06-18','capabilities':{},'serverInfo':{'name':'test','version':'1'}}
    elif m['method']=='tools/list': result={'tools':[{'name':n} for n in ['codex-start','codex-thread-read','codex-reply-start','codex-status','codex-result']]}
    else:
        n=m['params']['name']; a=m['params']['arguments']
        with open(Path(__file__).with_suffix('.calls'),'a') as f:f.write(n+'\n')
        if n in {'codex-start','codex-reply-start'}:
            paths=json.loads(re.search(r'Owned paths: (\[.*?\])',a['prompt']).group(1))
            p=Path(paths[0]);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(p.read_text()+'revision\n' if p.exists() else 'implementation\n')
            data={'jobId':'fixture-job','threadId':thread}
        elif n=='codex-thread-read':data={'thread':{'cwd':os.getcwd(),'status':{'type':'notLoaded'}}}
        elif n=='codex-status':data={'state':'completed','threadId':thread,'cursor':1}
        else:data={'text':'Fixture changed owned artifact; controller must verify it.','threadId':thread}
        result={'structuredContent':data}
    print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
'''


class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.workspace = self.base / 'repo'
        self.workspace.mkdir()
        git(self.workspace, 'init')
        git(self.workspace, 'config', 'user.email', 'fixture@example.invalid')
        git(self.workspace, 'config', 'user.name', 'Fixture')
        (self.workspace / 'README').write_text('base\n')
        git(self.workspace, 'add', 'README')
        git(self.workspace, 'commit', '-m', 'fixture')
        self.owner = str(uuid.uuid4())
        self.env = patch.dict(os.environ, CODEX_THREAD_ID=self.owner)
        self.env.start()
        self.project = {'id': 'P', 'items': {'nodes': [
            {'id': 'ITEM'+str(i), 'content': {'__typename': 'Issue', 'id': 'I'+str(i), 'body': 'Implement '+str(i), 'author': {'login': 'u'}, 'repository': {'nameWithOwner': 'u/r'}, 'comments': {'nodes': []}}}
            for i in range(5)]}}
        self.source = self.base / 'project.json'
        self.source.write_text(json.dumps(self.project))
        self.bridge = self.base / 'bridge.py'
        self.bridge.write_text(BRIDGE)
        self.config = {'workspace': str(self.workspace), 'project_node_id': 'P', 'repository': 'u/r', 'user_login': 'u',
            'source': {'type': 'fixture', 'path': str(self.source)}, 'node': sys.executable,
            'executor': {'enabled': True, 'isolate_worktree': True, 'server': str(self.bridge), 'bridge_state_root': str(self.base / 'bridge-state'), 'allowed_resources': ['database']}}
        self.config_path = self.base / 'config.json'
        self.config_path.write_text(json.dumps(self.config))
        self.owner_path = self.workspace / '.project-delegation/runtime/binding.json'
        self.owner_path.parent.mkdir(parents=True)
        scope = {k: self.config[k] for k in ('workspace', 'project_node_id', 'repository', 'user_login')}
        self.owner_path.write_text(json.dumps({'schema': 1, 'scope': scope, 'binding': {'scope': scope, 'provider_thread_id': self.owner, 'transport': 'app_server'}}))
        self.service = DelegationService(self.config_path)
        self.jobs = []

    def tearDown(self):
        try:
            # A terminal job can still have a detached worker persisting its
            # notification outcome. close() intentionally does not join it.
            if self.service.path.exists():
                state = json.loads(self.service.path.read_text())
                for job in state['jobs'].values():
                    self.wait_worker_exit(job)
        finally:
            self.service.close()
            self.env.stop()
        self.tmp.cleanup()

    def wait_worker_exit(self, job, timeout=20):
        pid = job.get('worker_pid')
        if not pid or pid == os.getpid():
            return  # Preparation failures and the synthetic launch-window test.
        message = 'Fixture worker did not exit: ' + str(job)
        if hasattr(os, 'pidfd_open'):
            # pidfds observe actual exit, including unreaped orphan workers from
            # the stdio test, without confusing zombies with live processes.
            try:
                descriptor = os.pidfd_open(pid)
            except ProcessLookupError:
                return
            try:
                self.assertTrue(select.select([descriptor], [], [], timeout)[0], message)
            finally:
                os.close(descriptor)
        else:
            until = time.monotonic() + timeout
            while process_alive(pid):
                self.assertLess(time.monotonic(), until, message)
                time.sleep(.01)

    def start(self, i=0, **kwargs):
        task = next(t for t in self.service.tasks_list()['tasks'] if t['issue_id'] == 'I'+str(i))
        job = self.service.executor_start(task['issue_id'], task['revision_hash'], 'Implement bounded fixture', ['p'+str(i)+'.txt'], **kwargs)
        self.jobs.append(job['id'])
        return job

    def wait(self, job):
        until = time.monotonic()+20
        while time.monotonic()<until:
            status = self.service.executor_status(job['id'])
            if status['status'] != 'running':
                self.wait_worker_exit(status, timeout=max(0, until - time.monotonic()))
                return status
            time.sleep(.04)
        self.fail('Fixture worker did not finish: '+str(status))

    @unittest.skipUnless(hasattr(os, 'pidfd_open'), 'Requires process-exit descriptors')
    def test_terminal_status_waits_for_remaining_worker_writes(self):
        marker = self.base / 'notification-written'
        script = ('import sys; from pathlib import Path; sys.stdin.read(1); '
                  'Path(sys.argv[1]).write_text("notification persisted")')
        worker = subprocess.Popen([sys.executable, '-c', script, str(marker)],
                                  stdin=subprocess.PIPE)
        status = dict(id='delayed-notification', status='verified', worker_pid=worker.pid)
        observe_exit = select.select

        def release_and_observe(*args):
            # Release the final write only when the fixture actually waits for
            # process exit. Returning at terminal status would miss this write.
            self.assertFalse(marker.exists())
            worker.stdin.write(b'x')
            worker.stdin.flush()
            return observe_exit(*args)

        try:
            with patch.object(self.service, 'executor_status', return_value=status), \
                    patch.object(select, 'select', side_effect=release_and_observe) as observe:
                self.assertEqual(self.wait(status), status)
                observe.assert_called_once()
            self.assertEqual(marker.read_text(), 'notification persisted')
            self.assertEqual(worker.poll(), 0)
        finally:
            worker.stdin.close()
            worker.wait(timeout=20)

    def test_real_async_start_resume_original_finish_and_restart(self):
        job = self.start()
        self.assertEqual(job['status'], 'running')
        first = self.wait(job)
        self.assertEqual(first['status'], 'verified', first)
        receipt = self.service.executor_result(job['id'])['receipt']
        self.assertIn('p0.txt', receipt['changed_paths'])
        self.assertIn('+implementation', receipt['patch'])
        self.assertNotIn('artifacts', receipt)
        self.assertNotIn('sha256', json.dumps(receipt))
        self.assertNotEqual(receipt['thread_id'], self.owner)
        self.service = DelegationService(self.config_path)
        resumed = self.service.executor_continue(job['id'], 'Refine original artifact')
        self.assertEqual(self.wait(resumed)['thread_id'], receipt['thread_id'])
        result = self.service.executor_result(job['id'])['receipt']
        self.assertEqual(len(result['previous_turns']), 1)
        self.assertNotEqual(result['attempt_id'], receipt['attempt_id'])
        ledger = json.loads(self.service.path.read_text())
        notices = [n for n in ledger['notifications'].values() if n['job_id'] == job['id']]
        self.assertEqual(len(notices), 2)
        self.assertEqual({n['attempt_id'] for n in notices}, {result['attempt_id'], receipt['attempt_id']})
        self.assertEqual({n['executor_thread_id'] for n in notices}, {receipt['thread_id']})
        done = self.service.task_finish(job['id'], True, 'Scoped fixture accepted', 'Actual scope check passed; no integration claimed')
        self.assertEqual(done['status'], 'accepted')
        self.assertTrue(Path(done['report']['local_path']).is_file())
        self.assertIsNone(done['report']['url'])
        self.assertEqual(self.service.task_finish(job['id'], True, 'Scoped fixture accepted', 'Actual scope check passed; no integration claimed')['status'], 'accepted')
        with self.assertRaises(ValueError):self.service.executor_continue(job['id'], 'again')
        calls = self.bridge.with_suffix('.calls').read_text().splitlines()
        self.assertEqual(calls.count('codex-start'), 1)
        self.assertEqual(calls.count('codex-reply-start'), 1)
        self.assertFalse((self.workspace/'p0.txt').exists())

    def test_recover_observes_original_job_without_replacement(self):
        job = self.start(); self.wait(job)
        result = self.service.executor_result(job['id'])['receipt']
        with self.service.transaction() as state:state['jobs'][job['id']]['status']='recovery_required'
        self.service.executor_continue(job['id'], '', recover_only=True)
        observed = self.wait(job)
        self.assertEqual(observed['thread_id'], result['thread_id'])
        calls = self.bridge.with_suffix('.calls').read_text().splitlines()
        self.assertEqual(calls.count('codex-start'), 1)
        self.assertEqual(calls.count('codex-reply-start'), 0)

    def test_bounded_slots_conflicts_duplicate_and_ambiguous_launch(self):
        with patch.object(self.service, '_launch', side_effect=OSError('unknown launch outcome')):
            first = self.start(0, resources=['database'])
            self.assertEqual(first['status'], 'recovery_required')
            with self.assertRaises(ValueError):self.start(0)
            with self.assertRaises(ValueError):self.start(1, resources=['database'])
            self.start(1); self.start(2)
            with self.assertRaisesRegex(ValueError, 'slots'):self.start(3)
        with self.assertRaisesRegex(ValueError, 'receipt missing'):
            self.service.executor_continue(first['id'], 'retry')
        self.assertFalse(self.bridge.with_suffix('.calls').exists())

    def test_authorization_and_source_rechecked(self):
        with patch.dict(os.environ, CODEX_THREAD_ID=str(uuid.uuid4())):
            with self.assertRaises(ValueError):DelegationService(self.config_path)
        with patch.dict(os.environ, CODEX_THREAD_ID=''):
            with self.assertRaises(ValueError):DelegationService(self.config_path)
        task = self.service.tasks_list()['tasks'][0]
        self.project['items']['nodes'][0]['content']['author']['login']='other'
        self.source.write_text(json.dumps(self.project))
        with self.assertRaises(ValueError):self.service.executor_start(task['issue_id'],task['revision_hash'],'go',['p.txt'])
        self.config['repository']='u/other';self.config_path.write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError,'Configuration changed'):self.service.tasks_list()

    def test_changed_git_diff_prevents_acceptance_and_rejection_can_continue(self):
        job = self.start(); self.wait(job)
        receipt = self.service.executor_result(job['id'])['receipt']
        artifact = Path(receipt['workspace'])/'p0.txt'
        artifact.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'Git changes differ'):
            self.service.task_finish(job['id'],True,'Accept','Evidence')
        self.assertEqual(self.service.task_finish(job['id'],False,'Needs revision','Tampered evidence')['status'],'rejected')
        self.service.executor_continue(job['id'],'Fix actual artifact')
        self.assertEqual(self.wait(job)['status'],'verified')

    def test_dependency_evidence_requires_accepted_unchanged_version(self):
        job=self.start();self.wait(job)
        with self.assertRaises(ValueError):self.start(1,depends_on=[job['id']])
        self.service.task_finish(job['id'],True,'Accepted','Evidence')
        dependent=self.start(1,depends_on=[job['id']]);self.wait(dependent)
        with self.service.transaction() as state:
            evidence = state['jobs'][dependent['id']]['dependencies'][0]
            self.assertEqual(evidence['job_id'],job['id'])
            self.assertEqual(evidence['attempt_id'], state['jobs'][job['id']]['attempt_id'])
            self.assertIn('+implementation', evidence['patch'])
            self.assertNotIn('artifacts', evidence)
            self.assertNotIn('sha256', json.dumps(evidence))
            self.service._check_dependencies(state, state['jobs'][dependent['id']])
            evidence['attempt_id'] = 'different-attempt'
            with self.assertRaisesRegex(ValueError, 'Pinned dependency attempt changed'):
                self.service._check_dependencies(state, state['jobs'][dependent['id']])
            evidence['attempt_id'] = state['jobs'][job['id']]['attempt_id']
        self.project['items']['nodes'][0]['content']['body']='changed authorized instruction'
        self.source.write_text(json.dumps(self.project))
        with self.assertRaisesRegex(ValueError,'Dependency source revision changed'):self.start(2,depends_on=[job['id']])

    def test_preparation_failure_retries_original_reservation_and_releases_capacity(self):
        (self.workspace/'p0.txt').write_text('user uncommitted file')
        job = self.start()
        self.assertEqual(job['status'], 'preparation_failed')
        self.assertEqual(job['phase'], 'preparing')
        self.assertFalse(Path(job['receipt']).exists())
        other = self.start(1); self.wait(other)
        (self.workspace/'p0.txt').unlink()
        retry = self.service.executor_continue(job['id'], 'Retry after user reconciles dirty scope')
        self.assertEqual(retry['id'], job['id'])
        self.assertEqual(self.wait(job)['status'], 'verified')
        self.assertEqual(self.bridge.with_suffix('.calls').read_text().splitlines().count('codex-start'), 2)

    def test_launch_window_rejects_second_continuation(self):
        job = self.start(); self.wait(job)
        def launching(value, mode):
            value.update(status='running', worker_pid=os.getpid(), mode=mode)
        with patch.object(self.service, '_launch', side_effect=launching):
            self.service.executor_continue(job['id'], 'FIRST')
            with self.assertRaisesRegex(ValueError, 'still active'):
                self.service.executor_continue(job['id'], 'SECOND')
        with self.service.transaction() as state:
            self.assertEqual(state['jobs'][job['id']]['assignment'], 'FIRST')

    def test_shared_services_use_one_durable_ledger(self):
        second = DelegationService(self.config_path)
        self.addCleanup(second.close)
        with self.service.transaction() as state:
            state['marker'] = 'shared'
        with second.transaction() as state:
            self.assertEqual(state['marker'], 'shared')
        self.assertEqual(self.service.root, self.workspace / '.project-delegation/runtime')
        self.service.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            self.service.tasks_list()

    def test_git_diff_detects_added_files_and_supports_deletion_only(self):
        task={'issue_id':'git-diff','revision_hash':'revision','dispatch_key':'dispatch'}
        workspace,head=create(self.workspace,task,self.service.root,['README','owned'])
        config=dict(self.config['executor'],cwd=str(workspace),base_head=head,owned_paths=['README','owned'],task_identity=task_identity(task))
        (workspace/'README').unlink()
        receipt=dict(status='completed',workspace=str(workspace),base_head=head,owned_paths=['README','owned'],bridge_state_root=self.config['executor']['bridge_state_root'],task_identity=task_identity(task))
        path=self.base/'git-diff.json'
        def save():path.write_text(json.dumps(receipt))
        _verify(config,workspace,config['owned_paths'],receipt,save)
        checked = validated_receipt(config,path)
        self.assertEqual(checked['changed_paths'], ['README'])
        self.assertIn('deleted file mode', checked['patch'])
        self.assertNotIn('artifacts', checked)
        (workspace/'README').write_text('restored')
        with self.assertRaises(ValueError):validated_receipt(config,path)
        (workspace/'README').unlink()
        (workspace/'owned').mkdir();(workspace/'owned/new.txt').write_text('added after verification')
        with self.assertRaises(ValueError):validated_receipt(config,path)

    def test_git_patch_includes_tracked_new_empty_and_binary_files(self):
        task = dict(issue_id='git-diff', revision_hash='revision', dispatch_key='dispatch')
        workspace, head = create(self.workspace, task, self.service.root, ['README', 'owned'])
        config = dict(self.config['executor'], cwd=str(workspace), base_head=head,
                      owned_paths=['README', 'owned'], task_identity=task_identity(task),
                      checks=[[sys.executable, '-c', 'print("behavioral fixture passed")']])
        (workspace / 'README').write_text('changed tracked file\n')
        (workspace / 'owned').mkdir()
        (workspace / 'owned/new.txt').write_text('new file\n')
        (workspace / 'owned/empty.txt').write_text('')
        (workspace / 'owned/binary.dat').write_bytes(b'\x00\xff\x01')
        receipt = dict(status='completed', workspace=str(workspace), base_head=head,
                       owned_paths=config['owned_paths'], bridge_state_root=config['bridge_state_root'],
                       task_identity=config['task_identity'])
        path = self.base / 'git-diff.json'
        def save():
            path.write_text(json.dumps(receipt))
        _verify(config, workspace, config['owned_paths'], receipt, save)
        checked = validated_receipt(config, path)
        self.assertEqual(checked['changed_paths'], ['README', 'owned/binary.dat', 'owned/empty.txt', 'owned/new.txt'])
        self.assertNotIn('artifacts', checked)
        self.assertNotIn('sha256', json.dumps(checked))
        self.assertIn('GIT binary patch', checked['patch'])
        self.assertIn('+new file', checked['patch'])
        self.assertEqual(checked['checks'][-1]['stdout'], 'behavioral fixture passed\n')
        self.assertEqual(git(workspace, 'diff', '--cached', '--name-only'), '')
        for name in checked['changed_paths']:
            target = workspace / name
            original = target.read_bytes()
            target.write_bytes(original + b'changed')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Git changes differ'):
                validated_receipt(config, path)
            target.write_bytes(original)
        self.assertEqual(validated_receipt(config, path)['patch'], checked['patch'])

    def test_acceptance_rejects_failed_recorded_checks_without_a_hash_inventory(self):
        job = self.start(); self.wait(job)
        receipt = self.service.executor_result(job['id'])['receipt']
        self.assertNotIn('artifacts', receipt)
        receipt['checks'][0]['returncode'] = 1
        Path(job['receipt']).write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'successful recorded checks'):
            self.service.task_finish(job['id'], True, 'Accept')

    def test_check_mutations_require_fresh_verification(self):
        task = dict(issue_id='checks', revision_hash='revision', dispatch_key='dispatch')
        workspace, head = create(self.workspace, task, self.service.root, ['README'])
        (workspace / 'README').write_text('implementation\n')
        config = dict(self.config['executor'], cwd=str(workspace), base_head=head,
                      owned_paths=['README'], task_identity=task_identity(task),
                      checks=[[sys.executable, '-c', 'from pathlib import Path; Path("README").write_text("changed by check")']])
        receipt = {}
        with self.assertRaisesRegex(ValueError, 'while checks ran'):
            _verify(config, workspace, config['owned_paths'], receipt, lambda: None)
        self.assertEqual(receipt['checks'][-1]['returncode'], 0)
        self.assertNotEqual(receipt.get('status'), 'verified')

    def test_task_finish_accepts_one_concise_summary_without_report(self):
        job = self.start(); self.wait(job)
        summary = 'Created the fixture output; scoped change checks passed.'
        response = dispatch(RequestService(self.config_path), {'method': 'tools/call', 'params': {
            '_meta': {'threadId': self.owner}, 'name': 'task_finish',
            'arguments': {'job_id': job['id'], 'accepted': True, 'summary': summary}}})
        self.assertNotIn('isError', response, response)
        result = response['structuredContent']
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['decision']['report'], summary)
        self.assertEqual(result['integration'], 'isolated_unmerged')
        self.assertIn(summary, Path(result['report']['local_path']).read_text())
        self.assertEqual(self.service.task_finish(job['id'], True, summary)['status'], 'accepted')

    def test_task_finish_summary_required_and_supplied_report_must_be_text(self):
        for accepted, summary, report in [('yes', 'Outcome', None), (True, '', None),
                                         (True, 'Outcome', ''), (True, 'Outcome', [])]:
            with self.subTest(accepted=accepted, summary=summary, report=report), self.assertRaises(ValueError):
                self.service.task_finish('unused', accepted, summary, report)

    def test_stdio_dispatch_worker_survives_connection_exit(self):
        task=self.service.tasks_list()['tasks'][0]
        request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'_meta':{'threadId':self.owner},'name':'executor_start','arguments':dict(issue_id=task['issue_id'],revision_hash=task['revision_hash'],assignment='Actual stdio dispatch',owned_paths=['p0.txt'])}}
        env = dict(os.environ)
        env.pop('CODEX_THREAD_ID', None)
        run=subprocess.run([sys.executable,str(ROOT/'scripts/delegation_mcp.py'),'--config',str(self.config_path)],input=json.dumps(request)+'\n',text=True,capture_output=True,timeout=10,env=env)
        self.assertEqual(run.returncode,0,run.stderr)
        job=json.loads(run.stdout)['result']['structuredContent']
        self.assertEqual(self.wait(job)['status'],'verified')
        # The stdio coordinator already exited; its detached worker still
        # persists a fixed-owner review event without requiring status polling.
        notices = json.loads(self.service.path.read_text())['notifications']
        event = next(n for n in notices.values() if n['job_id'] == job['id'])
        self.assertEqual(event['coordinator_thread_id'], self.owner)
        self.assertEqual(event['executor_status'], 'verified')
        self.assertEqual(event['attempt_id'], job['attempt_id'])

    def test_inactive_stale_revision_can_be_retired_without_writeback(self):
        job=self.start();self.wait(job)
        self.project['items']['nodes'][0]['content']['body']='new authorized revision'
        self.source.write_text(json.dumps(self.project))
        with self.assertRaisesRegex(ValueError,'source authorization/revision changed'):
            self.service.task_finish(job['id'],True,'accept','stale')
        retired=self.service.task_finish(job['id'],False,'Retire obsolete version','Source changed; preserve evidence locally')
        self.assertEqual(retired['status'],'superseded')
        self.assertTrue(retired['source_changed'])
        self.assertIsNone(retired['writeback'])
        new=self.start();self.assertNotEqual(new['id'],job['id'])
        self.assertEqual(self.wait(new)['status'],'verified')

    def test_source_change_before_worker_submission_is_retirable(self):
        def reserve(value, mode):value.update(status='running',mode=mode)
        with patch.object(self.service,'_launch',side_effect=reserve):job=self.start()
        self.project['items']['nodes'][0]['content']['body']='new instruction before worker begins'
        self.source.write_text(json.dumps(self.project))
        self.service.run_worker(job['id'])
        status=self.service.executor_status(job['id'])
        self.assertEqual(status['status'],'preparation_failed')
        self.assertEqual(status['phase'],'worker_validation_failed')
        self.assertFalse(Path(status['receipt']).exists())
        self.assertEqual(self.service.task_finish(job['id'],False,'Retire stale pre-submission task','No bridge call occurred')['status'],'superseded')
        new=self.start();self.assertEqual(self.wait(new)['status'],'verified')

    def test_stale_recovery_observes_original_without_source_writeback(self):
        job=self.start();self.wait(job)
        with self.service.transaction() as state:state['jobs'][job['id']]['status']='recovery_required'
        self.project['items']['nodes'][0]['content']['body']='changed while original job needed observation'
        self.source.write_text(json.dumps(self.project))
        self.service.executor_continue(job['id'],'',recover_only=True)
        self.assertEqual(self.wait(job)['status'],'verified')
        self.assertEqual(self.service.task_finish(job['id'],False,'Retire observed stale version','Original receipt retained')['status'],'superseded')
        calls=self.bridge.with_suffix('.calls').read_text().splitlines()
        self.assertEqual(calls.count('codex-start'),1)
        self.assertEqual(calls.count('codex-reply-start'),0)

    def test_discovery_does_not_require_binding_or_create_runtime(self):
        workspace = self.base / 'discovery-only'
        workspace.mkdir()
        config = self.base / 'discovery-config.json'
        config.write_text(json.dumps({'workspace': str(workspace)}))
        adapter = RequestService(config)
        self.assertIn('serverInfo', dispatch(adapter, {'method': 'initialize'}))
        self.assertEqual(dispatch(adapter, {'method': 'ping'}), {})
        self.assertEqual(len(dispatch(adapter, {'method': 'tools/list'})['tools']), 6)
        self.assertFalse((workspace / '.project-delegation').exists())

    def test_stdio_without_environment_uses_each_host_request_identity(self):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        ]
        for i, meta in enumerate([None, {}, {'threadId': 'invalid'},
                                  {'threadId': str(uuid.uuid4())},
                                  {'threadId': self.owner}, None], 3):
            params = {'name': 'tasks_list', 'arguments': {}}
            if meta is not None:
                params['_meta'] = meta
            requests.append({'jsonrpc': '2.0', 'id': i, 'method': 'tools/call', 'params': params})
        env = dict(os.environ)
        env.pop('CODEX_THREAD_ID', None)
        run = subprocess.run([sys.executable, str(ROOT/'scripts/delegation_mcp.py'),
                              '--config', str(self.config_path)],
                             input=''.join(json.dumps(x)+'\n' for x in requests),
                             text=True, capture_output=True, timeout=10, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        output = [json.loads(line)['result'] for line in run.stdout.splitlines()]
        self.assertEqual(output[0]['serverInfo']['name'], 'project-delegation')
        self.assertEqual(len(output[1]['tools']), 6)
        for i in (2, 3, 4, 5, 7):
            self.assertTrue(output[i]['isError'])
        self.assertIn('_meta.threadId', output[2]['content'][0]['text'])
        self.assertIn('bound fixed coordinator', output[5]['content'][0]['text'])
        self.assertEqual(len(output[6]['structuredContent']['tasks']), 5)

    def test_mcp_never_uses_server_environment_as_caller_identity(self):
        adapter = RequestService(self.config_path)
        result = dispatch(adapter, {'method': 'tools/call',
                                    'params': {'name': 'tasks_list', 'arguments': {}}})
        self.assertTrue(result['isError'])
        self.assertIn('_meta.threadId', result['content'][0]['text'])
        with self.assertRaisesRegex(ValueError, 'Invalid tool arguments'):
            dispatch(adapter, {'method': 'tools/call', 'params': {
                'name': 'tasks_list', 'arguments': {'threadId': self.owner}}})
        self.config['repository'] = 'changed/repository'
        self.config_path.write_text(json.dumps(self.config))
        result = dispatch(adapter, {'method': 'tools/call', 'params': {
            'name': 'tasks_list', 'arguments': {}, '_meta': {'threadId': self.owner}}})
        self.assertTrue(result['isError'])
        self.assertIn('Configuration changed', result['content'][0]['text'])

    def test_authenticated_dispatch_passes_identity_to_detached_worker(self):
        with patch.dict(os.environ, CODEX_THREAD_ID=''):
            service = DelegationService(self.config_path, caller_thread_id=self.owner)
            self.addCleanup(service.close)
            task = service.tasks_list()['tasks'][0]
            job = service.executor_start(task['issue_id'], task['revision_hash'],
                                         'Implement bounded fixture', ['p0.txt'])
            self.assertEqual(self.wait(job)['status'], 'verified')

    def test_stdio_tools_list_call_and_no_override_surface(self):
        requests = [{'jsonrpc':'2.0','id':1,'method':'initialize'},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'tasks_list','arguments':{},'_meta':{'threadId':self.owner}}},
            {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'executor_start','arguments':{'shell':'bad'}}}]
        run=subprocess.run([sys.executable,str(ROOT/'scripts/delegation_mcp.py'),'--config',str(self.config_path)],input=''.join(json.dumps(x)+'\n' for x in requests),text=True,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        output=[json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(len(output),4)
        self.assertEqual(len(output[1]['result']['tools']),6)
        self.assertEqual(len(output[2]['result']['structuredContent']['tasks']),5)
        self.assertIn('error',output[3])
        self.assertNotIn('shell',json.dumps(output[1]))


if __name__=='__main__':unittest.main()
