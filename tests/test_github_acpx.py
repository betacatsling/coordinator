"""Offline tests: no GitHub requests, model calls, or business workspace changes."""
import importlib.util
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from github_project_inputs import normalize_project
from project_acpx import Coordinator
from mcp_executor import execute_assignment


def fixture(body='Implement a helper', comments=None, labels=None, repository='example-owner/example-project'):
    issue = {'__typename': 'Issue', 'id': 'fixture-issue', 'body': body,
             'author': {'login': 'example-user'}, 'repository': {'nameWithOwner': repository},
             'url': 'https://example.invalid/issues/1',
             'comments': {'nodes': comments or [], 'pageInfo': {'hasNextPage': False}},
             'labels': {'nodes': labels or []}}
    return {'id': 'fixture-project', 'items': {'nodes': [{'content': issue}], 'pageInfo': {'hasNextPage': False}}}


class GitHubInputTests(unittest.TestCase):
    def normalize(self, project, **extra):
        return normalize_project(project, 'fixture-project', 'example-user', selected_repository='example-owner/example-project', **extra)
    def test_all_labels_and_unlabelled_eligible(self):
        plain = self.normalize(fixture())[0]
        labelled = self.normalize(fixture(labels=[{'name': 'arbitrary-label'}]))[0]
        self.assertEqual(plain['revision_hash'], labelled['revision_hash'])
    def test_only_selected_user_body_and_comments(self):
        project = fixture(comments=[{'id': 'other', 'body': 'Untrusted comment', 'author': {'login': 'other-user'}},
                                    {'id': 'user', 'body': 'User instruction', 'author': {'login': 'EXAMPLE-USER'}}])
        project['items']['nodes'][0]['content']['author']['login'] = 'other-user'
        task = self.normalize(project)[0]
        self.assertEqual(task['instructions'], '')
        self.assertEqual([c['id'] for c in task['user_comments']], ['user'])
    def test_result_comments_excluded_and_revision_updates(self):
        comments=[{'id': 'result', 'body': 'Generated result', 'author': {'login': 'example-user'}}]
        base=self.normalize(fixture())[0]
        ignored=self.normalize(fixture(comments=comments),result_comment_ids=['result'])[0]
        self.assertEqual(base['revision_hash'], ignored['revision_hash'])
        self.assertNotEqual(base['revision_hash'],self.normalize(fixture(body='Changed instruction'))[0]['revision_hash'])
    def test_binding_and_repository_isolation(self):
        self.assertEqual(self.normalize(fixture(repository='other-owner/other-project')), [])
        wrong=fixture();wrong['id']='wrong-project'
        with self.assertRaises(ValueError): self.normalize(wrong)
    def test_incomplete_pagination_fails_closed(self):
        project=fixture();project['items']['pageInfo']['hasNextPage']=True
        with self.assertRaises(ValueError): self.normalize(project)
        project=fixture();project['items']['nodes'][0]['content']['comments']['pageInfo']['hasNextPage']=True
        with self.assertRaises(ValueError): self.normalize(project)
    def test_queue_dedupe_and_superseding_preserve_running_snapshot(self):
        import project_acpx
        project=fixture();original=project_acpx.fetch
        project_acpx.fetch=lambda config:project
        try:
            coordinator=Coordinator.__new__(Coordinator)
            coordinator.config={'project_node_id':'fixture-project','repository':'example-owner/example-project','user_login':'example-user'}
            coordinator.state={'queue':[],'result_comment_ids':[]};coordinator.save=lambda:None
            coordinator.scan();coordinator.scan()
            self.assertEqual(len(coordinator.state['queue']),1)
            old=coordinator.state['queue'][0]['task']['revision_hash']
            project['items']['nodes'][0]['content']['body']='New input'
            coordinator.scan()
            self.assertEqual(coordinator.state['queue'][0]['status'],'superseded')
            coordinator.state['queue'][1]['status']='running'
            running=coordinator.state['queue'][1]['task']['revision_hash']
            project['items']['nodes'][0]['content']['body']='Third input'
            coordinator.scan()
            self.assertEqual(coordinator.state['queue'][1]['status'],'running')
            self.assertEqual(coordinator.state['queue'][1]['task']['revision_hash'],running)
            self.assertNotEqual(old,running)
        finally: project_acpx.fetch=original
    def test_executor_rejects_path_escape_before_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'cwd':directory,'owned_paths':['../escape.py'],'checks':[[sys.executable,'--version']]}
            with self.assertRaises(ValueError): execute_assignment('fixture',config,Path(directory)/'receipt.json','not-used')
    def test_structured_plan_rejects_non_object(self):
        self.assertEqual(Coordinator.parse_object('```json\n{"assignment":"Do one thing"}\n```')['assignment'],'Do one thing')
        with self.assertRaises(ValueError): Coordinator.parse_object('[]')
    def test_identity_guard_refuses_new_fork_and_wrong_session(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); ledger = folder/'provider.json'
            ledger.write_text(json.dumps({'creation':'allowed'}))
            adapter = folder/'fixture_adapter.py'
            adapter.write_text("import json,sys\nfor line in sys.stdin:\n m=json.loads(line)\n result={'sessionId':'fixture-provider'} if m['method']=='session/new' else {'stopReason':'end_turn'}\n print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)\n")
            process = subprocess.Popen([sys.executable,str(ROOT/'scripts/acp_identity_guard.py'),'--ledger',str(ledger),'--node',sys.executable,'--adapter',str(adapter)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            def request(number, method, params):
                process.stdin.write(json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params})+'\n');process.stdin.flush()
                return json.loads(process.stdout.readline())
            try:
                self.assertEqual(request(1,'session/new',{})['result']['sessionId'],'fixture-provider')
                self.assertEqual(json.loads(ledger.read_text())['provider_thread_id'],'fixture-provider')
                for number,method,params in [(2,'session/new',{}),(3,'session/fork',{}),(4,'session/prompt',{'sessionId':'wrong-provider'})]:
                    self.assertIn('error',request(number,method,params))
                self.assertEqual(request(5,'session/prompt',{'sessionId':'fixture-provider'})['result']['stopReason'],'end_turn')
            finally:
                process.stdin.close();process.wait(timeout=5);process.stdout.close();process.stderr.close()

if __name__=='__main__': unittest.main()
