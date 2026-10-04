#!/usr/bin/env python3
"""Resolve the current project and enroll/reuse its actual coordinator identity."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
import uuid
from register_coordinator import enroll

REQUIRED=('workspace','repository','project_node_id','user_login')


def git_context(cwd):
    try:
        r=subprocess.run(['git','-C',str(cwd),'rev-parse','--show-toplevel'],capture_output=True,text=True,timeout=10)
        if r.returncode:return None,None
        root=Path(r.stdout.strip()).resolve()
        r=subprocess.run(['git','-C',str(root),'remote','get-url','origin'],capture_output=True,text=True,timeout=10)
        raw=r.stdout.strip() if not r.returncode else ''
    except (OSError,subprocess.TimeoutExpired):return None,None
    match=re.fullmatch(r'git@github\.com:([^/]+/[^/]+?)(?:\.git)?',raw)
    if match:return root,match.group(1)
    parsed=urlsplit(raw)
    if parsed.hostname=='github.com':
        name=parsed.path.strip('/')
        if name.endswith('.git'):name=name[:-4]
        if re.fullmatch(r'[^/]+/[^/]+',name):return root,name
    return root,None


def resolve_config(cwd=None,home=None,explicit=None):
    cwd=Path(cwd or os.getcwd()).resolve(strict=True);home=Path(home or Path.home()).resolve()
    git_root,remote=git_context(cwd)
    paths=[]
    if explicit:paths=[Path(explicit)]
    else:
        for ancestor in [cwd,*cwd.parents]:
            paths.extend([ancestor/'.project-delegation/github-acpx/config.json',ancestor/'.project-delegation/config.json'])
        registry=home/'.local/share/project-delegation/projects'
        if registry.is_dir():paths.extend(sorted(registry.glob('*/config.json')))
    matches=[];invalid=[];seen=set()
    for path in paths:
        if not path.is_file():continue
        path=path.resolve()
        if path in seen:continue
        seen.add(path)
        try:
            c=json.loads(path.read_text())
            if not isinstance(c,dict) or not isinstance(c.get('workspace'),str):raise ValueError()
            if not Path(c['workspace']).is_absolute():
                invalid.append({'config_path':str(path),'missing':['absolute workspace']});continue
            workspace=Path(c['workspace']).resolve(strict=True)
            if cwd!=workspace and workspace not in cwd.parents:continue
            if git_root and workspace!=git_root:continue
            missing=[key for key in REQUIRED if not isinstance(c.get(key),str) or not c[key].strip()]
            if missing:invalid.append({'config_path':str(path),'missing':missing});continue
            if remote and c['repository'].lower()!=remote.lower():
                return {'status':'blocked','reason':'Git origin differs from configured repository; refusing scope change'}
            c['workspace']=str(workspace)
            matches.append((len(workspace.parts),path,c))
        except (OSError,ValueError,TypeError,KeyError):
            # Never print arbitrary configuration contents, errors or remote credentials.
            if explicit:return {'status':'needs_configuration','reason':'Selected project configuration is unreadable or incomplete'}
    if not matches:return {'status':'needs_configuration','repository':remote,'missing':invalid or ['matching project binding'],'question':'Which existing GitHub Project should this workspace use?'}
    depth=max(item[0] for item in matches);matches=[item for item in matches if item[0]==depth]
    if len(matches)>1:return {'status':'needs_selection','choices':[{'config_path':str(p),'repository':c['repository'],'project_node_id':c['project_node_id']} for _,p,c in matches],'question':'Which existing binding should this project use?'}
    _,path,c=matches[0]
    return {'status':'resolved','config_path':str(path),'config':c,'scope':{key:c[key] for key in REQUIRED}}


def owner_present(folder):
    path=folder/'controller.lock'
    if not path.exists():return False
    with open(path,'r') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        return False


def bootstrap(cwd=None,home=None,environment=None,explicit=None,inspect=False):
    found=resolve_config(cwd,home,explicit)
    if found['status']!='resolved':return found
    c=found['config'];scope=found['scope'];workspace=Path(scope['workspace']).resolve(strict=True)
    backstage=(workspace/'.project-delegation').resolve();folder=Path(c.get('state_directory',str(backstage/'github-acpx'))).resolve()
    if workspace not in backstage.parents or backstage not in folder.parents:return {'status':'blocked','reason':'Project state path escapes workspace'}
    out={key:found[key] for key in ['config_path','scope']}
    env=os.environ if environment is None else environment;thread=env.get('CODEX_THREAD_ID','')
    try:
        if str(uuid.UUID(thread))!=thread:raise ValueError()
    except (ValueError,TypeError,AttributeError):return dict(out,status='blocked',reason='Current tool runtime does not provide a valid CODEX_THREAD_ID; do not ask the user to guess/paste/override an identity')
    try:state=json.loads((folder/'state.json').read_text()) if (folder/'state.json').exists() else {}
    except (OSError,ValueError):return dict(out,status='blocked',reason='Existing controller state is unreadable; preserve it for recovery')
    if not isinstance(state,dict):return dict(out,status='blocked',reason='Existing controller state has invalid structure; preserve it for recovery')
    identity=state.get('identity')
    if identity and not isinstance(identity,dict):return dict(out,status='blocked',reason='Existing controller identity has invalid structure')
    if identity and any(identity.get(key)!=scope[key] for key in REQUIRED):return dict(out,status='blocked',reason='Existing controller scope differs from selected configuration')
    binding=state.get('binding') or {}
    if not isinstance(binding,dict):return dict(out,status='blocked',reason='Existing controller binding has invalid structure')
    old=binding.get('provider_thread_id')
    if old and not identity:return dict(out,status='blocked',reason='Existing owner has no verifiable project scope; preserve it for recovery')
    try:present=owner_present(backstage/'github-acpx')
    except OSError:return dict(out,status='blocked',reason='Cannot inspect existing owner lock; preserve current owner')
    out.update(provider_thread_id=thread,previous_provider_thread_id=old,owner_present=present)
    if old==thread:
        ledger=Path(c.get('provider_ledger',str(folder/'provider.json'))).resolve()
        if backstage not in ledger.parents:return dict(out,status='blocked',reason='Provider ledger leaves project scope')
        try:provider=json.loads(ledger.read_text()).get('provider_thread_id')
        except (OSError,ValueError,AttributeError):provider=None
        if provider!=thread:return dict(out,status='blocked',reason='Existing binding/ledger disagree; never replace it automatically')
        return dict(out,status='active',action='reuse_existing_owner',activation_performed=False)
    registration=folder/'enrollments'/(thread+'.json')
    if registration.exists():
        try:receipt=json.loads(registration.read_text())
        except (OSError,ValueError):return dict(out,status='blocked',reason='Existing enrollment unreadable; do not replace it')
        if not isinstance(receipt,dict) or receipt.get('scope')!=scope or receipt.get('provider_thread_id')!=thread or receipt.get('identity_source')!='runtime:CODEX_THREAD_ID':return dict(out,status='blocked',reason='Existing enrollment scope or runtime provenance differs')
        if receipt.get('status')=='adopted':return dict(out,status='blocked',reason='Previously adopted enrollment differs from current owner; explicit recovery required')
        return dict(out,status='pending',registration=str(registration),registration_status=receipt.get('status'),action='continue_existing_handoff_after_current_turn',first_owner=not bool(old),activation_performed=False)
    if inspect:return dict(out,status='registration_needed',action='enroll_existing_current_thread',first_owner=not bool(old),activation_performed=False)
    # Role enrollment is bounded/idempotent; actual ACP verification must be post-turn.
    try:path,receipt=enroll(found['config_path'],environment=env,cwd=workspace)
    except (OSError,ValueError,TypeError,KeyError):return dict(out,status='blocked',reason='Current runtime enrollment could not be written safely; preserve existing state')
    return dict(out,status='pending',registration=str(path),registration_status=receipt['status'],action='finish_current_turn_then_supported_handoff',first_owner=not bool(old),activation_performed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inspect',action='store_true');p.add_argument('--config',type=Path)
    a=p.parse_args();value=bootstrap(explicit=a.config,inspect=a.inspect);print(json.dumps(value,ensure_ascii=False))

if __name__=='__main__':main()
