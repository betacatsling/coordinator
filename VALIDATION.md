# Validation — fresh-only candidate

Validated in the cloud on 2026-10-05. This package supports one path: GitHub board notifications, one chosen native coordinator, and direct delegation MCP tools. It does not import or migrate previous controller state.

## Tested

106 tests cover fresh native-session binding, board pagination and filtering, title-only inputs, notification deduplication, six MCP tool contracts, detached workers, concurrency and ownership checks, original-session continuation/recovery, stale-version retirement, exact artifacts/patch verification, deletion-only outputs, GitHub writeback and local HTML reports. Executor/network fixtures are deterministic; real stdio subprocess boundaries and worker persistence are exercised.

Run: `PROJECT_DELEGATION_TEST_NODE=python3 python3 -m unittest discover -s tests -v`

## Not yet verified live

This fresh-only candidate has not been installed or activated on a user host. Live GitHub mutation, native desktop notification delivery and complete model-driven execution still require a controlled end-to-end run. The installed-host checks below verify MCP identity routing only. Reports are local files; hosted report links are not implemented in the new service. Accepted worktrees remain unmerged.

Fresh initialization uses `.project-delegation/runtime`. Existing repository files, running agents and unrelated state are not deleted or terminated. Stop competing old automation explicitly before activating the new notifier.

Public macOS release verification: all 106 tests passed in 8.437 seconds using temporary fixtures. Release hygiene and whitespace checks passed. Only the public source checkout changed; installed skills, live project files, sessions and state were untouched.

## Windows portability candidate — 2026-10-05

Mac release verification ran 131 tests in 9.208 seconds: 130 passed and one real-Windows-kernel case was skipped. The implementation task reported the same total and skip on Linux. Coverage adds Windows lock/process/path/UTF-8 boundaries and the configured official app-server proxy byte relay, using deterministic subprocess fixtures on POSIX. Release hygiene and whitespace checks passed.

Native Windows kernel/runtime integration and live Windows or WSL2 Codex end-to-end operation remain unverified. See [Windows transport requirements and evidence](references/windows-transport.md). This publication changed only the public source checkout; no personal skill installation, project configuration or service was modified.

## Read-only WebUI — 2026-10-05

Mac release verification ran 140 tests in 11.870 seconds: 139 passed and one real-Windows-kernel case was skipped. Dashboard fixtures use canonical temporary paths on macOS. JavaScript syntax, release hygiene and whitespace checks passed. DOM contract tests consume the real backend data shape but use a DOM stub.

A separate CLI HTTP smoke used two explicitly synthetic temporary projects and an ephemeral IPv4 loopback port. HTML/CSS/JS, the two-project catalog, five saved tasks/executors and rejection of POST with HTTP 405 passed. The owned temporary server was stopped after testing. No live user project, installed skill or MCP configuration was read or changed.

Actual browser rendering, desktop/mobile visual layout, dark-theme rendering and browser interaction have not been verified. The optional browser smoke script requires separately installed Playwright; no software was installed for this release. Saved status is not proof of worker liveness, and report downloads are not proof of acceptance.

## MCP handshake and host identity — 2026-10-05

MCP discovery no longer depends on a thread environment variable. Business calls require the host-owned per-request `_meta.threadId`, checked against the existing binding and scope; missing/malformed/mismatched metadata returns a tool error without exiting. The MCP adapter does not fall back to the server environment or accept a model-supplied identity argument.

Mac release verification ran 144 tests in 12.518 seconds: 143 passed and one real-Windows-kernel case was skipped. Release hygiene, JavaScript syntax and whitespace checks passed. Previous WebUI and 106-test historical evidence above is retained.

The implementation task reported five installed-host checks passing with Codex 0.159.2. This release independently passed all five on macOS with installed Codex 0.160.0: actual initialize/list/call sequence; host-supplied matching thread metadata; no CODEX_THREAD_ID in the MCP process; a fixture read by the bound thread; and rejection of a second actual ephemeral host thread. Run the opt-in harness with `python3 tests/codex_host_smoke.py --codex PATH`.

The harness uses credential-free temporary CODEX_HOME/state and a separate owned stdio test host, leaving the existing daemon unchanged. It requests no model turn, GitHub call or executor launch. These checks do not establish model-driven execution, live write-back, native notifications or browser rendering. No installed skill or real project state was changed during publication.

## Installation guide and offline example — 2026-10-05

The installation guide and standalone synthetic-data dashboard demo are included and linked from both READMEs. Mac verification ran 144 tests in 12.391 seconds (143 passed, one Windows-kernel test skipped), including the executor receipt lock using the shared cross-platform helper. Both embedded demo scripts and WebUI scripts passed JavaScript syntax checks; release hygiene and whitespace checks passed. No browser visual validation or native Windows E2E is claimed. No installation or deployment was performed.
