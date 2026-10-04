#!/usr/bin/env python3
"""Issue-specific detached worktrees; never apply patches to the dirty main tree."""
from pathlib import Path
import hashlib
import subprocess

PROTECTED={'.git','.codex','.agents','.project-delegation','reports'}


def validate_paths(paths):
    if not isinstance(paths,list) or not paths:raise ValueError('An explicit per-Issue file/directory scope is required')
    for name in paths:
        p=Path(name)
        if not isinstance(name,str) or not name or p.is_absolute() or '..' in p.parts or p==Path('.') or any(v in PROTECTED for v in p.parts):raise ValueError('Unsafe executor file scope')
    return paths


def git(root,*argv):
    r=subprocess.run(['git','-C',str(root),*argv],capture_output=True,text=True,timeout=30)
    if r.returncode:raise RuntimeError('Git worktree operation failed: '+r.stderr.strip())
    return r.stdout.strip()


def create(repo, task, state_dir, owned_paths=None):
    repo=Path(repo).resolve(strict=True)
    if Path(git(repo,'rev-parse','--show-toplevel')).resolve()!=repo:raise ValueError('Executor must bind selected repository root')
    if owned_paths:
        validate_paths(owned_paths)
        dirty=git(repo,'diff','--name-only','HEAD').splitlines()+git(repo,'ls-files','--others','--exclude-standard').splitlines()
        if any(any(n==p or n.startswith(p.rstrip('/')+'/') for p in owned_paths) for n in dirty):raise ValueError('Issue scope overlaps uncommitted main-workspace files; preserve them and reconcile explicitly')
    root=Path(state_dir)/'worktrees';root.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256((task['issue_id']+task.get('dispatch_key',task['revision_hash'])).encode()).hexdigest()[:24]
    target=root/key
    if target.exists():raise ValueError('Task worktree already exists; inspect before explicit recovery')
    head=git(repo,'rev-parse','HEAD');git(repo,'worktree','add','--detach',str(target),head)
    return target,head


def inspect(workspace, paths):
    validate_paths(paths);workspace=Path(workspace)
    names=git(workspace,'diff','--name-only','HEAD').splitlines()+git(workspace,'ls-files','--others','--exclude-standard').splitlines()
    for name in names:
        if not any(name==p or name.startswith(p.rstrip('/')+'/') for p in paths):raise ValueError('Executor modified outside owned paths: '+name)
    for name in names:
        p=workspace/name
        if p.exists() and (p.is_symlink() or workspace.resolve() not in p.resolve().parents):raise ValueError('Unsafe executor artifact')
    if git(workspace,'diff','--cached','--name-only'):raise ValueError('Executor staged changes; do not alter shared Git state')
    git(workspace,'diff','--check')
    return sorted(set(names))
