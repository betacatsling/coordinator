#!/usr/bin/env python3
"""ACP proxy: reserve exactly one session/new, then reject fallback or identity changes."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import threading
from watch_project import atomic_write

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ledger',required=True,type=Path)
parser.add_argument('--node',required=True)
parser.add_argument('--adapter',required=True)
args=parser.parse_args();ledger=args.ledger.resolve();lock_path=ledger.with_suffix('.lock')
output_lock=threading.Lock();requests={};request_lock=threading.Lock()
bootstrap_response = None
bootstrap_id = 'fixed-coordinator-bootstrap'

def send(value):
    with output_lock:
        sys.stdout.write(json.dumps(value)+'\n');sys.stdout.flush()

def change(fn):
    with open(lock_path,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(ledger.read_text())
        result=fn(state)
        atomic_write(ledger,json.dumps(state,indent=2)+'\n')
        return result

def deny(message):
    raise ValueError(message)

child=subprocess.Popen([args.node,args.adapter],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr,text=True,bufsize=1)

def read_child():
    global bootstrap_response
    for line in child.stdout:
        try:
            message=json.loads(line)
            if message.get('id') == bootstrap_id:
                if message.get('error') or message.get('result', {}).get('stopReason') != 'end_turn':
                    send({'jsonrpc':'2.0','id':bootstrap_response['id'],'error':{'code':-32603,'message':'Fixed coordinator bootstrap failed; explicit recovery required'}})
                else:
                    send(bootstrap_response)
                bootstrap_response = None
                continue
            if bootstrap_response is not None and message.get('method') == 'session/update':
                continue
            if bootstrap_response is not None and 'id' in message and 'method' in message:
                child.stdin.write(json.dumps({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32600,'message':'Bootstrap is tool-free'}})+'\n');child.stdin.flush()
                continue
            with request_lock:method=requests.pop(str(message.get('id')),None)
            if method=='session/new':
                def save(s):
                    provider=message.get('result',{}).get('sessionId')
                    if not provider:
                        s['creation']='failed';return
                    s['provider_thread_id']=provider;s['creation']='bound'
                change(save)
                if message.get('result', {}).get('sessionId'):
                    bootstrap_response = message
                    child.stdin.write(json.dumps({'jsonrpc':'2.0','id':bootstrap_id,'method':'session/prompt','params':{'sessionId':message['result']['sessionId'],'prompt':[{'type':'text','text':'Initialize this fixed project coordinator. Reply READY only. Do not use tools, access files, invoke network, delegate, or change settings.'}]}})+'\n');child.stdin.flush()
                    continue
            send(message)
        except Exception as exc:
            print('ACP identity guard response failed: '+str(exc),file=sys.stderr)
            child.terminate();return

reader=threading.Thread(target=read_child,daemon=True);reader.start()
try:
    for line in sys.stdin:
        try:
            message=json.loads(line);method=message.get('method');params=message.get('params',{})
            def validate(s):
                bound=s.get('provider_thread_id')
                if method=='session/new':
                    if bound or s.get('creation')!='allowed':deny('Fixed coordinator forbids session/new fallback; explicit recovery required')
                    s['creation']='attempted'
                elif method=='session/fork':deny('Fixed coordinator forbids session/fork')
                elif method in {'session/load','session/resume','session/prompt'}:
                    if not bound or params.get('sessionId')!=bound:deny('Provider session identity differs from fixed binding')
            if method and method.startswith('session/'):
                change(validate)
            if 'id' in message:
                with request_lock:requests[str(message['id'])]=method
            child.stdin.write(json.dumps(message)+'\n');child.stdin.flush()
        except ValueError as exc:
            if 'id' in message:send({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32600,'message':str(exc)}})
        except Exception as exc:
            print('ACP identity guard input failed: '+str(exc),file=sys.stderr);break
finally:
    child.stdin.close()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=5)
    reader.join(timeout=1)
