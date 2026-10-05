# Bind the current project session

The user says “你作为这个项目的 coordinator”, “请把当前会话设为本项目协调者” or “Be this project's coordinator” in the session they want to use. Do not ask for copied commands, fabricated session IDs or a separate coordination session.

## Resolve the real project

The agent invokes the installed entry script in the actual project runtime:

```sh
python3 <installed skill>/scripts/coordinator_bootstrap.py
```

It uses the current cwd and runtime `CODEX_THREAD_ID`, checks the Git repository and searches ancestor `.project-delegation/github-acpx/config.json`, `.project-delegation/config.json` and matching entries in `~/.local/share/project-delegation/projects/*/config.json`. Use the unique deepest matching binding; `--inspect` is read-only diagnosis. A truncated host label, session title or screenshot is not identity or workspace evidence.

Handle returned states directly:

- `active`: reuse the current verified binding; do not create a session or restart a service
- `pending`: preserve and continue the same registration; do not create another candidate
- `registration_needed`: read-only inspection found a registration is needed
- `needs_selection` / `needs_configuration`: inspect available current-project information and ask only for the unresolved choice
- `blocked`: report the actual identity, scope, ownership or transport blocker; retain the existing owner

Runtime identity is a trusted runtime hint, not cryptographic proof. Do not take it from the user's prose, override it, copy an unrelated local identity into SSH or inspect private databases to manufacture a binding. Missing permissions remain blockers.

## Activation and ownership

The controller's supported transport must establish the actual current session and exclusive ownership before dispatch. Pending enrollment is not activation. Preserve the same pending record and report its actual state; do not promise automatic handoff or desktop synchronization without verified evidence. Do not introduce extra user-run commands or a new manual approval gate to compensate for an unimplemented transport.

An existing owner stays authoritative until a safe handoff completes. Settle admitted work, hold the canonical controller lock, check the expected old identity and preserve queue, baseline, board observations, comment deduplication and executor receipts. Never race an active turn, force-stop a user session or replace the native coordinator because recovery failed. A role request does not authorize unrelated tasks, historical replay or production migration.

The current-session transport and a legacy ACP binding are distinct runtime choices. Do not automatically rewrite a production binding to a different transport. When the controller cannot safely use the configured transport, retain the binding and report the concrete blocker.

## Legacy ACP resume protocol

Only for an existing ACP-based configuration: end the candidate's registration turn before external ACP loading. Obtain supported idle evidence and verify exact-native-ID resume/recovery without `session/new`, fork or replacement fallback. Retain pending if identity or readiness cannot be established. Do not make ACP load its own still-active tool turn, which can deadlock.

The compatibility path requires its existing proof and owner checks before committing a transfer. The administrative `init` action creates a separate coordinator only when explicitly chosen; it is never a fallback for the current-session request. ACP recovery evidence does not establish desktop list visibility or live UI synchronization.

## Continue the project workflow

Use the [GitHub board workflow](github-acpx.md): the coordinator plans and accepts, independent persistent executors default to three concurrent slots, and task follow-ups resume their original sessions. Only configured, authorized, current board tasks may be admitted. Claim comments, actual executor IDs, verified results and HTML reports use the same scoped write-back protocol.

See [VALIDATION.md](../VALIDATION.md) for observed evidence and remaining transport/end-to-end limitations. Editing or installing this package does not activate a production binding.

## Shared app-server queue transport (candidate)

Set `coordinator_transport: "app_server"` in a project profile whose official shared
app-server already has the chosen native thread loaded. `app_server_socket` may
name that official Unix endpoint; otherwise the entry reads
`codex app-server daemon version`. No private session database is used and no new
app-server is started to manufacture a loaded/idle state.

The bootstrap writes one idempotent binding request. The existing controller
consumes it only when it has no admitted or unreconciled tasks. It keeps the old
binding if metadata does not match. A running UI turn is allowed: subsequent
messages use `thread/queue/add`, whose native scheduler waits for that turn.
There is no separate handoff worker and no two-model-turn nonce ritual on this
path. Optional `auto_start_controller: true` starts the same single controller if
none is running; otherwise the entry reports the missing supervisor explicitly.

Requests and final results remain correlated by task/phase and stable client
message IDs. Unknown submission outcomes are observed rather than resubmitted;
late completion unblocks the original task. This transport currently has isolated
protocol/state tests only. A real loaded-session end-to-end test is required
before enabling it in a live profile. Existing ACP profiles are not silently
converted or restarted by installation.
