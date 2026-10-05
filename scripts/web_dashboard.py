#!/usr/bin/env python3
"""Read-only local dashboard. Never starts workers, writes runtime state or contacts GitHub."""
import argparse
import hashlib
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MAX_JSON = 4 * 1024 * 1024
MAX_REPORT = 8 * 1024 * 1024
ACTIVE = {'reserved', 'running', 'recovery_required', 'waiting_for_input', 'initializing'}
STATUSES = ACTIVE | {'accepted', 'verified', 'completed', 'failed', 'canceled', 'timed_out', 'checks_failed', 'verification_failed', 'preparation_failed', 'superseded'}
STATIC = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/app.css': ('app.css', 'text/css')}
SCOPE = ('workspace', 'repository', 'project_node_id', 'user_login')
SECRET = re.compile(r'(?i)(?:\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{8,})\b|(?:bearer\s+\S+)|(?:-----BEGIN[^\n]*PRIVATE KEY-----[\s\S]*))')
ASSIGNMENT = re.compile(r'(?i)\b(token|password|secret|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+')


def text(value, limit=240):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    value = str(value)
    value = SECRET.sub('[redacted]', value)
    value = ASSIGNMENT.sub(r'\1=[redacted]', value)
    return ''.join(c for c in value if c >= ' ' and c != '\x7f')[:limit]


def stamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')
        except (ValueError, OverflowError, OSError):
            pass
    return None


def status(value):
    return value if isinstance(value, str) and value in STATUSES else 'unknown'


def safe_bytes(path, root, limit):
    """Reject symlinks throughout the selected subtree, oversized/nonregular files."""
    path, root = Path(path), Path(root)
    relative = path.relative_to(root)
    if '..' in relative.parts or root.is_symlink():
        raise ValueError('unsafe path')
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlink refused')
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('missing, nonregular or oversized file')
    before = path.stat()
    with path.open('rb') as stream:
        import os
        opened = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError('file changed')
        body = stream.read(limit + 1)
    after = path.stat()
    if len(body) > limit or (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino):
        raise ValueError('file changed')
    return body, after.st_mtime


class Dashboard:
    def __init__(self, configs, web_root=None):
        self.projects = {}
        self.cache = {}
        self.lock = threading.RLock()
        self.web_root = Path(web_root or Path(__file__).resolve().parents[1] / 'web')
        for filename in configs:
            path = Path(filename).resolve(strict=True)
            if path.stat().st_size > MAX_JSON:
                raise ValueError('Config too large')
            config = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(config, dict) or not all(isinstance(config.get(k), str) and config[k] for k in SCOPE):
                raise ValueError('Config requires workspace, repository, project_node_id and user_login')
            if not Path(config['workspace']).is_absolute():
                raise ValueError('Workspace must be absolute')
            workspace = Path(config['workspace']).resolve()
            scope = {k: config[k] for k in SCOPE}
            scope['workspace'] = str(workspace)
            pid = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
            limit = config.get('max_parallel_executors', 3)
            self.projects[pid] = {'scope': scope, 'root': workspace, 'limit': limit if isinstance(limit, int) and 1 <= limit <= 3 else None,
                                  'name': text(config.get('name') or config['repository'])}

    def read(self, project, filename):
        root = project['root']
        path = root / '.project-delegation' / 'runtime' / filename
        key = str(path)
        try:
            body, modified = safe_bytes(path, root, MAX_JSON)
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError('JSON object required')
            if filename in ('jobs.json', 'binding.json', 'notifier.json') and value.get('scope') != project['scope']:
                raise ValueError('scope mismatch')
            expected = {'jobs.json': ('jobs', dict), 'binding.json': ('binding', dict), 'notifier.json': ('outbox', list)}.get(filename)
            if expected and not isinstance(value.get(expected[0]), expected[1]):
                raise ValueError('Invalid state structure')
            self.cache[key] = (value, modified)
            return value, {'status': 'ok', 'modified_at': stamp(modified), 'stale': False, 'error': None}
        except (OSError, ValueError, TypeError, RecursionError):
            # Do not disclose parser errors or file content. A partial producer write
            # retains the last successful snapshot, clearly marked stale.
            value, modified = self.cache.get(key, ({}, None))
            return value, {'status': 'unavailable', 'modified_at': stamp(modified), 'stale': True,
                           'error': 'Missing, invalid, unsafe or mismatched state; last good snapshot shown if available'}

    def project_info(self, pid):
        p = self.projects[pid]
        return {'id': pid, 'name': p['name'], 'repository': text(p['scope']['repository']),
                'workspace': text(p['root'], 500) if isinstance(p['root'], str) else text(str(p['root']), 500),
                'available': p['root'].is_dir()}

    def report_files(self, pid):
        root = self.projects[pid]['root']
        reports = root / 'reports'
        found = {}
        if reports.is_symlink() or not reports.is_dir():
            return found
        # Only direct report files, never recursive arbitrary workspace browsing.
        for path in sorted(reports.iterdir())[:200]:
            if path.suffix.lower() not in {'.html', '.htm', '.pdf', '.txt', '.md'}:
                continue
            try:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REPORT:
                    continue
                rid = hashlib.sha256(path.name.encode()).hexdigest()[:20]
                found[rid] = path
            except OSError:
                continue
        return found

    def detail(self, pid, filters=None):
        with self.lock:
            return self._detail(pid, filters or {})

    def _detail(self, pid, filters):
        p = self.projects[pid]
        binding, bm = self.read(p, 'binding.json')
        ledger, jm = self.read(p, 'jobs.json')
        notifier, nm = self.read(p, 'notifier.json')
        sources = {'binding': bm, 'jobs': jm, 'notifier': nm}
        warnings = ['Live worker and coordinator liveness is unknown. Counts reflect saved local state, not verified running processes.',
                    'Tasks include locally saved jobs and notifier entries; this is not a live GitHub board.']
        warnings += [name + ': ' + meta['error'] for name, meta in sources.items() if meta['error']]
        tasks, executors, events = {}, [], []
        jobs = ledger.get('jobs', {})
        jobs = jobs if isinstance(jobs, dict) else {}
        counts = {}
        if len(jobs) > 1000:
            warnings.append('Job view and counts limited to the first 1000 saved jobs')
        for jid, job in list(jobs.items())[:1000]:
            if not isinstance(job, dict) or not isinstance(jid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', jid):
                continue
            task = job.get('task', {})
            task = task if isinstance(task, dict) else {}
            tid = text(task.get('issue_id') or jid)
            current = status(job.get('status'))
            counts[current] = counts.get(current, 0) + 1
            # Receipt filename is derived from the validated ledger key, never a supplied path.
            receipt, rm = self.read(p, jid + '.receipt.json')
            title = text(task.get('title')) or 'Untitled saved task'
            url = self.issue_url(task.get('url'), p['scope']['repository'])
            dependencies = job.get('dependencies', [])
            dependencies = [text(d if isinstance(d, str) else d.get('job_id')) for d in dependencies[:50] if isinstance(d, (str, dict))] if isinstance(dependencies, list) else []
            dependencies = [d for d in dependencies if d]
            tasks[tid] = {'id': tid, 'title': title, 'status': current, 'assignee': None, 'updated_at': stamp(job.get('updated_at') or job.get('created_at')), 'url': url, 'dependencies': dependencies}
            paths = job.get('owned_paths', [])
            paths = [text(v) for v in paths[:100] if isinstance(v, str)] if isinstance(paths, list) else []
            checks = receipt.get('checks', [])
            checks = [{'name': 'Check ' + str(i + 1), 'status': 'passed' if c.get('returncode') == 0 else ('failed' if isinstance(c.get('returncode'), int) else 'unknown'),
                       'returncode': c.get('returncode') if isinstance(c.get('returncode'), int) else None,
                       'passed': c.get('returncode') == 0} for i, c in enumerate(checks[:50]) if isinstance(c, dict)] if isinstance(checks, list) else []
            executors.append({'id': jid, 'task_id': tid, 'title': title, 'status': current, 'executor_status': status(receipt.get('status')),
                              'session_id': text(receipt.get('thread_id')), 'workspace': text(receipt.get('workspace'), 500),
                              'owned_paths': paths, 'checks': checks, 'result': None, 'report_url': None,
                              'updated_at': stamp(receipt.get('completed_at') or receipt.get('submitted_at') or job.get('updated_at') or job.get('created_at')),
                              'live_status': 'unknown', 'receipt': rm})
        outbox = notifier.get('outbox', [])
        for entry in outbox[:1000] if isinstance(outbox, list) else []:
            if not isinstance(entry, dict):
                continue
            t = entry.get('task', {})
            if isinstance(t, dict) and text(t.get('issue_id')) and text(t.get('issue_id')) not in tasks:
                tid = text(t['issue_id'])
                tasks[tid] = {'id': tid, 'title': text(t.get('title')) or 'Saved task notice', 'status': 'noticed', 'assignee': None,
                              'updated_at': stamp(entry.get('created_at')), 'url': self.issue_url(t.get('url'), p['scope']['repository']), 'dependencies': []}
            events.append({'id': text(entry.get('id')), 'timestamp': stamp(entry.get('created_at')), 'type': 'notice',
                           'message': 'Saved board notification', 'executor_id': None})
        seen = notifier.get('seen', {})
        for entry in list(seen.values())[:1000] if isinstance(seen, dict) else []:
            t = entry.get('task', {}) if isinstance(entry, dict) else {}
            if isinstance(t, dict) and text(t.get('issue_id')) and text(t.get('issue_id')) not in tasks:
                tid = text(t['issue_id'])
                tasks[tid] = {'id': tid, 'title': text(t.get('title')) or 'Saved baseline task', 'status': 'noticed',
                              'assignee': None, 'updated_at': None, 'url': self.issue_url(t.get('url'), p['scope']['repository']), 'dependencies': []}
        reports = []
        try:
            for rid, path in self.report_files(pid).items():
                st = path.stat()
                reports.append({'id': rid, 'title': text(path.name), 'url': '/reports/' + pid + '/' + rid,
                                'updated_at': stamp(st.st_mtime), 'size': st.st_size})
        except OSError:
            warnings.append('Report directory unavailable')
        active = sum(counts.get(s, 0) for s in ACTIVE)
        task_values = list(tasks.values())
        query = filters.get('search', [''])[0].lower()[:200]
        selected_status = filters.get('status', [''])[0]
        def selected(item):
            return (not selected_status or item['status'] == selected_status) and (not query or query in (item['title'] + ' ' + item['id']).lower())
        b = binding.get('binding', {})
        b = b if isinstance(b, dict) else {}
        return {'project': self.project_info(pid), 'updated_at': stamp(time.time()),
                'source_updated_at': max((v['modified_at'] for v in sources.values() if v['modified_at']), default=None),
                'available': any(v['status'] == 'ok' for v in sources.values()), 'stale': any(v['stale'] for v in sources.values()),
                'warnings': warnings, 'sources': sources,
                'coordinator': {'thread_id': text(b.get('provider_thread_id')), 'status': 'saved binding' if b else 'unknown',
                                'workspace': text(str(p['root']), 500), 'verified_at': None, 'live_status': 'unknown'},
                'summary': {'active': active, 'limit': p['limit'], 'waiting': counts.get('waiting_for_input', 0),
                            'blocked': sum(counts.get(s, 0) for s in ('recovery_required', 'failed', 'checks_failed', 'verification_failed', 'preparation_failed', 'timed_out')),
                            'completed': sum(counts.get(s, 0) for s in ('accepted', 'completed', 'verified')),
                            'running_verified': None, 'active_unknown': active, 'total_jobs': sum(counts.values()), 'status_counts': counts},
                'tasks': [t for t in task_values if selected(t)], 'executors': [e for e in executors if selected(e)],
                'events': events, 'reports': reports}

    @staticmethod
    def issue_url(value, repository):
        if isinstance(value, str) and re.fullmatch(r'https://github\.com/' + re.escape(repository) + r'/issues/[1-9][0-9]*', value):
            return value
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond()

    def do_HEAD(self):
        self.respond(head=True)

    def do_POST(self):
        self.send_error(405, 'Read-only dashboard')

    def respond(self, head=False):
        port = self.server.server_port
        if self.headers.get('Host') not in {'127.0.0.1:' + str(port), 'localhost:' + str(port)}:
            self.send_error(403, 'Loopback Host required')
            return
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or '%' in parsed.path or '\\' in parsed.path or '..' in parsed.path.split('/'):
            self.send_error(404)
            return
        app = self.server.dashboard
        path = parsed.path
        disposition = None
        try:
            if path == '/api/projects':
                with app.lock:
                    data = {'projects': [dict(app.project_info(pid), available=app.detail(pid)['available']) for pid in app.projects], 'updated_at': stamp(time.time())}
                body, mime = json.dumps(data).encode(), 'application/json'
            elif path.startswith('/api/projects/') and path.count('/') == 3:
                data = app.detail(path.split('/')[-1], parse_qs(parsed.query))
                body, mime = json.dumps(data).encode(), 'application/json'
            elif path.startswith('/reports/') and path.count('/') == 3:
                _, _, pid, rid = path.split('/')
                report = app.report_files(pid)[rid]
                body, _ = safe_bytes(report, app.projects[pid]['root'], MAX_REPORT)
                mime = 'application/octet-stream'
                disposition = 'attachment; filename="report' + report.suffix.lower() + '"'
            elif path in STATIC:
                filename, mime = STATIC[path]
                body, _ = safe_bytes(app.web_root / filename, app.web_root, MAX_REPORT)
            else:
                raise KeyError(path)
        except (OSError, ValueError, KeyError, TypeError):
            self.send_error(404, 'Unavailable')
            return
        self.send_response(200)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if mime != 'application/octet-stream' else ''))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "sandbox; default-src 'none'" if disposition else "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if disposition:
            self.send_header('Content-Disposition', disposition)
        self.end_headers()
        if not head:
            self.wfile.write(body)


def make_server(configs, port=18766, web_root=None):
    dashboard = Dashboard(configs, web_root)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.dashboard = dashboard
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', action='append', required=True, type=Path, help='Project config; repeat to show multiple projects')
    parser.add_argument('--port', type=int, default=18766)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('Port must be between 0 and 65535')
    try:
        server = make_server(args.config, args.port)
    except (OSError, ValueError, TypeError) as error:
        parser.error('Cannot load selected project configs: ' + type(error).__name__)
    print('Read-only dashboard: http://127.0.0.1:' + str(server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
