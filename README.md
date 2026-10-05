# project-delegation

Use your chosen native Codex session to read the project, dispatch independent persistent executors and review their work. [中文](README.zh-CN.md)

## Start

Tell your chosen session: **Be this project's coordinator using /absolute/project.json**.

With setup complete, it verifies this session, starts or reuses notifications and the local dashboard, reads `tasks_list`, dispatches independent executors, then ends its turn until a completion notice prompts review. Board changes reach the same coordinator session.

Notifications supply input; the coordinator still plans, requests corrections and accepts verified outcomes. Service health, queued input, a started or completed coordinator turn and task acceptance are separate facts.

## Setup

Use Python 3.9+, Node.js 26+, authenticated Codex and GitHub CLIs, and separately installed [mcp-agents](https://github.com/thomaswitt/mcp-agents). All runtime components and the chosen coordinator's shared native AppServer belong on the same machine.

1. Follow [installation](references/installation.md) to install the skill and executor dependency
2. Review [the example configuration](assets/fresh-config.example.json), supplying the repository, Project, authorized user, exact board mappings and executor permissions
3. Register `python3 /absolute/skill/scripts/delegation_mcp.py --config /absolute/project.json` using your Codex client's MCP setup and load it in the chosen session. The host must supply per-call `_meta.threadId`; never copy a thread ID into global configuration
4. Give the one-sentence request above. The session runs `coordinator_bootstrap.py --config /absolute/project.json init` from the selected workspace and verifies a real `tasks_list` call

Bootstrap creates or verifies the binding under `.project-delegation/runtime`; it does not install tools, create a new shared AppServer or change project configuration. Existing files elsewhere are preserved. The example disables GitHub write-back; live execution needs explicitly authorized claim writes and verified board mappings.

The dashboard opens in the default browser when a local desktop is detected. `--no-open` suppresses browser opening, while the local service still starts. Use the returned URL; [remote access](references/web-dashboard.md) needs a private tunnel arranged separately.

Windows uses the configured `codex.exe` and official `app-server proxy` to reach the existing daemon. [Windows prerequisites and validation limits](references/windows-transport.md) include the WSL2 alternative. Full model-driven native macOS, Windows and WSL2 end-to-end operation remains unverified; observed host checks are recorded in VALIDATION.md.

## Work and review

`tasks_list` → `executor_start` → end this turn → completion notice → `executor_status` / `executor_result` → `executor_continue` for corrections or `task_finish` after review.

Up to three independent jobs can run concurrently. Dependencies use accepted job IDs and pinned receipts, without automatic patch integration. Owned paths, resources, source revisions and durable receipts guard dispatch and recovery. When all useful independent work is dispatched, yield instead of repeatedly polling or sleeping inside a tool call.

An executor finishing its turn makes its result available for review. Acceptance records reviewed implementation evidence; isolated worktrees still need separately authorized integration. Nothing automatically merges, pushes, deploys or closes Issues.

Private HTML reports can be read in the dashboard's isolated static preview or downloaded, with verified GitHub links for context. JavaScript and external resources are disabled in previews. Reports have no public hosted URL.

Detached executors and local services may outlive an MCP connection. Preserve original sessions, worktrees and receipts until reviewed; stop only services you own and intend to stop.

To uninstall, remove only the installed skill and MCP entries you added; preserve sessions, worktrees and private state until reviewed.

## Documentation and tests

- [Standalone synthetic-data demo](examples/dashboard-demo.html) — download and open locally
- [Skill workflow](SKILL.md)
- [Coordinator tool contracts](references/coordinator-tools.md)
- [Local dashboard and reports](references/web-dashboard.md)
- [Validation evidence and limits](VALIDATION.md)

Run `python3 -m unittest discover -s tests -v` and `python3 scripts/scan_release.py`. Offline fixtures do not establish live installation, notification wakeup or GitHub write-back.

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md).
