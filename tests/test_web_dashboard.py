"""Offline dashboard tests; all state is synthetic and isolated in temporary directories."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('web_dashboard_test', ROOT / 'scripts/web_dashboard.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.configs = []
        for name in ('one', 'two'):
            workspace = self.root / name
            runtime = workspace / '.project-delegation/runtime'
            runtime.mkdir(parents=True)
            scope = dict(workspace=str(workspace), repository='example/' + name, project_node_id=name, user_login='tester')
            config = self.root / (name + '.json')
            config.write_text(json.dumps(dict(scope, token='CONFIG-SECRET', executor={'env': {'KEY': 'ENV-SECRET'}})))
            self.configs.append(config)
            (runtime / 'binding.json').write_text(json.dumps(dict(scope=scope, binding={'provider_thread_id': 'coordinator', 'socket_path': 'SOCKET-SECRET'})))
            (runtime / 'jobs.json').write_text(json.dumps(dict(scope=scope, jobs={'job1': {'id': 'job1', 'status': 'running', 'task': {'issue_id': 'I1', 'title': 'Build alpha', 'url': 'https://github.com/example/' + name + '/issues/1'}, 'owned_paths': ['src/a.py'], 'assignment': 'PROMPT-SECRET', 'executor_config': {'token': 'EXECUTOR-SECRET'}, 'receipt': '/arbitrary/path.json', 'created_at': 1700000000}})))
            (runtime / 'job1.receipt.json').write_text(json.dumps({'status': 'running', 'thread_id': 'executor', 'executor_result': 'RESULT-SECRET', 'error': 'ERROR-SECRET', 'patch': 'PATCH-SECRET', 'checks': [{'command': 'COMMAND-SECRET', 'stdout': 'STDOUT-SECRET', 'returncode': 0}]}))
            (runtime / 'notifier.json').write_text(json.dumps(dict(scope=scope, outbox=[{'id': 'n1', 'text': 'NOTICE-SECRET', 'created_at': 1700000000}])))
            (workspace / 'reports').mkdir()
            (workspace / 'reports/report.html').write_text('<script>alert("report")</script>')
        self.app = web.Dashboard(self.configs)
        self.pid = next(iter(self.app.projects))
        self.runtime = self.root / 'one/.project-delegation/runtime'
        self.server = web.make_server(self.configs, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def get(self, route, **kwargs):
        return urlopen(Request(self.base + route, **kwargs), timeout=3)

    def test_multi_project_actual_state_and_filter(self):
        with self.get('/api/projects') as response:
            index = json.load(response)
        self.assertEqual(len(index['projects']), 2)
        detail = self.app.detail(self.pid)
        self.assertEqual(detail['summary']['active'], 1)
        self.assertIsNone(detail['summary']['running_verified'])
        self.assertEqual(detail['executors'][0]['session_id'], 'executor')
        self.assertEqual(detail['coordinator']['live_status'], 'unknown')
        self.assertEqual(detail['executors'][0]['checks'][0]['status'], 'passed')
        with self.get('/api/projects/' + self.pid + '?search=nonexistent') as response:
            filtered = json.load(response)
        self.assertEqual(filtered['tasks'], [])
        self.assertEqual(filtered['summary']['active'], 1)
        self.assertEqual(self.app.detail(self.pid, {'status': ['failed']})['executors'], [])

    def test_allowlist_and_secret_redaction(self):
        serialized = json.dumps(self.app.detail(self.pid))
        for secret in ('CONFIG-SECRET', 'ENV-SECRET', 'PROMPT-SECRET', 'SOCKET-SECRET', 'RESULT-SECRET', 'ERROR-SECRET', 'PATCH-SECRET', 'COMMAND-SECRET', 'STDOUT-SECRET', 'NOTICE-SECRET', 'EXECUTOR-SECRET'):
            self.assertNotIn(secret, serialized)
        self.assertNotIn('/arbitrary/path.json', serialized)
        self.assertEqual(web.text('token=abc ghp_abcdefghij password:hunter2'), 'token=[redacted] [redacted] password=[redacted]')
        self.assertEqual(web.text('x' * 1000), 'x' * 240)

    def test_partial_corrupt_and_missing_state(self):
        original = self.app.detail(self.pid)
        (self.runtime / 'jobs.json').write_text('{"partial":')
        detail = self.app.detail(self.pid)
        self.assertTrue(detail['stale'])
        self.assertEqual(detail['executors'], original['executors'])
        self.assertEqual(detail['sources']['jobs']['status'], 'unavailable')
        fresh = web.Dashboard(self.configs).detail(self.pid)
        self.assertEqual(fresh['executors'], [])
        (self.runtime / 'binding.json').unlink()
        self.assertEqual(web.Dashboard(self.configs).detail(self.pid)['coordinator']['status'], 'unknown')

    def test_scope_mismatch_excluded(self):
        value = json.loads((self.runtime / 'jobs.json').read_text())
        value['scope']['repository'] = 'other/repo'
        (self.runtime / 'jobs.json').write_text(json.dumps(value))
        detail = self.app.detail(self.pid)
        self.assertEqual(detail['executors'], [])
        self.assertTrue(detail['sources']['jobs']['stale'])

    def test_malicious_urls_and_report_attachment(self):
        value = json.loads((self.runtime / 'jobs.json').read_text())
        value['jobs']['job1']['task']['url'] = 'javascript:alert(1)'
        value['jobs']['job1']['report_url'] = 'https://evil.test/leak'
        (self.runtime / 'jobs.json').write_text(json.dumps(value))
        detail = self.app.detail(self.pid)
        self.assertIsNone(detail['tasks'][0]['url'])
        self.assertIsNone(detail['executors'][0]['report_url'])
        with self.get(detail['reports'][0]['url']) as response:
            self.assertEqual(response.headers['Content-Type'], 'application/octet-stream')
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertIn('sandbox', response.headers['Content-Security-Policy'])
        for url in ['https://github.com/example/one/issues/1?token=abc', 'https://github.com.evil.test/example/one/issues/1', '//evil.test', 'https://user:pw@github.com/example/one/issues/1']:
            self.assertIsNone(web.Dashboard.issue_url(url, 'example/one'))

    def test_traversal_host_and_read_only(self):
        for route in ['/../one.json', '/%2e%2e/one.json', '/api/projects/' + self.pid + '/../../one.json', '/reports/' + self.pid + '/../../one.json', '/scripts/web_dashboard.py']:
            with self.assertRaises(HTTPError) as error:
                self.get(route)
            self.assertEqual(error.exception.code, 404)
        with self.assertRaises(HTTPError) as error:
            self.get('/api/projects', headers={'Host': 'attacker.test'})
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.get('/api/projects', method='POST', data=b'{}')
        self.assertEqual(error.exception.code, 405)
        with self.get('/api/projects') as response:
            self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.app.detail(self.pid)
        after = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_symlink_receipt_report_and_runtime_blocked(self):
        outside = self.root / 'outside.json'
        outside.write_text('{"thread_id":"OUTSIDE-SECRET"}')
        receipt = self.runtime / 'job1.receipt.json'
        receipt.unlink()
        try:
            receipt.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')
        (self.root / 'one/reports/secret.txt').symlink_to(outside)
        detail = self.app.detail(self.pid)
        self.assertIsNone(detail['executors'][0]['session_id'])
        self.assertEqual(len(detail['reports']), 1)
        self.runtime.rename(self.runtime.with_name('saved'))
        self.runtime.symlink_to(self.runtime.with_name('saved'), target_is_directory=True)
        detail = web.Dashboard(self.configs).detail(self.pid)
        self.assertEqual(detail['executors'], [])
        self.assertFalse(detail['available'])

    def test_oversized_and_wrong_structure(self):
        (self.runtime / 'jobs.json').write_text('x' * (web.MAX_JSON + 1))
        self.assertEqual(self.app.detail(self.pid)['executors'], [])
        (self.runtime / 'jobs.json').write_text(json.dumps({'scope': self.app.projects[self.pid]['scope'], 'jobs': []}))
        self.assertEqual(self.app.detail(self.pid)['sources']['jobs']['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
