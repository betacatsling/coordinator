---
name: project-delegation
description: Use when the user says 你作为这个项目的 coordinator, 担任当前项目的协调者, be this project's coordinator, or requests project delegation, parallel Codex task sessions, task coordination and acceptance, or automatic progression. Resolve the current project binding and actual session automatically, reuse active or pending ownership, and keep implementation in independent persistent executors.
---

# Project delegation

## One sentence role activation

The user only needs to say **“你作为这个项目的 coordinator”** (or an equivalent natural role request). Do not ask them to paste commands, paths, Project IDs, session IDs or workflow rules. Apply this skill and [the short-prompt procedure](references/manual-coordinator.md).

Run `python3 <this installed skill>/scripts/coordinator_bootstrap.py` internally in the current project tool runtime. It discovers the closest existing project binding from project-local configuration and the personal project registry, checks Git origin/workspace, and uses only runtime `CODEX_THREAD_ID`. Never forward an unrelated local identity into SSH or pretend a remote workspace is local. Read-only `--inspect` is available for diagnosis.

- `active`: reuse the same binding and owner; do not create a session, restart a service, or race a background turn.
- `pending`: continue the existing enrollment/handoff, without another owner or duplicate registration.
- `registration_needed` is the read-only preview. Normal invocation enrolls the existing current thread and returns pending. End this turn before external verification; never invoke ACP prompts into your own still-active tool turn.
- `needs_selection` or `needs_configuration`: inspect relevant current-project instructions and connected read-only binding information, then ask only for the unresolved binding. Infer the repository from Git instead of asking again. Do not guess a Project or silently broaden scope.
- `blocked`: explain the actual identity/path/owner/proof problem, retain the current owner and use supported recovery. Missing runtime identity is not a request for the user to fabricate a UUID.

After this turn ends, use the supported verified handoff procedure: official idle evidence, two exact-native-ID ACP turns, shared owner lock and no admitted work. First-owner activation and transfer are distinct; never create a replacement native thread. A pending receipt is not activation and the short prompt is not a claim of desktop synchronization. A role request itself does not authorize the workflow maintainer to choose or launch research tasks.

All task policy belongs here: fixed coordinator only plans and accepts; each independent task gets its own persistent Codex executor session, default three in parallel; declared dependencies, file scopes and approved resource leases limit overlap. Preserve dirty work, comment only on actual claim, sync configured Project status, update the same claim with the real executor ID, verify actual artifacts/checks, publish a truthful HTML result with a verified private link, and exclude own outputs from fresh inputs. [GitHub backend details](references/github-acpx.md) hold the exact protocol; legacy local-document hooks remain optional. The user need not repeat these rules.

Use the user's project document as the source of goals, acceptance criteria, feedback, and task status. Resolve its absolute path and the project workspace before dispatch. Read the relevant sections and record a revision marker or content hash. Preserve the document's existing format.

Release validation covers offline bootstrap and ownership fixtures. Desktop natural-trigger end-to-end operation and real user takeover remain unverified; publishing or installing this package does not change production bindings or tasks.

## Coordinator

Split work into independently checkable tasks with stable IDs. Record each task's scope, owned files, dependencies, acceptance checks, document version, status, and execution `threadId` / `jobId`. Use separate workspaces or nonoverlapping file ownership for concurrent writers. Concurrency is configurable; default to three independent persistent Codex executor sessions. Executors do not recursively delegate.

Use the available MCP tool schemas rather than guessing parameters. With the Codex provider, start independent work using `codex-start` with an absolute `cwd`, `sandbox: workspace-write`, and `allow_subagents: false`. The server must use `on-request` approvals. Include an executor brief: task ID, document path/version, relevant goals and feedback, allowed files, expected deliverables, and acceptance checks. For reviews use `read-only`.

Keep the MCP connection alive while jobs run. `codex-status` checks asynchronous progress; `codex-result` retrieves completed output. `jobId` belongs to that connection and disconnect cancels active work. `threadId` is durable: use `codex-reply-start` for follow-up work on the same task, retaining its sandbox and workspace. Use `codex-steer` for relevant new feedback during an active turn. Resolve approval requests through `codex-interactions` only within user authorization; report blocked requests.

Re-read the document before applying results. Update only the task's related blocks, preserving human edits elsewhere. If a related block changed, reconcile against current goals or mark the task blocked instead of overwriting it. Verify artifacts and run the relevant checks before marking complete. Record evidence and any unresolved limitation.

## Automatic local file trigger

When requested, use [references/file-watch.md](references/file-watch.md) and `scripts/watch_project.py`. In the simple format, every unique `##` heading starts a task with natural language below it. The reserved `## 执行报告` section contains only dated HTML links. Internal hashes, state, logs, and execution identifiers belong in `.project-delegation/`, not the reader document. Unchanged successfully processed tasks are not resubmitted; only new or changed task sections are dispatched. Code-fenced headings and report links do not become tasks. Legacy explicit input markers remain supported.

The watcher never creates a coordinator. Without `--thread-id`, it records debounced input in `.project-delegation/pending.json` without starting MCP or a model. This is an inbox, not automatic delivery to an open UI session. An explicit `--thread-id` may resume only an existing unloaded MCP-visible thread whose workspace matches the project; unavailable or loaded threads block, with no new-thread fallback or forced takeover. For the current coordinator, use native synchronous reminder hooks as described below. Hooks inject reminders into their own current session; they do not need external thread binding. An idle session still needs a future hook event or an explicit wait tool. Do not infer a UI binding from watcher state or a bare thread ID. Preserve any already running real-project watcher until the user explicitly authorizes switching it.

Each completed result is rendered with the installed `answer-me-with-html` CLI into persistent `reports/` files and appended to `## 执行报告`. Report writes do not trigger work. Watch only the selected project, debounce ten quiet seconds, and coalesce edits during execution.
For a complex summary, use the installed `answer-me-with-html` skill and render with `--no-open`. Link the HTML and project document, and report what was tested through MCP separately from direct CLI checks or simulated inputs.

## Executor

Read the assigned document sections and confirm the task ID, version, file scope, and acceptance checks. Execute only the assignment in the provided workspace. If new feedback changes the goal, reflect it in the work and report the resulting revision. Do not spawn additional agents.

Return task ID, source document version, changed files or artifacts, commands and observed check results, and blockers. Do not mark the shared project complete or overwrite the coordinator's task records unless that write is explicitly assigned.

## Availability

Discover and call the configured `mcp-agents-codex` tools when the host exposes them. If unavailable, report the missing local MCP connection; do not describe a CLI subprocess or mock response as an MCP success. A generic ChatGPT desktop host does not necessarily have access to local stdio. Sidebar document editing and automatic wake-up require an actual host interface; do not assume they exist.

## Remind the current coordinator through native hooks

Run the watcher without `--thread-id`: it only debounces PROJECT.md into pending input. Install project-local synchronous PreToolUse, PostToolUse, UserPromptSubmit and Stop handlers calling `scripts/coordinator_reminder.py --project /absolute/project`. Use `assets/reminder-hooks.example.json` as the template, substituting actual script and project paths. Review and trust the exact definitions through `/hooks`; do not silently change global hooks or take over another coordinator.

Tool/prompt events return hookSpecificOutput.additionalContext to the current coordinator. Stop returns decision:block with a reason once per notified revision, allowing the current coordinator to continue. Stop's optional `--wait-seconds 12` allows a pending ten-second debounce to settle during the ending turn. Do not promise idle wakeup; async completion cannot start a turn. During deliberate monitoring the current coordinator can use `wait_for_pending.py` as a bounded wait tool, then its PostToolUse hook delivers the reminder.

The reminder asks the current coordinator to read the simple H2 tasks, process only notified revisions, verify results, publish dated HTML links under 执行报告, then acknowledge the exact revision with the provided `--ack` command. Delivery itself never marks tasks complete. Acknowledgement retains later edits. Per-session/revision dedupe and stop_hook_active prevent reminder/output loops.

## Verification scope

On 2026-10-04, Codex CLI 0.159.0 delivered a PreToolUse additionalContext reminder inside the same isolated current session. The coordinator ran pwd only and correctly reported both task titles without reading PROJECT.md or pending files. The exact project-local PreToolUse definition was reviewed and trusted through /hooks. PostToolUse, UserPromptSubmit, and Stop output contracts, dedupe, loop guard, project scope, stale suppression, and exact-revision acknowledgement were tested directly as protocol responses; do not describe them as native event runs. No automatic idle wakeup was tested or provided.

Templates are optional project-level examples, not installation-time activation. Installing these skill files does not configure or trust real-project hooks, stop watchers, or change global hook rules. Review each chosen definition when enabling a project; never use trust-all as a substitute for that review.

## GitHub Project backend

For the selected repository and Project, follow [references/github-acpx.md](references/github-acpx.md) and `scripts/project_acpx.py`:

1. Read Issue bodies and user comments from that Project and repository. Accept all labels and unlabelled Issues. Submitted versions enter the queue directly; there is no ten-second quiet condition or implicit Ready gate. Polling is ordinary API detection, not model waiting.
2. Initialize one coordinator once and persist Project node ID, repository, acpx record/session IDs and provider thread ID. Resume that exact identity thereafter. Failed recovery blocks; never create a replacement session automatically. Baseline historical versions before enabling real events.
3. The coordinator only assigns and verifies. An independently scoped MCP executor implements; program-run checks and actual source return to the original coordinator for acceptance. Use explicit owned paths and checks; do not ask users to repeat these workflow rules in every prompt.
4. Produce a concise result, verification and HTML report. Write Issue result comments and Project state only after the selected destination and field mapping are established; record result comment IDs to prevent output loops. A local report path is not a network link: do not claim an accessible HTML URL until hosting/access is verified.

Keep the old file watcher and native hooks as optional backends; they do not form part of the default GitHub loop. Do not change answer-me-with-html. Do not enable competing real-project watchers, copy credentials between hosts, expand permissions without authorization, or auto-approve unsafe actions.

For the GitHub backend, use scoped idempotent write-back, exact live status mappings, verified private report-base URLs and per-Issue detached worktrees as described in `references/github-acpx.md`. Keep dry-run/default writes disabled until configured. Preserve dirty main-workspace files; a live legacy watcher blocks competing input ownership.

When the user selects the TODO board, configure its verified view/Type/Status mapping; claim only 待做 cards and exclude 项目跟踪. Entering 待做 triggers admission even for baseline text. Only actual admitted slots post stable claim comments and move to 进行中; polling/queueing never do. See `references/github-acpx.md`.

If the user chooses their current project session as coordinator, use [manual coordinator registration](references/manual-coordinator.md): runtime identity enrollment is pending, not activation. End the registration turn before a two-turn exact-native-ID ACP resume proof; then quiesce the old owner and commit under the shared lock without losing queue/baseline. Never claim desktop visibility or migrate merely from a user-supplied ID.

For independent ready work, the coordinator assigns one separate persistent Codex executor session per task; use the GitHub backend pool (default three, configurable) rather than sequential execution or native subagents. Coordinator planning/acceptance stays serialized in its fixed session; file/resource leases and dependencies constrain executors. Persist and display task-to-native-session mappings, append the actual executor ID to the same claim comment, and resume follow-ups with that task’s original receipt/workspace. Do not set a global executor ID or choose/dispatch research Issues while merely modifying this workflow.
