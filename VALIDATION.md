# Release validation

Validated on macOS with Python 3.9.6 and Node.js 26.8.1 on 2026-10-04.

- Six standard-library unittest cases pass, including a real ten-second debounce loop with fake MCP and fake renderer processes.
- Input hashing excludes output/notes; invalid marker pairs are rejected.
- Report publication preserves the original document body, deduplicates links, and recovers a link after a stale editor save.
- MCP JSON-RPC initialization, tools/list, structuredContent, start, completion, and clean shutdown are exercised through a deterministic fixture.
- The real installed answer-me-with-html renderer produced a nonempty HTML report and a working relative document target in a temporary smoke test; no model was called.
- CLI help works without installed dependencies; missing dependency paths fail early with actionable errors.
- Release hygiene scan checks personal absolute paths, UUIDs, common token/private-key formats, generated state/logs, and unexpected binaries.
- Release copy was compared against the final installed source. Skill and hook logic match; release changes make runtime paths configurable, remove personal paths, validate dependency paths, and close the bridge stdout after shutdown.

The upstream implementation task reported three real MCP coordinator turns validating HTML report links before this snapshot. No real thread IDs, project inputs, logs, or generated user reports are included. The release tests above use fixtures and do not independently replay model execution. Linux support follows POSIX APIs and has a CI workflow; Linux CI results must be checked after publication. Windows is unsupported.

The secret scan is heuristic. It is not a complete credential detector. Review file contents before publishing changes. External tool compatibility can change; use the documented tested versions when reproducing behavior.
