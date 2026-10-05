"""Render/event contract smoke with a minimal DOM stub, not visual browser QA."""
import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from browser_dashboard_smoke import fixture, make_server
from web_dashboard import preview_html

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_health_disclosure_markup_is_passive_and_collapsed(self):
        class Markup(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = {}

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if attrs.get('id'):
                    self.ids[attrs['id']] = (tag, attrs)

        markup = Markup()
        markup.feed((ROOT / 'web/index.html').read_text(encoding='utf-8'))
        tag, attrs = markup.ids['service-health']
        self.assertEqual(tag, 'details')
        self.assertNotIn('open', attrs)
        self.assertIn('hidden', attrs)  # No health assertion before API evidence.
        for key in ('notification-status', 'notification-last-check', 'notification-detail'):
            self.assertIn(key, markup.ids)
        self.assertEqual(markup.ids['report-reader'][0], 'section')

    @unittest.skipUnless(shutil.which('node'), 'Node is required for JavaScript contract smoke')
    def test_frontend_consumes_real_backend_shape(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-contract-test-') as directory:
            root = Path(directory).resolve()
            config, _ = fixture(root, 'Populated')
            empty_config, _ = fixture(root, 'Empty', False)
            server = make_server([config, empty_config], port=0)
            try:
                app = server.dashboard
                pid = next(iter(app.projects))
                self.assertIsInstance(app.detail(pid)['notifications'], dict)
                path = root / 'snapshot.json'
                previews = {'/preview/' + pid + '/' + rid: preview_html(artifact.read_bytes()).decode('utf-8')
                            for rid, artifact in app.report_files(pid).items()}
                path.write_text(json.dumps({'catalog': {'projects': [app.project_info(project) for project in app.projects]},
                                            'detail': app.detail(pid), 'details': {project: app.detail(project) for project in app.projects},
                                            'previews': previews}), encoding='utf-8')
                result = subprocess.run([shutil.which('node'), str(ROOT / 'tests/dashboard_dom_contract.js'), str(path)],
                                        cwd=str(ROOT), capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            finally:
                server.server_close()
