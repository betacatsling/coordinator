# Release validation

Validated on macOS with Python 3.9.6 and Node.js 26.8.1 on 2026-10-04.

- Ten standard-library unittest cases cover legacy and H2 input, changed-task deduplication, default inbox mode with an unusable Node path, loaded-thread refusal, and explicit MCP continuation. Each watcher loop uses the real ten-second debounce, with fake MCP/renderer fixtures.
- Input hashing excludes output/notes; invalid marker pairs are rejected.
- Report publication preserves the original document body, deduplicates links, and recovers a link after a stale editor save.
- MCP JSON-RPC initialization, tools/list, structuredContent, thread inspection, reply, completion, and clean shutdown are exercised through a deterministic fixture.
- The real installed answer-me-with-html renderer produced a nonempty HTML report and a working relative document target in a temporary smoke test; no model was called.
- CLI help works without installed dependencies; missing dependency paths fail early with actionable errors.
- Release hygiene scan checks personal absolute paths, UUIDs, common token/private-key formats, generated state/logs, and unexpected binaries.
- The three updated source files matched every SHA256 in source-release.json before portable path adaptation. Release changes make runtime paths configurable, validate dependencies only for explicit binding, and close bridge stdout after shutdown. No installed source or existing watcher was modified.

The implementation task reported an isolated real two-task MCP run and HTML rendering for this source release. The included demo contains only its task document, two Python files, and sanitized report; file links were changed to relative paths. No real thread IDs, project inputs, logs, or generated user reports are included. The release tests above use fixtures and do not independently replay model execution. Linux support follows POSIX APIs and has a CI workflow. The initial release passed Linux CI; this update must pass its own publication run. Windows is unsupported.

The secret scan is heuristic. It is not a complete credential detector. Review file contents before publishing changes. External tool compatibility can change; use the documented tested versions when reproducing behavior.

## Native reminder update

The five finalized files matched native-hook-release.json before removing a project-specific name from public documentation. No logs, session identifiers, actual hook trust records, private paths, or real project state are included.

Five additional fixture tests pass for PreToolUse/PostToolUse/UserPromptSubmit response contracts, per-session revision deduplication, Stop continuation guarding, stale input suppression, project scope, and exact acknowledgement that preserves newer edits. Delivery alone does not acknowledge tasks; undelivered revisions cannot be acknowledged. These tests invoke the handler directly and are not native hook runs.

The implementation task separately verified PreToolUse in a real Codex CLI 0.159.0 current session: the coordinator ran only pwd and quoted both task titles from injected context without reading the project files. Other events were protocol-tested only. A fully idle session with no event is not automatically woken. Hook templates remain optional and require review of exact project definitions.

## GitHub/acpx foundation update

All seven source files matched github-acpx-release.json before a host-specific word was generalized in documentation and the skill gained an explicit release-stage notice. Only the stable manifest snapshot was copied; no later implementation changes, real business configuration, Project IDs, Issue baselines, provider/session records, credentials or private paths are included.

Nine additional offline tests pass for labeled/unlabeled input, selected-user body/comment handling, result-comment exclusion, revision changes, repository/Project isolation, incomplete pagination rejection, pending-version superseding without mutation of running snapshots, owned-path escape rejection, structured plan parsing, and a fake ACP adapter verifying refusal of new/fork/wrong-session fallback. They make no GitHub API requests or model calls.

The implementation task separately reported macOS same-session restart/busy queue, fixture version deduplication and local HTML reports, an independent MCP executor with four actual unit tests and original-coordinator acceptance, plus remote Linux same-session restart/deduplication/local HTML reports. These are source-task observations rather than replayed release tests.

Remaining: Issue result comments and Project status writeback are not implemented/enabled; report hosting is not configured and URLs are null; no production executor scope is configured. The real Project event loop was not started. Owned-path validation is not a separate operating-system file-access boundary.
