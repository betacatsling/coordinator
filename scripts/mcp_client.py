"""MCP connection for independent executor sessions."""
import json
import queue
import subprocess
import threading
import time

class MCP:
    def __init__(self, command, cwd, log):
        self.process = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8", bufsize=1)
        self.responses = queue.Queue()
        self.seq = 0
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()
        self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                               'clientInfo': {'name': 'project-delegation-executor', 'version': '1.0'}})
        self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        names = {t['name'] for t in self.rpc('tools/list')['tools']}
        required = {'codex-thread-read', 'codex-reply-start', 'codex-status', 'codex-result'}
        if not required <= names:
            raise RuntimeError('MCP server lacks required Codex tools')

    def _read(self):
        try:
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
        finally:
            self.responses.put(None)

    def _send(self, obj):
        self.process.stdin.write(json.dumps(obj) + '\n')
        self.process.stdin.flush()

    def rpc(self, method, params=None):
        with self.lock:
            self.seq += 1
            rid = self.seq
            self._send({'jsonrpc': '2.0', 'id': rid, 'method': method,
                        **({'params': params} if params is not None else {})})
            deadline = time.monotonic() + 360
            while True:
                obj = self.responses.get(timeout=max(.1, deadline - time.monotonic()))
                if obj is None:
                    raise RuntimeError('MCP connection closed')
                if obj.get('id') == rid:
                    if 'error' in obj:
                        raise RuntimeError(obj['error'])
                    return obj['result']

    def call(self, name, args):
        result = self.rpc('tools/call', {'name': name, 'arguments': args})
        data = result.get('structuredContent')
        if data is None:
            texts = [c['text'] for c in result.get('content', []) if c.get('type') == 'text']
            data = json.loads('\n'.join(texts))
        if result.get('isError'):
            raise RuntimeError(data)
        return data

    def close(self):
        # Closing this private connection cancels its jobs; never touch other clients.
        self.process.stdin.close()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)
        self.process.stdout.close()

