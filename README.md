# project-delegation

A Codex skill and local document watcher for project work. [中文](README.zh-CN.md)

## GitHub input mode: scoped writeback and worktrees

This release includes fixed acpx coordinator binding, GitHub input parsing and durable revision queue, optional executor/acceptance, scoped result writeback, report endpoint verification and per-Issue detached worktrees. See [setup and commands](references/github-acpx.md), the [generic configuration](assets/github-acpx.example.json), and [validation](VALIDATION.md). Existing local-file watching and native reminder hooks remain optional.

The workflow binds one GitHub Project and one repository. Explicit initialization creates one fixed acpx coordinator, then resumes its saved identity. In-scope Issue bodies and comments from the configured user are input regardless of labels, including issues with no labels. `run` uses ordinary API polling, with a default 15-second cadence and no ten-second quiet gate or model calls spent waiting. Historical versions are baselined on real GitHub initialization. Changing a binding or interrupted work requires explicit investigation, not automatic replacement or replay.

The coordinator delegates work and checks acceptance. With explicit executor configuration, an independent MCP executor works in a per-Issue detached worktree; the original coordinator assesses actual source and observations. Dirty main-workspace files are preserved and overlapping scope blocks execution. Changes are kept for review without merging, committing or pushing. Checks are controller-configured; the default worktree diff/scope/Python-syntax checks are static validation, not behavioral correctness. Without executor configuration, a turn produces coordination guidance and does not complete the Issue. Owned paths constrain plans and acceptance, but are not a separate operating-system file-access boundary.

**Production activation remains unconfigured.** Comment/status writeback is implemented but disabled by default; dry-run is the example default. It checks live Project/repository membership, current input revision and authenticated author, with own-result marker recovery for retry deduplication. A status update requires an exact live field/option mapping; isolated patches awaiting merge are not automatically marked Done.

`report_base_url` must point to an existing private HTTP(S) endpoint. Only HTTP 200 with identical report bytes produces a verified URL. Without that, reports retain a local path and `url: null`. Controller-host verification does not prove reader reachability. The optional [serve_reports.py helper and SSH forwarding instructions](references/github-acpx.md#private-report-access) require operator configuration and authorization; this package starts neither. The earlier follow-up verification used real GitHub reads/dry-run with zero mutations. Generic examples do not activate a production controller. A live legacy watcher blocks a competing controller until its work is settled and an explicit safe handoff is authorized. The external HTML renderer remains unchanged.

GitHub mode also requires GitHub CLI authentication, acpx 0.19.4 and @agentclientprotocol/codex-acp 2.1.1 installed separately. Configure explicit runtime paths; do not copy credentials or real binding state. `init` creates the fixed coordinator; `once` handles queued input; `run` polls until Ctrl-C/SIGTERM, then settles an admitted turn before releasing its lock. Enable a real event loop only after completing the remaining production setup and checking other input owners.

An optional explicitly selected TODO board narrows intake: only its verified ready status is claimable, and the configured project-tracking type is excluded. View filters, field IDs and option names must match live values; changed or incomplete mappings fail closed. Entering the ready state creates a deduplicated dispatch generation, including baseline text. Only an actually admitted serial slot posts a retry-safe claim comment and sets the mapped in-progress state; polling alone does not claim work. Own claim/result comments never become new instructions. See [board scope and claims](references/github-acpx.md#explicit-todo-board-intake-and-claim-notifications).

To propose the current project session as coordinator, follow [manual registration and handoff](references/manual-coordinator.md). Registration uses runtime `CODEX_THREAD_ID` in the exact workspace and stays pending. After that turn ends, verification resumes the same native ID twice across TTL; an explicit handoff additionally requires a stopped/quiescent old owner, the canonical lock, a matching old binding and fresh proof. Queue/baseline history is retained and services are not automatically started. Isolated same-thread QA passed; **the real user target was not registered and desktop visibility/synchronization was not verified**. Registration support does not establish a completed production handoff or concurrent UI ownership.

Write tasks under unique `##` headings in `PROJECT.md`. After **10 quiet seconds**, the watcher queues changed tasks in a local inbox. Explicit `--thread-id` binding can continue an eligible existing MCP thread. The watcher never creates a coordinator. Completed results become dated HTML reports linked from the document.

View the [two-task demo](examples/simple-two-task-demo/PROJECT.md), [report HTML source/download](examples/simple-two-task-demo/reports/report.html), and [runnable example](examples/simple-two-task-demo/example.py). The report is a sanitized copy of a real implementation demo. GitHub displays HTML source; download it to view locally.

## Requirements and installation

- macOS or Linux; Python 3.9+ (standard library only; uses POSIX `fcntl`). Windows is unsupported.
- Node.js 26+ and an authenticated Codex CLI available on PATH. The source implementation used Codex CLI 0.159.0.
- External [mcp-agents](https://github.com/thomaswitt/mcp-agents), tested with 0.33.1. Explicit watcher binding uses `codex-thread-read`, `codex-reply-start`, `codex-status`, and `codex-result`; manual coordination can also use `codex-start`.
- External [answer-me-with-html](https://github.com/QingYunA/answer-me-with-html), installed separately. Its `scripts/am.mjs` renders reports. No third-party source is bundled.

Clone this repository. To install the skill, copy `SKILL.md`, `scripts/`, `references/`, and `assets/` into `$HOME/.codex/skills/project-delegation/`; back up an existing installation first. No installer runs or changes configuration automatically.

Install a pinned bridge into a directory of your choice:

```sh
npm install --prefix "$HOME/.local/share/project-delegation-deps" mcp-agents@0.33.1
export PROJECT_DELEGATION_SERVER="$HOME/.local/share/project-delegation-deps/node_modules/mcp-agents/server.js"
export PROJECT_DELEGATION_HTML_CLI="$HOME/.codex/skills/answer-me-with-html/scripts/am.mjs"
```

Install the renderer using its upstream instructions. Check both exported paths exist. Authentication remains owned by Codex; do not put tokens in project documents.

## Run

Copy [examples/PROJECT.md](examples/PROJECT.md) into your chosen workspace, adjust its goals and acceptance checks, then run:

```sh
python3 scripts/watch_project.py --project /absolute/path/to/workspace
```

Only future input changes run by default. Add `--run-current` to submit the initial input after ten quiet seconds. Explicit `--server`, `--html-cli`, and `--node` options override defaults; `PROJECT_DELEGATION_NODE` overrides Node discovery. The two dependency environment variables also work for optional hooks.

The default command only writes `.project-delegation/pending.json`. It does not call a model or deliver input by itself. Inbox mode requires neither the bridge nor renderer. Add `--thread-id EXISTING_THREAD_ID` only to continue an unloaded MCP-visible thread in the same workspace. Unavailable, loaded, or mismatched threads block with no new-thread fallback.

To remind your current coordinator, use the optional native synchronous hooks in [assets/reminder-hooks.example.json](assets/reminder-hooks.example.json). Replace script/project paths, merge only those entries into the selected project's `.codex/hooks.json`, then review and trust the exact definitions through Codex `/hooks`. Keep the watcher in inbox mode. On a tool/prompt event, `coordinator_reminder.py` injects pending task context into that same session through `hookSpecificOutput.additionalContext`. Stop can request one continuation per revision. The reminder asks the coordinator to verify work, publish an HTML report, and acknowledge the exact delivered revision; delivery itself does not complete a task. Newer edits remain pending.

**No hook event means no reminder.** A fully idle session is not automatically woken. Deliberate monitoring can use `python3 scripts/wait_for_pending.py --project /absolute/project --timeout 45` within an active turn; it is a bounded wait, not a background wakeup service. Installing this skill does not activate or trust hooks. See [observed validation](VALIDATION.md): only PreToolUse was tested as a real native event; other events have protocol tests.

Manual coordination uses the skill's executor briefs and separate owned workspaces. Explicit watcher execution performs one bounded step and disables recursive agents. Its private stdio MCP connection does not edit desktop MCP config.

## Reports and state

- `PROJECT.md`: input, human notes, and dated report links.
- `reports/`: persistent HTML history rendered with `--no-open`.
- `DELEGATION-RESULTS.md`: auxiliary latest text result.
- `.project-delegation/`: private state, thread IDs, logs, and report index.

Unique H2 titles identify tasks; renaming a title creates a new task. Successfully completed unchanged tasks are skipped. The reserved `## 执行报告` section and fenced headings are excluded. Legacy single `<!-- delegation:input -->` / `<!-- /delegation:input -->` markers remain supported. Output edits do not trigger another call. Atomic-save gaps pause dispatch; stale editor saves can have generated report links restored from the index. Keep state and reports private when they contain project content.

## Stop and uninstall

Press Ctrl-C or send SIGTERM to the watcher you started. Closing its private MCP connection cancels active jobs; inspect files before retrying. Stop it before deleting its state. Remove the installed skill directory to uninstall. Remove only the optional hook entries you added, preserving other hooks. Dependencies can be removed from their dedicated install directory if no other project uses them. Reports are retained until you choose to delete them.

Optional project-local SessionStart/SessionEnd hooks are in [assets/hooks.example.json](assets/hooks.example.json). Replace the placeholder project path and skill path, ensure dependency environment variables reach the CLI, and review/trust the exact definitions with Codex `/hooks`. This repository does not install a service, login item, or global hooks. Hook lifecycle is version dependent; switching tabs is not necessarily SessionEnd.

## Limits

This watches a real local file and queues input by default. **A ChatGPT sidebar Page/Canvas is not automatically mapped to that file.** A real file mapping or authorized event adapter is required. Relative-link clicks depend on the frontend renderer.

The watcher must remain running. Saved thread IDs are not silently reused without `--thread-id`; job IDs are connection scoped. Approval policy is `on-request`; requests stay pending and the watcher cannot approve them. Stop it and handle blocked work in an interactive approval UI. It instructs the coordinator to avoid network, dependency installation, credentials, settings, and watcher-owned output; a prompt is not a security boundary. Workspace sandboxing and host policy remain authoritative.

Input hashes deduplicate identical content, and active edits coalesce to the newest revision. Failures do not automatically retry the same input. Filesystem events cannot identify the author of a change. Append-only publication checks atomic replacement, but does not provide transactions against arbitrary concurrent in-place writers. State stores and stdout logs can contain sensitive project output.

## Tests and license

```sh
python3 -m unittest discover -s tests -v
python3 scripts/scan_release.py
python3 scripts/watch_project.py --help
```

Tests cover task parsing, deduplication, legacy input, report publication/recovery, renderer invocation, MCP framing, inbox mode, and explicit binding through **fake** MCP fixtures. These are not live model tests. The source implementation task separately reported a real two-task MCP run with HTML rendering for this update; that result is not a guarantee for another host. See [VALIDATION.md](VALIDATION.md).

Own skill and glue code: [MIT](LICENSE). External dependencies keep their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md). This is an independent project, not an official OpenAI product.
