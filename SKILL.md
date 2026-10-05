---
name: project-delegation
description: Use the user's chosen native Codex session as a project coordinator, dispatch independent persistent executors through MCP, and review their results when completion or board-change notices arrive. Trigger with “你作为这个项目的 coordinator” or “Be this project's coordinator”.
---

# Project delegation

## Start in this session

Treat “你作为这个项目的 coordinator” as the entry request. Resolve the repository, GitHub Project and authorized user from the reviewed project configuration. Use the actual tool runtime's `CODEX_THREAD_ID`; verify that the native AppServer returns that exact loaded thread and workspace. Never ask the user to paste an identity, silently choose another session or manufacture a binding.

Read [coordinator tools](references/coordinator-tools.md). Run `coordinator_bootstrap.py --config /absolute/project.json init` from the selected workspace. It creates or verifies `.project-delegation/runtime/binding.json`, then starts or reuses the single local dashboard-and-notification service. A different owner, scope or populated unbound runtime blocks initialization without overwriting it.

Return the actual `dashboard_url`, notification health and any warning. On a local desktop, the project page opens in the default browser; repeated initialization reuses the healthy service and does not reopen a successfully opened page for this coordinator. `--no-open` or `"dashboard": {"auto_open": false}` suppresses only the browser. SSH/headless URLs belong to the runtime host and need a separately arranged private tunnel for remote viewing. Service failures leave the binding intact but do not establish working notifications. `status` is read-only. See [service and dashboard lifecycle](references/web-dashboard.md).

Verify the six delegation MCP tools are exposed in this session and call `tasks_list` immediately. Initial board contents become the notification baseline, so this first read is essential. A checkout, MCP registration or bootstrap alone does not prove tool availability. MCP discovery needs no identity; business calls require host-supplied `_meta.threadId` matching the binding, never a copied environment value or model argument. Ask only for missing configuration or permissions that cannot be resolved safely.

## Dispatch, yield, review

1. Read current tasks, Issue text, authorized comments, code and linked artifacts. Reconcile durable jobs before dispatching more work
2. Decide the split here. Give each executor a bounded outcome, owned paths, dependencies, resources and relevant checks. Run independent tasks in parallel within capacity; avoid overlapping edits and preserve dirty project files
3. Call `executor_start`. Each task gets an independent persistent Codex session and isolated worktree. Distinguish reserved, waiting and running work using the returned evidence
4. When useful independent work is dispatched, report the pending work briefly and **end this coordinator turn**. Do not keep the turn busy by sleeping in tools or repeatedly polling. Completion notices and board changes target this same session; they do not create another coordinator
5. On a completion notice, read `executor_status` and `executor_result`. Review the actual changes and relevant test results against the task goal. Use `executor_continue` for corrections in the original session, then yield again. Use `task_finish` only after review
6. On a board-change notice, call `tasks_list` and reconcile the current revision and existing jobs before deciding what to dispatch. A notice is not authorization to replay old work
7. Report what changed, the result of relevant checks and any remaining decision or blocker. Keep routine updates brief; notification delivery and a completed executor turn do not establish that the task goal was met

Keep responsibility through corrections and acceptance. The runtime collects the Git changes and check results; do not ask executors to prepare a separate artifact manifest, file hashes or a fixed-field evidence checklist. A successful check does not replace reviewing whether the work meets the request.

An executor ending a turn is only ready for review. Accepted isolated changes still require authorized integration; do not automatically merge, push, deploy or close Issues. Mention remaining integration when it affects delivery, rather than repeating unrelated status boilerplate in every update. If original-session recovery is unavailable, preserve the execution record and report the blocker.

## Notifications and reports

The local service only observes board changes and delivers/reconciles notices; it never plans, dispatches or accepts work. Executor outcomes are saved with durable completion notices before delivery is attempted. An uncertain submission is retained for reconciliation rather than blindly resent. Delivery depends on the bound native session and host; a healthy service or queued notice is not proof that the session has started processing it. `delivered` confirms the exact input appeared in the original thread; its `turn_status` is separate from executor outcome and task acceptance.

Use a short, natural-language Issue summary: what was done, what the checks showed and any meaningful limitation. Include a usable report link when one exists; keep local paths, debug fields and missing-link notices out of the result comment. The HTML report can hold useful supporting detail without a required section list or copied runtime fields. Publish only authorized configured write-back.

HTML reports remain private local files, readable through the dashboard's isolated static preview or original download. Scripts and external resources are disabled in the preview. GitHub links provide verified source context, not public report hosting.

This is an experimental fresh runtime. Offline tests do not establish live notification wakeup, browser behavior or GitHub execution. See [validation evidence](VALIDATION.md).
