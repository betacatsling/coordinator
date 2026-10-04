import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('watch_reminder_test', ROOT/'scripts/watch_project.py')
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)

class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='reminder-test-')
        self.project = Path(self.tmp.name)
        self.folder = self.project/'.project-delegation'; self.folder.mkdir()
        self.doc = self.project/'PROJECT.md'
        self.doc.write_text('## First\nDo one thing.\n## Second\nDo two things.\n')
        snapshot, self.digest = w.read_input(self.doc)
        self.pending = {'input_hash': self.digest, 'tasks': w.task_changes(self.doc, {}), 'snapshot': snapshot}
        (self.folder/'pending.json').write_text(json.dumps(self.pending))
    def tearDown(self): self.tmp.cleanup()
    def hook(self, event='PreToolUse', session='fixture-session', **extra):
        payload = {'hook_event_name': event, 'session_id': session, 'cwd': str(self.project), **extra}
        result = subprocess.run([sys.executable, str(ROOT/'scripts/coordinator_reminder.py'), '--project', str(self.project)], input=json.dumps(payload), text=True, capture_output=True, check=True)
        return json.loads(result.stdout)
    def test_context_events_and_session_dedupe(self):
        for event in ['PreToolUse','PostToolUse','UserPromptSubmit']:
            response = self.hook(event, session=event)
            self.assertEqual(response['hookSpecificOutput']['hookEventName'], event)
            context = response['hookSpecificOutput']['additionalContext']
            self.assertIn('First, Second', context)
            self.assertIn('current coordinator', context)
            self.assertEqual(self.hook(event, session=event), {})
        self.assertFalse((self.folder/'acknowledged.json').exists())
    def test_stop_blocks_once_and_guards_continuation(self):
        self.assertEqual(self.hook('Stop', stop_hook_active=True), {})
        self.assertEqual(self.hook('Stop')['decision'], 'block')
        self.assertEqual(self.hook('Stop'), {})
    def test_stale_pending_and_wrong_project_suppressed(self):
        self.assertEqual(self.hook(cwd=str(self.project/'other')), {})
        self.doc.write_text('## First\nNew task body.\n')
        self.assertEqual(self.hook(), {})
    def test_ack_exact_revision_preserves_newer_edits(self):
        self.hook()
        self.doc.write_text('## First\nNew task body.\n## Second\nDo two things.\n')
        subprocess.run([sys.executable,str(ROOT/'scripts/coordinator_reminder.py'),'--project',str(self.project),'--ack',self.digest],capture_output=True,text=True,check=True)
        self.assertEqual([t['title'] for t in w.task_changes(self.doc,{})], ['First'])
    def test_undelivered_revision_cannot_be_acknowledged(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/coordinator_reminder.py'),'--project',str(self.project),'--ack',self.digest],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.folder/'acknowledged.json').exists())

if __name__=='__main__': unittest.main()
