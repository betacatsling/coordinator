# Coordinator: one fixed Manager, attach-only reconnects

Each repository has one fixed main Pi conversation in its primary Herdr
workspace. Pi runs Herdsman's Manager role; Herdsman owns Lead/Agent delegation.
Herdr owns the terminal process. Each Termius tab attaches to its repository's
existing main Pi without opening the Herdr workspace UI.

## One-time setup

Install the separately managed dependencies and this Pi package as described in
[README.md](README.md#install-and-configure) and [DEPENDENCIES.md](DEPENDENCIES.md).
Run setup on the repository host, as the same OS user Termius will log in as.
Direct terminal attachment requires a Linux or macOS host.

These examples use Herdr session namespace `projects` and unique agent name
`repo-main`. Replace them deliberately; use `--session default` for the default
server. A Herdr session name, Herdr agent name and Pi session ID are different
identifiers. Give each repository its own unique main-agent name.

Complete Herdr's [native first startup][persistence] once if its server is not
running. This is separate setup, never a Termius startup command. Inspect
existing topology before creating anything:

```sh
herdr session list --json
herdr --session projects workspace list
herdr --session projects pane list
herdr --session projects agent list
```

Use the repository's existing primary workspace and main pane. Only if that
workspace does not exist, explicitly create it once:

```sh
herdr --session projects workspace create --cwd /path/to/repo --label repo
```

Record the returned `result.root_pane.pane_id`. For existing workspaces, verify
the main pane from the listing, not a worker pane. Replace the quoted pane
placeholder below with the actual ID.

## First initialization and binding

If the fixed main Pi already exists, reuse its exact session. Do not create a
conversation just to configure Termius. For an existing Pi running in Herdr,
verify its identity with Pi's `/session`; name it without relaunching if needed:

```sh
herdr --session projects agent rename '<main-pane-id>' repo-main
```

For a repository with no main Pi, create it **once**, in an available shell
pane of the primary workspace, then attach:

```sh
herdr --session projects agent start repo-main --kind pi --pane '<main-pane-id>'
herdr --session projects agent attach repo-main
```

Inside Pi, use Herdsman's `/manager`, then `/session` to record the exact Pi
session ID and file path; ensure the session file has been saved before exiting.
Complete the repository's `.pi/github-project.json`
with this ID as `mainSessionId` and the reviewed GitHub scope. The name
`repo-main` is not a substitute for `mainSessionId`.

For the first enable only, exit that Pi process cleanly, verify it is no longer
running and its pane is an available shell, then launch the **same saved
session** with the enable flag:

```sh
herdr --session projects agent start repo-main --kind pi --pane '<main-pane-id>' -- --session /path/to/manager-session.jsonl --github-project-manager
herdr --session projects agent attach repo-main
```

The first `--session` selects Herdr; the one after `--` selects Pi. Use the
recorded absolute session file, not a guessed path, partial ID, `--continue`,
`--resume`, `--session-id` or `--fork`. Pi's `--resume` opens a picker;
`--session-id` can create a session if absent. Never launch a second owner
process against the same Pi session.

Confirm the same `/session` ID, active Manager role and `github_project_watch`
status. Re-enter `/manager` if role restoration did not activate it.
Already-enabled Managers skip the first-enable relaunch. A main Pi outside
Herdr must be stopped and deliberately resumed in its verified Herdr pane;
attachment cannot migrate a process.

## Every ordinary Termius connection

Set the repository's Termius SSH tab to run this command **on the remote host**,
with an interactive terminal and `herdr` on that user's PATH:

```sh
exec herdr --session projects agent attach repo-main
```

Opening the tab again uses the identical command. It connects to the existing
terminal without launching Pi or selecting a Pi conversation. Never put `pi`,
`agent start`, `workspace create`, `/manager`, or an attach-or-create fallback
in the login/startup command. Bare `herdr`, `herdr --remote` and `herdr session
attach` open the full Herdr UI, so are not this reconnect path.

Detach with `Ctrl+B`, then `q`; send a literal `Ctrl+B` with `Ctrl+B`, `Ctrl+B`.
Detach or SSH client loss leaves the server-owned Pi running while the host and
Herdr server remain alive. Exiting Pi, closing its pane, stopping Herdr or
shutting down the host is different.

Only one writable direct-attach client controls a terminal. Detach the previous
client first; add `--takeover` only when deliberately replacing its control.
Do not put takeover in the default startup command.

## Missing target, exited Pi or server restart

An attach failure is a diagnostic, not permission to create another Manager.
Inspect `herdr session list --json`. If the server stopped, use native Herdr
startup as deliberate recovery before inspecting agents. Then check its `agent list`, `pane
list` and `agent get repo-main`. Verify namespace, primary workspace, process
and native Pi session reference before changing anything.

In Herdr 0.9.3 an agent target is a unique live agent name or current
agent-hosting pane ID. Bare kind labels such as `pi` and terminal IDs are not
agent targets; terminal IDs belong to `herdr terminal attach`. Names follow
live agents and can be lost on exit. A name alone does not verify Pi identity.

A server restart ends the old processes. Herdr can restore a recorded Pi
conversation through its official Pi integration. Agents launched by `agent
start` may retain their managed names; a manually launched Pi merely named
with `agent rename` loses that label on the native-resume path. Inspect the
actual result before renaming the
verified main or resuming it. Native restore depends on valid saved session
references and client attachment context; unattended reboot recovery is not
promised by this package.

If the fixed main truly exited and was not restored, verify no owner process
remains, choose an available shell pane in the same primary workspace, then
deliberately resume its recorded file:

```sh
herdr --session projects agent start repo-main --kind pi --pane '<main-pane-id>' -- --session /path/to/manager-session.jsonl
```

The persisted binding no longer needs `--github-project-manager`. Check the Pi
ID, Manager role and watcher status again, then use the ordinary attach command.
Preserve an explicit watcher pause unless you mean to restart it. No extra
launcher, compatibility layer or supervisor is needed.

## Sources and validation limits

Commands and identity/restore behavior were checked against these upstream
releases. This guide adds no live installation, Termius/SSH disconnect,
delegation or reboot test evidence.

- [Herdr 0.9.3 CLI][cli] and [session-selector implementation][selector]
- [Herdr persistence and direct attach][persistence]
- [Native session restore][restore] and [name restoration implementation][names]
- [Pi Herdsman 0.21.0 Manager workflow][manager]
- [Pi 1.0.2 session identity][pi-sessions] and [CLI selectors][pi-cli]

[cli]: https://github.com/herdrdev/herdr/blob/v0.9.3/docs/next/website/src/content/docs/cli-reference.mdx
[selector]: https://github.com/herdrdev/herdr/blob/v0.9.3/src/session.rs
[persistence]: https://github.com/herdrdev/herdr/blob/v0.9.3/docs/next/website/src/content/docs/persistence-remote.mdx
[restore]: https://github.com/herdrdev/herdr/blob/v0.9.3/docs/next/website/src/content/docs/session-state.mdx
[names]: https://github.com/herdrdev/herdr/blob/v0.9.3/src/persist/restore.rs
[manager]: https://github.com/boadij/pi-herdsman/blob/v0.21.0/docs/guides/project-orchestration.md
[pi-sessions]: https://github.com/earendil-works/pi/blob/v1.0.2/packages/coding-agent/docs/sessions.md
[pi-cli]: https://github.com/earendil-works/pi/blob/v1.0.2/packages/coding-agent/docs/cli.md
