"""Offline title-input regressions: no GitHub calls or production state."""
import unittest
from unittest.mock import patch

from test_github_acpx import fixture
from github_project_inputs import normalize_project
from project_acpx import Coordinator, fetch


class GitHubTitleInputTests(unittest.TestCase):
    def project(self, title='Implement a bounded helper', body=''):
        project = fixture(body=body)
        project['items']['nodes'][0]['content']['title'] = title
        return project

    def normalize(self, project, **kwargs):
        return normalize_project(project, 'fixture-project', 'example-user',
                                 selected_repository='example-owner/example-project', **kwargs)

    def test_authorized_title_only_is_actionable(self):
        task = self.normalize(self.project())[0]
        self.assertEqual(task['instructions'], 'Implement a bounded helper')
        self.assertEqual(task['user_comments'], [])

    def test_title_and_body_are_preserved_as_instructions(self):
        task = self.normalize(self.project(body='Preserve the existing API.'))[0]
        self.assertEqual(task['instructions'], 'Implement a bounded helper\n\nPreserve the existing API.')

    def test_title_edit_changes_revision_but_repeat_deduplicates(self):
        project = self.project()
        obj = Coordinator.__new__(Coordinator)
        obj.config = {'project_node_id': 'fixture-project', 'user_login': 'example-user',
                      'repository': 'example-owner/example-project'}
        obj.state = {'queue': [], 'result_comment_ids': []}
        obj.save = lambda: None
        with patch('project_acpx.fetch', return_value=project):
            obj.scan(); obj.scan()
            self.assertEqual(len(obj.state['queue']), 1)
            old = obj.state['queue'][0]['task']['revision_hash']
            project['items']['nodes'][0]['content']['title'] = 'Implement a different bounded helper'
            obj.scan(); obj.scan()
        self.assertEqual([e['status'] for e in obj.state['queue']], ['superseded', 'pending'])
        self.assertNotEqual(old, obj.state['queue'][1]['task']['revision_hash'])

    def test_unauthorized_or_deleted_author_title_cannot_dispatch(self):
        for author in ({'login': 'other-user'}, None):
            project = self.project()
            project['items']['nodes'][0]['content']['author'] = author
            with self.subTest(author=author):
                self.assertEqual(self.normalize(project), [])

    def test_unauthorized_title_never_enters_authorized_comment_task(self):
        project = self.project(body='Untrusted body')
        issue = project['items']['nodes'][0]['content']
        issue['author'] = {'login': 'other-user'}
        issue['comments']['nodes'] = [{'id': 'C', 'body': 'Authorized comment',
                                      'author': {'login': 'EXAMPLE-USER'}}]
        task = self.normalize(project)[0]
        issue['title'] = 'Changed untrusted title'
        updated = self.normalize(project)[0]
        self.assertEqual(task['instructions'], '')
        self.assertEqual(task['revision_hash'], updated['revision_hash'])
        self.assertEqual(task['user_comments'][0]['body'], 'Authorized comment')

    def test_title_keeps_scope_and_result_exclusions(self):
        project = self.project()
        original = self.normalize(project)[0]
        issue = project['items']['nodes'][0]['content']
        issue['comments']['nodes'] = [{'id': 'RESULT', 'body': 'Generated result',
                                      'author': {'login': 'example-user'}}]
        self.assertEqual(original['revision_hash'], self.normalize(project, result_comment_ids=['RESULT'])[0]['revision_hash'])
        issue['repository']['nameWithOwner'] = 'other-owner/other-project'
        self.assertEqual(self.normalize(project), [])
        issue['repository']['nameWithOwner'] = 'example-owner/example-project'
        issue['__typename'] = 'DraftIssue'
        self.assertEqual(self.normalize(project), [])

    def test_blank_title_and_body_without_comments_still_ignored(self):
        self.assertEqual(self.normalize(self.project(title='  ', body='\n')), [])

    def test_github_fetch_requests_issue_title(self):
        project = self.project()
        project['items']['pageInfo']['endCursor'] = None
        with patch('project_acpx.gh', return_value={'node': project}) as query:
            fetched = fetch({'source': {'type': 'github'}, 'project_node_id': 'fixture-project'})
        self.assertRegex(query.call_args.args[0], r'\bid number title body\b')
        self.assertEqual(self.normalize(fetched)[0]['instructions'], 'Implement a bounded helper')


class TitleRevisionMigrationTests(unittest.TestCase):
    def setup_controller(self, status='baseline', generation=1):
        from test_board_claim_review import BoardClaimReviewTests
        from github_board import select_tasks
        fixture_case = BoardClaimReviewTests(); fixture_case.setUp()
        project, config = fixture_case.project, fixture_case.config
        issue = project['items']['nodes'][0]['content']
        issue['title'] = 'Existing title'
        legacy = normalize_project(project, 'P', 'u', selected_repository='u/r', include_titles=False)
        observations = {}
        old = select_tasks(project, config, legacy, observations)[0]
        old['ready_generation'] = generation
        obj = Coordinator.__new__(Coordinator)
        obj.config = config
        obj.state = {'queue': [{'task': old, 'status': status, 'executor_receipt': '/retained/receipt'}],
                     'result_comment_ids': [], 'board_observations': observations}
        obj.save = lambda: None
        return obj, project

    def test_unchanged_historical_revisions_do_not_replay_or_rewrite_identity(self):
        import copy
        for status in ('baseline', 'completed', 'blocked'):
            obj, project = self.setup_controller(status)
            original = copy.deepcopy(obj.state['queue'][0]['task'])
            with patch('project_acpx.fetch', return_value=project):
                obj.scan(); obj.scan()
                # Persisted state round-trip represents the next process scan.
                import json
                obj.state = json.loads(json.dumps(obj.state)); obj.scan()
            with self.subTest(status=status):
                self.assertEqual(len(obj.state['queue']), 1)
                self.assertEqual(obj.state['queue'][0]['task'], original)
                self.assertEqual(obj.state['queue'][0]['executor_receipt'], '/retained/receipt')
                self.assertIn('title_revision_baseline', obj.state['queue'][0])
                self.assertEqual(obj.state['input_revision_schema'], 2)

    def test_later_title_edit_dispatches_once(self):
        obj, project = self.setup_controller()
        with patch('project_acpx.fetch', return_value=project):
            obj.scan()
            project['items']['nodes'][0]['content']['title'] = 'Changed title'
            obj.scan(); obj.scan()
        self.assertEqual([e['status'] for e in obj.state['queue']], ['baseline', 'pending'])

    def test_later_ready_generation_dispatches_once(self):
        obj, project = self.setup_controller()
        status = project['items']['nodes'][0]['fieldValues']['nodes'][0]
        with patch('project_acpx.fetch', return_value=project):
            obj.scan()
            status['optionId'] = 'doing'; obj.scan()
            status['optionId'] = 'todo'; obj.scan(); obj.scan()
        self.assertEqual([e['status'] for e in obj.state['queue']], ['baseline', 'pending'])
        self.assertEqual(obj.state['queue'][1]['task']['ready_generation'], 2)

    def test_body_or_generation_changes_are_not_baselined(self):
        for change in ('body', 'generation'):
            obj, project = self.setup_controller(generation=0 if change == 'generation' else 1)
            if change == 'body':
                project['items']['nodes'][0]['content']['body'] = 'New body instruction'
            with patch('project_acpx.fetch', return_value=project):
                obj.scan()
            with self.subTest(change=change):
                self.assertNotIn('title_revision_baseline', obj.state['queue'][0])
                self.assertEqual(obj.state['queue'][1]['status'], 'pending')

    def test_pending_and_running_entries_are_not_aliased(self):
        for status in ('pending', 'running'):
            obj, project = self.setup_controller(status)
            with patch('project_acpx.fetch', return_value=project):
                obj.scan()
            with self.subTest(status=status):
                self.assertNotIn('title_revision_baseline', obj.state['queue'][0])
                self.assertEqual(obj.state['queue'][0]['status'], 'superseded' if status == 'pending' else status)

    def test_previously_ignored_title_only_issue_is_not_baselined(self):
        obj, project = self.setup_controller()
        project['items']['nodes'][0]['content']['body'] = ''
        obj.state['queue'] = []
        with patch('project_acpx.fetch', return_value=project):
            obj.scan(); obj.scan()
        self.assertEqual([e['status'] for e in obj.state['queue']], ['pending'])


if __name__ == '__main__':
    unittest.main()
