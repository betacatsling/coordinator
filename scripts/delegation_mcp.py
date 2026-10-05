#!/usr/bin/env python3
"""Stdio MCP for one bound project coordinator (JSON-RPC transport, not chat JSON)."""
import argparse
import hashlib
from pathlib import Path
import uuid
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
    {'name': 'executor_result', 'description': 'Read original executor receipt, scoped Git changes and controller-run checks for independent review.', 'inputSchema': schema({'job_id': STRING}, ('job_id',))},
    {'name': 'executor_continue', 'description': 'Continue the original completed executor thread. recover_only observes an interrupted original job without submitting a turn; never creates a replacement.',
     'inputSchema': schema({'job_id': STRING, 'assignment': {'type': 'string'}, 'recover_only': {'type': 'boolean'}}, ('job_id', 'assignment'))},
    {'name': 'task_finish', 'description': 'Record coordinator acceptance/rejection and a concise outcome summary; optional report adds review details. Save a private HTML report and perform configured issue/board writeback. Acceptance does not merge or deploy.',
     'inputSchema': schema({'job_id': STRING, 'accepted': {'type': 'boolean'}, 'summary': STRING, 'report': STRING}, ('job_id', 'accepted', 'summary'))},
]


class RequestService:
    """Host-owned stdio metadata, not model arguments, identifies each caller.

    The private stdio transport is the trust boundary. This is not authentication
    for an arbitrary network client and must not be exposed as an open endpoint.
    """
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve(strict=True)
        self.config_hash = hashlib.sha256(self.config_path.read_bytes()).hexdigest()

    def for_request(self, params):
        meta = params.get('_meta')
        owner = meta.get('threadId') if isinstance(meta, dict) else None
        try:
            if not isinstance(owner, str) or str(uuid.UUID(owner)) != owner:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ValueError('Host MCP request _meta.threadId is required; reconnect with a Codex client that supplies per-call thread metadata')
        if hashlib.sha256(self.config_path.read_bytes()).hexdigest() != self.config_hash:
            raise ValueError('Configuration changed; reconnect with reviewed configuration')
        return DelegationService(self.config_path, caller_thread_id=owner)


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
        request_service = service.for_request(params)
        try:
            result = getattr(request_service, tool['name'])(**args)
        finally:
            request_service.close()
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
    serve(RequestService(args.config), sys.stdin, sys.stdout)


if __name__ == '__main__':
    main()
