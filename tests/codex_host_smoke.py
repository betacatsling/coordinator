#!/usr/bin/env python3
"""Opt-in actual Codex host MCP test; not part of unittest discovery.

Requires an installed Codex CLI with experimental mcpServer/tool/call support
(verified with 0.159.2). Run: python3 tests/codex_host_smoke.py [--codex PATH]

Uses temporary fixture state and an isolated CODEX_HOME without credentials.
No model turn, GitHub call, executor launch, or global configuration change is
requested. The host creates the thread IDs; no MCP identity is injected.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]

# Delegate every MCP response to the production adapter. Capture only identity
# evidence, not arbitrary request contents. The temporary capture is not saved.
CAPTURE = r'''
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from delegation_mcp import RequestService, dispatch
service = RequestService(sys.argv[2])
log = Path(sys.argv[3])
for line in sys.stdin:
    message = json.loads(line)
    meta = (message.get('params') or {}).get('_meta') or {}
    with log.open('a', encoding='utf-8') as target:
        target.write(json.dumps({
            'method': message.get('method'),
            'meta_keys': list(meta),
            'threadId': meta.get('threadId'),
            'has_thread_env': 'CODEX_THREAD_ID' in os.environ,
        }) + '\n')
    if 'id' not in message:
        continue
    try:
        response = {'jsonrpc': '2.0', 'id': message['id'],
                    'result': dispatch(service, message)}
    except Exception as exc:
        response = {'jsonrpc': '2.0', 'id': message['id'],
                    'error': {'code': -32603, 'message': str(exc)}}
    print(json.dumps(response), flush=True)
'''


class Host:
    def __init__(self, executable, env, cwd, stderr):
        self.process = subprocess.Popen(
            [executable, 'app-server'], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=stderr, text=True, encoding='utf-8',
            env=env, cwd=cwd)
        self.messages = queue.Queue()
        self.next_id = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except Exception as exc:
            self.messages.put(exc)
        finally:
            self.messages.put(EOFError('Codex app-server closed stdout'))

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def call(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + 60
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Timed out waiting for ' + method)
            try:
                response = self.messages.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError('Timed out waiting for ' + method) from None
            if isinstance(response, Exception):
                raise response
            if response.get('id') != request_id:
                continue
            if 'error' in response:
                raise RuntimeError(method + ': ' + json.dumps(response['error']))
            return response['result']

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.reader.join(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()


def check(condition, description):
    if not condition:
        raise AssertionError(description)
    print('PASS: ' + description)


def run(executable, base):
    workspace = base / 'fixture'
    workspace.mkdir()
    source = base / 'project.json'
    source.write_text(json.dumps({'id': 'P', 'items': {'nodes': [{
        'id': 'ITEM', 'content': {
            '__typename': 'Issue', 'id': 'I1',
            'body': 'Read-only host handshake fixture',
            'author': {'login': 'fixture-user'},
            'repository': {'nameWithOwner': 'fixture-user/fixture-repo'},
            'comments': {'nodes': []},
        },
    }]}}), encoding='utf-8')
    config = {
        'workspace': str(workspace), 'project_node_id': 'P',
        'repository': 'fixture-user/fixture-repo', 'user_login': 'fixture-user',
        'source': {'type': 'fixture', 'path': str(source)},
        'executor': {'enabled': True, 'isolate_worktree': True},
    }
    config_path = base / 'fixture-config.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    capture = base / 'capture.py'
    capture.write_text(CAPTURE, encoding='utf-8')
    wire_path = base / 'wire.jsonl'
    home = base / 'codex-home'
    home.mkdir()
    command = json.dumps(sys.executable)
    arguments = json.dumps([str(capture), str(ROOT / 'scripts'),
                            str(config_path), str(wire_path)])
    (home / 'config.toml').write_text(
        'check_for_update_on_startup = false\n'
        '[analytics]\nenabled = false\n'
        '[mcp_servers.delegation]\n'
        f'command = {command}\nargs = {arguments}\n', encoding='utf-8')
    runtime = base / 'runtime'
    runtime.mkdir(mode=0o700)
    env = os.environ.copy()
    env.update(CODEX_HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
               CODEX_SQLITE_HOME=str(home / 'sqlite'))
    env.pop('CODEX_THREAD_ID', None)
    with (base / 'host.stderr').open('w+', encoding='utf-8') as stderr:
        host = Host(executable, env, workspace, stderr)
        try:
            host.call('initialize', {
                'clientInfo': {'name': 'delegation-host-smoke', 'version': '1'},
                'capabilities': {'experimentalApi': True},
            })
            host.send({'method': 'initialized', 'params': {}})
            # No execution environment is needed to exercise MCP routing. This
            # prevents shell/AGENTS loading and does not relax the sandbox.
            thread_params = {'cwd': str(workspace), 'ephemeral': True,
                             'environments': [], 'sandbox': 'read-only',
                             'approvalPolicy': 'never'}
            owner = host.call('thread/start', thread_params)['thread']['id']
            scope = {key: config[key] for key in
                     ('workspace', 'project_node_id', 'repository', 'user_login')}
            binding = workspace / '.project-delegation/runtime/binding.json'
            binding.parent.mkdir(parents=True)
            binding.write_text(json.dumps({
                'schema': 1, 'scope': scope,
                'binding': {'scope': scope, 'provider_thread_id': owner,
                            'transport': 'app_server'},
            }), encoding='utf-8')
            result = host.call('mcpServer/tool/call', {
                'threadId': owner, 'server': 'delegation',
                'tool': 'tasks_list', 'arguments': {},
            })
            wire = [json.loads(line) for line in
                    wire_path.read_text(encoding='utf-8').splitlines()]
            methods = [message['method'] for message in wire]
            check(methods[:4] == ['initialize', 'notifications/initialized',
                                 'tools/list', 'tools/call'],
                  'actual host initialize/list/call sequence')
            check(wire[-1]['threadId'] == owner,
                  'host supplies matching per-call _meta.threadId')
            check(not any(message['has_thread_env'] for message in wire),
                  'MCP server has no CODEX_THREAD_ID environment variable')
            check(not result.get('isError') and
                  result['structuredContent']['tasks'][0]['issue_id'] == 'I1',
                  'bound host thread reads the fixture task')
            other = host.call('thread/start', thread_params)['thread']['id']
            denied = host.call('mcpServer/tool/call', {
                'threadId': other, 'server': 'delegation',
                'tool': 'tasks_list', 'arguments': {},
            })
            check(other != owner and denied.get('isError') is True and
                  'Only the bound fixed coordinator' in
                  denied['content'][0]['text'],
                  'a different actual host thread is rejected')
        except Exception:
            stderr.flush()
            stderr.seek(0)
            print(stderr.read(), file=sys.stderr)
            raise
        finally:
            host.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', default='codex', help='Installed Codex executable')
    args = parser.parse_args()
    executable = shutil.which(args.codex)
    if not executable:
        parser.error('Codex CLI not found; install Codex or provide --codex PATH')
    version = subprocess.run([executable, '--version'], check=True,
                             capture_output=True, text=True).stdout.strip()
    print('Testing ' + version)
    with tempfile.TemporaryDirectory(prefix='delegation-host-smoke-') as directory:
        run(executable, Path(directory).resolve())
    print('5 checks passed; no model turn, GitHub call, or executor launch requested')


if __name__ == '__main__':
    main()
