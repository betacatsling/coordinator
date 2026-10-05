# Coordinator-driven delegation

Use this reference when the chosen native Codex session directly manages independent executor sessions through MCP. Read the server's exposed schemas before calling tools; the installed version is authoritative.

## Responsibility and review

The coordinator reads the project, chooses tasks and parallelism, dispatches executors, handles follow-ups and decides whether the result meets the request. Review the actual changes and relevant tests against the task goal. The runtime records the Git diff, changed paths and check outcomes automatically; executors do not need to write a separate artifact manifest, compute file hashes or fill a fixed-field checklist.

An executor finishing its turn means the result is ready for review. Accepting isolated work does not merge it or make a requested deployment available. State that remaining work when it affects delivery; it is not a required disclaimer for every update. Do not infer behavioral correctness from static checks or a successful process exit.

The local dashboard service watches board changes and reconciles completion notices. It does not plan, dispatch or accept work.

## Tool workflow

Bootstrap → initial `tasks_list` → dispatch independent executors → end the coordinator turn → completion notice → inspect results and continue or accept. Board changes return to `tasks_list` in the same session. Do not keep an idle coordinator turn running through repeated status calls or tool-side sleeps.

### `tasks_list()`

Read the current authorized eligible task identities and durable jobs. Match both the Issue identity and current revision before dispatch. Reconcile existing jobs first; a notification is a reason to inspect current state, not an instruction to replay every historical task.

### `executor_start(issue_id, revision_hash, assignment, owned_paths, depends_on, resources)`

Start one independent persistent Codex executor with a bounded assignment. Use the exact task identity and revision returned by current intake. Keep `owned_paths` minimal and relative to the project. `depends_on` lists accepted **job IDs**, not Issue numbers; `resources` uses approved configured resource names. Both lists default to empty.

A dependency supplies pinned accepted receipts as context; it does not apply another executor's patch to this worktree. If implementation requires predecessor changes in the filesystem, arrange the authorized integration/base first or keep the work waiting.

Record the returned job, thread and workspace identities. Observe the result if capacity, eligibility, leases or publication prevents startup; do not assume a requested start is a running executor. Retry using the durable state rather than creating another task session.

### `executor_status(job_id)` and `executor_result(job_id)`

Use status for lifecycle/progress and result for the saved execution record, Git changes and recorded check commands, exit codes and output. Read the changed code and run any further relevant checks needed to judge the goal. No manually prepared file inventory or checksum report is needed. Recover an uncertain process outcome before deciding whether another turn is needed.

### `executor_continue(job_id, assignment, recover_only)`

Continue the original task's native session and workspace with a concrete correction or follow-up before final acceptance. Rejected results may be corrected this way; accepted jobs are closed. With `recover_only: true`, observe the existing bridge job without submitting a new turn. If original-session recovery is unavailable, report the specific blocker and retain the receipt; do not replace it with a new session as a recovery shortcut. A `preparation_failed` reservation releases its slot and leases. Before any executor was launched, this tool can retry that original reservation using its durable claiming/preparing phase and idempotent claim. A missing receipt after launch remains a manual-recovery blocker.

### `task_finish(job_id, accepted, summary, report?)`

Record the coordinator's decision after reviewing the work. Use `accepted: true` only when the current result and relevant checks support the task goal. The runtime checks the task/attempt identity, owned paths and that the reviewed Git changes are still current. These guards do not substitute for the coordinator's judgment. When rejecting, explain the correction needed.

`summary` is a short, plain-language Issue update: what was done, what the checks showed and any meaningful limitation. `report` is optional free-form supporting detail; omit it when the summary is enough. The generated report then uses the summary. Neither requires a fixed set of fields, a file inventory, hashes or repeated runtime metadata. Mention unmerged changes when that affects the requested delivery; do not imply integration happened. Keep debug identifiers and local paths out of the result comment.

The tool records integration status, renders a private local HTML report and performs configured write-back. The local dashboard can preview or download the report. A usable hosted report link may be included in the Issue comment when available; the default local report has `url: null`, so do not promise a public link or add a missing-link notice. The tool does not merge, push or deploy.

If the source has changed, acceptance refuses the stale result. Explicitly rejecting an inactive stale job retires it locally as `superseded`, releases its leases and returns `source_changed: true` with `writeback: null`; it does not publish stale results. Rejection of an unchanged task remains retryable in the original session.

## Fresh setup

Use `assets/fresh-config.example.json` as a template, not a ready-to-run profile. Set the selected repository, Project, authorized user, absolute workspace and exact board mappings. Enable isolated executors. Live GitHub execution requires authorized enabled, non-dry-run claim write-back. Capacity is one to three jobs, default three. Review the configuration before initialization: existing notification history pins it, and later changes fail closed. Restore the original configuration rather than reset history; use `--no-open` to suppress browser opening without editing it.

Run from the selected workspace:

```sh
python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/config.json init
python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/config.json status
```

The entry point reads the actual runtime `CODEX_THREAD_ID` and verifies native AppServer thread identity, cwd and loaded status. It initializes `.project-delegation/runtime/binding.json` or verifies an exact matching binding. A different owner or scope and a populated unbound runtime fail closed. After binding, initialization starts or reuses the single local dashboard-and-notification service. It does not create a new shared AppServer. A status check does not create state, start services or open a browser. `app_server_socket` may select a supported socket; otherwise the endpoint is discovered through the configured `codex` executable.

Coordinator state lives under the fixed `.project-delegation/runtime` directory: `binding.json`, `jobs.json`, `notifier.json`, `notifier-service.json`, `dashboard.json`, plus local locks, logs and acceptance reports. Do not point configuration at a different state directory. Existing data elsewhere is neither imported nor deleted.

## Explicit MCP connection

Register this stdio command using the actual Codex client's supported MCP configuration:

```sh
python3 /absolute/skill/scripts/delegation_mcp.py --config /absolute/config.json
```

MCP startup does not require `CODEX_THREAD_ID`: `initialize`, `ping` and `tools/list` work without a caller identity or binding. Every business tool call requires the Codex host's request `_meta.threadId`, checked against the existing project binding and scope. Missing, malformed or different identities return a tool error without stopping the server. Identity arguments supplied by the model are rejected; the server environment is never an MCP caller fallback. Never insert a copied `CODEX_THREAD_ID` into a generic global server configuration.

Use a Codex client version that actually sends per-call thread metadata. Current [official Codex source](https://github.com/openai/codex/blob/main/codex-rs/core/src/mcp_tool_call.rs) injects `threadId`; verify the installed host rather than assuming every release supports it. This relies on the private, host-owned stdio connection, not cryptographic authentication of arbitrary clients; do not expose it as an unauthenticated network service. Bootstrap still uses the authentic shell runtime identity. Detached workers receive the identity from their already authorized dispatch, never from a global configuration. Check that all six tools are actually exposed in the chosen session, inspect their installed schemas and verify a successful read-only `tasks_list` call. A source checkout, bootstrap success or offline tests do not prove a live MCP connection. MCP registration does not refresh a running client; bootstrap starts the local service only after binding verification. Report the specific missing setup step when discovery or identity checks fail.

## Event-driven notifications

Bootstrap starts the notification watcher inside the same local process as the dashboard. Its first successful initialization records the current eligible board versions silently. They remain available through the coordinator's initial `tasks_list`; the baseline does not dispatch or replay them. Later source changes or ready-state re-entry generate notices to the same bound session.

When an executor attempt finishes or becomes blocked, its actual outcome and a completion notice are persisted together in `jobs.json`. The notice identifies the job and attempt and asks the coordinator to inspect `executor_status` / `executor_result`. It does not contain free-form executor output or decide acceptance. The worker attempts delivery immediately; the local service handles remaining prepared notices and reconciles uncertain or queued submissions.

Keep delivery evidence separate from work:

- **Service healthy:** the bound watcher has a live process, fresh heartbeat and recent successful check; this says nothing about a particular coordinator turn
- **Prepared / submitting:** a durable notice is pending, or submission may be uncertain
- **Queued:** the native host returned a queue receipt; this is not evidence of a started turn
- **Delivered:** the exact notice appears as a user message in the original native thread. `turn_id` and `turn_status` distinguish `inProgress`, `completed`, `failed`, `interrupted` or an unknown outcome
- **Implementation accepted:** the coordinator reviewed the work and called `task_finish`; no notification state implies this

Delivered in-progress turns continue to be reconciled until their outcome is known. `rejected` records an explicit queue rejection; `obsolete` retires a definitely unsent completion notice after the job was already continued or reviewed. An uncertain submission is retained without automatic resubmission. A failed or interrupted coordinator turn proves delivery, not successful review; inspect `turn_error` and the durable job. Never create a replacement coordinator to mask a delivery or recovery problem.

Use `coordinator_bootstrap.py --config /absolute/project.json status` for read-only binding/service diagnostics, including baseline, recent watcher observations and coordinator availability. The same command with `stop` shuts down the matching dashboard and watcher together, leaving executor jobs and history intact. The low-level `board_notifier.py` commands are for diagnosis, not an additional startup step; do not start a competing watcher beside the local service. See [service lifecycle](web-dashboard.md) and [validation limits](../VALIDATION.md).
