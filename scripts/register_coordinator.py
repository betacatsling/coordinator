#!/usr/bin/env python3
"""Enroll the current runtime-provided Codex thread; never activate a controller."""
import argparse
import json
import os
from pathlib import Path
import time
import uuid
from watch_project import atomic_write


def enroll(config_path, environment=None, cwd=None):
    environment = os.environ if environment is None else environment
    config_path = Path(config_path).resolve(strict=True)
    config = json.loads(config_path.read_text())
    workspace = Path(config['workspace']).resolve(strict=True)
    if Path(cwd or os.getcwd()).resolve() != workspace:
        raise ValueError('Registration must run in the configured project root')
    provider = environment.get('CODEX_THREAD_ID', '')
    try:
        if str(uuid.UUID(provider)) != provider:
            raise ValueError()
    except ValueError:
        raise ValueError('Missing valid runtime CODEX_THREAD_ID; do not guess or pass a thread ID')
    scope = {key: config[key] for key in ('project_node_id', 'repository', 'user_login')}
    scope['workspace'] = str(workspace)
    folder = Path(config.get('state_directory', workspace / '.project-delegation/github-acpx')).resolve() / 'enrollments'
    try:
        folder.relative_to(workspace / '.project-delegation')
    except ValueError:
        raise ValueError('Controller state directory must remain inside project .project-delegation')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / (provider + '.json')
    receipt = dict(scope=scope, provider_thread_id=provider, status='pending',
                   identity_source='runtime:CODEX_THREAD_ID', created_at=time.time(),
                   config_path=str(config_path))
    if path.exists():
        existing = json.loads(path.read_text())
        if existing['scope'] != scope or existing['provider_thread_id'] != provider:
            raise ValueError('Existing enrollment has a different scope')
        return path, existing
    atomic_write(path, json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    os.chmod(path, 0o600)
    return path, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    path, receipt = enroll(args.config)
    print(json.dumps({'registration': str(path), 'status': receipt['status'],
                      'provider_thread_id': receipt['provider_thread_id'],
                      'active': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
