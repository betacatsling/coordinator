# Validation

The publication suite passes 101/101 offline Node tests on macOS, including ten
multi-project isolation tests, ten additional refactor regressions and thirteen
concrete-event notification tests, plus thirteen membership regressions. The multi-project tests use
two fake Pi Managers and a shared fake GraphQL service with real adapters and
file-backed state, covering independent scopes, pagination, notices, receipts,
restart recovery, writes, forks and pauses. They do not verify native multi-host
workers, Termius, Herdr leases or production configurations. Publication checks
rerun `npm test` and the release hygiene scan. CI runs those checks on Node 22
and 24 on Linux. These tests use fake Pi/GitHub and need no credentials/network.

```sh
npm test
node scripts/scan-release.mjs
node tests/pi-loader-smoke.mjs /path/to/existing-pi-package
```

The optional loader check previously passed against Pi 1.0.2: one TypeScript
extension, schema acceptance/rejection, no live session. The current publication
loader check also passed against Pi 1.0.2 with four tools and optional `issueId`
on `github_project_read`, without installing dependencies or starting a session.

The source's isolated native CLI/Herdr PTY fixture passed with Pi 1.0.2,
PiHerdsman 0.21.0 and Herdr 0.9.3. It checked native Manager tools and charter,
first-read notification, busy coalescing, two persisted notices, two role hooks,
and silent unchanged polls. It used two local Faux responses, zero remote
model calls, fake GitHub and zero delegations. The portable result summary is
[tests/herdsman-real-report.json](tests/herdsman-real-report.json); the opt-in
fixture is [tests/herdsman-cli-fixture.ts](tests/herdsman-cli-fixture.ts).
That native fixture is historical source-validation evidence from before this
refactor. It was not rerun for this release or by public CI; its test/result
files remain unchanged. The current native loader and 101 offline tests passed.

Tests cover session ownership, lifecycle cancellation, scope/mapping checks,
pagination, stale revisions, authenticated-author gating on every mutation,
comment retries, durable notice receipts, restart recovery, coalescing,
private atomic state and symlink rejection. Event tests cover initial/current
labels, added-task content, distinct comments and edits, busy coalescing, status
round trips, author/actor distinction, external-data labels, marked truncation,
full hashes beyond excerpt boundaries, bounded message details, scope departure,
legacy baselines, receipt replay and clearing pending excerpts.
Membership regressions cover busy departures/rejoins, final observed scope,
historical departure wording, retained comments, repair of older unsent batches,
stable receipts and frozen in-flight delivery across restarts.

## Remaining limits

- No real model task decomposition, Lead/Agent assignment or production session
  was tested. The extension itself never dispatches work.
- No live GitHub permissions, rate limits, Project mapping or mutation was tested.
- A crash before transcript persistence can repeat a notice; local state is not
  a cross-process lock. Run one owner process per Project.
- GitHub comments and status writes are independent. Local atomic replacement
  is not a transaction spanning GitHub and Pi.
- Configuration edits apply on session reload. Scope, author allowlist and
  mapping changes fail closed and require explicit reconciliation. Poll interval
  and semantic ordering do not change the new state binding.
- Legacy schema-2 state must first load and save using the unchanged original
  configuration before changing its poll interval. Loading alone does not
  guarantee a save, especially while paused. Do not delete queued state to bypass
  a fingerprint mismatch.
- The declared Pi minimum is 1.0.1; only Pi 1.0.2 was used for the loader/native
  fixture. Windows native integration and unattended reboot recovery are untested.
- No production installation or deployment is part of this release.
