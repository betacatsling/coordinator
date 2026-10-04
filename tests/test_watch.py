import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('watch', ROOT/'scripts/watch_project.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='delegation-test-')
        self.root = Path(self.tmp.name)
        self.doc = self.root/'PROJECT.md'
        self.doc.write_text(w.BEGIN+'\nGoal: fixture\n'+w.END+'\nHuman notes\n')
    def tearDown(self):
        self.tmp.cleanup()
    def test_input_hash_excludes_output(self):
        before = w.read_input(self.doc)
        self.doc.write_text(self.doc.read_text()+'Report outside input\n')
        self.assertEqual(before, w.read_input(self.doc))
        self.doc.write_text(self.doc.read_text().replace('Goal: fixture', 'Goal: changed'))
        self.assertNotEqual(before, w.read_input(self.doc))
    def test_reject_malformed_input(self):
        for text in [w.BEGIN, w.END+w.BEGIN, w.BEGIN+w.BEGIN+w.END]:
            self.doc.write_text(text)
            with self.assertRaises(ValueError): w.read_input(self.doc)
    def test_h2_tasks_exclude_fences_reports_and_duplicates(self):
        text = '# Project\n## First\nDo one thing.\n```text\n## Not a task\n```\n## Second\nDo two.\n## 执行报告\n- [Report](reports/example.html)\n'
        self.assertEqual([t['title'] for t in w.parse_tasks(text)], ['First', 'Second'])
        self.doc.write_text(text)
        before = w.read_input(self.doc)
        self.doc.write_text(text+'Another report line\n')
        self.assertEqual(before, w.read_input(self.doc))
        with self.assertRaises(ValueError): w.parse_tasks('## Same\nA\n## Same\nB')
    def test_task_deduplication(self):
        self.doc.write_text('## One\nA\n## Two\nB\n')
        tasks = w.task_changes(self.doc, {})
        state = {'task_hashes': {t['id']: t['hash'] for t in tasks}}
        self.assertEqual(w.task_changes(self.doc, state), [])
        self.doc.write_text('## One\nChanged\n## Two\nB\n')
        self.assertEqual([t['title'] for t in w.task_changes(self.doc, state)], ['One'])
    def test_inbox_never_starts_model(self):
        self.doc.write_text('## One\nA\n## Two\nB\n')
        cmd = [sys.executable, str(ROOT/'scripts/watch_project.py'), '--project', str(self.root), '--run-current', '--node', '/does/not/exist']
        with open(self.root/'process.log', 'w') as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=log)
            start = time.monotonic()
            pending = self.root/'.project-delegation/pending.json'
            try:
                while not pending.exists() and time.monotonic()-start < 14:
                    if proc.poll() is not None: self.fail((self.root/'process.log').read_text())
                    time.sleep(.1)
                self.assertEqual(len(json.loads(pending.read_text())['tasks']), 2)
                events = (self.root/'.project-delegation/events.jsonl').read_text()
                self.assertNotIn('"event": "dispatch"', events)
                self.assertNotIn('"event": "job"', events)
            finally:
                proc.terminate(); proc.wait(timeout=5)
    def test_loaded_binding_blocks_without_replacement(self):
        cmd = [sys.executable, str(ROOT/'scripts/watch_project.py'), '--project', str(self.root), '--run-current',
               '--node', sys.executable, '--server', str(ROOT/'tests/fake_mcp.py'),
               '--html-cli', str(ROOT/'tests/fake_renderer.py'), '--thread-id', 'fixture-loaded']
        with open(self.root/'process.log', 'w') as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=log)
            start = time.monotonic(); event_path = self.root/'.project-delegation/events.jsonl'
            try:
                while time.monotonic()-start < 14:
                    events = [json.loads(x) for x in event_path.read_text().splitlines()] if event_path.exists() else []
                    if any(e['event'] == 'error' for e in events): break
                    time.sleep(.1)
                error = next(e for e in events if e['event'] == 'error')
                self.assertIn('refusing to take over', error['error'])
                self.assertFalse(any(e['event'] == 'job' for e in events))
            finally:
                proc.terminate(); proc.wait(timeout=5)
    def test_append_and_recover(self):
        original = self.doc.read_text()
        record = {'relative_path':'reports/example.html','date':'fixture date','description':'Example'}
        self.assertTrue(w.append_report_link(self.doc, record))
        self.assertTrue(w.append_report_link(self.doc, record))
        self.assertEqual(self.doc.read_text().count('](reports/example.html)'), 1)
        self.assertTrue(self.doc.read_text().startswith(original))
        self.doc.write_text(original)  # stale editor save
        self.assertTrue(w.append_report_link(self.doc, record))
        self.assertEqual(self.doc.read_text().count('](reports/example.html)'), 1)
    def test_publish_renderer_and_idempotency(self):
        folder=self.root/'.project-delegation'; folder.mkdir()
        state={}
        args=SimpleNamespace(node=sys.executable,html_cli=ROOT/'tests/fake_renderer.py')
        data={'input_hash':'fixture-hash','jobId':'fixture-job','text':'Fixture result','status':'completed'}
        record=w.publish_html(self.root,folder,data,state,args)
        self.assertTrue((self.root/record['relative_path']).is_file())
        w.publish_html(self.root,folder,data,state,args)
        self.assertEqual(len(state['reports']),1)
    def test_mcp_framing(self):
        with open(self.root/'fixture.log','w') as log:
            client=w.MCP([sys.executable,str(ROOT/'tests/fake_mcp.py')],self.root,log)
            try:
                self.assertEqual(client.call('codex-reply-start',{})['jobId'],'fixture-job')
            finally: client.close()
    def test_real_debounce_loop_with_fake_mcp(self):
        cmd=[sys.executable,str(ROOT/'scripts/watch_project.py'),'--project',str(self.root),
             '--node',sys.executable,'--server',str(ROOT/'tests/fake_mcp.py'),
             '--html-cli',str(ROOT/'tests/fake_renderer.py'),'--run-current','--thread-id','fixture-thread']
        with open(self.root/'process.log','w') as log:
            proc=subprocess.Popen(cmd,stdout=log,stderr=log)
            start=time.monotonic()
            try:
                event_path=self.root/'.project-delegation/events.jsonl'
                while time.monotonic()-start<18:
                    events=[json.loads(x) for x in event_path.read_text().splitlines()] if event_path.exists() else []
                    if any(e['event']=='html_report' for e in events): break
                    if proc.poll() is not None: self.fail((self.root/'process.log').read_text())
                    time.sleep(.1)
                self.assertTrue(any(e['event']=='html_report' for e in events))
                dispatch=next(e for e in events if e['event']=='dispatch')
                began=next(e for e in events if e['event']=='watch_started')
                self.assertGreaterEqual(dispatch['time']-began['time'],9.9)
                self.doc.write_text(self.doc.read_text()+'More human notes\n')
                time.sleep(.6)
                events=[json.loads(x) for x in event_path.read_text().splitlines()]
                self.assertEqual(sum(e['event']=='dispatch' for e in events),1)
                self.assertIn('](reports/',self.doc.read_text())
            finally:
                proc.terminate(); proc.wait(timeout=5)
            state=json.loads((self.root/'.project-delegation/state.json').read_text())
            self.assertEqual(state['threadId'],'fixture-thread')
            self.assertEqual(state['status'],'stopped')

if __name__=='__main__': unittest.main()
