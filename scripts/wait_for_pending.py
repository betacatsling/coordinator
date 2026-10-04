#!/usr/bin/env python3
"""A bounded current-coordinator wait tool, not an idle-session wakeup service."""
import argparse
import json
from pathlib import Path
import time
from watch_project import read_input, task_changes

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project',required=True,type=Path)
parser.add_argument('--timeout',type=float,default=45)
args=parser.parse_args();project=args.project.resolve(strict=True)
deadline=time.monotonic()+max(0,min(args.timeout,60))
while True:
    try:
        pending=json.loads((project/'.project-delegation/pending.json').read_text())
        if pending.get('input_hash')==read_input(project/'PROJECT.md')[1] and task_changes(project/'PROJECT.md',{}):
            print('PROJECT.md has debounced pending tasks. Read it and the pending snapshot.');break
    except (OSError,ValueError,UnicodeError):
        pass
    if time.monotonic()>=deadline:
        print('No new debounced task revision within this bounded wait.');break
    time.sleep(.25)
