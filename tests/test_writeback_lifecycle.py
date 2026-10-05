import uuid
"""Offline crash boundaries and stale-card guards for the owned lifecycle."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from github_board import select_tasks
from github_project_inputs import normalize_project
from github_writeback import (CLAIM_PENDING, CLAIM_COMPLETE, dispatch_marker,
                              write_claim, write_result, write_executor_session)


class WritebackLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            'project_node_id': 'P', 'repository': 'owner/repo', 'user_login': 'owner',
            'board': {'view_id': 'V', 'view_filter': '-type:tracking',
                      'status_field_id': 'S', 'ready_option_id': 'todo', 'ready_option_name': 'Todo',
                      'type_field_id': 'T', 'excluded_type_option_id': 'tracking',
                      'excluded_type_option_name': 'Tracking'},
            'writeback': {'status': {'field_id': 'S', 'claimed_option_id': 'doing',
                                     'claimed_option_name': 'Doing', 'accepted_option_id': 'done',
                                     'accepted_option_name': 'Done'}}}
        self.issue = {'id': 'I', '__typename': 'Issue', 'number': 1, 'body': 'Implement fix',
                      'repository': {'nameWithOwner': 'owner/repo'}, 'author': {'login': 'owner'},
                      'comments': {'nodes': []}}
        self.item = {'id': 'ITEM', 'content': self.issue,
                     'fieldValues': {'nodes': [{'field': {'id': 'S'}, 'optionId': 'todo'},
                                               {'field': {'id': 'T'}, 'optionId': 'work'}]}}
        self.project = {'id': 'P', 'items': {'nodes': [self.item]},
                        'views': {'nodes': [{'id': 'V', 'filter': '-type:tracking', 'layout': 'BOARD_LAYOUT'}]},
                        'fields': {'pageInfo': {'hasNextPage': False}, 'nodes': [
                            {'id': 'S', 'options': [{'id': 'todo', 'name': 'Todo'},
                                                   {'id': 'doing', 'name': 'Doing'}, {'id': 'done', 'name': 'Done'}]},
                            {'id': 'T', 'options': [{'id': 'tracking', 'name': 'Tracking'}]}]}}
        task = normalize_project(self.project, 'P', 'owner', selected_repository='owner/repo')[0]
        self.task = select_tasks(self.project, self.config, [task], {})[0]
        self.mutations = []
        self.fail_at = None
        self.fail_after = False

    def query(self, query, **args):
        if 'viewer' in query:
            return {'viewer': {'login': 'owner'}}
        if 'fields(' in query:
            return {'node': {'fields': self.project['fields']}}
        self.mutations.append((query, args))
        fail = len(self.mutations) == self.fail_at
        if fail and not self.fail_after:
            raise RuntimeError('Interrupted before mutation')
        if 'addComment' in query:
            comment_id = 'C' + str(len(self.issue['comments']['nodes']) + 1)
            self.issue['comments']['nodes'].append({'id': comment_id, 'body': args['body'], 'author': {'login': 'owner'}})
            result = {'addComment': {'commentEdge': {'node': {'id': comment_id}}}}
        elif 'updateIssueComment' in query:
            next(c for c in self.issue['comments']['nodes'] if c['id'] == args['id'])['body'] = args['body']
            result = {'updateIssueComment': {'issueComment': {'id': args['id']}}}
        elif 'updateProjectV2ItemFieldValue' in query:
            self.set_status(args['option'])
            result = {'updateProjectV2ItemFieldValue': {'projectV2Item': {'id': 'ITEM'}}}
        else:
            raise AssertionError(query)
        if fail:
            raise RuntimeError('Lost response after mutation')
        return result

    def set_status(self, value):
        self.item['fieldValues']['nodes'][0]['optionId'] = value

    def claim(self):
        return write_claim(self.config, self.task, self.project, self.query, False)

    def result(self, accepted=True, text='Verified isolated implementation'):
        return write_result(self.config, self.task, self.project, text, {}, accepted, self.query, False)

    def assert_no_mutation(self, call):
        before = len(self.mutations)
        with self.assertRaises(ValueError):
            call()
        self.assertEqual(len(self.mutations), before)

    def test_claim_recovers_every_crash_boundary_without_duplicate_comments(self):
        for mutation in range(1, 4):
            for after in [False, True]:
                with self.subTest(mutation=mutation, after=after):
                    self.setUp()
                    self.fail_at, self.fail_after = mutation, after
                    with self.assertRaises(RuntimeError):
                        self.claim()
                    self.fail_at = None
                    self.claim()
                    self.assertEqual(len(self.issue['comments']['nodes']), 1)
                    self.assertIn(CLAIM_COMPLETE, self.issue['comments']['nodes'][0]['body'])
                    self.assertEqual(self.item['fieldValues']['nodes'][0]['optionId'], 'doing')
                    self.assertEqual(self.claim()['operations'], [])

    def test_result_recovers_every_crash_boundary_without_duplicate_comments(self):
        for mutation in range(1, 3):
            for after in [False, True]:
                with self.subTest(mutation=mutation, after=after):
                    self.setUp()
                    self.claim()
                    self.mutations = []
                    self.fail_at, self.fail_after = mutation, after
                    with self.assertRaises(RuntimeError):
                        self.result()
                    self.fail_at = None
                    self.result()
                    self.assertEqual(len(self.issue['comments']['nodes']), 2)
                    self.assertEqual(self.item['fieldValues']['nodes'][0]['optionId'], 'done')
                    self.assertEqual(self.result()['operations'], [])

    def test_result_refuses_unowned_or_incomplete_claim(self):
        self.assert_no_mutation(self.result)
        self.fail_at = 2
        with self.assertRaises(RuntimeError):
            self.claim()
        self.fail_at = None
        self.set_status('doing')
        self.assertIn(CLAIM_PENDING, self.issue['comments']['nodes'][0]['body'])
        self.assert_no_mutation(self.result)

    def test_moved_card_rejects_claim_result_and_session_notice(self):
        self.claim()
        for status in ['todo', 'triage', 'done']:
            self.set_status(status)
            self.assert_no_mutation(self.claim)
            self.assert_no_mutation(self.result)
            self.assert_no_mutation(lambda: write_executor_session(
                self.config, self.task, self.project, str(uuid.UUID(int=1)), self.query, False))

    def test_revision_changed_and_excluded_card_reject_results(self):
        self.claim()
        self.issue['body'] = 'New instructions'
        self.assert_no_mutation(self.result)
        self.issue['body'] = 'Implement fix'
        self.item['fieldValues']['nodes'][1]['optionId'] = 'tracking'
        self.assert_no_mutation(self.result)

    def test_old_dispatch_cannot_publish_over_new_owned_dispatch(self):
        self.claim()
        newer = dict(self.task, dispatch_key='a' * 64)
        self.issue['comments']['nodes'].append({
            'id': 'NEW', 'author': {'login': 'owner'},
            'body': dispatch_marker(self.config, newer, 'claim') + '\n' + CLAIM_COMPLETE})
        self.assert_no_mutation(self.result)
        self.assert_no_mutation(self.claim)

    def test_terminal_recovery_requires_identical_result(self):
        self.claim()
        self.result()
        self.assert_no_mutation(lambda: self.result(text='Different result'))
        self.assert_no_mutation(lambda: self.result(accepted=False))

    def test_partial_result_cannot_finish_after_card_moves(self):
        self.claim()
        self.mutations = []
        self.fail_at = 2
        with self.assertRaises(RuntimeError):
            self.result()
        self.fail_at = None
        self.set_status('todo')
        self.assert_no_mutation(self.result)

    def test_claim_preview_validates_mapping_before_any_mutation(self):
        self.config['writeback']['status']['claimed_option_id'] = 'unknown'
        self.assert_no_mutation(self.claim)

    def test_board_claim_requires_same_status_field_and_mapping(self):
        for mapping in [{}, {'field_id': 'OTHER', 'claimed_option_id': 'doing', 'claimed_option_name': 'Doing'}]:
            self.config['writeback']['status'] = mapping
            self.assert_no_mutation(self.claim)

    def test_explicit_non_board_intake_checks_claimed_state_when_mapped(self):
        self.config.pop('board')
        self.claim()
        self.set_status('todo')
        self.assert_no_mutation(self.result)
        self.assert_no_mutation(self.claim)
        self.set_status('doing')
        self.result()
        self.assertEqual(self.result()['operations'], [])

    def test_explicit_comment_only_intake_remains_supported(self):
        self.config.pop('board')
        self.config['writeback'].pop('status')
        self.claim()
        self.result()
        self.assertEqual(self.result()['operations'], [])
        self.assertEqual(len(self.issue['comments']['nodes']), 2)

    def test_session_notice_edits_claim_once(self):
        self.claim()
        args = (self.config, self.task, self.project, str(uuid.UUID(int=1)), self.query, False)
        write_executor_session(*args)
        self.assertEqual(write_executor_session(*args)['operations'], [])
        self.assertEqual(len(self.issue['comments']['nodes']), 1)


if __name__ == '__main__':
    unittest.main()
