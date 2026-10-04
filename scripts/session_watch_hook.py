#!/usr/bin/env python3
"""Optional project-local SessionStart/SessionEnd handler; trust via Codex /hooks."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project', required=True, type=Path)
args = parser.parse_args()
payload = json.load(sys.stdin)
project = args.project.resolve(strict=True)
if Path(payload.get('cwd', '')).resolve() != project:
    sys.exit(0)
session = payload.get('session_id')
event = payload.get('hook_event_name')
if not session or event not in {'SessionStart', 'SessionEnd'}:
    sys.exit(0)
folder = project / '.project-delegation'
folder.mkdir(exist_ok=True)
stop = folder / ('stop-' + hashlib.sha256(session.encode()).hexdigest())
if event == 'SessionEnd':
    # A session can only request shutdown of a watcher it started.
    stop.write_text('SessionEnd\n')
else:
    if not (project / 'PROJECT.md').is_file():
        sys.exit(0)
    with open(folder / 'watch.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit(0)
        stop.unlink(missing_ok=True)
    script = Path(__file__).with_name('watch_project.py')
    with open(folder / 'watcher.log', 'a') as log:
        subprocess.Popen([sys.executable, str(script), '--project', str(project),
                          '--hook-session', session], cwd=project,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True, close_fds=True)
print(json.dumps({'suppressOutput': True}))
