#!/usr/bin/env python3
"""Conservative release hygiene scan. Does not inspect credentials or print matches."""
from pathlib import Path
import re
import sys
root = Path(__file__).resolve().parents[1]
patterns = [r'/Users/[A-Za-z0-9_.-]+/', r'/home/[A-Za-z0-9_.-]+/',
            r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b',
            r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            r'\b[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{12}\b',
            r'\bAKIA[A-Z0-9]{16}\b']
failures=[]
for path in root.rglob('*'):
    if not path.is_file() or any(part in {'.git','__pycache__'} for part in path.relative_to(root).parts):
        continue
    if path.name in {'.env','state.json','events.jsonl'} or path.suffix in {'.log','.pyc'}:
        failures.append(str(path.relative_to(root))+': private/generated file')
        continue
    try: text=path.read_text(encoding='utf-8')
    except UnicodeError:
        failures.append(str(path.relative_to(root))+': unexpected binary'); continue
    # RFC 6455 section 1.3: a public protocol constant, not a private session ID.
    text=text.replace('258EAFA5-E914-47DA-95CA-C5AB0DC85B11','RFC6455_GUID')
    if any(re.search(pattern,text) for pattern in patterns):
        failures.append(str(path.relative_to(root))+': prohibited pattern')
if failures:
    print('\n'.join(failures)); sys.exit(1)
print('PASS: no personal absolute paths, real UUIDs, common token/key patterns, or generated private files detected.')
print('This heuristic scan is not a guarantee against every possible secret format.')
