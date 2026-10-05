---
name: project-delegation
description: Coordinate a project's GitHub board from the user's chosen Codex session and delegate work to independent persistent Codex executors. Use when the user says “你作为这个项目的 coordinator”, asks this session to coordinate a project, or asks it to dispatch, monitor, resume or accept project tasks.
---

# Project delegation

## Use the chosen session as coordinator

Treat “你作为这个项目的 coordinator” as the entry request. Resolve the current workspace, repository, configured GitHub Project and real runtime session identity. Keep the user's chosen native Codex session as the coordinator across turns. Reuse its binding; ask only for genuinely missing configuration or an ownership decision.

Act as the project manager: read Issues, comments, repository code, linked artifacts and available tools; decide how to split work, what can run in parallel and what evidence is needed. Make these decisions in this conversation and call the delegation MCP tools directly. Do not emit machine-plan JSON for a watcher to interpret. A watcher only reports changes or wakes this session; it does not plan, dispatch or accept work.

Read [coordinator tools](references/coordinator-tools.md) for the installed tool contract and setup/migration checks. Check actual availability before using this mode. A source checkout, pending binding or offline test does not establish a live MCP connection or an active watcher.

## Run the project

1. **Understand current work.** Use `tasks_list` and read the current task sources and artifacts. Start with the configured board and authorized scope. Reconcile existing tasks before launching more; determine whether changed inputs invalidate a plan or result.
2. **Choose a useful split.** Give each executor a clear outcome, owned paths, dependencies, relevant context and acceptance checks. Parallelize independent work within the configured capacity. Wait on shared resources or overlapping edits, and preserve dirty project work.
3. **Dispatch directly.** Use `executor_start` for each admitted task. Each task gets its own persistent Codex session and receipt. Let the MCP implementation enforce eligibility, leases, capacity and retry-safe records; use its actual response to distinguish waiting, admitted and running work.
4. **Stay responsible for progress.** Use `executor_status` for progress and `executor_result` for actual output and artifacts. Investigate stalls or failed checks. Use `executor_continue` for corrections or follow-ups in the original task session and workspace. Keep independent work moving while a task waits for evidence or a user decision.
5. **Accept the delivered outcome.** Inspect the changes and observed checks against the task's current requirements. Run or request missing checks. An executor reporting “done” means its turn ended, not that the project task is complete. A patch remaining only in an isolated worktree still needs integration; preserve that distinction in the outcome recorded through `task_finish`.
6. **Report what matters.** Tell the user what changed, what was verified, where the artifacts are, and what remains blocked or needs a decision. Publish only the configured, authorized write-back. Treat local reports as local until the user's access to a private link is verified.

Keep working through corrections and acceptance within the user's scope. Do not automatically merge, push or close an Issue to make a task look finished. Explain an unavailable tool, unsupported recovery or missing permission with its concrete impact rather than replacing the chosen coordinator or silently creating a duplicate executor.

## Setup and compatibility

Normal coordination begins after the required project binding and delegation tools are available. Installing this skill does not register MCP tools, restart a session, activate a watcher or switch a production controller.

For a new setup or migration, use [coordinator tools](references/coordinator-tools.md). Preserve active legacy work and its receipts until settled; changing the configured coordination mode is a separate explicit step. Read [current-session binding](references/manual-coordinator.md) and [GitHub configuration](references/github-acpx.md) only when resolving existing setup or compatibility behavior. Use [document watching](references/file-watch.md) only when explicitly selected. Check [validation evidence](VALIDATION.md) for what has actually been tested.
