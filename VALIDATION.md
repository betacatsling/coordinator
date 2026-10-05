# Validation — fresh-only candidate

Validated in the cloud on 2026-10-05. This package supports one path: GitHub board notifications, one chosen native coordinator, and direct delegation MCP tools. It does not import or migrate previous controller state.

## Tested

106 tests cover fresh native-session binding, board pagination and filtering, title-only inputs, notification deduplication, six MCP tool contracts, detached workers, concurrency and ownership checks, original-session continuation/recovery, stale-version retirement, exact artifacts/patch verification, deletion-only outputs, GitHub writeback and local HTML reports. Executor/network fixtures are deterministic; real stdio subprocess boundaries and worker persistence are exercised.

Run: `PROJECT_DELEGATION_TEST_NODE=python3 python3 -m unittest discover -s tests -v`

## Not yet verified live

This fresh-only candidate has not been installed or activated on a user host. Codex MCP runtime identity propagation, live GitHub mutation, native desktop notification delivery and complete model-driven execution still require a controlled end-to-end run. Reports are local files; hosted report links are not implemented in the new service. Accepted worktrees remain unmerged.

Fresh initialization uses `.project-delegation/runtime`. Existing repository files, running agents and unrelated state are not deleted or terminated. Stop competing old automation explicitly before activating the new notifier.

Public macOS release verification: all 106 tests passed in 8.437 seconds using temporary fixtures. Release hygiene and whitespace checks passed. Only the public source checkout changed; installed skills, live project files, sessions and state were untouched.
