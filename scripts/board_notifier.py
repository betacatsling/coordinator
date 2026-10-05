#!/usr/bin/env python3
"""Read-only GitHub board watcher delivering notices to a fixed native coordinator.

Coordinator bootstrap starts this project watcher automatically. Existing
cards form a silent baseline only when notification history is absent. This component never plans, claims, executes, or writes
GitHub state; the native coordinator owns all delegation decisions.
"""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import time
import uuid

from app_server_client import AppServer, endpoint
from coordinator_notifications import pending_notice, deliver_notice, reconcile_notice
from notifier_status import SERVICE, config_signature, service_status
from github_board import select_tasks
from github_project_inputs import normalize_project
from github_writeback import is_workflow_comment
from github_source import fetch
from state_io import atomic_write
from platform_support import acquire_lock


class BoardNotifier:
    def __init__(self, config_path, *, client_factory=AppServer, fetcher=fetch, readonly=False):
        self.config_path = Path(config_path).resolve(strict=True)
        self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        self.readonly = readonly
        self.signature = config_signature(self.config)
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
        if not readonly:
            self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.binding = json.loads((self.folder / 'binding.json').read_text(encoding='utf-8'))
        if (self.binding.get('schema') != 1 or self.binding.get('scope') != self.scope
                or self.binding.get('binding', {}).get('scope') != self.scope
                or self.binding['binding'].get('transport') != 'app_server'):
            raise ValueError('Native binding scope differs')
        identity = self.binding['binding']['provider_thread_id']
        if str(uuid.UUID(identity)) != identity:
            raise ValueError('Invalid native thread ID')
        try:
            self.notifier_lock = None
            if not readonly:
                self.notifier_lock = open(self.folder / 'notifier.lock', 'a+b')
                acquire_lock(self.notifier_lock, blocking=False)
            self.path = self.folder / 'notifier.json'
            self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
            if self.state is not None:
                if (self.state.get('schema') != 1 or self.state.get('scope') != self.scope
                        or self.state.get('board') != self.config['board']
                        or self.state.get('config_signature') != self.signature):
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
        self.assert_binding()
        atomic_write(self.path, json.dumps(self.state, ensure_ascii=False, indent=2) + '\n')
        os.chmod(self.path, 0o600)

    def assert_binding(self):
        if json.loads(self.config_path.read_text(encoding='utf-8')) != self.config:
            raise ValueError('Notifier configuration changed; restart with the authorized configuration')
        if json.loads((self.folder / 'binding.json').read_text(encoding='utf-8')) != self.binding:
            raise ValueError('Coordinator binding changed; reconnect notifier')
        if not getattr(self, 'notifier_lock', None):
            raise ValueError('Notifier is closed')

    def socket_path(self):
        return self.config.get('app_server_socket') or endpoint(self.config['codex'])

    def open_client(self):
        socket_path = self.socket_path()
        if self.client_factory is AppServer:
            return self.client_factory(socket_path, codex=self.config['codex'])
        return self.client_factory(socket_path)

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
        with self.open_client() as client:
            client.thread(identity, self.workspace)
        observations = {}
        tasks = self.snapshot(observations)
        self.state = {'schema': 1, 'scope': self.scope, 'board': self.config['board'],
                      'binding': self.binding['binding'],
                      'config_signature': self.signature,
                      'baseline': {'mode': 'current', 'at': time.time(), 'count': len(tasks)},
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
        reconcile_notice(client, self.state['binding']['provider_thread_id'],
                         self.workspace, entry, self.save)

    def deliver(self):
        self.assert_binding()
        if self.state is None:
            raise ValueError('Notifier has no explicit baseline')
        entries = [entry for entry in self.state['outbox'] if pending_notice(entry)]
        if entries:
            with self.open_client() as client:
                for entry in entries:
                    deliver_notice(client, self.state['binding']['provider_thread_id'],
                                   self.workspace, entry, self.save, self.assert_binding)

    def status(self):
        value = dict(self.state or {})
        value['notifications'] = service_status(
            self.folder, self.scope, self.binding['binding']['provider_thread_id'], self.signature)
        return value

    def save_service(self):
        self.service['heartbeat_at'] = time.time()
        atomic_write(self.folder / 'notifier-service.json', json.dumps(self.service) + '\n')

    def watch_cycle(self, *, initialize_current=False, completion_delivery=None):
        # Identity/config drift is terminal. Never continue to either outbox.
        self.assert_binding()
        errors = []
        self.service.update(status='checking', last_attempt_at=time.time())
        self.save_service()
        try:
            with self.open_client() as client:
                thread = client.thread(self.binding['binding']['provider_thread_id'], self.workspace)
            self.service.update(coordinator_available=True, coordinator_status=thread.get('status', {}).get('type'),
                                coordinator_checked_at=time.time())
        except Exception as error:
            self.service.update(coordinator_available=False, coordinator_status='unavailable',
                                coordinator_checked_at=time.time())
            errors.append('Coordinator unavailable: ' + str(error))
        try:
            if self.state is None:
                if not initialize_current:
                    raise ValueError('Notification baseline is missing; run coordinator bootstrap init')
                self.initialize('current')
            else:
                self.observe()
            self.service['last_board_success_at'] = time.time()
        except Exception as error:
            errors.append('Board observation: ' + str(error))
        # Board outages must not prevent executor completion notices from waking
        # the coordinator. Both channels remain bound to the same project owner.
        self.assert_binding()
        if self.state is not None:
            try:
                self.deliver()
            except Exception as error:
                errors.append('Board delivery: ' + str(error))
        if completion_delivery is None:
            from executor_notifications import deliver_executor_notifications
            completion_delivery = deliver_executor_notifications
        self.assert_binding()
        try:
            self.service['executor_notifications'] = completion_delivery(
                self.config_path, client_factory=self.client_factory)
        except Exception as error:
            errors.append('Executor delivery: ' + str(error))
        self.assert_binding()
        if self.state is not None and any(entry.get('status') in ('submitting', 'rejected')
                or entry.get('turn_status') in ('failed', 'interrupted') for entry in self.state['outbox']):
            errors.append('Board delivery: unresolved rejected, uncertain or failed-turn notice')
        summary = self.service.get('executor_notifications') or {}
        if any(summary.get(key, 0) for key in ('submitting', 'rejected', 'turn_failed')):
            errors.append('Executor delivery: unresolved rejected, uncertain or failed-turn notice')
        self.service.update(initialized=self.state is not None,
                            baseline=self.state.get('baseline') if self.state else None,
                            status='degraded' if errors else 'running',
                            last_error='; '.join(errors) if errors else None)
        if not errors:
            self.service['last_success_at'] = time.time()
        self.save_service()
        return self.service

    def watch(self, *, interval=10, initialize_current=False, instance=None, stop_event=None):
        self.service = {'service': SERVICE, 'scope': self.scope,
                        'owner': self.binding['binding']['provider_thread_id'],
                        'config_signature': self.signature, 'instance': instance or str(uuid.uuid4()),
                        'pid': os.getpid(), 'interval': interval, 'started_at': time.time(),
                        'status': 'starting', 'initialized': self.state is not None,
                        'coordinator_available': None, 'last_error': None}
        self.save_service()
        try:
            while stop_event is None or not stop_event.is_set():
                self.watch_cycle(initialize_current=initialize_current)
                if stop_event is None:
                    time.sleep(interval)
                else:
                    stop_event.wait(interval)
        except Exception as error:
            self.service.update(status='blocked', last_error=str(error), coordinator_available=None)
            self.save_service()
            raise
        finally:
            if self.service['status'] != 'blocked':
                self.service.update(status='stopped', coordinator_available=None)
                self.save_service()

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
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error('--interval must be positive')
    with BoardNotifier(args.config, readonly=args.action == 'status') as notifier:
        if args.action == 'init':
            if not args.baseline:
                parser.error('init requires --baseline current')
            notifier.initialize(args.baseline)
        elif args.action == 'status':
            print(json.dumps(notifier.status(), ensure_ascii=False))
        elif args.action == 'once':
            notifier.once()
        else:
            notifier.watch(interval=args.interval)


if __name__ == '__main__':
    main()
