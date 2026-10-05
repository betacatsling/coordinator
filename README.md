# project-delegation

Make your chosen Codex project session the coordinator. It reads the project, dispatches independent persistent Codex executors through MCP, follows their progress and accepts verified results. [中文](README.zh-CN.md)

## Start

Tell the session you want to use:

> Be this project's coordinator

Or: **你作为这个项目的 coordinator**

The coordinator resolves the current repository, configured GitHub Project and real session identity. It stays the project's manager: it can inspect code and tools, decide what can run in parallel, request corrections and report results. The watcher only notifies this session about changed tasks; it does not make plans or dispatch work from JSON in the conversation.

The new coordinator-driven mode is implemented and tested offline. Live Codex MCP loading, native notification delivery and end-to-end GitHub execution in this mode are not yet validated. Installation does not register MCP tools, restart a session, start a watcher or change an existing production binding. See [setup and tool contracts](references/coordinator-tools.md).

## Workflow

- Read current Issue titles, bodies, authorized user comments and relevant repository artifacts from the selected board
- Use `tasks_list` to reconcile existing work, then `executor_start` to dispatch eligible tasks into independent persistent sessions, up to three concurrently
- Respect current-version dependencies, owned paths and shared resources; preserve dirty files in the project
- Inspect progress and artifacts with `executor_status` and `executor_result`; use `executor_continue` for corrections in the original session
- Use `task_finish` to record the coordinator's evidence-based decision and configured write-back

An executor finishing its turn is not project completion. Accepted changes remain in isolated worktrees (`isolated_unmerged`) until separately integrated. There is no automatic merge, push, deployment or Issue closure. Reports from this mode are private local HTML files; the tool provides no hosted URL.

## Requirements and setup

Use macOS or Linux, Python 3.9+, Node.js, authenticated Codex and GitHub CLIs, and separately installed [mcp-agents](https://github.com/thomaswitt/mcp-agents) for executor sessions. Native board notifications use the supported shared Codex app-server. The acpx/codex-acp transport and external HTML renderer belong to the legacy controller workflow, not the new direct delegation path.

For a local skill installation, back up any existing copy and place SKILL.md, VALIDATION.md, scripts/, references/ and assets/ under `$HOME/.codex/skills/project-delegation/`. Then follow [coordinator setup](references/coordinator-tools.md) to configure the exact project/board scope, enrollment, isolated executors, authorized write-back and stdio MCP connection. Examples are not live credentials or ready-to-run production profiles.

Migration is a separate explicit configuration switch after active work has settled. Preserve the existing owner, task sessions and receipts. The notifier's `--baseline current` deliberately skips notifications for currently eligible versions; inspect current work rather than assuming it will replay. New and legacy dispatch owners cannot run together.

## Stop and uninstall

Stop only the notifier/watcher/controller you started with Ctrl-C or SIGTERM; check any explicitly configured supervisor before restarting. Detached executor work can outlive the MCP connection: observe it and let admitted work settle before removing its runtime. Keep original sessions, reports, worktrees and private state until reviewed.

To uninstall, remove the installed skill directory and only the MCP or hook entries you added. Remove dedicated dependencies only if no other project uses them.

The legacy watcher reads a real local file. A ChatGPT sidebar Page/Canvas is not automatically mapped to PROJECT.md, and idle UI wakeup requires a supported host interface. Session synchronization and transport support remain host dependent.

## Documentation and tests

- [Skill workflow](SKILL.md)
- [Coordinator MCP tools, enrollment and migration](references/coordinator-tools.md)
- [Legacy current-session binding](references/manual-coordinator.md)
- [Shared GitHub configuration and legacy operations](references/github-acpx.md)
- [Legacy PROJECT.md watcher and hooks](references/file-watch.md)
- [Validation evidence and limitations](VALIDATION.md)

Run the portable offline suite from the repository root:

```sh
PROJECT_DELEGATION_TEST_NODE=python3 \
PROJECT_DELEGATION_TEST_HTML_CLI="$PWD/tests/backend_renderer.py" \
python3 -m unittest discover -s tests -v
python3 scripts/scan_release.py
```

Fixture success does not establish live MCP installation, desktop synchronization, native wakeup or live GitHub write-back.

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md).
