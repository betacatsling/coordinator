---
name: project-delegation
description: Use the user's chosen native Codex session as a project coordinator, dispatch independent persistent executors through MCP, review their work and follow it through acceptance. Trigger with “你作为这个项目的 coordinator” or “Be this project's coordinator”.
---

# Project delegation

## Start in this session

Treat “你作为这个项目的 coordinator” as the entry request. Resolve the selected repository, GitHub Project and authorized user from an explicit project configuration. Use the actual tool runtime's `CODEX_THREAD_ID`; verify that the native AppServer returns that exact loaded thread and workspace before initializing its fresh binding. Never ask the user to paste an identity, choose another session implicitly or manufacture a binding.

Read [coordinator tools](references/coordinator-tools.md). MCP discovery requires no thread identity; business calls require host-supplied `_meta.threadId` matching the verified binding, never a copied environment value or model identity argument. Run `coordinator_bootstrap.py --config /absolute/config.json init` from the selected workspace. This initializes only `.project-delegation/runtime/binding.json`; a matching binding is verified and reused. A different owner, scope, or populated unbound runtime blocks initialization without overwriting it. Existing files elsewhere are untouched. There is no automatic process startup or termination.

Check the actual delegation MCP tools exposed in this session and successfully call `tasks_list`. A skill checkout or successful bootstrap does not register an MCP server or establish live tool availability. If configuration or tools are missing, explain the exact missing step and ask only for information that cannot be read safely.

## Coordinate directly

1. Read current board tasks, Issue text, authorized comments, repository code and linked artifacts. Reconcile durable jobs before dispatching more work
2. Decide the split here. Give each executor a bounded outcome, owned paths, dependencies, resources and acceptance checks. Run independent tasks in parallel within capacity; avoid overlapping edits and preserve dirty project files
3. Call `executor_start` directly. Each task gets an independent persistent Codex session and isolated worktree. Use actual tool results to distinguish reserved, waiting and running work
4. Check `executor_status` and inspect `executor_result`. Request corrections through `executor_continue` in the original session and workspace. Investigate blocked checks while other independent work continues
5. Inspect changes and observed checks against current requirements before `task_finish`. A completed executor turn is only ready for review. Accepted isolated changes still require separately authorized integration before project completion
6. Report useful outcomes, verified evidence, artifacts and remaining decisions. Publish only authorized configured write-back. A private local report path is not a shareable hosted URL

Keep responsibility through corrections and acceptance. Do not merge, push, deploy or close Issues automatically. If recovery is unavailable, preserve receipts and report the blocker instead of creating a replacement session.

## Optional notifications

The board watcher only reports changed inputs to the bound coordinator. It never plans, dispatches or accepts work, and never interprets chat as a machine plan. Initialize its current board baseline explicitly, then start it only when requested. Existing eligible tasks remain visible through `tasks_list`; baseline initialization does not dispatch or replay them.

This is a fresh experimental runtime with no compatibility or migration path. Source changes and offline tests do not establish live MCP discovery, native notification delivery or live GitHub execution. See [validation evidence](VALIDATION.md).
