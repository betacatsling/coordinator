# One repository and Project with a fixed acpx coordinator

This backend is optional. The existing document watcher and native reminder hooks remain available. Copy `assets/github-acpx.example.json` and replace its paths and exact selected Project node ID, repository and authorized user. Do not initialize a real Project before the user has selected it. The fixture source uses `{"type":"fixture","path":"/absolute/source.json"}` instead of GitHub API calls and never writes GitHub.

Pinned dependencies tested: acpx 0.19.4 and @agentclientprotocol/codex-acp 2.1.1 from registry.npmjs.org, installed in a private prefix with npm lifecycle scripts disabled. Node 26 already exists on the tested hosts. The adapter uses the explicit existing CODEX_PATH; no credentials are copied. Never use unpinned automatic npx downloads or switch global Node.

Initialize once:

```
python3 scripts/project_acpx.py --config /absolute/config.json init
python3 scripts/project_acpx.py --config /absolute/config.json once
```

`run` polls GitHub every 15 seconds with ordinary API code. Submitted Issue bodies and user comments enter the serial queue immediately; there is no ten-second quiet gate for GitHub. Every label and unlabelled Issue is eligible. Only Issues in the selected Project and repository contribute instructions; only the selected user's body and comments are instructions. Recorded self-result comment IDs are excluded. Unchanged version hashes are skipped. Older pending versions are superseded; running snapshots remain immutable. No Ready label or status gate is imposed.

Initialization creates one native coordinator and a tool-free bootstrap turn before saving Project/repository -> acpx record/session/provider binding. This first turn is necessary to persist an otherwise empty native thread. Later calls only resume the same identity. The ACP proxy rejects any new/fork fallback and wrong session IDs before forwarding. `sessions show` and the provider ledger are checked before and after each turn. A failed or interrupted initialization requires explicit investigation; never delete its ledger and silently replace the coordinator.

The fixed coordinator only coordinates and verifies acceptance; it does not implement repository changes. Implementation may be assigned to authorized independent executors. With an explicit executor configuration, the coordinator returns a structured assignment for the preconfigured owned paths. An independent MCP executor implements it, the controller runs preconfigured argv checks, and the original coordinator reviews actual source and observations before accepting. With no executor configuration, the turn only produces coordination guidance; it does not complete the Issue. Reads-only is the default permission policy; unattended approval requests fail rather than being auto-approved. Do not equate successful completion of a coordination turn with completion of the underlying Issue.

A single controller lock owns the queue. Queue and receipts are durable under `.project-delegation/github-acpx/`. Restart recovers the binding and pending versions. An interrupted running row becomes blocked because its request may already have executed; it is not automatically replayed. A new user revision can queue separately. Duplicate controller processes fail without taking over a live owner.

Reports are rendered with the installed answer-me-with-html CLI and indexed under local `reports/`. `local_path` is a host filesystem path; `url` remains null without a verified configured endpoint. Optional scoped comments/status write-back is described below and disabled by default. Receiving permission scopes does not enable it automatically. The controller records and rediscovers its result comments before using comments as fresh task inputs.

GitHub classic OAuth `project` covers Project read/write; existing `repo` scope covers repository operations. Use the official gh flow for missing scopes, with the user completing browser authorization. Never print tokens, copy auth to another host, or infer private Project IDs. The controller's GitHub queries include item and comment pagination and fail closed on incomplete input.

Observed validations live in the local test artifacts; distinguish real ACP model runs from fixture normalization tests. The original two-turn test preserved context across owner TTL expiry and rejected new-session fallback. Busy acpx requests retained one provider thread. No existing desktop UI chat binding is required or claimed.

## Bounded implementation executor

Add an `executor` object only when its workspace, file ownership and checks are known: `enabled`, `cwd`, `owned_paths` (relative file names), `checks` (argv arrays), `server` (existing mcp-agents server.js), `bridge_state_root` (private directory outside executor workspace), and `timeout`. The executor cwd must be inside the selected repository workspace. The coordinator cannot enlarge its permitted file set or invent executable check commands. Receipts persist the separate executor thread, actual source hashes, and independently run checks. Failed approvals, invalid plans, failed checks or rejected acceptance block that version without replacing the coordinator or automatically rerunning it.

For real initialization, record a baseline of already observed historical versions before starting new-event processing. Do not treat all historical completed Issues as new requests. Existing legacy watchers must be checked for activity before enabling another input owner; initialization alone must not kill them.

## Scoped GitHub write-back

`writeback: {"enabled": true, "dry_run": true}` enables planning only. Set `dry_run` false only for the already authorized selected repository/Project. `writeback-dry-run` previews completed entries; `retry-writeback` reconciles their results without replaying model turns. Before each write the controller re-fetches the Project, checks current user-input revision, Issue membership, repository and authenticated author. Stale results refuse write-back. A Project/Issue/version marker identifies one own result comment. Remote markers recover dedupe after a lost local receipt; known own markers never become new task inputs. GitHub does not provide atomic compare-and-set for comment creation, so a single controller lock owns writes; do not run another writer with this marker namespace.

Optional `writeback.status` requires exact `field_id`, `accepted_option_id`, and `accepted_option_name`. The live field/options are checked before any mutation. Missing/changed mappings refuse the operation rather than guessing a state. Choose a review/in-progress option for isolated patches awaiting merge; do not advertise a patch as fully Done. No Issue closure, merge, commit or push occurs. Comment-only operation is supported with no status mapping.

## Private report access

`scripts/serve_reports.py` is an optional foreground helper for an explicitly selected reports directory. It binds IPv4 loopback only and rejects resolved paths outside that directory, including escaping symlinks. It serves files and directory listings from that directory; select a dedicated report folder, not a repository or credential directory. It does not provide authentication, TLS, a public URL, an SSH connection, or service installation.

After selecting an unused local port and authorizing the service, run:

```sh
python3 scripts/serve_reports.py --directory /absolute/reports --port "$REPORT_PORT"
```

For access from another computer, configure an authorized SSH connection to the report host and forward the chosen port:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L "127.0.0.1:${REPORT_PORT}:127.0.0.1:${REPORT_PORT}" REPORT_HOST
```

Set the controller's `report_base_url` to the matching loopback URL on the controller host. Test reader access through the forward separately. Both commands stay in the foreground; Ctrl-C or SIGTERM stops only the process you started. Stop the report process and forwarding process separately. Installing this repository runs neither command and does not change existing production services. No real deployment configuration or reports are distributed here.

`report_base_url` names an existing private HTTP(S) endpoint serving the reports directory. It starts no service or tunnel. A rendered report is read back from that exact URL; only identical bytes with HTTP 200 produce a non-null `url` and `access_verified: true`. An unavailable endpoint retains `local_path` and `configured_url`, with `url: null`; comments never invent an accessible link. Verification on the controller host does not prove reachability from another computer. Do not upload confidential reports to a public host. A new persistent loopback server or SSH forward requires concrete user approval; do not bind 0.0.0.0, edit firewall rules or repurpose another project's existing service.

## Per-Issue repository worktrees

An executor with `isolate_worktree: true` binds the exact selected Git repository root. The fixed coordinator proposes a minimal relative file/directory list for each Issue; traversal and controller/auth/Git paths are rejected. The controller creates a new detached worktree at current committed HEAD, keeps it and its receipt for review, and never applies it to the main workspace. If its requested scope overlaps dirty main-workspace files, execution blocks with that concrete reason; existing edits are not overwritten, stashed or silently included.

Executors cannot invent check commands from comments. Optional `checks` remain controller-configured argv arrays. Without those, worktree mode performs scope/diff checks and Python AST parsing, explicitly reported as static verification rather than behavioral tests. Original-coordinator acceptance reviews actual artifacts and observations. Unowned changes, changed HEAD, staged changes and unsafe symlinks block acceptance. File ownership is enforced at plan and acceptance; the Codex workspace sandbox is the actual OS boundary, not a claim that each owned path has its own OS sandbox. Worktree Git metadata points back to the repository; executors are instructed not to use Git, and Git operations require normal sandbox approvals where applicable. Never claim full filesystem isolation or copy authentication into a worktree.

Before `run`/`once`, a live legacy watcher PID blocks the new owner. Settle/ack its pending work first, explicitly stop only its watcher after any admitted turn finishes, then start the GitHub controller; never terminate coordinators or user model tasks. `init`, `status`, and write-back inspection do not take over the old watcher.
