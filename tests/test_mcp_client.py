import sys
from pathlib import Path
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from mcp_client import MCP

class MCPClientTests(unittest.TestCase):
    def test_mcp_framing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (root / 'fixture.log').open('w') as log:
                client = MCP([sys.executable, str(ROOT / 'tests/fake_mcp.py')], root, log)
                try:
                    self.assertEqual(client.call('codex-reply-start', {})['jobId'], 'fixture-job')
                finally:
                    client.close()
