#!/usr/bin/env python3
"""Bind the actual current native Codex thread to a fresh project runtime."""
import argparse
import json
import os
import subprocess
from pathlib import Path
import uuid

from app_server_client import AppServer, endpoint
from state_io import atomic_write
from dashboard_launcher import launch_dashboard, stop_dashboard
from notifier_status import service_status, config_signature
from platform_support import acquire_lock

SCOPE_KEYS = ('workspace', 'repository', 'project_node_id', 'user_login')


def bootstrap(config_path, *, cwd=None, environment=None, inspect=False,
              client_factory=AppServer, open_dashboard=True, stop=False):
    """Verify native identity before creating or reusing a project binding.

    The injectable client is for offline tests. Production always uses the native
    AppServer thread/read response; no caller-supplied thread override exists.
    """
    path = Path(config_path).resolve(strict=True)
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in SCOPE_KEYS:
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError('Missing project scope: ' + key)
    if not Path(config['workspace']).is_absolute():
        raise ValueError('Workspace must be absolute')
    workspace = Path(config['workspace']).resolve(strict=True)
    current = Path(cwd or os.getcwd()).resolve(strict=True)
    if current != workspace and workspace not in current.parents:
        raise ValueError('Current working directory is outside selected workspace')
    scope = {key: config[key] for key in SCOPE_KEYS}
    scope['workspace'] = str(workspace)
    env = os.environ if environment is None else environment
    identity = env.get('CODEX_THREAD_ID', '')
    try:
        if str(uuid.UUID(identity)) != identity:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Valid runtime CODEX_THREAD_ID required; do not paste or override identities')
    root = workspace / '.project-delegation' / 'runtime'
    folder = Path(config.get('state_directory', root)).resolve()
    if workspace not in root.resolve().parents or folder != root.resolve():
        raise ValueError('Fresh state must remain within .project-delegation/runtime')
    binding_path = folder / 'binding.json'
    # A status read does not create directories or lock files.
    if (inspect or stop) and not binding_path.exists():
        return {'status': 'uninitialized', 'scope': scope, 'binding_path': str(binding_path)}
    if not inspect and not stop:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = None
    try:
        if not inspect and not stop:
            lock = open(folder / 'binding.lock', 'a+b')
            acquire_lock(lock)
        existing = json.loads(binding_path.read_text(encoding="utf-8")) if binding_path.exists() else None
        if existing is not None:
            if not isinstance(existing, dict) or not isinstance(existing.get('binding'), dict):
                raise ValueError('Invalid existing binding; refusing overwrite')
            binding = existing['binding']
            if (existing.get('schema') != 1 or existing.get('scope') != scope
                    or binding.get('scope') != scope
                    or binding.get('transport') != 'app_server'
                    or binding.get('provider_thread_id') != identity):
                raise ValueError('Existing binding belongs to another owner or scope; refusing overwrite')
        elif any(folder.iterdir()):
            if any(p.name != 'binding.lock' for p in folder.iterdir()):
                raise ValueError('Unbound runtime contains existing data; refusing initialization')
        if stop:
            return stop_dashboard(path, scope, identity)
        native_error = None
        try:
            socket_path = config.get('app_server_socket') or endpoint(config['codex'])
            with (client_factory(socket_path, codex=config['codex']) if client_factory is AppServer
                  else client_factory(socket_path)) as client:
                thread = client.thread(identity, workspace)
            # Verify explicitly even for custom fixture backends.
            if (thread.get('id') != identity or not thread.get('cwd')
                    or Path(thread['cwd']).resolve() != workspace
                    or thread.get('status', {}).get('type') not in ('active', 'idle')):
                raise ValueError('Native thread identity, workspace or loaded status differs')
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            if not inspect:
                raise
            native_error = str(error)
        if existing is None:
            value = {'schema': 1, 'scope': scope, 'binding': {
                'transport': 'app_server', 'provider_thread_id': identity,
                'scope': scope, 'socket_path': str(socket_path)}}
            atomic_write(binding_path, json.dumps(value, indent=2) + '\n')
            os.chmod(binding_path, 0o600)
        result = {'status': 'verified' if inspect else ('reused' if existing else 'initialized'),
                'scope': scope, 'provider_thread_id': identity,
                'binding_path': str(binding_path)}
        if inspect:
            result['notifications'] = service_status(folder, scope, identity, config_signature(config))
            result['coordinator_available'] = native_error is None
            if native_error:
                result.update(status='unavailable', reason=native_error)
        else:
            dashboard = config.get('dashboard', {})
            auto_open = open_dashboard and (not isinstance(dashboard, dict) or dashboard.get('auto_open', True) is not False)
            result.update(launch_dashboard(path, scope, identity, auto_open=auto_open, environment=env))
        return result
    finally:
        if lock is not None:
            lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--no-open', action='store_true', help='Start dashboard without opening a browser')
    parser.add_argument('command', choices=('init', 'status', 'stop'))
    args = parser.parse_args()
    try:
        value = bootstrap(args.config, inspect=args.command == 'status', open_dashboard=not args.no_open,
                          stop=args.command == 'stop')
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'blocked', 'reason': str(error)}))
        return 1
    print(json.dumps(value))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
