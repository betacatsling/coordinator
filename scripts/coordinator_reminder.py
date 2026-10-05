#!/usr/bin/env python3
"""Inject pending PROJECT.md reminders through the current session's native hooks."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time

from state_io import atomic_write
from watch_project import read_input, task_changes

EVENTS = {'PreToolUse', 'PostToolUse', 'UserPromptSubmit', 'Stop'}

def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def run(args):
    project = args.project.resolve(strict=True)
    folder = project / '.project-delegation'
    folder.mkdir(exist_ok=True)
    if args.ack:
        revision = folder / 'reminders' / (args.ack + '.json')
        if len(args.ack) != 64 or any(c not in '0123456789abcdef' for c in args.ack):
            raise ValueError('Invalid revision')
        pending = load(revision, None)
        if pending is None:
            raise ValueError('Only a revision actually delivered by a hook can be acknowledged')
        with open(folder / 'reminder.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ack = load(folder / 'acknowledged.json', {})
            ack.update({t['id']: t['hash'] for t in pending.get('tasks', [])})
            atomic_write(folder / 'acknowledged.json', json.dumps(ack, indent=2) + '\n')
        print('Acknowledged processed task revision; newer edits remain pending.')
        return
    payload = json.load(sys.stdin)
    event, session = payload.get('hook_event_name'), payload.get('session_id')
    if event not in EVENTS or not session or Path(payload.get('cwd', '')).resolve() != project:
        print('{}');return
    # Never create an endless chain of Stop continuations.
    if event == 'Stop' and payload.get('stop_hook_active'):
        print('{}');return
    deadline = time.monotonic() + (min(args.wait_seconds, 12) if event == 'Stop' else 0)
    while True:
        try:
            pending = load(folder / 'pending.json', None)
            _, current_hash = read_input(project / 'PROJECT.md')
            changes = task_changes(project / 'PROJECT.md', {})
            if not changes:
                print('{}');return
            if pending and pending.get('input_hash') == current_hash:
                break
        except (OSError, ValueError, UnicodeError):
            pending = None
        if time.monotonic() >= deadline:
            print('{}');return
        time.sleep(.25)
    digest = pending['input_hash']
    key = hashlib.sha256(session.encode()).hexdigest() + ':' + digest
    with open(folder / 'reminder.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        delivered = load(folder / 'reminder-delivery.json', {})
        if key in delivered:
            print('{}');return
        # Preserve the exact notified snapshot so acknowledging it cannot absorb later edits.
        atomic_write(folder / 'reminders' / (digest + '.json'), json.dumps(pending, ensure_ascii=False, indent=2))
        delivered[key] = {'event': event, 'time': time.time()}
        atomic_write(folder / 'reminder-delivery.json', json.dumps(delivered, indent=2))
    titles = ', '.join(t['title'] for t in changes)[:500]
    script = Path(__file__).resolve()
    import shlex
    ack_command = shlex.join([sys.executable, str(script), '--project', str(project), '--ack', digest])
    reminder = (f'PROJECT.md has new or changed tasks after ten quiet seconds: {titles}. '
                f'You are the current coordinator; read {project / "PROJECT.md"} and '
                f'{folder / "reminders" / (digest + ".json")} to process only the notified task revisions. '
                'Preserve human edits. Do not create or resume a substitute coordinator. '
                'Keep IDs and hashes backstage. After processing and verifying these tasks, '
                'render a dated HTML report and append its relative link under ## 执行报告. '
                f'Only after the notified tasks are handled, acknowledge their exact revision with: {ack_command}. '
                'A reminder alone is not completion. Report unresolved blockers honestly.')
    if event == 'Stop':
        print(json.dumps({'decision': 'block', 'reason': reminder}, ensure_ascii=False))
    else:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': reminder}}, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--wait-seconds', type=float, default=0)
    parser.add_argument('--ack')
    run(parser.parse_args())
