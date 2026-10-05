#!/usr/bin/env python3
"""Verify an enrolled native thread, then explicitly adopt it while the owner is stopped."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from state_io import atomic_write


def private_write(path, text):
    atomic_write(path, text)
    os.chmod(path, 0o600)


def load_context(config_path, registration):
    config_path = Path(config_path).resolve(strict=True)
    registration = Path(registration).resolve(strict=True)
    config = json.loads(config_path.read_text())
    receipt = json.loads(registration.read_text())
    scope = {key: config[key] for key in ('project_node_id', 'repository', 'user_login')}
    workspace = Path(config['workspace']).resolve(strict=True)
    scope['workspace'] = str(workspace)
    if receipt['scope'] != scope or receipt.get('identity_source') != 'runtime:CODEX_THREAD_ID':
        raise ValueError('Enrollment scope or runtime provenance differs')
    folder = Path(config.get('state_directory', workspace / '.project-delegation/github-acpx')).resolve()
    try:
        folder.relative_to(workspace / '.project-delegation')
    except ValueError:
        raise ValueError('Controller state directory must remain inside project .project-delegation')
    if registration.parent != folder / 'enrollments':
        raise ValueError('Enrollment is outside this controller state directory')
    return config_path, config, registration, receipt, folder


def assert_quiescent(state, expected_old):
    old = state.get('binding', {}).get('provider_thread_id')
    if old != expected_old:
        raise ValueError('Old owner changed; explicit handoff target no longer matches')
    if any(item.get('status') == 'running' for item in state.get('queue', [])):
        raise ValueError('An existing task is running; finish it before handoff')


def command(config, agent_command, arguments):
    argv = [config['node'], config['acpx'], '--cwd', config['workspace'], '--agent', agent_command,
            '--format', 'json', '--suppress-reads', '--deny-all', '--ttl', '1', '--timeout', '90'] + arguments
    result = subprocess.run(argv, env=dict(os.environ, CODEX_PATH=config['codex']),
                            capture_output=True, text=True, timeout=110)
    if result.returncode:
        raise RuntimeError('ACP resume failed; no replacement is allowed; old owner remains unchanged')
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def response(events, expected):
    ids, chunks, ended = set(), [], False
    for event in events:
        params = event.get('params', {})
        if params.get('sessionId'):
            ids.add(params['sessionId'])
        update = params.get('update', {})
        if update.get('sessionUpdate') == 'agent_message_chunk':
            chunks.append(update.get('content', {}).get('text', ''))
        if event.get('result', {}).get('stopReason') == 'end_turn':
            ended = True
    if ids != {expected} or not ended:
        raise RuntimeError('Resume turn did not finish in exactly the enrolled native thread')
    return ''.join(chunks)


def verify(config_path, registration):
    _, config, registration, receipt, folder = load_context(config_path, registration)
    provider = receipt['provider_thread_id']
    # Permanent paths: acpx keys its record by this exact agent command.
    qa = folder / 'enrollments' / (provider + '-verified')
    qa.mkdir(exist_ok=True, mode=0o700)
    ledger = qa / 'provider.json'
    if not ledger.exists():
        atomic_write(ledger, json.dumps({'creation': 'bound', 'provider_thread_id': provider}) + '\n')
        os.chmod(ledger, 0o600)
    elif json.loads(ledger.read_text()).get('provider_thread_id') != provider:
        raise ValueError('Enrollment ledger changed')
    agent = shlex.join([sys.executable, str(Path(__file__).with_name('acp_identity_guard.py').resolve()),
                        '--ledger', str(ledger), '--node', config['node'], '--adapter', config['adapter']])
    name = 'project-' + hashlib.sha256(config['project_node_id'].encode()).hexdigest()[:20]
    if receipt.get('verification') or receipt.get('resume_record'):
        meta = command(config, agent, ['sessions', 'show', name])[0]
    else:
        meta = command(config, agent, ['sessions', 'new', '--name', name, '--resume-session', provider])[0]
    if meta.get('acpSessionId', meta.get('acpxSessionId')) != provider or meta.get('closed'):
        raise RuntimeError('ACP record differs from enrolled native thread')
    receipt['resume_record'] = {'acpx_record_id': meta['acpxRecordId'], 'provider_thread_id': provider,
                                'session_name': name, 'agent_command': agent}
    private_write(registration, json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    token = 'COORDINATOR-ENROLLMENT-' + hashlib.sha256(provider.encode()).hexdigest()[:12]
    first = response(command(config, agent, ['prompt', '--session', name,
        'Verify handoff only. Do not use any tools or execute tasks. Remember this enrollment token: ' + token + '. Reply with the exact token only.']), provider)
    time.sleep(2)  # Past acpx TTL; second command must resume the same provider.
    second = response(command(config, agent, ['prompt', '--session', name,
        'Verify resumption only. Do not use tools. Reply with the exact enrollment token from the previous turn only.']), provider)
    if first.strip() != token or second.strip() != token:
        raise RuntimeError('Same-thread continuity test failed; old owner remains unchanged')
    verified = dict(provider_thread_id=provider, acpx_record_id=meta['acpxRecordId'],
                    acpx_session_id=provider, session_name=name, provider_ledger=str(ledger),
                    agent_command=agent, verified_at=time.time(),
                    proof='Two completed tool-free prompts across TTL, same native ID and token',
                    turns=[{'provider_thread_id': provider, 'stop_reason': 'end_turn', 'nonce_matches': True},
                           {'provider_thread_id': provider, 'stop_reason': 'end_turn', 'nonce_matches': True}],
                    token_sha256=hashlib.sha256(token.encode()).hexdigest())
    receipt['verification'] = verified
    receipt['status'] = 'verified_pending_handoff'
    private_write(registration, json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return verified


def validate_proof(config, receipt, folder):
    proof = receipt.get('verification')
    age = time.time() - proof.get('verified_at', 0) if proof else float('inf')
    if not proof or not 0 <= age <= 900:
        raise ValueError('Fresh same-thread verification required before handoff')
    provider = receipt['provider_thread_id']
    if proof.get('provider_thread_id') != provider or proof.get('acpx_session_id') != provider:
        raise ValueError('Proof native identity differs from enrollment')
    if proof.get('session_name') != 'project-' + hashlib.sha256(config['project_node_id'].encode()).hexdigest()[:20]:
        raise ValueError('Proof session name differs from Project binding')
    ledger = Path(proof['provider_ledger']).resolve(strict=True)
    ledger.relative_to(folder)
    bound = json.loads(ledger.read_text())
    if bound.get('creation') != 'bound' or bound.get('provider_thread_id') != provider:
        raise ValueError('Proof ledger is not bound to the enrolled native thread')
    expected = [sys.executable, str(Path(__file__).with_name('acp_identity_guard.py').resolve()),
                '--ledger', str(ledger), '--node', config['node'], '--adapter', config['adapter']]
    if shlex.split(proof['agent_command']) != expected:
        raise ValueError('Proof guard command differs from the explicit installed runtime')
    turns = proof.get('turns', [])
    if len(turns) != 2 or any(t.get('provider_thread_id') != provider or t.get('stop_reason') != 'end_turn' or not t.get('nonce_matches') for t in turns):
        raise ValueError('Two completed same-native continuity turns required')
    return proof


def initial_baseline(config, state):
    """Read current Project once; preserve prior queue and suppress historical replay."""
    from project_acpx import fetch
    from github_project_inputs import normalize_project
    project = fetch(config)
    tasks = normalize_project(project, config['project_node_id'], config['user_login'],
                              state.get('result_comment_ids', []), config['repository'])
    if config.get('board'):
        from github_board import select_tasks
        selected = select_tasks(project, config, tasks, state.setdefault('board_observations', {}))
        selected = {task['issue_id']: task for task in selected}
        tasks = [selected.get(task['issue_id'], task) for task in tasks]
    key = lambda task: (task['issue_id'], task.get('dispatch_key', task['revision_hash']))
    queue = state.setdefault('queue', [])
    known = {key(entry['task']) for entry in queue}
    for task in tasks:
        if key(task) not in known:
            queue.append({'task': task, 'status': 'baseline', 'observed_at': time.time()})
    state['baseline_at'] = time.time()


def commit(config_path, registration, expected_old=None, first_owner=False):
    config_path, config, registration, receipt, folder = load_context(config_path, registration)
    if first_owner and expected_old is not None:
        raise ValueError('First owner activation cannot name an existing owner')
    if not first_owner and not expected_old:
        raise ValueError('Ordinary handoff requires an explicit old owner')
    proof = validate_proof(config, receipt, folder)
    canonical = Path(config['workspace']).resolve() / '.project-delegation/github-acpx'
    canonical.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(canonical / 'controller.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = folder / 'state.json'
        state = json.loads(path.read_text()) if path.exists() else {'queue': [], 'result_comment_ids': []}
        if first_owner and state.get('binding'):
            raise ValueError('An owner already exists; first owner activation refuses replacement')
        if not first_owner and not state.get('identity'):
            raise ValueError('Existing owner identity is missing; explicit recovery required')
        assert_quiescent(state, expected_old)
        for key in ('project_node_id', 'repository', 'user_login', 'workspace'):
            if state.get('identity') and state['identity'].get(key) != receipt['scope'][key]:
                raise ValueError('Existing controller identity has a different Project/repository scope')
        meta = command(config, proof['agent_command'], ['sessions', 'show', proof['session_name']])[0]
        if meta.get('closed') or meta.get('acpxRecordId') != proof['acpx_record_id'] or meta.get('acpSessionId') != proof['provider_thread_id']:
            raise RuntimeError('Verified record is no longer valid')
        updated = copy.deepcopy(state)
        if first_owner:
            initial_baseline(config, updated)
        backup = folder / ('handoff-' + str(time.time_ns()))
        backup.mkdir(mode=0o700)
        for source in (path, config_path):
            if source.exists():
                private_write(backup / source.name, source.read_text())
        if not updated.get('identity'):
            updated['identity'] = dict(receipt['scope'])
        updated['identity']['agent_command'] = proof['agent_command']
        updated['initialization'] = 'completed'
        updated['binding'] = {key: proof[key] for key in ('provider_thread_id', 'acpx_record_id', 'acpx_session_id', 'session_name')}
        updated.setdefault('handoff_history', []).append({'previous_provider_thread_id': expected_old,
            'provider_thread_id': proof['provider_thread_id'], 'at': time.time(), 'backup': str(backup)})
        config.update(state_directory=str(folder), provider_ledger=proof['provider_ledger'], agent_command=proof['agent_command'])
        # Fail closed on interrupted two-file commit: identity mismatch prevents startup.
        private_write(config_path, json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        private_write(path, json.dumps(updated, ensure_ascii=False, indent=2) + '\n')
        receipt['status'] = 'adopted'
        private_write(registration, json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        return {'status': 'adopted', 'provider_thread_id': proof['provider_thread_id'], 'backup': str(backup), 'controller_started': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--registration', required=True, type=Path)
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--expected-old-thread')
    parser.add_argument('--first-owner', action='store_true', help='Activate a verified existing native thread only if no prior owner exists')
    args = parser.parse_args()
    if args.first_owner and (not args.commit or args.expected_old_thread):
        parser.error('--first-owner requires --commit and forbids --expected-old-thread')
    if args.commit and not (args.expected_old_thread or args.first_owner):
        parser.error('--commit requires --expected-old-thread or --first-owner')
    result = commit(args.config, args.registration, args.expected_old_thread, args.first_owner) if args.commit else verify(args.config, args.registration)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
