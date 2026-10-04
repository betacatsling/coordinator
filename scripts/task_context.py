#!/usr/bin/env python3
"""Bounded read-only snapshots of user-linked Markdown in the selected repository."""
import hashlib
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


def snapshots(workspace,repository,task):
    workspace=Path(workspace).resolve(strict=True);text=task['instructions']+'\n'+'\n'.join(c['body'] for c in task['user_comments']);out={}
    pattern=r'https://github\.com/'+re.escape(repository)+r'/blob/(?:main|master)/([^\s)#?]+)'
    for raw in dict.fromkeys(re.findall(pattern,text)):
        name=unquote(raw);path=Path(name)
        if path.is_absolute() or '..' in path.parts or any(v.startswith('.') for v in path.parts) or path.suffix!='.md':continue
        target=(workspace/path).resolve()
        if workspace not in target.parents or not target.is_file() or target.stat().st_size>96000:continue
        data=target.read_bytes();dirty=subprocess.run(['git','-C',str(workspace),'status','--porcelain','--',name],capture_output=True,text=True,timeout=10)
        out[name]={'main_workspace_dirty':bool(dirty.stdout.strip()),'sha256':hashlib.sha256(data).hexdigest(),'text':data.decode('utf-8'),'reference_only':True}
        if len(out)==4:break
    return out
