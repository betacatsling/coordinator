#!/usr/bin/env python3
"""One local project service for dashboard and notifications; no OS startup service."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import webbrowser

from platform_support import acquire_lock, detached_process_options, process_alive
from state_io import atomic_write
from notifier_status import config_signature, service_status, SERVICE as NOTIFIER_SERVICE

SERVICE = 'project-delegation-dashboard-v1'


def project_id(scope):
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]


def local_browser_available(environment):
    if any(environment.get(key) for key in ('SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY', 'CI')):
        return False
    if sys.platform == 'win32':
        return bool(environment.get('SESSIONNAME')) and environment['SESSIONNAME'].lower() != 'services'
    if sys.platform == 'darwin':
        # A Mac can run without a logged-in graphical session. Do not mistake
        # every non-SSH process for a desktop merely because this is macOS.
        try:
            return subprocess.run(
                ['/bin/launchctl', 'print', 'gui/' + str(os.getuid())],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=1, check=False).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    return bool(environment.get('DISPLAY') or environment.get('WAYLAND_DISPLAY'))


def healthy(state, pid):
    """Use direct loopback HTTP, never proxy settings or a URL from saved state."""
    port = state.get('port')
    if (state.get('project_id') != pid or not isinstance(port, int)
            or isinstance(port, bool) or not 1 <= port <= 65535
            or not isinstance(state.get('instance'), str)):
        return False
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=0.5)
    try:
        connection.request('GET', '/api/health')
        response = connection.getresponse()
        data = json.loads(response.read(65537))
        return (response.status == 200 and data.get('service') == SERVICE
                and data.get('instance') == state['instance']
                and data.get('project_ids') == [pid])
    except (OSError, ValueError, TypeError, AttributeError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def read_state(path):
    try:
        if path.stat().st_size > 65536:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def launch_dashboard(config_path, scope, owner, *, auto_open=True, environment=None):
    """Return current-attempt results; browser success means accepted open request."""
    result = {'dashboard_url': None, 'opened': False, 'server_started': False}
    environment = os.environ if environment is None else environment
    local = local_browser_available(environment)
    result['remote_access_required'] = not local
    folder = Path(scope['workspace']) / '.project-delegation' / 'runtime'
    state_path = folder / 'dashboard.json'
    pending_path = folder / 'dashboard-start.json'
    pid = project_id(scope)
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    signature = config_signature(config)
    try:
        # Serialize startup and browser-open bookkeeping across repeated init calls.
        with (folder / 'dashboard.lock').open('a+b') as lock:
            deadline = time.monotonic() + 8
            while True:
                try:
                    acquire_lock(lock, blocking=False)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Dashboard startup is busy; retry initialization')
                    time.sleep(0.05)
            state = read_state(state_path)
            if state and process_alive(state.get('pid')) and (state.get('owner') != owner or state.get('config_signature') != signature):
                raise RuntimeError('Project service configuration or binding differs; stop the original service before restarting')
            if not healthy(state, pid):
                if process_alive(state.get('pid')):
                    raise RuntimeError('Project service process is alive but unavailable; no duplicate started')
                # The same lock is held by the entire HTTP+watcher process.
                with (folder / 'project-service.lock').open('a+b') as ownership:
                    try:
                        acquire_lock(ownership, blocking=False)
                    except BlockingIOError:
                        raise RuntimeError('Project service owns the runtime lock; no duplicate started') from None
                with (folder / 'notifier.lock').open('a+b') as ownership:
                    try:
                        acquire_lock(ownership, blocking=False)
                    except BlockingIOError:
                        raise RuntimeError('An existing watcher owns the project lock; no duplicate started') from None
                pending = read_state(pending_path)
                if pending.get('project_id') == pid and process_alive(pending.get('pid')):
                    raise RuntimeError('An earlier dashboard startup is still pending; no duplicate launched')
                # Child binds an ephemeral port if the preferred port is occupied.
                # It publishes readiness only after owning the listening socket.
                with (folder / 'dashboard.log').open('ab') as log:
                    process = subprocess.Popen(
                        [sys.executable, str(Path(__file__).resolve()), '--serve',
                         '--config', str(Path(config_path).resolve()), '--state', str(state_path)],
                        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        **detached_process_options())
                atomic_write(pending_path, json.dumps({'pid': process.pid, 'project_id': pid}) + '\n')
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    state = read_state(state_path)
                    if healthy(state, pid):
                        result['server_started'] = True
                        pending_path.unlink(missing_ok=True)
                        break
                    if process.poll() is not None:
                        raise RuntimeError('Dashboard process exited before becoming ready')
                    time.sleep(0.05)
                else:
                    raise RuntimeError('Dashboard did not become ready in time; retry initialization')
            result['notifications'] = service_status(folder, scope, owner, signature)
            if not result['notifications']['healthy']:
                result['notification_warning'] = result['notifications'].get('last_error') or 'Notification watcher is not ready; check service status before relying on wake-ups'
            result['dashboard_url'] = 'http://127.0.0.1:' + str(state['port']) + '/?project=' + pid
            if auto_open and local and state.get('opened_for') != owner:
                result['opened'] = bool(webbrowser.open(result['dashboard_url'], new=2))
                if result['opened']:
                    state['opened_for'] = owner
                    atomic_write(state_path, json.dumps(state) + '\n')
                else:
                    result['dashboard_warning'] = 'Default browser did not accept the open request; use dashboard_url'
            elif auto_open and not local:
                result['dashboard_warning'] = 'No local desktop detected; dashboard_url is local to this host and remote access must be arranged separately'
    except Exception as error:
        # Dashboard is optional: binding and MCP must remain usable on failures.
        result['dashboard_warning'] = 'Project service launch failed: ' + str(error)
        result.setdefault('notifications', {'status': 'blocked', 'running': False, 'healthy': False,
                                           'coordinator_available': None, 'last_error': str(error)})
    return result


def stop_dashboard(config_path, scope, owner):
    """Request shutdown of the matching project instance, never signal a PID."""
    folder = Path(scope['workspace']) / '.project-delegation' / 'runtime'
    state = read_state(folder / 'dashboard.json')
    if not state or not process_alive(state.get('pid')):
        return {'status': 'stopped', 'service_stopped': True}
    if (state.get('owner') != owner or not healthy(state, project_id(scope))):
        raise RuntimeError('Cannot verify the current project service; refusing to stop an unknown process')
    atomic_write(folder / 'dashboard-stop.json', json.dumps({'instance': state['instance'], 'owner': owner}) + '\n')
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if not process_alive(state['pid']):
            return {'status': 'stopped', 'service_stopped': True}
        time.sleep(0.05)
    return {'status': 'stopping', 'service_stopped': False,
            'reason': 'Shutdown requested; active notification I/O is finishing'}


def serve(config_path, state_path):
    # One lifetime lock covers both HTTP and notification processing.
    with (Path(state_path).parent / 'project-service.lock').open('a+b') as lock:
        acquire_lock(lock, blocking=False)
        _serve(config_path, state_path)


def _serve(config_path, state_path):
    from board_notifier import BoardNotifier
    from web_dashboard import make_server
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    folder = Path(state_path).parent
    binding = read_state(folder / 'binding.json')
    owner = binding.get('binding', {}).get('provider_thread_id')
    scope = {key: config[key] for key in ('workspace', 'repository', 'project_node_id', 'user_login')}
    scope['workspace'] = str(Path(scope['workspace']).resolve())
    signature = config_signature(config)
    try:
        server = make_server([config_path], 18766)
    except OSError:
        server = make_server([config_path], 0)
    stopped = threading.Event()
    def notifications():
        try:
            with BoardNotifier(config_path) as notifier:
                notifier.watch(initialize_current=True, instance=server.instance, stop_event=stopped)
        except Exception as error:
            # If construction itself failed, there was no watcher to record it.
            state = read_state(folder / 'notifier-service.json')
            if state.get('instance') != server.instance:
                atomic_write(folder / 'notifier-service.json', json.dumps({
                    'service': NOTIFIER_SERVICE, 'scope': scope, 'owner': owner,
                    'config_signature': signature, 'instance': server.instance,
                    'pid': os.getpid(), 'interval': 10, 'heartbeat_at': time.time(),
                    'status': 'blocked', 'initialized': False,
                    'coordinator_available': None, 'last_error': str(error)}) + '\n')
    def shutdown_monitor():
        while not stopped.wait(0.2):
            request = read_state(folder / 'dashboard-stop.json')
            if request.get('instance') == server.instance and request.get('owner') == owner:
                stopped.set()
                server.shutdown()
    worker = threading.Thread(target=notifications, name='project-notifications', daemon=True)
    monitor = threading.Thread(target=shutdown_monitor, name='project-shutdown', daemon=True)
    try:
        ids = list(server.dashboard.projects)
        state = {'port': server.server_port, 'pid': os.getpid(), 'instance': server.instance,
                 'project_id': ids[0], 'owner': owner, 'config_signature': signature}
        worker.start()
        monitor.start()
        atomic_write(Path(state_path), json.dumps(state) + '\n')
        server.serve_forever()
    finally:
        stopped.set()
        server.server_close()
        worker.join(timeout=2)
        monitor.join(timeout=1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true', required=True)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path)
    args = parser.parse_args()
    serve(args.config, args.state)
