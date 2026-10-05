"""Offline title-input regressions: no GitHub calls or production state."""
import unittest
from unittest.mock import patch

from test_github_inputs import fixture
from github_project_inputs import normalize_project
from github_source import fetch


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


    def test_title_edit_changes_revision_and_repeat_is_stable(self):
        project = self.project()
        original = self.normalize(project)[0]
        self.assertEqual(original, self.normalize(project)[0])
        project['items']['nodes'][0]['content']['title'] = 'Implement a different bounded helper'
        updated = self.normalize(project)[0]
        self.assertNotEqual(original['revision_hash'], updated['revision_hash'])
        self.assertEqual(updated, self.normalize(project)[0])

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
        with patch('github_source.gh', return_value={'node': project}) as query:
            fetched = fetch({'source': {'type': 'github'}, 'project_node_id': 'fixture-project'})
        self.assertRegex(query.call_args.args[0], r'\bid number title body\b')
        self.assertEqual(self.normalize(fetched)[0]['instructions'], 'Implement a bounded helper')




if __name__ == '__main__':
    unittest.main()
