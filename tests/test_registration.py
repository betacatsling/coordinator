import json
import os
import uuid
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from register_coordinator import enroll
from adopt_coordinator import assert_quiescent, load_context, response


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(dict(workspace=str(self.root), project_node_id='P1',
                                               repository='owner/repo', user_login='owner')))
        self.thread = str(uuid.UUID(int=1))

    def tearDown(self):
        self.temp.cleanup()

    def test_runtime_only_and_idempotent_pending(self):
        with self.assertRaises(ValueError):
            enroll(self.config, {}, self.root)
        with self.assertRaises(ValueError):
            enroll(self.config, {'CODEX_THREAD_ID': 'guessed'}, self.root)
        first, receipt = enroll(self.config, {'CODEX_THREAD_ID': self.thread}, self.root)
        second, again = enroll(self.config, {'CODEX_THREAD_ID': self.thread}, self.root)
        self.assertEqual(first, second)
        self.assertEqual(receipt, again)
        self.assertEqual(receipt['status'], 'pending')
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)

    def test_scope_and_wrong_working_directory(self):
        with self.assertRaises(ValueError):
            enroll(self.config, {'CODEX_THREAD_ID': self.thread}, self.root.parent)
        path, receipt = enroll(self.config, {'CODEX_THREAD_ID': self.thread}, self.root)
        receipt['scope']['repository'] = 'other/repo'
        path.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            load_context(self.config, path)

    def test_running_or_changed_owner_refuses(self):
        with self.assertRaises(ValueError):
            assert_quiescent({'binding': {'provider_thread_id': 'old'}, 'queue': [{'status': 'running'}]}, 'old')
        with self.assertRaises(ValueError):
            assert_quiescent({'binding': {'provider_thread_id': 'changed'}}, 'old')
        assert_quiescent({'binding': {'provider_thread_id': 'old'}, 'queue': [{'status': 'baseline'}, {'status': 'pending'}]}, 'old')

    def test_completed_native_identity_required(self):
        events = [{'params': {'sessionId': self.thread, 'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'text': 'proof'}}}},
                  {'result': {'stopReason': 'end_turn'}}]
        self.assertEqual(response(events, self.thread), 'proof')
        with self.assertRaises(RuntimeError):
            response(events, 'different')
        with self.assertRaises(RuntimeError):
            response(events[:1], self.thread)


if __name__ == '__main__':
    unittest.main()
