#!/usr/bin/env python3
"""Config-bound coordinator tools. Detached workers own original executor turns.

The service never interprets coordinator chat. The stdio MCP adapter is the only
public command surface; assignments are text, never executable controller argv.
"""
from contextlib import contextmanager
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
import threading
import uuid

from state_io import atomic_write
from platform_support import acquire_lock, detached_process_options, process_alive
from github_project_inputs import normalize_project
from github_board import select_tasks, assert_claimable
from github_writeback import (is_workflow_comment, write_claim, write_result,
    validate_scope, assert_owned_active, write_executor_session)
from issue_worktree import validate_paths, create, resume
from mcp_executor import (execute_assignment, resume_assignment, recover_assignment,
    validated_receipt, task_identity)
from github_source import fetch, gh
from executor_notifications import (EVENT_STATUSES, receipt_for_job,
    record_executor_notification, deliver_executor_notifications)


def overlaps(a, b):
    from platform_support import IS_WINDOWS
    if IS_WINDOWS:a,b=a.casefold(),b.casefold()
    a, b = PurePosixPath(a), PurePosixPath(b)
    return a == b or a in b.parents or b in a.parents


ACTIVE = {'reserved', 'running', 'recovery_required', 'waiting_for_input'}


class DelegationService:
    def __init__(self, config_path, *, caller_thread_id=None):
        self.config_path = Path(config_path).resolve(strict=True)
        self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        c = self.config
        self.workspace = Path(c['workspace']).resolve(strict=True)
        backstage = (self.workspace / '.project-delegation').resolve()
        self.folder = backstage / 'runtime'
        if self.workspace not in backstage.parents or self.folder.resolve().parent != backstage:
            raise ValueError('State must remain inside selected project backstage')
        if 'state_directory' in c and Path(c['state_directory']).resolve() != self.folder:
            raise ValueError('State directory must be workspace/.project-delegation/runtime')
        self.root = self.folder
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.closed = False
        self.path = self.root / 'jobs.json'
        self.scope = {key: c[key] for key in ('project_node_id', 'repository', 'user_login')}
        self.scope['workspace'] = str(self.workspace)
        self.config_hash = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        # Direct CLI/worker callers use their runtime environment. MCP callers must
        # supply host request context explicitly; never fall back to server env.
        self.owner = (os.environ.get('CODEX_THREAD_ID', '')
                      if caller_thread_id is None else caller_thread_id)
        self._authorize()
        if not c.get('executor', {}).get('enabled') or not c['executor'].get('isolate_worktree'):
            raise ValueError('Delegation requires enabled isolated executors')
        if not 1 <= int(c.get('max_parallel_executors', 3)) <= 3:
            raise ValueError('Coordinator delegation supports at most three executor jobs')
        if c.get('source', {}).get('type') == 'github':
            if not c.get('board') or not c.get('writeback', {}).get('enabled') or c['writeback'].get('dry_run', True):
                raise ValueError('GitHub execution requires verified board mapping and enabled live claim writeback')

    def close(self):
        self.closed = True

    def _authorize(self):
        if getattr(self, 'closed', True):
            raise ValueError('Delegation service is closed')
        if hashlib.sha256(self.config_path.read_bytes()).hexdigest() != self.config_hash:
            raise ValueError('Configuration changed; reconnect with reviewed configuration')
        try:
            if str(uuid.UUID(self.owner)) != self.owner:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ValueError('Valid runtime CODEX_THREAD_ID required; caller cannot supply an identity')
        state = json.loads((self.folder / 'binding.json').read_text(encoding='utf-8'))
        if state.get('schema') != 1:
            raise ValueError('Unknown coordinator binding schema')
        if state.get('binding', {}).get('transport') != 'app_server' or state.get('binding', {}).get('provider_thread_id') != self.owner:
            raise ValueError('Only the bound fixed coordinator may use delegation tools')
        identity = state.get('scope', {})
        if state.get('binding', {}).get('scope') != self.scope or any(identity.get(k) != v for k, v in self.scope.items()):
            raise ValueError('Coordinator project/repository scope differs')

    @contextmanager
    def transaction(self):
        self._authorize()
        with open(self.root / 'jobs.lock', 'a') as lock:
            acquire_lock(lock)
            state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'scope': self.scope, 'jobs': {}, 'observations': {}}
            if state.get('scope') != self.scope:
                raise ValueError('Durable job ledger scope changed')
            yield state
            atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2) + '\n')
            os.chmod(self.path, 0o600)

    def _source(self, state):
        project = fetch(self.config)
        ignored = []
        for item in project.get('items', {}).get('nodes', []):
            issue = item.get('content') or {}
            for comment in issue.get('comments', {}).get('nodes', []):
                if (comment.get('author') or {}).get('login', '').lower() == self.config['user_login'].lower() and is_workflow_comment(comment.get('body', ''), self.config, issue.get('id', '')):
                    ignored.append(comment['id'])
        tasks = normalize_project(project, self.config['project_node_id'], self.config['user_login'], ignored, self.config['repository'])
        eligible = select_tasks(project, self.config, tasks, state['observations']) if self.config.get('board') else [dict(t, dispatch_key=t['revision_hash']) for t in tasks]
        return project, tasks, eligible

    def _current(self, state, task, starting=False):
        project, tasks, eligible = self._source(state)
        current = next((t for t in tasks if t['issue_id'] == task['issue_id']), None)
        if not current or current['revision_hash'] != task['revision_hash']:
            raise ValueError('Task source authorization/revision changed; coordinator must review')
        if self.config['source']['type'] == 'github':
            if starting:
                assert_claimable(project, self.config, task)
            else:
                item, issue, viewer = validate_scope(self.config, task, project, gh)
                assert_owned_active(self.config, task, project, item, issue, viewer)
        return project

    def tasks_list(self):
        with self.transaction() as state:
            _, _, eligible = self._source(state)
            return {'tasks': eligible, 'jobs': [self._view(j) for j in state['jobs'].values()], 'scope': self.scope}

    def _job(self, state, job_id):
        if not isinstance(job_id, str) or job_id not in state['jobs']:
            raise ValueError('Unknown job in this project')
        return state['jobs'][job_id]

    def _view(self, job):
        result = {k: v for k, v in job.items() if k not in {'executor_config', 'assignment', 'dependencies'}}
        path = Path(job['receipt'])
        if path.exists():
            receipt = json.loads(path.read_text(encoding='utf-8'))
            result['executor_status'] = receipt.get('status')
            result['thread_id'] = receipt.get('thread_id')
            result['executor_error'] = receipt.get('error')
        return result

    def _admit(self, state, job, continuing=False):
        active = [j for j in state['jobs'].values() if j['id'] != job['id'] and j['status'] in ACTIVE]
        if len(active) >= int(self.config.get('max_parallel_executors', 3)):
            raise ValueError('All executor slots are occupied; observe existing jobs first')
        for other in state['jobs'].values():
            if other['id'] == job['id'] or other['status'] in {'accepted', 'preparation_failed', 'superseded'}:
                continue
            if other['task']['issue_id'] == job['task']['issue_id']:
                raise ValueError('Task already has an unfinished executor; continue original job')
            if set(other['resources']) & set(job['resources']) or any(overlaps(a, b) for a in other['owned_paths'] for b in job['owned_paths']):
                raise ValueError('Owned paths/shared resources conflict with unfinished executor')

    def executor_start(self, issue_id, revision_hash, assignment, owned_paths, depends_on=None, resources=None):
        if not isinstance(assignment, str) or not assignment.strip():
            raise ValueError('Nonempty bounded assignment required')
        validate_paths(owned_paths)
        depends_on = [] if depends_on is None else depends_on
        resources = [] if resources is None else resources
        if not isinstance(depends_on, list) or not all(isinstance(v, str) for v in depends_on) or not isinstance(resources, list) or not all(isinstance(v, str) for v in resources):
            raise ValueError('Dependencies/resources must be string arrays')
        if set(resources) - set(self.config['executor'].get('allowed_resources', [])):
            raise ValueError('Unapproved shared resource')
        with self.transaction() as state:
            project, _, tasks = self._source(state)
            task = next((t for t in tasks if t['issue_id'] == issue_id and t['revision_hash'] == revision_hash), None)
            if not task:
                raise ValueError('Task is not currently authorized and eligible at this revision')
            if any(j['task'].get('dispatch_key') == task['dispatch_key'] for j in state['jobs'].values()):
                raise ValueError('Dispatch already exists; use its original job')
            job_id = uuid.uuid4().hex
            job = dict(id=job_id, task=task, status='reserved', assignment=assignment,
                owned_paths=owned_paths, resources=resources, dependencies=[], created_at=time.time(),
                coordinator_thread_id=self.owner, attempt_id=str(uuid.uuid4()),
                receipt=str(self.root / (job_id + '.receipt.json')), config_hash=self.config_hash)
            self._admit(state, job)
            for dependency_id in depends_on:
                dependency = self._job(state, dependency_id)
                if dependency['status'] != 'accepted' or dependency['task']['issue_id'] == issue_id:
                    raise ValueError('Dependencies must be accepted other-task job IDs')
                # Source must still represent exactly the accepted version.
                _, all_tasks, _ = self._source(state)
                if not any(t['issue_id'] == dependency['task']['issue_id'] and t['revision_hash'] == dependency['task']['revision_hash'] for t in all_tasks):
                    raise ValueError('Dependency source revision changed')
                evidence = validated_receipt(dependency['executor_config'], dependency['receipt'])
                job['dependencies'].append(dict(job_id=dependency_id, task=dependency['task'],
                    attempt_id=evidence['attempt_id'], workspace=evidence['workspace'], base_head=evidence['base_head'],
                    checks=evidence.get('checks', []), changed_paths=evidence.get('changed_paths', []), patch=evidence.get('patch', '')))
            state['jobs'][job_id] = job
            # Reserve durably before any external mutation; uncertain outcomes never auto-restart.
            atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2))
            self._prepare_and_launch(state, job, project)
            return self._view(job)

    def _prepare_and_launch(self, state, job, project):
        try:
            job['phase'] = 'claiming'
            atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2))
            if self.config['source']['type'] == 'github':
                job['claim'] = write_claim(self.config, job['task'], project, gh, False)
            job['phase'] = 'preparing'
            atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2))
            workspace, head = create(self.workspace, job['task'], self.root, job['owned_paths'])
            job['executor_config'] = dict(self.config['executor'], cwd=str(workspace), base_head=head,
                owned_paths=job['owned_paths'], task_identity=task_identity(job['task']))
            job['phase'] = 'launching'
            atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2))
            self._schedule(state, job, 'start')
        except Exception as exc:
            job.update(status='preparation_failed' if job['phase'] == 'preparing' else 'recovery_required', error=str(exc))
            record_executor_notification(state, job)

    @staticmethod
    def _worker_alive(job):
        return process_alive(job.get('worker_pid'))

    def _schedule(self, state, job, mode):
        if job.get('coordinator_thread_id', self.owner) != self.owner:
            raise ValueError('Executor job belongs to a different fixed coordinator')
        job['coordinator_thread_id'] = self.owner
        if mode == 'resume' or not job.get('attempt_id'):
            job['attempt_id'] = str(uuid.uuid4())
        job['executor_config']['attempt_id'] = job['attempt_id']
        job.update(status='running', mode=mode, launched_at=time.time())
        job.pop('worker_pid', None)
        # The attempt is durable before spawning; worker receipts cannot be
        # mistaken for an earlier continuation after a crash.
        atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2))
        self._launch(job, mode)

    def _launch(self, job, mode):
        with open(self.root / (job['id'] + '.worker.log'), 'a', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--config', str(self.config_path), '--worker', job['id'], '--attempt', job['attempt_id']],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=str(self.workspace),
                env=dict(os.environ, CODEX_THREAD_ID=self.owner), **detached_process_options())
        job['worker_pid'] = process.pid
        # Reap while the stdio server lives; daemonization keeps workers independent
        # when the coordinator closes its MCP connection.
        threading.Thread(target=process.wait, daemon=True).start()

    def executor_status(self, job_id):
        with self.transaction() as state:
            return self._view(self._job(state, job_id))

    def executor_result(self, job_id):
        with self.transaction() as state:
            job = self._job(state, job_id)
            path = Path(job['receipt'])
            return dict(job=self._view(job), receipt=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None)

    def _check_dependencies(self, state, job):
        if not job['dependencies']:
            return
        _, current, _ = self._source(state)
        for pinned in job['dependencies']:
            dependency = self._job(state, pinned['job_id'])
            if dependency['status'] != 'accepted' or dependency['task'] != pinned['task']:
                raise ValueError('Pinned dependency acceptance changed')
            if not any(t['issue_id'] == pinned['task']['issue_id'] and t['revision_hash'] == pinned['task']['revision_hash'] for t in current):
                raise ValueError('Pinned dependency source revision changed')
            evidence = validated_receipt(dependency['executor_config'], dependency['receipt'])
            if evidence['attempt_id'] != pinned['attempt_id']:
                raise ValueError('Pinned dependency attempt changed')

    def executor_continue(self, job_id, assignment, recover_only=False):
        if not isinstance(assignment, str) or not isinstance(recover_only, bool) or (not recover_only and not assignment.strip()):
            raise ValueError('A new bounded assignment is required for continuation')
        with self.transaction() as state:
            job = self._job(state, job_id)
            if job['status'] in {'accepted', 'superseded'}:
                raise ValueError('Accepted or superseded task is closed')
            if job['status'] == 'running' and self._worker_alive(job):
                raise ValueError('Original executor worker is still active or launching')
            lock_path = self.root / (job_id + '.worker.lock')
            with open(lock_path, 'a') as lock:
                try:
                    acquire_lock(lock, blocking=False)
                except BlockingIOError:
                    raise ValueError('Original executor worker is still active')
                if not Path(job['receipt']).exists() or 'executor_config' not in job:
                    if recover_only:
                        raise ValueError('No original executor receipt exists to observe')
                    if job.get('phase') not in {'claiming', 'preparing', 'worker_validation_failed'}:
                        raise ValueError('Original submission receipt missing; inspect manually, never replace session')
                    project, tasks, _ = self._source(state)
                    if not any(t['issue_id'] == job['task']['issue_id'] and t['revision_hash'] == job['task']['revision_hash'] for t in tasks):
                        raise ValueError('Task source revision changed before preparation retry')
                    self._check_dependencies(state, job)
                    self._admit(state, job, True)
                    if assignment.strip():
                        job['assignment'] = assignment
                    if job.get('phase') == 'worker_validation_failed':
                        config = job['executor_config']
                        proof = dict(workspace=config['cwd'], base_head=config['base_head'], owned_paths=config['owned_paths'], task_identity=config['task_identity'])
                        resume(self.workspace, job['task'], self.root, job['owned_paths'], proof)
                        job.update(phase='launching', status='reserved')
                        atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2))
                        try:
                            self._schedule(state, job, 'start')
                        except Exception as exc:
                            job.update(status='recovery_required', error=str(exc))
                            record_executor_notification(state, job)
                    else:
                        self._prepare_and_launch(state, job, project)
                    return self._view(job)
                if not recover_only:
                    self._current(state, job['task'])
                    self._check_dependencies(state, job)
                receipt = json.loads(Path(job['receipt']).read_text(encoding='utf-8'))
                resume(self.workspace, job['task'], self.root, job['owned_paths'], receipt)
                if not recover_only and (not receipt.get('thread_id') or receipt.get('status') not in {'verified', 'checks_failed', 'verification_failed', 'failed', 'canceled', 'timed_out', 'completed'}):
                    raise ValueError('Original job requires recovery before continuation')
                self._admit(state, job, True)
                job['assignment'] = assignment
                self._schedule(state, job, 'recover' if recover_only else 'resume')
            return self._view(job)

    def _report(self, job, summary, report):
        path = self.root / (job['id'] + '.html')
        details = '<pre>' + html.escape(report) + '</pre>' if report != summary else ''
        content = '<!doctype html><meta charset="utf-8"><title>Coordinator acceptance</title><h1>Coordinator acceptance</h1><p>' + html.escape(summary) + '</p>' + details + '<p>Isolated worktree; not merged or deployed.</p>'
        atomic_write(path, content)
        os.chmod(path, 0o600)
        return {'local_path': str(path), 'url': None, 'access_verified': False}

    def task_finish(self, job_id, accepted, summary, report=None):
        if not isinstance(accepted, bool) or not isinstance(summary, str) or not summary.strip():
            raise ValueError('Explicit acceptance and a nonempty summary required')
        if report is None:
            report = summary
        if not isinstance(report, str) or not report.strip():
            raise ValueError('Report must be nonempty text when supplied')
        with self.transaction() as state:
            job = self._job(state, job_id)
            decision = dict(accepted=accepted, summary=summary, report=report)
            if job.get('decision') == decision and job['status'] in {'accepted', 'rejected', 'superseded'}:
                return self._view(job)
            if job['status'] in ACTIVE or job['status'] in {'accepted', 'superseded'}:
                raise ValueError('Observe/recover executor before accepting; accepted task is closed')
            # write_result owns terminal-status retry validation. A previous result
            # mutation may have succeeded before its response was persisted.
            project, current_tasks, _ = self._source(state)
            if not any(t['issue_id'] == job['task']['issue_id'] and t['revision_hash'] == job['task']['revision_hash'] for t in current_tasks):
                if accepted:
                    raise ValueError('Task source authorization/revision changed')
                # Explicit coordinator rejection may retire an inactive obsolete
                # version locally. Never publish over the new source revision.
                job.update(status='superseded', decision=decision,
                    report=self._report(job, summary, report), finished_at=time.time(),
                    integration='isolated_unmerged', source_changed=True, writeback=None)
                return self._view(job)
            if accepted:
                self._check_dependencies(state, job)
                resume(self.workspace, job['task'], self.root, job['owned_paths'], json.loads(Path(job['receipt']).read_text(encoding='utf-8')))
                validated_receipt(job['executor_config'], job['receipt'])
            job['report'] = self._report(job, summary, report)
            job['decision'] = decision
            atomic_write(self.path, json.dumps(state, ensure_ascii=False, indent=2))
            if self.config['source']['type'] == 'github':
                job['writeback'] = write_result(self.config, job['task'], project, summary, job['report'], accepted, gh, False)
            job.update(status='accepted' if accepted else 'rejected', finished_at=time.time(), integration='isolated_unmerged')
            return self._view(job)

    def run_worker(self, job_id, attempt_id=None):
        with open(self.root / (job_id + '.worker.lock'), 'a') as lock:
            acquire_lock(lock, blocking=False)
            method_started = False
            receipt = None
            try:
                with self.transaction() as state:
                    job = dict(self._job(state, job_id))
                    if ((attempt_id is not None and job.get('attempt_id') != attempt_id)
                            or job['status'] != 'running'):
                        return  # Stale workers never execute or replace newer outcomes.
                    attempt_id = job.get('attempt_id')
                    if job['config_hash'] != self.config_hash:
                        raise ValueError('Dispatch configuration changed')
                    if job['mode'] != 'recover':
                        self._current(state, job['task'])
                        self._check_dependencies(state, job)
                def announce(info):
                    if info['thread_id'] == self.owner:
                        raise ValueError('Executor must be independent of coordinator')
                    if self.config['source']['type'] == 'github' and job['mode'] != 'recover':
                        write_executor_session(self.config, job['task'], fetch(self.config), info['thread_id'], gh, False)
                brief = job['assignment'] + '\n\nAuthorized task source:\n' + json.dumps(job['task'], ensure_ascii=False) + '\n\nPinned dependency evidence (reference only, not merged):\n' + json.dumps(job['dependencies'], ensure_ascii=False)
                method = {'start': execute_assignment, 'resume': resume_assignment, 'recover': recover_assignment}[job['mode']]
                args = (job['executor_config'], job['receipt'], self.config['node'])
                method_started = True
                receipt = method(*args, on_session=announce) if job['mode'] == 'recover' else method(brief, *args, on_session=announce)
                status, error = receipt['status'], None
            except Exception as exc:
                status, error = 'recovery_required', str(exc)
                if 'job' in locals() and Path(job['receipt']).exists():
                    try:
                        receipt = receipt_for_job(job)
                        if receipt.get('status') in EVENT_STATUSES - {'completed', 'verified'} or (not method_started and receipt.get('status') == 'verified'):
                            status = receipt['status']
                    except (OSError, ValueError) as receipt_error:
                        receipt = None
                        error += '; ' + str(receipt_error)
                elif 'job' in locals() and job.get('mode') == 'start' and not method_started:
                    # The worker itself proves it rejected admission before calling
                    # the bridge. No native job exists; preserve the worktree.
                    status = 'preparation_failed'
                    job['phase'] = 'worker_validation_failed'
            with self.transaction() as state:
                current = self._job(state, job_id)
                if current.get('attempt_id') != attempt_id:
                    return
                current.update(status=status, error=error, observed_at=time.time())
                if status == 'preparation_failed':
                    current['phase'] = 'worker_validation_failed'
                record_executor_notification(state, current, receipt)
        # Detached workers can notify after their coordinator's MCP turn ends.
        # Delivery failure must not overwrite the executor's actual outcome.
        try:
            deliver_executor_notifications(self.config_path)
        except Exception as exc:
            print(json.dumps({'notification_error': str(exc)}), file=sys.stderr, flush=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--worker', required=True)
    parser.add_argument('--attempt')
    args = parser.parse_args()
    DelegationService(args.config).run_worker(args.worker, args.attempt)


if __name__ == '__main__':
    main()
