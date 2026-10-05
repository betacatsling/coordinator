# Validation — fresh-only candidate

Validated in the cloud on 2026-10-05. The workflow uses one chosen native coordinator, one local dashboard-and-notification service and direct delegation MCP tools.

## Tested

The final integrated suite ran **221 tests: 220 passed, one skipped**. The skipped exited-process probe requires a native Windows kernel. Script, test and web-file checksums were unchanged across the run. Python compilation, `scan_release.py` and `git diff --check` also passed.

Coverage includes native-session binding, board filtering and title-only inputs, six MCP tool contracts, detached workers, concurrency and ownership, original-session recovery, stale-result retirement, artifact/check verification, GitHub write-back fixtures, private HTML reports, isolated preview/download restrictions and dashboard startup/navigation contracts.

Twelve cross-component cases exercise real durable files and locks, bootstrap binding, the watcher loop, worker outcome/notice transactions and dashboard reads. They cover silent baseline → changed board input → queue → worker completion → review by the same coordinator; repeated init/stop/restart; both-outbox deduplication; outages; lost acknowledgements; queue rejection; crash recovery; failed review; binding/configuration drift; and redacted status. Native queue, GitHub, process startup and worktree boundaries in these cases are fixtures. They do not establish live wakeup or execution.

Before this integration, the recorded baseline was 170 tests: 169 passed and one skipped.

Before notification integration, a separate Linux fixture smoke verified a real detached dashboard process, HTTP page serving, automatic fallback from an occupied preferred port, headless reuse and `--no-open` server startup. Browser-open deduplication and macOS/Windows desktop detection were tested with mocks; this is not native browser or native macOS/Windows validation.

Cloud-side browser validation was blocked. The implementation task subsequently reported Mac-rendered screenshots, but browser exit timed out; complete browser interaction validation is not claimed. Native Windows end-to-end operation remains unverified.

Run: `python3 -m unittest discover -s tests -v`

MCP startup no longer requires `CODEX_THREAD_ID`. Real stdio fixture tests cover identity-free initialization/discovery, per-call host `_meta.threadId`, missing/malformed/mismatched identity rejection, configuration changes, and detached-worker identity propagation. These fixture tests cover protocol and authorization behavior; the separate installed-host check below verifies native metadata propagation.

## Installed Codex host smoke test

On 2026-10-05, the opt-in `python3 tests/codex_host_smoke.py` passed all five checks against installed Codex CLI 0.159.2:

1. Actual host MCP initialization, tool discovery and tool call
2. Host-generated `_meta.threadId` matches the actual ephemeral thread
3. MCP server has no `CODEX_THREAD_ID` environment variable
4. The bound thread successfully reads a fixture task
5. A second actual host-created thread is rejected

The harness uses temporary fixture state, a credential-free isolated `CODEX_HOME`, and the native app-server `mcpServer/tool/call` API. It requests no model turn, GitHub call or executor launch, and changes no global configuration. IDs come from `thread/start`; no identity is fabricated or inserted into MCP metadata. `environments: []` disables unrelated shell execution for these test threads. Requires an installed Codex CLI with this experimental API; use `--codex PATH` if it is not on PATH. Captured metadata remains temporary and is deleted after the run.

## Not yet verified live

The implementation task reported installing this candidate on macOS and Linux and verifying synthetic-board notifications waking the same real idle native thread on both hosts, plus Linux HTTP lifecycle and isolated HTML preview. These checks establish the observed notification/lifecycle paths; complete model-driven execution and live GitHub write-back still require separate evidence. The installed-host smoke test verifies MCP identity routing only, not model-driven coordinator or executor behavior. Reports are local files; hosted report links are not implemented in the new service. Accepted worktrees remain unmerged.

Fresh initialization uses `.project-delegation/runtime`. Existing repository files, running agents and unrelated state are not deleted or terminated. Stop competing automation explicitly before activating the local service.

Public release verification on macOS ran 221 tests in 16.806 seconds: 220 passed and one native-Windows-kernel case was skipped. Web JavaScript syntax, release hygiene and whitespace checks passed. Only the public source checkout changed.

## Additional host observations

The implementation task reported 221 tests on both macOS and Linux (220 passed, one Windows-kernel skip), five credential-free native-host identity checks and synthetic idle-thread notification delivery. Private project paths, native IDs, credentials and task contents are omitted. Publishing this repository does not migrate or operate an installed service.

## Earlier published verification (historical)

The following records describe earlier commits, not a fresh result for every current component.

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
