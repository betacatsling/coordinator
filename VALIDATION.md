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
