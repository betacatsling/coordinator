# Coordinator Console

A local web console over the real `ProjectController`: the board of scoped Issues,
full Issue reading with authorship provenance, revision-checked comment and status
writes, the watcher (start / pause / resend), the Manager notice queue with explicit
receipt, and the configured scope and guarantees.

    npm run console                      # demo: in-memory GitHub, nothing leaves the machine
    node console/server.mjs --workspace <dir> [--port 4317]   # live: <dir>/.pi/github-project.json + gh

Binds to 127.0.0.1 only. No dependencies, no build step. Keys: 1/2/3 switch views,
Esc closes an Issue, ⌘/Ctrl+Enter posts a comment.

In live mode the console acts as the bound Manager session itself: run it instead of,
not alongside, the Pi Manager for the same workspace, since both would share
`.pi/github-project-state.json`.
