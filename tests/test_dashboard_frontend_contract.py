"""Render/event contract smoke with a minimal DOM stub, not visual browser QA."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from browser_dashboard_smoke import fixture, make_server

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for JavaScript contract smoke')
    def test_frontend_consumes_real_backend_shape(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-contract-test-') as directory:
            root = Path(directory).resolve()
            config, _ = fixture(root, 'Populated')
            server = make_server([config], port=0)
            try:
                app = server.dashboard
                pid = next(iter(app.projects))
                path = root / 'snapshot.json'
                path.write_text(json.dumps({'catalog': {'projects': [app.project_info(pid)]}, 'detail': app.detail(pid)}), encoding='utf-8')
                result = subprocess.run([shutil.which('node'), str(ROOT / 'tests/dashboard_dom_contract.js'), str(path)],
                                        cwd=str(ROOT), capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            finally:
                server.server_close()
