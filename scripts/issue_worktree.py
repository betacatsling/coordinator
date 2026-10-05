#!/usr/bin/env python3
"""Issue-specific detached worktrees; never apply patches to the dirty main tree."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import hashlib
import json
from state_io import atomic_write
import subprocess
from platform_support import IS_WINDOWS

PROTECTED={'.git','.codex','.agents','.project-delegation','reports'}


def validate_paths(paths):
    if not isinstance(paths,list) or not paths:raise ValueError('An explicit per-Issue file/directory scope is required')
    for name in paths:
        if not isinstance(name,str):raise ValueError('Unsafe executor file scope')
        p=PurePosixPath(name)
        if '\\' in name or PureWindowsPath(name).drive or ':' in name:raise ValueError('Use repository-relative forward-slash paths')
        if IS_WINDOWS and any(v.endswith((' ', '.')) or PureWindowsPath(v).is_reserved() for v in p.parts):raise ValueError('Unsafe Windows executor file scope')
        if not name or p.is_absolute() or '..' in p.parts or p==PurePosixPath('.') or any((v.casefold() if IS_WINDOWS else v) in PROTECTED for v in p.parts):raise ValueError('Unsafe executor file scope')
    return paths


def within_scope(name, scope):
    if IS_WINDOWS:name,scope=name.casefold(),scope.casefold()
    return name==scope or name.startswith(scope.rstrip('/')+'/')


def git(root,*argv):
    r=subprocess.run(['git','-C',str(root),*argv],capture_output=True,text=True,encoding="utf-8",timeout=30)
    if r.returncode:raise RuntimeError('Git worktree operation failed: '+r.stderr.strip())
    return r.stdout.strip()


def create(repo, task, state_dir, owned_paths=None):
    repo=Path(repo).resolve(strict=True)
    if Path(git(repo,'rev-parse','--show-toplevel')).resolve()!=repo:raise ValueError('Executor must bind selected repository root')
    if owned_paths:
        validate_paths(owned_paths)
        dirty=git(repo,'diff','--name-only','HEAD').splitlines()+git(repo,'ls-files','--others','--exclude-standard').splitlines()
        if any(any(within_scope(n,p) for p in owned_paths) for n in dirty):raise ValueError('Issue scope overlaps uncommitted main-workspace files; preserve them and reconcile explicitly')
    root=Path(state_dir).resolve()/'worktrees';root.mkdir(parents=True,exist_ok=True)
    key=_key(task)
    target=root/key
    if target.exists():raise ValueError('Task worktree already exists; inspect before explicit recovery')
    head=git(repo,'rev-parse','HEAD');git(repo,'worktree','add','--detach',str(target),head)
    metadata={'task_identity':_identity(task),'repository':str(repo),'workspace':str(target.resolve()),'base_head':head,'owned_paths':owned_paths}
    atomic_write(root/(key+'.json'),json.dumps(metadata,indent=2))
    return target,head


def _identity(task):
    from mcp_executor import task_identity
    return task_identity(task)


def _key(task):
    return hashlib.sha256(json.dumps(_identity(task),sort_keys=True).encode()).hexdigest()[:24]


def resume(repo, task, state_dir, owned_paths, receipt):
    """Reuse only a positively identified original worktree; never recreate it."""
    repo=Path(repo).resolve(strict=True)
    validate_paths(owned_paths)
    root=Path(state_dir).resolve()/'worktrees';key=_key(task)
    metadata=json.loads((root/(key+'.json')).read_text())
    target=(root/key).resolve(strict=True)
    expected={'task_identity':_identity(task),'repository':str(repo),'workspace':str(target),'owned_paths':owned_paths}
    for name,value in expected.items():
        if metadata.get(name)!=value:raise ValueError('Worktree recovery changed '+name)
    for name in ('task_identity','workspace','owned_paths','base_head'):
        if receipt.get(name)!=metadata.get(name):raise ValueError('Worktree receipt differs: '+name)
    if target==repo or Path(git(target,'rev-parse','--show-toplevel')).resolve()!=target:
        raise ValueError('Recovery workspace is not the original worktree root')
    common=lambda path: (path/ git(path,'rev-parse','--git-common-dir')).resolve()
    if common(target)!=common(repo):raise ValueError('Recovery workspace belongs to another repository')
    head=git(target,'rev-parse','HEAD')
    if head!=metadata['base_head']:raise ValueError('Recovery worktree HEAD changed')
    inspect(target,owned_paths)
    return target,head


def inspect(workspace, paths):
    validate_paths(paths);workspace=Path(workspace)
    names=git(workspace,'diff','--name-only','HEAD').splitlines()+git(workspace,'ls-files','--others').splitlines()
    for name in names:
        if not any(within_scope(name,p) for p in paths):raise ValueError('Executor modified outside owned paths: '+name)
    for name in names:
        p=workspace/name
        if p.is_symlink() or (p.exists() and workspace.resolve() not in p.resolve().parents):raise ValueError('Unsafe executor artifact')
    if git(workspace,'diff','--cached','--name-only'):raise ValueError('Executor staged changes; do not alter shared Git state')
    git(workspace,'diff','--check')
    return sorted(set(names))
