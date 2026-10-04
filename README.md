# project-delegation

A Codex skill and local document watcher for project work. [中文](README.zh-CN.md)

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
