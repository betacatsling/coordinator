# Coordinator-driven delegation

Use this reference when the chosen native Codex session directly manages independent executor sessions through MCP. Read the server's exposed schemas before calling tools; the installed version is authoritative.

## Responsibility and evidence

The coordinator reads the project, chooses tasks and parallelism, dispatches executors, handles follow-ups, inspects artifacts and decides acceptance. The MCP server supplies durable execution records and deterministic checks. A watcher is only an input-change notification source; it does not run a second planning/acceptance loop.

Keep three distinct states in reports:

- **Executor turn complete:** output is ready for inspection
- **Implementation accepted:** the coordinator verified the isolated artifacts and checks
- **Project task complete:** the requested deliverable, including any required integration or deployment, is actually available

Acceptance of a detached worktree does not merge it. Preserve the remaining integration work in the result and board status. Do not infer behavioral correctness from static checks or a successful process exit.

## Tool workflow

### `tasks_list()`

Read the current authorized eligible task identities and durable jobs. Match both the Issue identity and current revision before dispatch. Reconcile existing jobs first; a notification is a reason to inspect current state, not an instruction to replay every historical task.

### `executor_start(issue_id, revision_hash, assignment, owned_paths, depends_on, resources)`

Start one independent persistent Codex executor with a bounded assignment. Use the exact task identity and revision returned by current intake. Keep `owned_paths` minimal and relative to the project. `depends_on` lists accepted **job IDs**, not Issue numbers; `resources` uses approved configured resource names. Both lists default to empty.

A dependency supplies pinned accepted receipts as context; it does not apply another executor's patch to this worktree. If implementation requires predecessor changes in the filesystem, arrange the authorized integration/base first or keep the work waiting.

Record the returned job, thread and workspace identities. Observe the result if capacity, eligibility, leases or publication prevents startup; do not assume a requested start is a running executor. Retry using the durable state rather than creating another task session.

### `executor_status(job_id)` and `executor_result(job_id)`

Use status for lifecycle/progress and result for the durable receipt, actual artifacts and recorded checks. Inspect the reported paths and output as needed. Recover an uncertain process outcome before deciding whether another turn is needed.

### `executor_continue(job_id, assignment, recover_only)`

Continue the original task's native session and workspace with a concrete correction or follow-up before final acceptance. Rejected results may be corrected this way; accepted jobs are closed. With `recover_only: true`, observe the existing bridge job without submitting a new turn. If original-session recovery is unavailable, report the specific blocker and retain the receipt; do not replace it with a new session as a recovery shortcut. A `preparation_failed` reservation releases its slot and leases. Before any executor was launched, this tool can retry that original reservation using its durable claiming/preparing phase and idempotent claim. A missing receipt after launch remains a manual-recovery blocker.

### `task_finish(job_id, accepted, summary, report)`

Record the coordinator's decision after inspecting evidence. Use `accepted: true` only for artifacts the helper has verified against the current task and the coordinator has judged sufficient. Describe failed checks or required corrections when rejecting a result. Keep implementation acceptance and integration status explicit in `summary` and `report`.

The tool returns `integration: isolated_unmerged`, renders an escaped private local HTML report with `url: null`, and performs configured write-back. It provides no hosting, merge, push or deployment. A local path is not a shareable URL.

If the source has changed, acceptance refuses the stale result. Explicitly rejecting an inactive stale job retires it locally as `superseded`, releases its leases and returns `source_changed: true` with `writeback: null`; it does not publish stale results. Rejection of an unchanged task remains retryable in the original session.

## Setup and activation

This repository contains the coordinator-driven implementation. Its presence, documentation or offline tests do not establish that a running Codex session has loaded the MCP server. Check [validation evidence](../VALIDATION.md) and the actual tools exposed in the chosen session before reporting live availability.

Configuration uses `delegation.enabled: true` with the existing project board/source, executor runtime, write-back and report settings. Enable isolated executors (`executor.enabled` and `executor.isolate_worktree`); this mode supports one to three parallel jobs, default three. Live GitHub execution requires a verified board mapping and enabled, non-dry-run claim write-back. Configure those writes only within the user's authorization. The server reads only `notifier_state_directory/state.json` (default `.project-delegation/board-notifier/state.json`). Its top-level `scope` and `binding.scope` must match the project; `binding.transport` must be `app_server`, and `binding.provider_thread_id` must match the actual runtime `CODEX_THREAD_ID`. There is no legacy-state fallback. A title, user-supplied ID or manually edited identity is not evidence of a valid binding.

The stdio server entry point is:

```sh
python3 /absolute/skill/scripts/delegation_mcp.py --config /absolute/config.json
```

Register that command using the supported MCP configuration for the actual Codex client; run it with the authentic chosen session's runtime context. Never insert a copied `CODEX_THREAD_ID` into a generic global server configuration. Verify tool discovery and a read-only `tasks_list` call in the bound session. Do not promise that copying this skill automatically registers the server, refreshes tools in a running session, restarts Codex or starts a watcher. Report exactly which setup step is still needed if discovery or identity checks fail.

## Migrate without losing work

Treat the coordination-mode switch as a separate explicit configuration change:

1. Inspect the existing owner, controller, queue and executor receipts. Keep the current owner authoritative while admitted work is active. Preserve every existing running task and its original session during migration.
2. Let that work settle and reconcile its output, publication and integration state. A worker's completion alone does not settle a task whose artifact is still isolated or whose result is unpublished.
3. Preserve bindings, baseline/queue observations, deduplication markers and executor receipts. Use the supported handoff/configuration path once safe; do not edit identities to manufacture readiness or run two dispatch owners.
4. Verify the selected session's new tools and ownership before starting new work. Confirm any watcher that remains is notification-only; an old executing controller is not a harmless notifier.

The [binding guide](manual-coordinator.md) and [GitHub workflow](github-acpx.md) document older controller modes and shared configuration. Do not combine their controller-driven planning/dispatch loop with the direct MCP workflow. An installation or source update leaves the existing live configuration unchanged until the explicit switch is performed.

## Enrollment and optional board notifications

`scripts/board_notifier.py` establishes the owner state used by the delegation server and provides notification-only watching. After the authorized mode switch, initialize it with the verified registration and explicit baseline choice before connecting the server. Continuous watching is optional:

```sh
python3 scripts/board_notifier.py --config /absolute/config.json init \
  --registration /absolute/registration.json --baseline current
python3 scripts/board_notifier.py --config /absolute/config.json once
# Or, when continuous notifications are wanted:
python3 scripts/board_notifier.py --config /absolute/config.json watch
```

`--baseline current` silently records all currently eligible versions; it does not replay them. Confirm this migration choice deliberately so ready work is not mistaken for automatically dispatched work. Inspect current tasks through the coordinator tools as appropriate. Subsequent changed versions or ready-state re-entry can notify the chosen session.

The notifier uses a separate `notifier_state_directory` (default `.project-delegation/board-notifier`), the existing board/source scope and `delegation.enabled: true`. The notifier, delegation service and detached workers hold the canonical `.project-delegation/github-acpx/controller.lock` shared for their lifetimes. The legacy controller requires that lock exclusively, so it cannot run alongside them. The notifier additionally holds an exclusive `notifier.lock` in its own state directory to prevent duplicate scanners. Lock acquisition precedes state reads and initialization. Its default watch interval is ten seconds. Use `status` to inspect its outbox and errors; an uncertain submission is retained for reconciliation rather than automatically resent. A queued notification is not evidence that the coordinator has processed it or dispatched an executor.
