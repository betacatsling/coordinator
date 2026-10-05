"""Read-only health for the unified local project notification service.

This is a project process, not an operating-system login or boot service. Saved
PID metadata alone never proves health: a live process and fresh heartbeat must
both match the fixed project binding and configuration.
"""
import hashlib
import json
import math
from pathlib import Path
import time

from platform_support import process_alive

SERVICE = 'project-delegation-notifier-v1'


def config_signature(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def service_status(folder, scope, owner, signature, *, now=None):
    """Read health without acquiring locks, creating files or probing a session."""
    try:
        state = read_json(Path(folder) / 'notifier-service.json')
    except (OSError, ValueError):
        return {'status': 'blocked', 'running': False, 'healthy': False,
                'coordinator_available': None, 'last_error': 'Notification status is unreadable'}
    return evaluate_status(state, scope, owner, signature, now=now)


def evaluate_status(state, scope, owner, signature, *, now=None):
    if not state:
        return {'status': 'not_running', 'running': False, 'healthy': False,
                'coordinator_available': None}
    result = dict(state)
    identity_matches = (state.get('service') == SERVICE and state.get('scope') == scope
                        and state.get('owner') == owner and state.get('config_signature') == signature)
    alive = process_alive(state.get('pid'))
    now = time.time() if now is None else now
    heartbeat = state.get('heartbeat_at')
    interval = state.get('interval', 10)
    valid_interval = isinstance(interval, (int, float)) and not isinstance(interval, bool) and math.isfinite(interval) and interval > 0
    fresh = (isinstance(heartbeat, (int, float)) and not isinstance(heartbeat, bool)
             and valid_interval and 0 <= now - heartbeat <= max(60, 3 * interval))
    success = state.get('last_success_at')
    recent_success = (isinstance(success, (int, float)) and not isinstance(success, bool)
                      and valid_interval and 0 <= now - success <= max(60, 3 * interval))
    result.update(running=bool(alive and state.get('status') not in ('blocked', 'stopped')), healthy=bool(identity_matches and alive and fresh
                  and state.get('status') in ('running', 'checking') and state.get('initialized')
                  and recent_success
                  and state.get('coordinator_available') is True))
    if not identity_matches:
        result.update(status='blocked', healthy=False, running=False, last_error='Watcher configuration or binding differs; refusing reuse')
    elif not alive:
        result.update(status='stopped', healthy=False, coordinator_available=None)
    elif not fresh:
        result.update(status='stale', healthy=False, coordinator_available=None)
    return result

