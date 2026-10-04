# Document watching

Use a simple PROJECT.md:

```markdown
# My project

## Create the helper
Write a sum_numbers function and check empty and negative values.

## Write a usage example
Create a short example using the helper and verify its output.

## 执行报告
```

Start an inbox with `python3 scripts/watch_project.py --project /absolute/project --run-current`. It saves pending input without calling a model. To explicitly continue an existing MCP thread, add `--thread-id ID`; this does not bind a currently open UI window. Unavailable, busy, mismatched, or loaded threads block; the script never creates another coordinator. Session hooks cannot automatically wake an idle UI session.

The selected project must have PROJECT.md. Unique H2 titles identify tasks. Changing a title creates a new task. Completed unchanged sections are skipped; changed sections are submitted again. Reports and bookkeeping are excluded. Reports are appended as dated relative links. Existing legacy input markers work for compatibility. Backstage files are under `.project-delegation/`; keep them out of user-facing deliverables.

Use isolated toy projects to test. Do not stop another project's watcher or rewrite its document. Stop only the process started for your own test. Approval requests are reported and never auto-approved.

## Updating an existing installation

Copying new skill files does not stop or reload an already running watcher. Keep that watcher and PROJECT.md intact. On a future explicitly authorized restart, the new default is pending-input mode; the old saved thread ID is not silently reused. An explicit `--thread-id` is required to continue an eligible MCP session. Legacy input markers remain supported, but do not imply thread binding. Do not migrate a live project without the user's authorization.

## Remind the current session

1. Start the watcher without `--thread-id` so it only records pending input after ten quiet seconds.
2. In the chosen project's `.codex/hooks.json`, install the synchronous handlers from `assets/reminder-hooks.example.json` with actual paths. Review that project's hooks through `/hooks` and trust the exact definitions.
3. The current coordinator receives additionalContext at tool/prompt events, or one Stop continuation for the revision. It reads the tasks, verifies its work, appends dated HTML links, and acknowledges that exact snapshot using the command in the reminder. IDs and acknowledgement files stay backstage.

No hook event means no delivery. An idle session waits for the next user interaction; deliberate monitoring may run `python3 scripts/wait_for_pending.py --project /absolute/project --timeout 45` in its own turn. Its tool completion supplies the normal PostToolUse event. Stop may wait up to twelve seconds for an existing debounce to settle, but cannot wake an already finished idle turn. Async hooks cannot start a new turn.

## Observed validation and enabling scope

PreToolUse was verified in a real Codex CLI 0.159.0 current-session run after reviewing only the exact isolated project hook through /hooks. The coordinator quoted the two task titles from injected context without reading task files. Other reminder events were protocol-tested only. The template remains optional; copying skill files does not enable hooks in any real project. Enable and review specific project definitions only when requested. No all-trust shortcut or idle-wakeup claim is part of this workflow.
