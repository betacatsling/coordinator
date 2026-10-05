#!/usr/bin/env python3
"""Stdio MCP for one bound project coordinator (JSON-RPC transport, not chat JSON)."""
import argparse
import json
import sys
from delegation_service import DelegationService


def schema(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}


STRING = {'type': 'string', 'minLength': 1}
STRINGS = {'type': 'array', 'items': STRING}
TOOLS = [
    {'name': 'tasks_list', 'description': 'Read live authorized eligible tasks and durable jobs in the bound project.', 'inputSchema': schema()},
    {'name': 'executor_start', 'description': 'Claim current task and start one independent persistent executor in an isolated worktree. Returns immediately; at most three active jobs. Never merges or deploys.',
     'inputSchema': schema({'issue_id': STRING, 'revision_hash': STRING, 'assignment': STRING, 'owned_paths': STRINGS, 'depends_on': STRINGS, 'resources': STRINGS}, ('issue_id', 'revision_hash', 'assignment', 'owned_paths'))},
    {'name': 'executor_status', 'description': 'Read persisted job/session status; never starts or replaces a session.', 'inputSchema': schema({'job_id': STRING}, ('job_id',))},
    {'name': 'executor_result', 'description': 'Read original executor receipt, changed artifacts and controller-run checks for independent review.', 'inputSchema': schema({'job_id': STRING}, ('job_id',))},
    {'name': 'executor_continue', 'description': 'Continue the original completed executor thread. recover_only observes an interrupted original job without submitting a turn; never creates a replacement.',
     'inputSchema': schema({'job_id': STRING, 'assignment': {'type': 'string'}, 'recover_only': {'type': 'boolean'}}, ('job_id', 'assignment'))},
    {'name': 'task_finish', 'description': 'Record coordinator acceptance/rejection, render a private HTML evidence report and perform configured issue/board writeback. Acceptance is isolated-worktree verification, not integration.',
     'inputSchema': schema({'job_id': STRING, 'accepted': {'type': 'boolean'}, 'summary': STRING, 'report': STRING}, ('job_id', 'accepted', 'summary', 'report'))},
]


def dispatch(service, message):
    method = message.get('method')
    if method == 'initialize':
        return {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'project-delegation', 'version': '1.0.0'}}
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': TOOLS}
    if method != 'tools/call':
        raise ValueError('Unsupported MCP method')
    params = message.get('params') or {}
    tool = next((t for t in TOOLS if t['name'] == params.get('name')), None)
    if not tool:
        raise ValueError('Unknown delegation tool')
    args = params.get('arguments', {})
    shape = tool['inputSchema']
    if not isinstance(args, dict) or set(args) - set(shape['properties']) or set(shape['required']) - set(args):
        raise ValueError('Invalid tool arguments; no scope, shell or identity overrides allowed')
    try:
        result = getattr(service, tool['name'])(**args)
        return {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'structuredContent': result}
    except Exception as exc:
        return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}


def serve(service, source, target):
    for line in source:
        message = None
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
                raise ValueError('Expected JSON-RPC 2.0 object')
            if 'id' not in message:
                continue
            response = {'jsonrpc': '2.0', 'id': message['id'], 'result': dispatch(service, message)}
        except Exception as exc:
            response = {'jsonrpc': '2.0', 'id': message.get('id') if isinstance(message, dict) else None, 'error': {'code': -32602, 'message': str(exc)}}
        target.write(json.dumps(response, ensure_ascii=False) + '\n')
        target.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    serve(DelegationService(args.config), sys.stdin, sys.stdout)


if __name__ == '__main__':
    main()
