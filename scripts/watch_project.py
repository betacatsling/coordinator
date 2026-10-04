#!/usr/bin/env python3
"""Debounce one PROJECT.md input block and continue one durable Codex MCP thread."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import shutil
import subprocess
import tempfile
import threading
import time

BEGIN = '<!-- delegation:input -->'
END = '<!-- /delegation:input -->'


def read_input(path):
    text = path.read_text(encoding='utf-8')
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError('PROJECT.md must contain exactly one input marker pair')
    start, finish = text.index(BEGIN) + len(BEGIN), text.index(END)
    if finish < start:
        raise ValueError('Input markers are in reverse order')
    value = text[start:finish].strip()
    return value, hashlib.sha256(value.encode()).hexdigest()


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def append_report_link(document, record):
    """Append only; never replace the user's document body or its input block."""
    marker = '<!-- delegation:report ' + record['relative_path'] + ' -->'
    label = record['description'].replace('[', '\\[').replace(']', '\\]')
    line = f'- [{record["date"]} · {label}]({record["relative_path"]})\n'
    for _ in range(3):
        try:
            # No O_CREAT: an atomic-save gap must not create a new empty PROJECT.md.
            fd = os.open(document, os.O_RDWR | os.O_APPEND)
            with os.fdopen(fd, 'r+', encoding='utf-8') as out:
                text = out.read()
                if marker in text:
                    return True
                if text.count(BEGIN) != 1 or text.count(END) != 1:
                    return False
                if os.fstat(out.fileno()).st_ino != document.stat().st_ino:
                    continue
                header = '\n\n<!-- delegation:reports -->\n## 执行报告\n\n' if '<!-- delegation:reports -->' not in text else '\n'
                os.write(out.fileno(), (header + marker + '\n' + line).encode())
                os.fsync(out.fileno())
            # An editor can atomically replace the path during the append. Retry on the new file.
            if marker in document.read_text(encoding='utf-8'):
                return True
        except (OSError, UnicodeError):
            return False
    return False


def publish_html(project, folder, data, state, args):
    records = state.setdefault('reports', {})
    key = data.get('jobId') or 'error-' + data['input_hash']
    if key not in records:
        now = datetime.now(timezone.utc)
        safe_key = ''.join(c for c in key if c.isalnum() or c in '-_')
        records[key] = {'relative_path': 'reports/' + now.strftime('%Y%m%dT%H%M%S%fZ-') + safe_key + '.html',
                        'date': now.strftime('%Y-%m-%d %H:%M:%S UTC'),
                        'description': data.get('description', '执行结果')[:80], 'linked': False}
    record = records[key]
    html_path = project / record['relative_path']
    html_path.parent.mkdir(exist_ok=True)
    if not html_path.exists():
        result = data.get('text', data.get('error', ''))
        # Keep coordinator headings inside the result panel instead of creating unbounded panels.
        lines, fenced = [], False
        for line in result.splitlines():
            if line.lstrip().startswith(('```', '~~~')):
                fenced = not fenced
            lines.append('### ' + line.lstrip('#').strip() if line.startswith('#') and not fenced else line)
        result = '\n'.join(lines)
        draft = (f'---\ntitle: 项目执行报告\nsubtitle: {record["date"]}\nlang: zh\n---\n'
                 '## A 本轮任务\n' + record['description'] + '\n\n'
                 '## B 执行结果 {span=2}\n' + result + '\n\n'
                 '## C 验证来源\n结果来自本地 MCP coordinator 的实际返回。\n'
                 '报告和入口链接由 watcher 生成。\n\n'
                 '## D 会话记录 {span=2}\n```kv\n'
                 f'状态: {data.get("status", "error")}\n'
                 f'输入版本: {data["input_hash"]}\n'
                 f'Thread: {data.get("threadId", state.get("threadId", "unavailable"))}\n'
                 f'Job: {data.get("jobId", "unavailable")}\n```\n')
        env = dict(os.environ, AM_HOME=str(folder / 'html-data'), AM_NO_UPDATE_CHECK='1', AM_NO_OPEN='1', CI='1')
        rendered = subprocess.run([args.node, str(args.html_cli), 'render', '-', '-o', str(html_path), '--no-open'],
                                  input=draft, capture_output=True, text=True, env=env, timeout=30)
        with open(folder / 'render.log', 'a', encoding='utf-8') as log:
            log.write(rendered.stdout + rendered.stderr)
        if rendered.returncode or not html_path.is_file():
            raise RuntimeError('answer-me-with-html render failed: ' + rendered.stderr)
        record['renderer'] = str(args.html_cli)
    record['linked'] = append_report_link(project / 'PROJECT.md', record)
    return record


class MCP:
    def __init__(self, command, cwd, log):
        self.process = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
        self.responses = queue.Queue()
        self.seq = 0
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()
        self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                               'clientInfo': {'name': 'project-delegation-watch', 'version': '1.0'}})
        self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        names = {t['name'] for t in self.rpc('tools/list')['tools']}
        required = {'codex-start', 'codex-reply-start', 'codex-status', 'codex-result'}
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


def run(args):
    project = args.project.resolve(strict=True)
    document = project / 'PROJECT.md'
    folder = project / '.project-delegation'
    folder.mkdir(exist_ok=True)
    lock = open(folder / 'watch.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('A watcher already owns this project')
    state_path = folder / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    observed, observed_hash = read_input(document)
    pending = (observed, observed_hash) if args.run_current and observed_hash != state.get('last_dispatched_hash') else None
    changed = time.monotonic()
    active = None
    stopped = threading.Event()
    updates = queue.Queue()
    invalid = False
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    hook_stop = folder / ('stop-' + hashlib.sha256(args.hook_session.encode()).hexdigest()) if args.hook_session else None

    def save():
        atomic_write(state_path, json.dumps(state, ensure_ascii=False, indent=2) + '\n')

    def event(kind, **fields):
        entry = {'time': time.time(), 'event': kind, **fields}
        with open(folder / 'events.jsonl', 'a', encoding='utf-8') as out:
            out.write(json.dumps(entry, ensure_ascii=False) + '\n')
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    command = [args.node, str(args.server), '--provider', 'codex', '--approval_policy', 'on-request',
               '--sandbox_mode', 'workspace-write', '--codex-workspace-network=false',
               '--codex-session-retention-days', '0', '--model_reasoning_effort', 'medium']
    if args.bridge_state_root:
        root = args.bridge_state_root.resolve()
        if root == project or project in root.parents:
            raise ValueError('Bridge state must be outside the project workspace')
        command += ['--codex-state-root', str(root)]
    log = open(folder / 'bridge.stderr.log', 'a')
    client = None

    def execute(snapshot, digest, thread_id):
        description = next((line.strip().lstrip('#').strip() for line in snapshot.splitlines() if line.strip()), '执行结果')
        try:
            prompt = (f'Act as the independent project coordinator for {project}. '
                      f'This turn uses immutable input SHA256 {digest}. Advance only the stated project goal '
                      'within this workspace, using the snapshot below. Newer edits are queued separately. '
                      'Do the next useful bounded step yourself; do not spawn agents or invoke delegation MCP. '
                      'Do not edit PROJECT.md, DELEGATION-RESULTS.md, reports/, or .project-delegation. '
                      'Do not install dependencies, change credentials/settings, or use network. '
                      'Return concise progress, changed artifacts, observed checks, and blockers. '
                      'Approval policy is on-request; report approval needs rather than bypassing them.\n\n'
                      + snapshot)
            if thread_id:
                started = client.call('codex-reply-start', {'threadId': thread_id, 'prompt': prompt})
            else:
                started = client.call('codex-start', {'prompt': prompt, 'cwd': str(project),
                                                     'sandbox': 'workspace-write', 'allow_subagents': False})
            job = started['jobId']
            updates.put(('job', {'jobId': job, 'input_hash': digest, 'continued': bool(thread_id)}))
            cursor = started.get('cursor', 0)
            last_thread = thread_id
            approval_reported = False
            while not stopped.is_set():
                status = client.call('codex-status', {'jobId': job, 'cursor': cursor, 'wait_ms': 10000})
                cursor = status.get('cursor', cursor)
                if status.get('threadId') and status['threadId'] != last_thread:
                    last_thread = status['threadId']
                    updates.put(('thread', {'threadId': last_thread}))
                if status.get('state') in {'completed', 'failed', 'canceled', 'cancelled', 'timed_out'}:
                    result = client.call('codex-result', {'jobId': job})
                    updates.put(('done', {'input_hash': digest, 'jobId': job,
                                         'threadId': result.get('threadId', last_thread),
                                         'status': status['state'], 'description': description,
                                         'text': result.get('text', str(result))}))
                    return
                if not approval_reported and (status.get('state') == 'waiting_for_input' or
                                              'waiting for approval' in status.get('message', '').lower()):
                    updates.put(('approval_needed', {'jobId': job, 'threadId': last_thread}))
                    approval_reported = True
        except Exception as exc:
            updates.put(('error', {'input_hash': digest, 'description': description, 'error': str(exc)}))

    event('watch_started', project=str(project), debounce_seconds=10,
          threadId=state.get('threadId'), run_current=args.run_current)
    state['project'] = str(project)
    state['watcher_pid'] = os.getpid()
    state['hook_session'] = args.hook_session
    state['status'] = 'watching'
    save()
    try:
        while not stopped.is_set():
            if hook_stop and hook_stop.exists():
                break
            # Stat/content sampling is local; it never polls a model to detect edits.
            try:
                current, digest = read_input(document)
                if invalid or digest != observed_hash:
                    observed, observed_hash = current, digest
                    changed = time.monotonic()
                    pending = (current, digest) if digest != state.get('last_dispatched_hash') else None
                    event('input_changed', input_hash=digest, queued=active is not None)
                invalid = False
            except (OSError, UnicodeError, ValueError):
                # Atomic replace gaps / partial writes are not instructions to run old input.
                invalid = True
                changed = time.monotonic()
            while not updates.empty():
                kind, data = updates.get_nowait()
                event(kind, **data)
                if kind == 'thread':
                    state['threadId'] = data['threadId']
                elif kind == 'job':
                    state['jobId'] = data['jobId']
                elif kind == 'approval_needed':
                    state['status'] = 'approval_needed'
                    atomic_write(project / 'DELEGATION-RESULTS.md',
                                 '# Delegation paused for approval\n\n'
                                 'The watcher does not approve requests automatically. Stop it and '
                                 'handle this step in an interactive Codex session with an approval UI.\n')
                elif kind in {'done', 'error'}:
                    active = None
                    state['status'] = data.get('status', 'error')
                    if data.get('threadId'):
                        state['threadId'] = data['threadId']
                    report = ('# Delegation results\n\n' +
                              f'Input SHA256: {data["input_hash"]}\n\n' +
                              f'Thread: {state.get("threadId", "unavailable")}\n\n' +
                              data.get('text', data.get('error', '')) + '\n')
                    atomic_write(project / 'DELEGATION-RESULTS.md', report)
                    try:
                        published = publish_html(project, folder, data, state, args)
                        event('html_report', **published)
                    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                        event('html_report_error', error=str(exc))
                save()
            # Recover an append deferred by a partial/atomic save, without another model call.
            try:
                published_text = document.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                published_text = ''
            for record in state.get('reports', {}).values():
                marker = '<!-- delegation:report ' + record['relative_path'] + ' -->'
                if marker not in published_text and (project / record['relative_path']).is_file():
                    if append_report_link(document, record):
                        record['linked'] = True
                        event('html_link_recovered', relative_path=record['relative_path'])
                        save()
            if not invalid and active is None and pending and time.monotonic() - changed >= 10:
                if not pending[0]:
                    pending = None
                else:
                    if client is None:
                        client = MCP(command, project, log)
                    if stopped.is_set() or (hook_stop and hook_stop.exists()):
                        break
                    # MCP startup may take time; edits during startup restart the debounce.
                    try:
                        latest, latest_hash = read_input(document)
                    except (OSError, UnicodeError, ValueError):
                        invalid = True
                        changed = time.monotonic()
                        continue
                    if latest_hash != observed_hash:
                        observed, observed_hash = latest, latest_hash
                        pending = (latest, latest_hash) if latest_hash != state.get('last_dispatched_hash') else None
                        changed = time.monotonic()
                        event('input_changed', input_hash=latest_hash, queued=False)
                        continue
                    snapshot, digest = pending
                    pending = None
                    state.update(last_dispatched_hash=digest, status='running')
                    save()
                    event('dispatch', input_hash=digest, threadId=state.get('threadId'))
                    active = threading.Thread(target=execute, args=(snapshot, digest, state.get('threadId')), daemon=True)
                    active.start()
            stopped.wait(.25)
    finally:
        stopped.set()
        if client:
            client.close()
        if active:
            active.join(timeout=2)
        state['status'] = 'stopped'
        save()
        event('watch_stopped')
        log.close()
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path, help='Only this project is watched')
    parser.add_argument('--run-current', action='store_true', help='Also submit current input after 10 quiet seconds')
    parser.add_argument('--node', default=os.environ.get('PROJECT_DELEGATION_NODE') or shutil.which('node') or 'node')
    parser.add_argument('--server', type=Path, default=Path(os.environ['PROJECT_DELEGATION_SERVER']) if os.environ.get('PROJECT_DELEGATION_SERVER') else None, help='mcp-agents server.js; or set PROJECT_DELEGATION_SERVER')
    parser.add_argument('--bridge-state-root', type=Path, help='Optional external state root for isolated tests')
    parser.add_argument('--html-cli', type=Path, default=Path(os.environ.get('PROJECT_DELEGATION_HTML_CLI', str(Path.home()/'.codex/skills/answer-me-with-html/scripts/am.mjs'))))
    parser.add_argument('--hook-session', default='', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.server is None or not args.server.is_file():
        parser.error('Set --server or PROJECT_DELEGATION_SERVER to an installed mcp-agents server.js')
    if not args.html_cli.is_file():
        parser.error('Set --html-cli or PROJECT_DELEGATION_HTML_CLI to an installed answer-me-with-html am.mjs')
    run(args)
