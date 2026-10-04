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

Remaining at the foundation release (superseded by the follow-up below): Issue result comments and Project status writeback were not implemented/enabled; report hosting is not configured and URLs are null; no production executor scope is configured. The real Project event loop was not started. Owned-path validation is not a separate operating-system file-access boundary.

## Scoped writeback/worktree follow-up

All eight source files matched github-acpx-followup-release.json before public documentation gained a release-stage notice and a host-specific word was generalized. The public manifest excludes business binding, status field IDs, credentials, private paths, provider IDs and real watcher state.

Five source tests cover dry-run without mutations, comment/status retry deduplication, current revision/author/scope/live option refusal, detached worktrees preserving dirty main files and rejecting unowned edits, live legacy-owner refusal, and temporary loopback HTTP report byte verification. Release CI uses a small Python renderer fixture for portability; it is not an answer-me-with-html renderer test. The actual installed renderer was separately verified by the implementation task.

The implementation task reported these five tests passing on macOS and remote Linux, plus actual Project/Issue/viewer/status API reads and dry-run with zero mutations. This release did not repeat business API calls or activate a controller. No persistent report server or SSH forward was started.

Remaining deployment work is concrete private report access and explicit safe handoff after legacy pending work settles. Reports expose a URL only after identical-byte HTTP verification on the controller host; reader reachability still needs verification. Per-Issue worktrees are retained for review without automatic merge. Static scope/diff/Python syntax checks are not behavioral tests.

## Loopback report helper

serve_reports.py matches the implementation source snapshot exactly (SHA256 b2ea9ee9df9701d1ef36c63bfba4a98d9c98bdfb9a8ec201d30f8c2f44afdfa5). Three temporary localhost tests cover GET/HEAD report bytes, rejection of a symlink escaping the selected directory, and parent/encoded-parent paths not exposing an outside fixture. Test listeners use ephemeral ports and are shut down after each case.

No production service, report, address, binding, deployment record or verification record was copied or operated during this release work. The included commands are generic foreground examples. Authentication/TLS and reader access are not supplied by the helper; operator-selected transport and access checks remain necessary.

## Board intake and candidate coordinator registration

All fourteen stable files matched the private coordinator-integrated manifest before copying. That manifest and all production/QA records were excluded from publication. Private project names/paths in manual instructions were generalized; the registration test now generates a deterministic fixture UUID at runtime. Previously published generic report-helper instructions are retained.

Source observations reported nineteen backend/board/ownership/registration tests passing on macOS and remote Linux, plus isolated exact-native-ID resumption across TTL. Release tests use temporary state, fake GitHub writes and adapter fixtures; they do not operate production or replay real registration. Coverage includes selected-board scope/pagination/type/status checks, ready generations, admission-only claims, lost-receipt claim deduplication, other-author marker handling, canonical ownership across state directories, runtime-only pending enrollment, changed/running-owner refusal and completed-native-ID proof requirements.

The real user target was not enrolled and desktop visibility/synchronization was not verified. No completed production handoff is claimed. Runtime CODEX_THREAD_ID is an identity hint rather than cryptographic proof, and pending registration is not activation.

## Parallel persistent executor structure

All twenty-one files in the stable parallel manifest matched before copying. The private manifest and isolated/production QA records were excluded. Previously generalized manual instructions and report-helper instructions are retained. Source test session literals were replaced by runtime-generated fixture UUIDs, and the overlap test name now explicitly identifies fake executors. Domain-specific research names were removed from public documentation.

The implementation task reported twenty-six backend/board/ownership/registration/pool tests passing on both hosts and two actual isolated Codex sessions overlapping and recovering their original IDs. The added release tests cover disjoint/overlapping path leases, shared resources, dependency readiness, updating an existing claim once with a task session, missing-claim refusal, fake worker overlap with serialized model callbacks, and an explicitly authorized revision batch. They do not start real sessions or select research work.

This release only changes architecture: default three independent executor slots, serialized coordinator planning/acceptance, per-task persistent sessions, and waiting on conflicts/dependencies. No production research dispatch or user-selected coordinator handoff is claimed; real research task selection remains the user coordinator's responsibility.

## One-sentence coordinator entry

All twenty-four files matched the stable source manifest before the six changed entry/ownership files were copied. Private manifests were excluded. Test session literals were replaced by deterministic runtime-generated fixture UUIDs; private-name assertions were replaced by generic behavior assertions. Existing generic report instructions and tests are retained.

The source task reported forty-nine source tests passing on macOS and remote Linux. Public release verification exercises binding discovery from temporary cwd/configuration/registry, runtime identity, active and pending reuse, ambiguity/missing/corrupt state, first-owner baselining, existing history preservation, lock/owner refusal and proof freshness. Tests mock external APIs and sessions and do not take over a real owner.

Desktop natural-trigger end-to-end operation and real user takeover remain unverified. Production binding and tasks are unchanged. Pending enrollment remains distinct from activation; the current turn must end before external exact-ID verification. No production services, credentials, project content or private release records are published.

Public macOS release validation: all 76 tests passed in 35.642 seconds using the bundled fake renderer and temporary localhost listeners. The conservative release scan passed; it is a heuristic, not a guarantee against every secret format. GitHub CI repeats these checks on Linux/Python 3.9.
