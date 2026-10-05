"""Controller-independent GitHub transport and paginated source loading."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from github_source import fetch, gh


class GitHubSourceTests(unittest.TestCase):
    def test_fixture_and_unknown_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'project.json'
            path.write_text(json.dumps({'id': 'P'}))
            self.assertEqual(fetch({'source': {'type': 'fixture', 'path': str(path)}}), {'id': 'P'})
        with self.assertRaises(ValueError): fetch({'source': {'type': 'unknown'}})

    def test_graphql_errors_and_variables(self):
        response = subprocess.CompletedProcess([], 0, stdout='{"data":{"node":1}}', stderr='')
        with patch('github_source.subprocess.run', return_value=response) as run:
            self.assertEqual(gh('query', id='P', cursor=None), {'node': 1})
            self.assertEqual(run.call_args.args[0], ['gh', 'api', 'graphql', '-f', 'query=query', '-f', 'id=P'])
        response.stdout = '{"errors":[{"message":"denied"}]}'
        with patch('github_source.subprocess.run', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'rejected'): gh('query')
        response.returncode = 1; response.stderr = 'offline'
        with patch('github_source.subprocess.run', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'offline'): gh('query')

    def test_paginated_items_and_comments(self):
        first = {'node': {'id': 'P', 'items': {'nodes': [{'content': {
            '__typename': 'Issue', 'id': 'I', 'comments': {'nodes': [{'id': 'C1'}],
            'pageInfo': {'hasNextPage': True, 'endCursor': 'comments-1'}}}}],
            'pageInfo': {'hasNextPage': True, 'endCursor': 'items-1'}}}}
        second = {'node': {'id': 'P', 'items': {'nodes': [{'content': {'__typename': 'DraftIssue'}}],
            'pageInfo': {'hasNextPage': False}}}}
        comments = {'node': {'comments': {'nodes': [{'id': 'C2'}], 'pageInfo': {'hasNextPage': False}}}}
        with patch('github_source.gh', side_effect=[first, second, comments]) as query:
            project = fetch({'source': {'type': 'github'}, 'project_node_id': 'P'})
        self.assertEqual(len(project['items']['nodes']), 2)
        self.assertEqual(project['items']['nodes'][0]['content']['comments']['nodes'], [{'id': 'C1'}, {'id': 'C2'}])
        self.assertEqual(query.call_args_list[1].kwargs, {'id': 'P', 'cursor': 'items-1'})
        self.assertEqual(query.call_args_list[2].kwargs, {'id': 'I', 'cursor': 'comments-1'})

    def test_no_controller_module_imported(self):
        code = "import github_source, board_notifier, delegation_service, sys; assert 'project_acpx' not in sys.modules"
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1] / 'scripts', capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
