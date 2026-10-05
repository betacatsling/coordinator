# project-delegation

Coordinate GitHub board tasks from your current Codex project session, with independent persistent executors and verified results. [中文](README.zh-CN.md)

## Start

Tell the session you want to use:

> Be this project's coordinator

The skill resolves the current workspace, repository, configured Project and runtime session identity. It reuses an active binding or registers the current session as pending. If configuration is missing or ambiguous, it asks only for the missing choice. It does not create a replacement coordinator or take over an existing owner.

Pending is not active. The supported controller transport must establish this session’s identity and safe ownership before background coordination can use it. See [binding and activation](references/manual-coordinator.md).

## Default workflow

- Use the selected GitHub board's configured ready state, excluding configured tracking cards
- Read current Issue bodies and authorized user comments; no separate PROJECT.md is required
- Keep planning and acceptance in the coordinator; run independent tasks in separate persistent Codex sessions, up to three in parallel by default
- Wait on current-version dependencies, overlapping paths and shared-resource conflicts
- Claim only admitted work, then add the actual executor ID to the same claim comment
- Verify artifacts and checks, publish a result and HTML report, and update only the configured Project status
- Preserve dirty files and original task sessions; keep detached worktree changes for review without automatic merge or push

A role request does not authorize unrelated task selection. Configuration must establish the board, execution scope, permissions and write-back before real work runs. Installation alone activates nothing.

## Requirements and setup

Use macOS or Linux, Python 3.9+, Node.js, an authenticated Codex CLI and GitHub CLI. The backend also uses separately installed acpx, codex-acp, [mcp-agents](https://github.com/thomaswitt/mcp-agents) and [answer-me-with-html](https://github.com/QingYunA/answer-me-with-html). Tested versions and evidence are recorded in [VALIDATION.md](VALIDATION.md); external compatibility is not guaranteed by installation.

To install this repository as a local skill, back up any existing installation and copy SKILL.md, VALIDATION.md, scripts/, references/ and assets/ into $HOME/.codex/skills/project-delegation/. No installer changes hooks, credentials or services.

Use [the configuration guide](references/github-acpx.md) and [example configuration](assets/github-acpx.example.json) to configure exact live Project/board mappings and runtime paths. Examples keep executors and write-back disabled, with dry-run enabled. Enable only the authorized scope. Missing or changed mappings fail closed.

HTML files stay local unless an existing private endpoint serves matching bytes. Controller-side verification alone does not establish reader access. Do not publish confidential reports to a public host.

## Stop and uninstall

Stop only the watcher/controller you started with Ctrl-C or SIGTERM and allow admitted work to settle; check any explicitly configured supervisor before restarting. Remove the installed skill directory to uninstall, and remove only hook entries you added. Keep reports and private state until you have reviewed them; remove dedicated dependencies only if no other project uses them.

The legacy watcher reads a real local file. A ChatGPT sidebar Page/Canvas is not automatically mapped to PROJECT.md, and idle UI wakeup requires a supported host interface. Session synchronization and transport support remain host dependent.

## Documentation

- [Skill workflow](SKILL.md)
- [Current-session binding](references/manual-coordinator.md)
- [GitHub configuration and operations](references/github-acpx.md)
- [Legacy PROJECT.md watcher and hooks](references/file-watch.md), only when explicitly selected
- [Validation and limitations](VALIDATION.md)

Run offline tests with `python3 -m unittest discover -s tests -v`. Fixture success does not establish desktop synchronization, real user takeover or live GitHub write-back.

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md).
