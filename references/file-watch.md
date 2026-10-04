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
