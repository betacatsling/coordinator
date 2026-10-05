# project-delegation

Make your chosen native Codex session the project coordinator. It reads the board and repository, dispatches independent persistent executors through MCP, requests corrections and accepts verified outcomes. [中文](README.zh-CN.md)

## Start

Tell your chosen session: **Be this project's coordinator** or **你作为这个项目的 coordinator**.

With a reviewed project configuration, it verifies the actual runtime `CODEX_THREAD_ID` against the native AppServer thread identity and workspace, then initializes a fresh binding. The coordinator makes planning, dispatch and acceptance decisions directly through tools. An optional board watcher only notifies it about changed inputs.

This is experimental, fresh-only code. There is no state conversion, ownership transfer or compatibility mode. It uses `.project-delegation/runtime` and preserves existing files elsewhere. Nothing automatically installs tools, starts a new shared app-server or changes a live project configuration. Requested connections on Windows start and clean up their own official byte-relay child.

## Setup

Use macOS, Linux or the native Windows portability candidate, Python 3.9+, Node.js, authenticated Codex and GitHub CLIs, and separately installed [mcp-agents](https://github.com/thomaswitt/mcp-agents). The chosen coordinator must be loaded in a supported shared native Codex AppServer.

1. Review [the example configuration](assets/fresh-config.example.json), fill in the selected repository, Project, authorized user and exact board mappings, and review executor and write-back permissions
2. From the selected workspace, run `python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/config.json init`
3. Explicitly register `python3 /absolute/skill/scripts/delegation_mcp.py --config /absolute/config.json` using your Codex client's supported MCP setup. Preserve the authentic runtime context; never copy a thread ID into global server configuration
4. Verify discovery of the six coordinator tools in the chosen session and a successful read-only `tasks_list` call
5. Optionally initialize the watcher with `board_notifier.py --config /absolute/config.json init --baseline current`, then run its `watch` command

The example deliberately disables write-back. Live GitHub execution requires authorized live claim writes and verified board mappings; turn those on only after review. Copying this skill does not register MCP tools or refresh an already running client.

Windows uses the configured `codex.exe` and official `app-server proxy` to reach the existing daemon. See [Windows prerequisites, WSL2 alternative and validation boundary](references/windows-transport.md). Linux-hosted contract tests pass; native Windows and WSL2 live end-to-end operation have not been verified.

## Work and acceptance

`tasks_list` → `executor_start` → `executor_status` / `executor_result` → `executor_continue` when corrections are needed → `task_finish` after review.

Up to three independent jobs can run concurrently. Dependencies use accepted job IDs; they provide pinned receipts, not automatic patch integration. Owned paths, resources, source revisions and durable receipts guard dispatch and recovery.

Executor completion means its turn ended. Acceptance records reviewed implementation evidence. Changes stay in isolated worktrees until separately integrated. There is no automatic merge, push, deployment or Issue closure. Reports are private local HTML files without a hosted URL.

Stop only a watcher you started and intend to stop. Detached executors may outlive an MCP connection; preserve their original sessions, worktrees and receipts until reviewed. Remove only your own MCP entries and installed skill files when uninstalling.

## Documentation and tests

- [Skill workflow](SKILL.md)
- [Setup and coordinator tool contracts](references/coordinator-tools.md)
- [Validation evidence and limitations](VALIDATION.md)

Run `python3 -m unittest discover -s tests -v` and `python3 scripts/scan_release.py` from this repository. Offline fixtures do not establish live MCP installation, native wakeup or GitHub write-back.

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md).
