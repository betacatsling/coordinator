# Windows transport and validation boundary

## Native Windows

The Windows client uses the configured Codex executable to run:

```text
codex.exe app-server proxy --sock <existing socketPath>
```

This official command is a **raw byte relay to the existing local app-server**.
The Python client sends its normal HTTP Upgrade and masked WebSocket frames
through that relay. It does not start a second app-server, implement a named-pipe
protocol, open a TCP listener, or read private session files. The executable is
passed as a subprocess argument, with no shell; paths containing spaces work.
Closing the connection terminates only the relay process owned by this client.

Why use the relay? Native CPython's socket module does not currently expose
AF_UNIX on standard Windows builds. Codex itself provides Windows UDS support.
The daemon's `version` command must report `status: running` and a `socketPath`;
bootstrap additionally checks the actual CODEX_THREAD_ID, loaded thread status,
and exact workspace through `thread/read` before creating a binding.

Prerequisites:

- A Codex version supporting Windows daemon management and `app-server proxy`
- An already running shared server that owns the current native Codex thread
- The same user, workspace and CODEX_HOME as that thread; a non-elevated terminal
- A short CODEX_HOME if necessary: upstream documents a 108-byte canonical UDS
  address limit, including the terminator
- Native `codex.exe`, rather than an npm `.cmd` shim, as the configured executable

A missing relay, stopped daemon, incompatible endpoint, failed handshake or
unloaded thread blocks initialization. There is no automatic daemon launch,
thread replacement, WSL switch or credential fallback. Pipe I/O has bounded
read/write waits; a failed initialization cleans up its relay.

## WSL2 alternative

Use one WSL2 Linux distribution for the workspace, Linux Codex CLI, Python,
Git/GitHub CLI and this runtime. Open the coordinator in that environment and
initialize from its actual Codex thread. Do not point Linux Python at a Windows
socket, reuse a native Windows binding, copy CODEX_THREAD_ID between sessions,
or mix Windows executable paths with Linux workspace paths. This uses the
existing Linux AF_UNIX transport; no special Windows bridge is needed.

## What has actually been verified

`tests/test_windows_transport.py` exercises the Windows-selected code path on
a Linux host against a real subprocess fixture: HTTP upgrade, masked frames,
initialize + RPC, paths containing spaces, bounded timeout, relay cleanup,
fail-fast EOF and rejection of invented named-pipe/TCP endpoints. These are
contract tests, not a real Windows machine or live Codex end-to-end test.

A release claim of native Windows E2E requires running the unit suite on Windows
and then binding an actual current Codex thread, initializing/polling the board,
and observing a coordinator round trip on that machine. The same real-world
qualification is needed before describing a particular WSL2 installation as
validated. No such live Windows or WSL2 result is claimed here.

## Primary-source references (checked 2026-10-05)

- [Codex CLI command dispatch and proxy definition](https://github.com/openai/codex/blob/main/codex-rs/cli/src/main.rs)
- [Official raw stdio-to-UDS relay implementation](https://github.com/openai/codex/blob/main/codex-rs/stdio-to-uds/src/lib.rs)
- [Codex daemon platform prerequisites](https://github.com/openai/codex/blob/main/codex-rs/app-server-daemon/README.md)
- [Official WebSocket-over-UDS client](https://github.com/openai/codex/blob/main/codex-rs/app-server-client/src/remote.rs)
- [CPython socket header: AF_UNIX requires sys/un.h](https://github.com/python/cpython/blob/main/Modules/socketmodule.h)
- [CPython Windows AF_UNIX implementation issue](https://github.com/python/cpython/issues/77589)
