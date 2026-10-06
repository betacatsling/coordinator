# Validation

The fixed source passed 55/55 offline Node tests on macOS. Ten additional
multi-project isolation tests bring the publication suite to 65/65. They use
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
extension, five tools, schema acceptance/rejection, no live session. Publication
reruns this against the existing Pi installation without installing dependencies.

The source's isolated native CLI/Herdr PTY fixture passed with Pi 1.0.2,
PiHerdsman 0.21.0 and Herdr 0.9.3. It checked native Manager tools and charter,
first-read notification, busy coalescing, two persisted notices, two role hooks,
and silent unchanged polls. It used two local Faux responses, zero remote
model calls, fake GitHub and zero delegations. The portable result summary is
[tests/herdsman-real-report.json](tests/herdsman-real-report.json); the opt-in
fixture is [tests/herdsman-cli-fixture.ts](tests/herdsman-cli-fixture.ts).
That native fixture is source-validation evidence, not rerun by public CI.

Tests cover session ownership, lifecycle cancellation, scope/mapping checks,
pagination, stale revisions, authenticated-author gating on every mutation,
comment retries, durable notice receipts, restart recovery, coalescing,
private atomic state and symlink rejection.

## Remaining limits

- No real model task decomposition, Lead/Agent assignment or production session
  was tested. The extension itself never dispatches work.
- No live GitHub permissions, rate limits, Project mapping or mutation was tested.
- A crash before transcript persistence can repeat a notice; local state is not
  a cross-process lock. Run one owner process per Project.
- GitHub comments and status writes are independent. Local atomic replacement
  is not a transaction spanning GitHub and Pi.
- Scope/mapping changes fail closed and require explicit reconciliation.
- The declared Pi minimum is 1.0.1; only Pi 1.0.2 was used for the loader/native
  fixture. Windows native integration and unattended reboot recovery are untested.
- No production installation or deployment is part of this release.
