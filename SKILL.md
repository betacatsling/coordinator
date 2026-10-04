---
name: project-delegation
description: Coordinate document-led project work through mcp-agents Codex sessions, execute assigned tasks, or debounce local PROJECT.md input into durable coordinator turns. Use when the user requests project delegation, local automatic progression, or work assigned through this workflow.
---

# Project delegation

Use the user's project document as the source of goals, acceptance criteria, feedback, and task status. Resolve its absolute path and the project workspace before dispatch. Read the relevant sections and record a revision marker or content hash. Preserve the document's existing format.

## Coordinator

Split work into independently checkable tasks with stable IDs. Record each task's scope, owned files, dependencies, acceptance checks, document version, status, and execution `threadId` / `jobId`. Use separate workspaces or nonoverlapping file ownership for concurrent writers. Concurrency is configurable; default to two. Executors do not recursively delegate.

Use the available MCP tool schemas rather than guessing parameters. With the Codex provider, start independent work using `codex-start` with an absolute `cwd`, `sandbox: workspace-write`, and `allow_subagents: false`. The server must use `on-request` approvals. Include an executor brief: task ID, document path/version, relevant goals and feedback, allowed files, expected deliverables, and acceptance checks. For reviews use `read-only`.

Keep the MCP connection alive while jobs run. `codex-status` checks asynchronous progress; `codex-result` retrieves completed output. `jobId` belongs to that connection and disconnect cancels active work. `threadId` is durable: use `codex-reply-start` for follow-up work on the same task, retaining its sandbox and workspace. Use `codex-steer` for relevant new feedback during an active turn. Resolve approval requests through `codex-interactions` only within user authorization; report blocked requests.

Re-read the document before applying results. Update only the task's related blocks, preserving human edits elsewhere. If a related block changed, reconcile against current goals or mark the task blocked instead of overwriting it. Verify artifacts and run the relevant checks before marking complete. Record evidence and any unresolved limitation.

## Automatic local file trigger

When requested, use [references/file-watch.md](references/file-watch.md) and `scripts/watch_project.py`. Watch only the selected project's `PROJECT.md` input block. Ten quiet seconds after an input change trigger one independent coordinator turn through real MCP. The watcher persists and reuses its thread and queues the latest input during execution. Each result is rendered through the installed `answer-me-with-html` CLI into the project's persistent `reports/` directory; append its dated relative link to the report area at the bottom of `PROJECT.md`. Preserve history and human edits; do not rewrite the input. `DELEGATION-RESULTS.md` is an auxiliary record. Report/link updates do not trigger another turn. Local file triggering requires an explicitly running watcher; sidebar Pages/Canvas require a real file mapping or event adapter.

For a complex summary, use the installed `answer-me-with-html` skill and render with `--no-open`. Link the HTML and project document, and report what was tested through MCP separately from direct CLI checks or simulated inputs.

## Executor

Read the assigned document sections and confirm the task ID, version, file scope, and acceptance checks. Execute only the assignment in the provided workspace. If new feedback changes the goal, reflect it in the work and report the resulting revision. Do not spawn additional agents.

Return task ID, source document version, changed files or artifacts, commands and observed check results, and blockers. Do not mark the shared project complete or overwrite the coordinator's task records unless that write is explicitly assigned.

## Availability

Discover and call the configured `mcp-agents-codex` tools when the host exposes them. If unavailable, report the missing local MCP connection; do not describe a CLI subprocess or mock response as an MCP success. A generic ChatGPT desktop host does not necessarily have access to local stdio. Sidebar document editing and automatic wake-up require an actual host interface; do not assume they exist.
