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

When requested, use [references/file-watch.md](references/file-watch.md) and `scripts/watch_project.py`. In the simple format, every unique `##` heading starts a task with natural language below it. The reserved `## 执行报告` section contains only dated HTML links. Internal hashes, state, logs, and execution identifiers belong in `.project-delegation/`, not the reader document. Unchanged successfully processed tasks are not resubmitted; only new or changed task sections are dispatched. Code-fenced headings and report links do not become tasks. Legacy explicit input markers remain supported.

The watcher never creates a coordinator. Without `--thread-id`, it records debounced input in `.project-delegation/pending.json` without starting MCP or a model. This is an inbox, not automatic delivery to an open UI session. An explicit `--thread-id` may resume only an existing unloaded MCP-visible thread whose workspace matches the project; unavailable or loaded threads block, with no new-thread fallback or forced takeover. A fixed current UI session needs a supported submission adapter owned by that UI; no such adapter is provided here. Do not infer a UI binding from watcher state or a bare thread ID. Preserve any already running real-project watcher until the user explicitly authorizes switching it.

Each completed result is rendered with the installed `answer-me-with-html` CLI into persistent `reports/` files and appended to `## 执行报告`. Report writes do not trigger work. Watch only the selected project, debounce ten quiet seconds, and coalesce edits during execution.
For a complex summary, use the installed `answer-me-with-html` skill and render with `--no-open`. Link the HTML and project document, and report what was tested through MCP separately from direct CLI checks or simulated inputs.

## Executor

Read the assigned document sections and confirm the task ID, version, file scope, and acceptance checks. Execute only the assignment in the provided workspace. If new feedback changes the goal, reflect it in the work and report the resulting revision. Do not spawn additional agents.

Return task ID, source document version, changed files or artifacts, commands and observed check results, and blockers. Do not mark the shared project complete or overwrite the coordinator's task records unless that write is explicitly assigned.

## Availability

Discover and call the configured `mcp-agents-codex` tools when the host exposes them. If unavailable, report the missing local MCP connection; do not describe a CLI subprocess or mock response as an MCP success. A generic ChatGPT desktop host does not necessarily have access to local stdio. Sidebar document editing and automatic wake-up require an actual host interface; do not assume they exist.
