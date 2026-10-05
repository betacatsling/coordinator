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

## Fresh setup

Use `assets/fresh-config.example.json` as a template, not a ready-to-run profile. Set the selected repository, Project, authorized user, absolute workspace and exact board mappings. Enable isolated executors. Live GitHub execution requires authorized enabled, non-dry-run claim write-back. Capacity is one to three jobs, default three.

Run from the selected workspace:

```sh
python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/config.json init
python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/config.json status
```

The entry point reads the actual runtime `CODEX_THREAD_ID` and verifies native AppServer thread identity, cwd and loaded status. It initializes `.project-delegation/runtime/binding.json` or verifies an exact matching binding. A different owner or scope and a populated unbound runtime fail closed. There is no thread-ID override, ownership transfer, state conversion, process termination or automatic startup. A status check does not create state. `app_server_socket` may select a supported socket; otherwise the endpoint is discovered through the configured `codex` executable.

All durable files live under the fixed `.project-delegation/runtime` directory: `binding.json`, `jobs.json`, `notifier.json`, plus locks and job artifacts. Do not point configuration at a different state directory. Existing data elsewhere is neither imported nor deleted.

## Explicit MCP connection

Register this stdio command using the actual Codex client's supported MCP configuration:

```sh
python3 /absolute/skill/scripts/delegation_mcp.py --config /absolute/config.json
```

MCP startup does not require `CODEX_THREAD_ID`: `initialize`, `ping` and `tools/list` work without a caller identity or binding. Every business tool call requires the Codex host's request `_meta.threadId`, checked against the existing project binding and scope. Missing, malformed or different identities return a tool error without stopping the server. Identity arguments supplied by the model are rejected; the server environment is never an MCP caller fallback. Never insert a copied `CODEX_THREAD_ID` into a generic global server configuration.

Use a Codex client version that actually sends per-call thread metadata. Current [official Codex source](https://github.com/openai/codex/blob/main/codex-rs/core/src/mcp_tool_call.rs) injects `threadId`; verify the installed host rather than assuming every release supports it. This relies on the private, host-owned stdio connection, not cryptographic authentication of arbitrary clients; do not expose it as an unauthenticated network service. Bootstrap still uses the authentic shell runtime identity. Detached workers receive the identity from their already authorized dispatch, never from a global configuration. Check that all six tools are actually exposed in the chosen session, inspect their installed schemas and verify a successful read-only `tasks_list` call. A source checkout, bootstrap success or offline tests do not prove a live MCP connection. Installation does not refresh a running client or start a watcher. Report the specific missing setup step when discovery or identity checks fail.

## Optional notification-only watcher

After a binding is initialized, explicitly choose a current-board baseline:

```sh
python3 scripts/board_notifier.py --config /absolute/config.json init --baseline current
python3 scripts/board_notifier.py --config /absolute/config.json once
# Only when continuous notifications are requested:
python3 scripts/board_notifier.py --config /absolute/config.json watch
```

`--baseline current` records currently eligible versions silently. They remain available through `tasks_list`; initialization does not replay or dispatch them. Subsequent source changes or ready-state re-entry may notify the bound session. The watcher never plans, claims, dispatches or accepts work. Its own `notifier.lock` prevents duplicate scanners; the service uses `jobs.lock` for durable job transactions.

Use the watcher's `status` command to inspect its outbox and errors. An uncertain submission remains for reconciliation rather than being automatically resent. A queued notification does not prove the coordinator processed it. Check [validation evidence](../VALIDATION.md) before claiming native delivery or live GitHub execution has been verified.
