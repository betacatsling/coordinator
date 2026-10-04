# Local project trigger

This script watches only the local `PROJECT.md` in the chosen project. It starts or
resumes an independent coordinator through the installed mcp-agents Codex provider.
It does not inject input into the current desktop conversation.

Put the editable project goal, scope, feedback, and acceptance checks inside one pair:

```markdown
# Project

<!-- delegation:input -->
Goal: ...
Allowed work: ...
Acceptance: ...
Feedback: ...
<!-- /delegation:input -->

Notes outside the input block do not trigger execution.
```

Start it in a terminal after selecting the actual project:

```bash
python3 $HOME/.codex/skills/project-delegation/scripts/watch_project.py \
  --project /absolute/path/to/project \
  --server /absolute/path/to/node_modules/mcp-agents/server.js \
  --html-cli "$HOME/.codex/skills/answer-me-with-html/scripts/am.mjs"
```

Edit the input block. After ten consecutive seconds without another observed input
change, the watcher dispatches one turn. `--run-current` also submits the initial
input after ten quiet seconds; the default watches future edits only. Ctrl-C stops
the watcher and its private MCP connection. No login item or background service is
installed. A project lock prevents two watchers from owning the same state.

## Optional native hook lifecycle

The source implementation was tested with Codex CLI 0.159.0. Hook support and event schemas depend on your installed CLI version. It discovers
project-local `.codex/hooks.json` in a trusted project. Copy the entries from
`../assets/hooks.example.json` into that project's existing hooks config without
replacing unrelated hooks, and replace the example project path with the exact
chosen project root. Launch the CLI from that root. Review and trust the exact
definitions using `/hooks`; changed hooks require review again. Do not bypass
hook trust or edit global trust records.

`SessionStart` calls `session_watch_hook.py` to start the project watcher once.
`SessionEnd` requests shutdown of the watcher owned by that session. Other sessions
cannot stop that owner's watcher. SessionEnd is a lifecycle event and may run later
than switching away from a tab; Ctrl-C remains the direct stop method for a manually
started watcher. Hooks do not have a filesystem-change event and asynchronous hook
completion does not wake an idle turn. The file watcher provides debounce; real MCP
start/reply dispatch provides the independent coordinator turn.

The lifecycle handler can be tested directly with simulated hook JSON. That proves
handler behavior, not a trusted native hook invocation. No hook has been enabled
globally, and the real project path and user hook trust are still needed.

Official hook reference: https://learn.chatgpt.com/docs/hooks

The script samples the one file locally every 250 ms, including across atomic
replacement. Model calls happen only on debounced input changes. SHA256 hashes
deduplicate identical input. During a running turn, changes coalesce to the latest
input; that input runs next once its quiet period has elapsed. Intermediate edits
are not separate jobs. Malformed or temporarily missing input pauses dispatch.

The coordinator receives an immutable input snapshot and does one bounded project
step itself. Recursive delegation is disabled. It cannot automatically approve
actions: an on-request approval is reported in results and remains pending. This
minimal watcher has no approval UI; stop it and handle the blocked step in an
interactive Codex session. Inspect the project's files before retrying canceled work.
Failures are reported without repeatedly retrying the same input.

Each completed turn is rendered using the installed `answer-me-with-html` CLI. Its
HTML stays in the project's `reports/` directory with a unique dated filename. The
watcher appends a dated, short-description relative link under `## 执行报告` at the
bottom of `PROJECT.md`. Open that link to read the report. Past reports remain; a
repeated publication does not append a duplicate link. The watcher re-reads the
document and only appends output, rather than replacing the user's input or notes.
Partial saves defer the link append; atomic replacement is checked and retried.
If a stale editor save drops generated links, the watcher restores them from its
report index without another model call. The report links are watcher-managed output.

`DELEGATION-RESULTS.md` remains an auxiliary text record, not the primary reading
entry. The coordinator does not edit the input document or reports; the watcher
publishes the HTML and link. Result/link updates and changes outside the input block
do not trigger. Any process changing the input block can trigger: filesystem events
cannot prove the author is human. This is an input/output separation, not author
detection. The coordinator is instructed not to modify the input or watcher state.

The resulting project layout is:

```text
PROJECT.md                    Input block, notes, and dated report links
reports/                      Persistent HTML report history
DELEGATION-RESULTS.md          Auxiliary latest text record
.project-delegation/           Watcher state and logs
```

Relative links resolve from the directory containing `PROJECT.md`. Local target
existence can be verified directly. Clicking them in a particular sidebar Markdown
renderer depends on that frontend; a ChatGPT Page is not automatically a local file.

`.project-delegation/state.json` persists the durable thread ID and last dispatched
hash. Restarting manually can reuse that thread; job IDs are valid only in the live
MCP connection. After stopping, editing the document does nothing until the watcher
is started again. A pending edit at shutdown is not automatically launched later;
use `--run-current` to submit it when restarting. Logs and state are project-local;
the bridge maintains its private durable session store outside the workspace.

ChatGPT Pages/Canvas in a sidebar are not proven to be this local file. For sidebar
automation, the selected frontend must save that document to this exact path or
provide an authorized change-event/export adapter. No such mapping or desktop
wake-up API has been configured here. A frontend editing the actual local file can
use this watcher without changing frontend.
