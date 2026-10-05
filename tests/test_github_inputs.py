"""Offline tests: no GitHub requests, model calls, or business workspace changes."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from github_project_inputs import normalize_project
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
    def test_executor_rejects_path_escape_before_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'cwd':directory,'owned_paths':['../escape.py'],'checks':[[sys.executable,'--version']]}
            with self.assertRaises(ValueError): execute_assignment('fixture',config,Path(directory)/'receipt.json','not-used')

if __name__=='__main__': unittest.main()
