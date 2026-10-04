"""Deterministic MCP fixture; never invokes a model."""
import json
import os
import sys
for line in sys.stdin:
    msg = json.loads(line)
    if 'id' not in msg:
        continue
    method = msg['method']
    if method == 'initialize':
        result = {'protocolVersion': '2025-06-18', 'capabilities': {}, 'serverInfo': {'name': 'fixture', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': [{'name': n} for n in ['codex-thread-read','codex-reply-start','codex-status','codex-result']]}
    else:
        name = msg['params']['name']
        if name == 'codex-start':
            raise AssertionError('Watcher must never create a coordinator')
        if name == 'codex-thread-read':
            status = 'idle' if msg['params']['arguments']['threadId'] == 'fixture-loaded' else 'notLoaded'
            data = {'thread': {'cwd': os.getcwd(), 'status': {'type': status}}}
        elif name == 'codex-reply-start':
            data = {'jobId': 'fixture-job', 'cursor': 0}
        elif name == 'codex-status':
            data = {'state': 'completed', 'threadId': 'fixture-thread', 'cursor': 1}
        else:
            data = {'text': 'Fixture result. No model was called.', 'threadId': 'fixture-thread'}
        result = {'structuredContent': data}
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result}), flush=True)
