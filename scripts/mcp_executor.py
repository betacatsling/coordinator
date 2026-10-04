#!/usr/bin/env python3
"""Execute one bounded assignment in an independent MCP thread, then run fixed checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from watch_project import MCP, atomic_write


def execute_assignment(prompt, config, receipt_path, node):
    workspace=Path(config['cwd']).resolve(strict=True)
    paths=config['owned_paths'];checks=config['checks']
    for name in paths:
        target=(workspace/name).resolve()
        if not name or target==workspace or workspace not in target.parents:raise ValueError('Executor owned path leaves its workspace')
    root=Path(config['bridge_state_root']).resolve()
    if root==workspace or workspace in root.parents:raise ValueError('Private bridge state must be outside executor workspace')
    root.mkdir(parents=True,exist_ok=True)
    command=[node,config['server'],'--provider','codex','--approval_policy','on-request','--sandbox_mode','workspace-write','--codex-workspace-network=false','--codex-state-root',str(root),'--codex-session-retention-days','0']
    receipt={'status':'initializing','workspace':str(workspace),'owned_paths':paths}
    atomic_write(receipt_path,json.dumps(receipt,indent=2))
    with open(receipt_path.with_suffix('.stderr'),'a') as log:
        client=MCP(command,workspace,log)
        try:
            brief=('You are an independent implementation executor, not the coordinator. Implement only the assignment below. '
                   'Owned paths: '+json.dumps(paths)+'. Do not edit any other project files, reports, controller state or credentials. '
                   'Do not delegate, install software, use network, modify auth/settings or touch other tasks. '
                   'Use the workspace sandbox with on-request approvals. Report approval needs; never bypass them. '
                   'Run the specified standard checks if possible and return artifacts, evidence and blockers.\n\n'+prompt)
            started=client.call('codex-start',{'prompt':brief,'cwd':str(workspace),'sandbox':'workspace-write','allow_subagents':False})
            receipt.update(status='running',job_id=started['jobId']);atomic_write(receipt_path,json.dumps(receipt,indent=2))
            cursor=started.get('cursor',0);deadline=time.monotonic()+config.get('timeout',240)
            while time.monotonic()<deadline:
                status=client.call('codex-status',{'jobId':started['jobId'],'cursor':cursor,'wait_ms':10000});cursor=status.get('cursor',cursor)
                if status.get('state')=='waiting_for_input' or 'waiting for approval' in status.get('message','').lower():raise RuntimeError('Executor requires interactive approval; no auto-approval')
                if status.get('state') in {'completed','failed','canceled','timed_out'}:
                    if status['state']!='completed':raise RuntimeError('Executor turn ended '+status['state'])
                    result=client.call('codex-result',{'jobId':started['jobId']});receipt.update(thread_id=result.get('threadId') or status.get('threadId'),executor_result=result.get('text',''));break
            else:raise TimeoutError('Executor did not complete within its bounded deadline')
        finally:client.close()
    observations=[]
    for argv in checks:
        if not isinstance(argv,list) or not argv or not all(isinstance(v,str) for v in argv):raise ValueError('Checks must be preconfigured argv arrays')
        r=subprocess.run(argv,cwd=workspace,capture_output=True,text=True,timeout=60)
        observations.append({'argv':argv,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    files={}
    for name in paths:
        target=workspace/name
        if not target.is_file():raise RuntimeError('Expected executor artifact missing: '+name)
        if workspace not in target.resolve().parents:raise RuntimeError('Executor artifact escaped through symlink')
        content=target.read_text();files[name]={'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'content':content[:20000]}
    receipt.update(status='verified' if all(r['returncode']==0 for r in observations) else 'checks_failed',checks=observations,artifacts=files)
    atomic_write(receipt_path,json.dumps(receipt,indent=2));return receipt
