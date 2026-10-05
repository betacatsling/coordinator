#!/usr/bin/env python3
"""Read-only GitHub board watcher delivering notices to a fixed native coordinator.

Initialize explicitly with ``init --baseline current``. Existing
cards form a silent baseline. This component never plans, claims, executes, or writes
GitHub state; the native coordinator owns all delegation decisions.
"""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import time
import uuid

from app_server_client import AppServer, RequestRejected, TurnFailed, endpoint, turn_result
from github_board import select_tasks
from github_project_inputs import normalize_project
from github_writeback import is_workflow_comment
from github_source import fetch
from state_io import atomic_write


class BoardNotifier:
    def __init__(self, config_path, *, client_factory=AppServer, fetcher=fetch):
        self.config_path = Path(config_path).resolve(strict=True)
        self.config = json.loads(self.config_path.read_text())
        self.workspace = Path(self.config['workspace']).resolve(strict=True)
        self.scope = {key: self.config[key] for key in ('repository', 'project_node_id', 'user_login')}
        self.scope['workspace'] = str(self.workspace)
        if not self.config.get('board'):
            raise ValueError('Notifier requires an explicit board mapping')
        self.client_factory, self.fetcher = client_factory, fetcher
        backstage = (self.workspace / '.project-delegation').resolve()
        if self.workspace not in backstage.parents:
            raise ValueError('Backstage escapes workspace')
        self.folder = backstage / 'runtime'
        if self.folder.resolve().parent != backstage:
            raise ValueError('Notifier state escapes workspace backstage')
        if 'state_directory' in self.config and Path(self.config['state_directory']).resolve() != self.folder:
            raise ValueError('State directory must be workspace/.project-delegation/runtime')
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.binding = json.loads((self.folder / 'binding.json').read_text())
        if (self.binding.get('schema') != 1 or self.binding.get('scope') != self.scope
                or self.binding.get('binding', {}).get('scope') != self.scope
                or self.binding['binding'].get('transport') != 'app_server'):
            raise ValueError('Native binding scope differs')
        identity = self.binding['binding']['provider_thread_id']
        if str(uuid.UUID(identity)) != identity:
            raise ValueError('Invalid native thread ID')
        try:
            self.notifier_lock = open(self.folder / 'notifier.lock', 'a')
            fcntl.flock(self.notifier_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.path = self.folder / 'notifier.json'
            self.state = json.loads(self.path.read_text()) if self.path.exists() else None
            if self.state is not None:
                if (self.state.get('schema') != 1 or self.state.get('scope') != self.scope
                        or self.state.get('board') != self.config['board']):
                    raise ValueError('Notifier scope/board differs; explicit new baseline required')
                binding = self.state.get('binding', {})
                if binding != self.binding['binding']:
                    raise ValueError('Native binding scope differs')
                uuid.UUID(binding['provider_thread_id'])
        except BaseException:
            self.close()
            raise

    def close(self):
        if getattr(self, 'notifier_lock', None):
            self.notifier_lock.close()
            self.notifier_lock = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def save(self):
        atomic_write(self.path, json.dumps(self.state, ensure_ascii=False, indent=2) + '\n')
        os.chmod(self.path, 0o600)
        # Persist the atomic rename as well as the file contents.
        fd = os.open(self.folder, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def assert_binding(self):
        if json.loads((self.folder / 'binding.json').read_text()) != self.binding:
            raise ValueError('Coordinator binding changed; reconnect notifier')
        if not getattr(self, 'notifier_lock', None):
            raise ValueError('Notifier is closed')

    def socket_path(self):
        return self.config.get('app_server_socket') or endpoint(self.config['codex'])

    def snapshot(self, observations):
        project = self.fetcher(self.config)
        ignored = set()
        for item in project.get('items', {}).get('nodes', []):
            issue = item.get('content') or {}
            for comment in issue.get('comments', {}).get('nodes', []):
                if ((comment.get('author') or {}).get('login', '').lower() == self.config['user_login'].lower()
                        and is_workflow_comment(comment.get('body', ''), self.config, issue.get('id', ''))):
                    ignored.add(comment['id'])
        tasks = normalize_project(project, self.config['project_node_id'], self.config['user_login'],
                                  ignored, self.config['repository'])
        return select_tasks(project, self.config, tasks, observations)

    def initialize(self, baseline):
        self.assert_binding()
        if self.state is not None:
            raise ValueError('Already initialized; existing history cannot be reset implicitly')
        if baseline != 'current':
            raise ValueError('Explicit --baseline current required; historical replay is not automatic')
        identity = self.binding['binding']['provider_thread_id']
        with self.client_factory(self.socket_path()) as client:
            client.thread(identity, self.workspace)
        observations = {}
        tasks = self.snapshot(observations)
        self.state = {'schema': 1, 'scope': self.scope, 'board': self.config['board'],
                      'binding': self.binding['binding'],
                      'baseline': {'mode': 'current', 'at': time.time()},
                      'board_observations': observations,
                      'seen': {t['dispatch_key']: {'kind': 'baseline', 'task': t} for t in tasks},
                      'outbox': []}
        self.save()

    def observe(self):
        self.assert_binding()
        if self.state is None:
            raise ValueError('Initialize explicitly with --baseline current before polling')
        observations = copy.deepcopy(self.state['board_observations'])
        tasks = self.snapshot(observations)
        for task in tasks:
            key = task['dispatch_key']
            if key in self.state['seen']:
                continue
            notice_id = str(uuid.uuid4())
            ref = f"{self.config['repository']}#{task.get('issue_number')}"
            text = (f"GitHub 看板有新的待办版本：{ref}\n"
                    f"来源：{task.get('url') or task['issue_id']}\n"
                    f"版本：{task['revision_hash']}；待做批次：{task['ready_generation']}\n"
                    "请先用 delegation MCP 的 tasks_list 核对现有任务，再自行协调执行与验收。\n"
                    f"通知编号：{notice_id}")
            self.state['outbox'].append({'id': notice_id, 'task': task, 'text': text,
                                          'status': 'prepared', 'created_at': time.time()})
            self.state['seen'][key] = {'kind': 'notice', 'id': notice_id}
        self.state['board_observations'] = observations
        self.save()

    def reconcile(self, client, entry):
        thread = client.thread(self.state['binding']['provider_thread_id'], self.workspace, turns=True)
        # Use the shared exact-user-text reconciliation, never assistant text or a
        # partial issue/version match. Failed turns still prove queue delivery.
        try:
            turn_result(thread, entry['text'])
        except TurnFailed as exc:
            entry.update(status='delivered', turn_error=str(exc), reconciled_at=time.time())
            self.save()
            return
        matches = [turn for turn in thread.get('turns', []) if any(
            item.get('type') == 'userMessage' and any(
                c.get('type') == 'text' and c.get('text') == entry['text']
                for c in item.get('content', [])) for item in turn.get('items', []))]
        if matches:
            entry.update(status='delivered', turn_id=matches[0].get('id'), reconciled_at=time.time())
            self.save()

    def deliver(self):
        self.assert_binding()
        if self.state is None:
            raise ValueError('Notifier has no explicit baseline')
        entries = [e for e in self.state['outbox'] if e['status'] in ('prepared', 'submitting', 'queued')]
        if not entries:
            return
        with self.client_factory(self.socket_path()) as client:
            identity = self.state['binding']['provider_thread_id']
            client.thread(identity, self.workspace)  # active and idle both permit native queueing
            for entry in entries:
                if entry['status'] != 'prepared':
                    self.reconcile(client, entry)
                    continue  # no uncertain retry, even when history has no match
                entry.update(status='submitting', attempted_at=time.time())
                self.save()  # crash from here onward is uncertain, never known-unsent
                try:
                    result = client.request('thread/queue/add', {
                        'threadId': identity, 'clientUserMessageId': entry['id'],
                        'input': [{'type': 'text', 'text': entry['text'], 'text_elements': []}]})
                except RequestRejected as exc:
                    entry.update(status='rejected', error=str(exc))
                    self.save()
                    continue
                except Exception as exc:
                    entry['error'] = 'Uncertain delivery: ' + str(exc)
                    self.save()
                    raise
                queue_id = result.get('queuedSubmission', {}).get('id')
                if not queue_id:
                    entry['error'] = 'Missing queue receipt; delivery remains uncertain'
                    self.save()
                    raise RuntimeError(entry['error'])
                entry.update(status='queued', queue_id=queue_id)
                self.save()

    def once(self):
        self.observe()
        self.deliver()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('action', choices=('init', 'once', 'watch', 'status'))
    parser.add_argument('--baseline', choices=('current',))
    parser.add_argument('--interval', type=float, default=10)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error('--interval must be positive')
    with BoardNotifier(args.config) as notifier:
        if args.action == 'init':
            if not args.baseline:
                parser.error('init requires --baseline current')
            notifier.initialize(args.baseline)
        elif args.action == 'status':
            print(json.dumps(notifier.state, ensure_ascii=False))
        elif args.action == 'once':
            notifier.once()
        else:
            if notifier.state is None:
                raise ValueError('Explicit initialization is required before watch')
            while True:
                try:
                    notifier.once()
                except Exception as exc:
                    print(json.dumps({'error': str(exc)}), flush=True)
                time.sleep(args.interval)


if __name__ == '__main__':
    main()
