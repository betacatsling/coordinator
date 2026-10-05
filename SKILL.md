---
name: project-delegation
description: Use when the user asks you to be the current project's coordinator (你作为这个项目的 coordinator), coordinate GitHub board tasks, or delegate project work to parallel persistent Codex executors. Resolve the project and current session, preserve existing ownership, plan independent work and verify results.
---

# Project delegation

## Start with the current session

Treat “你作为这个项目的 coordinator” as the entry request. Resolve the actual current workspace, Git repository, existing project binding and runtime `CODEX_THREAD_ID` session identity; do not ask the user to supply commands or invent session IDs. Run the installed `scripts/coordinator_bootstrap.py` in that workspace and follow [current-session binding](references/manual-coordinator.md).

Reuse an active owner or existing pending registration. Resolve only genuine configuration ambiguity with the user. Pending registration is not activation: let the supported controller transport establish readiness and ownership before dispatch. Never prompt the current session through legacy ACP while its registration turn is active. Never create a replacement coordinator or take over a busy owner to make activation appear successful. A role request does not itself authorize selecting or launching unrelated tasks.

## Coordinate the selected GitHub board

Use the selected GitHub Project/repository and its configured board as the default task source. Follow [configuration and execution](references/github-acpx.md) for the verified view, status/type mappings, executor settings and write-back protocol. Read current Issue bodies and authorized user comments, including relevant linked document snapshots. Do not require a separate PROJECT.md.

1. Admit only eligible current task versions. Respect the configured ready state and excluded task types; labels alone are not a gate. Polling or queueing is not a claim. Recheck scope, revision and eligibility before admission and write-back.
2. Plan independently verifiable tasks with explicit owned paths, dependencies, approved shared resources and acceptance checks. Keep coordinator planning and acceptance serialized. Use one independent persistent Codex executor per task, default three parallel slots; configure a different limit when needed. Executors do not recursively delegate or share a global task session.
3. Wait on unsatisfied dependencies and overlapping file/resource leases. Reconcile changed task versions and stale results before continuing. Preserve dirty work; use detached worktrees or explicitly nonoverlapping ownership. A file ownership policy is not an operating-system sandbox.
4. Post one retry-safe claim only for an actually admitted slot and update the configured in-progress status. Append the real executor ID to that same claim when available. Resume follow-ups in the task's original session/workspace; never silently replace a failed or interrupted executor.
5. Inspect actual artifacts and observed checks before accepting. Distinguish coordination, static validation, behavioral tests and domain conclusions. Re-read current inputs before publishing; do not overwrite newer human decisions or mark an isolated unmerged patch fully done.
6. Publish a concise result comment and HTML report through the configured renderer. Use only verified private report links and check reader access; otherwise state that only a local report exists. Exclude own claim/result comments and reports from new task input.

## Respect boundaries

Keep the selected repository, Project, authorized user and configured permissions fixed. Missing MCP access, unsupported session recovery, incomplete GitHub pagination, invalid mappings or unsafe approvals block the affected operation. Use actual tool schemas and configured runtimes; do not invent success, copy credentials, broaden permissions or auto-approve unsafe actions.

Do not stop other owners, migrate live watchers, merge, push, close Issues or start persistent report services without the required authorization. Keep queue, baseline, deduplication records and task/session receipts across safe handoffs. Installation does not activate a controller or change production configuration.

## References

- [Current-session binding](references/manual-coordinator.md): discovery, pending enrollment, verification and owner handoff
- [GitHub workflow](references/github-acpx.md): board configuration, execution, claims, results and private reports
- [Legacy document watcher/hooks](references/file-watch.md): use only when explicitly selected; do not combine with the default input owner
- [Validation](VALIDATION.md): observed test coverage and unverified end-to-end behavior
