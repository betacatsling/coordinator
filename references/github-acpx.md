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

Reports are rendered with the installed answer-me-with-html CLI and indexed under local `reports/`. `local_path` is a host filesystem path; `url` remains null. This backend does not publish a network link, upload confidential reports, post Issue comments, or update Project states. Those write actions require the selected Project and a concrete verified destination/field mapping. Receiving permission scopes does not enable them automatically. Record any later result comment IDs before using comments as fresh task inputs.

GitHub classic OAuth `project` covers Project read/write; existing `repo` scope covers repository operations. Use the official gh flow for missing scopes, with the user completing browser authorization. Never print tokens, copy auth to another host, or infer private Project IDs. The controller's GitHub queries include item and comment pagination and fail closed on incomplete input.

Observed validations live in the local test artifacts; distinguish real ACP model runs from fixture normalization tests. The original two-turn test preserved context across owner TTL expiry and rejected new-session fallback. Busy acpx requests retained one provider thread. No existing desktop UI chat binding is required or claimed.

## Bounded implementation executor

Add an `executor` object only when its workspace, file ownership and checks are known: `enabled`, `cwd`, `owned_paths` (relative file names), `checks` (argv arrays), `server` (existing mcp-agents server.js), `bridge_state_root` (private directory outside executor workspace), and `timeout`. The executor cwd must be inside the selected repository workspace. The coordinator cannot enlarge its permitted file set or invent executable check commands. Receipts persist the separate executor thread, actual source hashes, and independently run checks. Failed approvals, invalid plans, failed checks or rejected acceptance block that version without replacing the coordinator or automatically rerunning it.

For real initialization, record a baseline of already observed historical versions before starting new-event processing. Do not treat all historical completed Issues as new requests. Existing legacy watchers must be checked for activity before enabling another input owner; initialization alone must not kill them.
