"""Portable subprocess contract tests; not a native Windows/Codex E2E claim."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import app_server_client as transport

# A byte relay's other side: HTTP upgrade + two small WebSocket requests.
PEER = r'''
import base64, hashlib, json, struct, sys
r = sys.stdin.buffer
w = sys.stdout.buffer
header = b''
while not header.endswith(b'\r\n\r\n'):
    part = r.read(1)
    if not part: sys.exit(2)
    header += part
key = next(line.split(b': ', 1)[1] for line in header.split(b'\r\n') if line.startswith(b'Sec-WebSocket-Key:'))
accept = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
w.write(b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n'); w.flush()
while True:
    head = r.read(2)
    if not head: break
    n = head[1] & 127
    if n == 126: n = struct.unpack('!H', r.read(2))[0]
    elif n == 127: n = struct.unpack('!Q', r.read(8))[0]
    mask = r.read(4)
    payload = r.read(n)
    value = json.loads(bytes(v ^ mask[i % 4] for i, v in enumerate(payload)))
    if 'id' not in value: continue
    response = json.dumps({'id': value['id'], 'result': {'method': value['method']}}).encode()
    w.write(bytes([129, len(response)]) + response); w.flush()
'''


class WindowsTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.script = Path(self.temp.name) / 'peer.py'
        self.script.write_text(PEER, encoding='utf-8')
        self.real_popen = subprocess.Popen
        self.commands = []
        self.children = []

    def spawn(self, args, **kwargs):
        self.commands.append(args)
        child = self.real_popen([sys.executable, '-u', str(self.script)], **kwargs)
        self.children.append(child)
        return child

    def test_native_windows_uses_official_proxy_with_same_websocket_protocol(self):
        with patch.object(transport.os, 'name', 'nt'), patch.object(transport.subprocess, 'Popen', side_effect=self.spawn):
            with transport.AppServer('C:\\Codex\\control.sock', codex='C:\\Program Files\\Codex\\codex.exe') as client:
                self.assertEqual(client.request('fixture/check', {}), {'method': 'fixture/check'})
        self.assertEqual(self.commands, [['C:\\Program Files\\Codex\\codex.exe', 'app-server', 'proxy', '--sock', 'C:\\Codex\\control.sock']])
        self.assertIsNotNone(self.children[0].poll())

    def test_proxy_timeout_is_bounded_and_failed_init_cleans_up(self):
        self.script.write_text('import time; time.sleep(30)', encoding='utf-8')
        start = time.monotonic()
        with patch.object(transport.os, 'name', 'nt'), patch.object(transport.subprocess, 'Popen', side_effect=self.spawn):
            with self.assertRaisesRegex(TimeoutError, 'WSL2'):
                transport.AppServer('C:\\Codex\\control.sock', timeout=0.1)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIsNotNone(self.children[0].poll())

    def test_proxy_blocked_write_is_bounded_and_cleans_up(self):
        self.script.write_text('import time; time.sleep(30)', encoding='utf-8')
        with patch.object(transport.subprocess, 'Popen', side_effect=self.spawn):
            stream = transport.ProxyStream('codex.exe', 'fixture.sock', timeout=0.1)
            with self.assertRaisesRegex(TimeoutError, 'write timed out'):
                stream.sendall(b'x' * (1024 * 1024))
            stream.close()
        self.assertIsNotNone(self.children[0].poll())

    def test_bad_websocket_handshake_cleans_up(self):
        self.script.write_text(PEER.replace("key + b'258EAFA5", "key + b'WRONG258EAFA5"), encoding='utf-8')
        with patch.object(transport.os, 'name', 'nt'), patch.object(transport.subprocess, 'Popen', side_effect=self.spawn):
            with self.assertRaisesRegex(RuntimeError, 'handshake failed'):
                transport.AppServer('C:\\Codex\\control.sock')
        self.assertIsNotNone(self.children[0].poll())

    def test_proxy_exit_is_not_silent_fallback_to_another_server(self):
        self.script.write_text('raise SystemExit(1)', encoding='utf-8')
        with patch.object(transport.os, 'name', 'nt'), patch.object(transport.subprocess, 'Popen', side_effect=self.spawn):
            with self.assertRaisesRegex(RuntimeError, 'disconnected|unavailable'):
                transport.AppServer('C:\\Codex\\control.sock')
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.commands[0][1:3], ['app-server', 'proxy'])

    def test_named_pipe_and_tcp_are_not_guessed(self):
        for endpoint in ['ws://127.0.0.1:1234', r'\\.\pipe\codex']:
            with self.subTest(endpoint=endpoint), patch.object(transport.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(ValueError, 'socket path'):
                    transport.AppServer(endpoint)
                spawn.assert_not_called()

    def test_notifier_passes_configured_codex_executable(self):
        import board_notifier
        notifier = board_notifier.BoardNotifier.__new__(board_notifier.BoardNotifier)
        notifier.config = {'codex': 'C:\\Program Files\\Codex\\codex.exe',
                           'app_server_socket': 'C:\\Codex\\control.sock'}
        with patch.object(board_notifier, 'AppServer') as factory:
            notifier.client_factory = factory
            self.assertIs(notifier.open_client(), factory.return_value)
            factory.assert_called_once_with(notifier.config['app_server_socket'],
                                            codex=notifier.config['codex'])

    def test_notifier_fixture_factory_remains_single_argument(self):
        import board_notifier
        from unittest.mock import Mock
        notifier = board_notifier.BoardNotifier.__new__(board_notifier.BoardNotifier)
        notifier.config = {'app_server_socket': '/fixture/socket'}
        notifier.client_factory = Mock()
        notifier.open_client()
        notifier.client_factory.assert_called_once_with('/fixture/socket')

    def test_discovery_requires_running_daemon_with_socket_path(self):
        for value in [[], {'status': 'stopped'}, {'status': 'running', 'socketPath': 123}]:
            completed = subprocess.CompletedProcess(['codex'], 0, json.dumps(value), '')
            with patch.object(transport.subprocess, 'run', return_value=completed) as run:
                with self.assertRaisesRegex(RuntimeError, 'No running shared'):
                    transport.endpoint('codex.exe')
                self.assertEqual(run.call_args.args[0], ['codex.exe', 'app-server', 'daemon', 'version'])

if __name__ == '__main__':
    unittest.main()
