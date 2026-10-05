# Local project dashboard

The dashboard is a read-only view of saved coordinator, task, executor and report state. Its local service also watches GitHub board changes and handles notifications for the bound coordinator. The UI does not launch workers, write GitHub state, accept work, merge branches or publish reports.

## Default startup

After a successful `coordinator_bootstrap.py --config /absolute/project-config.json init`, one detached process starts the dashboard and notification watcher and its selected project page opens in the default browser when a local desktop is detected. Use the returned `dashboard_url`, not an assumed port: startup prefers 18766 and selects a free port if it is occupied. A healthy server is reused, and repeated initialization does not open another tab for the same coordinator after a browser-open request succeeds. `opened: true` means the browser accepted the request; it does not prove the page rendered.

Pass `--no-open` to bootstrap, or set `"dashboard": {"auto_open": false}` in the project configuration, to suppress browser opening only. The combined service still starts or is reused and returns its URL. `status` only inspects the binding and service; it does not start a server or open a browser. Launch failures return a warning without invalidating the coordinator binding, but notifications must not be assumed available.

The service remains running after initialization exits, until explicitly stopped or the host shuts down. Closing a browser tab does not stop it. Dashboard and watcher share the service lifecycle. Its PID, selected port and identity are recorded in `.project-delegation/runtime/dashboard.json`; notification health is recorded in `notifier-service.json`, and startup diagnostics go to `dashboard.log` alongside it. There is no login/OS-startup hook, automatic remote forwarding or public hosting.

To stop this project's managed dashboard and watcher together, run from the bound coordinator's workspace and runtime:

```sh
python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/project-config.json stop
```

The command verifies the matching service before requesting shutdown; `stopping` means shutdown has been requested but is not yet confirmed. It does not stop executor jobs or delete their history, so a still-running worker may send its own completion notice afterward. Stop requires the same bound owner but can operate when the native coordinator is unavailable. Run `init` again with the original reviewed configuration to restart the service. Do not stop unrelated processes or delete state to bypass an ownership/configuration mismatch.

## Remote and headless hosts

SSH, CI and headless environments skip automatic browser opening. The returned loopback URL belongs to the machine running the project; it is not directly usable from another computer. Arrange a private SSH tunnel through an already configured host alias, using the returned port on both ends. For example, if the returned port is 18766:

```sh
ssh -N -L 127.0.0.1:18766:127.0.0.1:18766 YOUR_SERVER_ALIAS
```

Keep the tunnel running and open the returned `dashboard_url` on the viewing computer, preserving its `?project=...` selection. If the server selected another port, replace both occurrences of 18766. The ports must match because the server validates the HTTP Host header. Headless operation on the same computer can use its local URL without a tunnel if a browser becomes available.

## Manual foreground server

No separate manual command is needed after initialization. For an independent read-only foreground viewer, including multiple projects, use Python 3.9 or later from the skill checkout. This manual mode does not start notification watchers:

```sh
python3 scripts/web_dashboard.py --config /absolute/project-config.json
```

On native Windows, use `python` if that is your Python command. The path must refer to a reviewed project configuration on that computer. The server prints its local address, normally `http://127.0.0.1:18766`. Open that exact address in a browser on the same computer. Stop the process with Ctrl+C when finished.

To show multiple projects, repeat `--config`:

```sh
python3 scripts/web_dashboard.py --config /absolute/first.json --config /absolute/second.json --port 18766
```

Use `--port 0` to let the operating system choose a free port, then use the address printed by the command. The server binds only IPv4 loopback. There is no public link or authentication service; do not expose it through a public tunnel or reverse proxy. Other local processes or users with access to the computer may be able to read the dashboard.

## What the data means

The server reads each configured workspace's `.project-delegation/runtime` files, direct files in its `reports` directory and exact acceptance reports recorded by the job ledger. The project configuration supplies the exact workspace, repository, project ID and authorized login used to check state scope.

- Saved job state is not a heartbeat. A job recorded as running may no longer have a live process
- Coordinator availability reflects the notification service's last native observation and timestamp; executor liveness remains unknown unless separately observed
- The UI shows locally saved jobs and notification entries; its refresh button does not itself fetch the GitHub board
- Notification service health, queued input, a started/completed coordinator turn, executor completion and task acceptance are separate stages
- Missing, mismatched or malformed state is reported as unavailable. After a successful read, the server may retain that last good snapshot and mark it stale
- Unknown values are not silently converted into success or activity

The `notifications` API/status data includes watcher health, initialization/baseline, last attempt/success times, coordinator availability and combined board/completion outbox counts. Dashboard errors expose categories; detailed diagnostics stay local. A healthy service or a queue receipt does not prove that the coordinator processed a notice.

The page refreshes saved data automatically and offers a manual refresh button. Repository and Issue links open the verified GitHub destination; a Project link appears only when a canonical `project_url` is configured. Select a project, filter or search its task list, and open an executor card to inspect saved session identity, workspace, owned paths and check outcomes. Close the detail panel with its close button or Escape. The appearance control switches between light and dark themes; the initial appearance follows the browser's preference.

## Reports and safety

Open an HTML report from the project list, task or executor details to read it in the dashboard. The reader shows its saved metadata, offers the original download and links to the associated GitHub Issue or repository. Its project-report list contains currently saved files, not a version history. Back, the close button and Escape return to the project; a changed file offers a reload without replacing the page you are reading.

The preview is a rebuilt static HTML subset in an isolated sandboxed frame. It allows inline styling and embedded raster images, but disables JavaScript, external resources, forms and external navigation. Interactive content and external images may be absent. Downloaded originals remain untrusted and are not sanitized.

Allowed artifacts are direct files in the selected workspace's `reports` directory (HTML, HTM, PDF, TXT and MD) and exact `.project-delegation/runtime/<job-id>.html` acceptance reports named in the scoped job ledger. Only HTML/HTM has an in-app preview; other formats download. Oversized files, symlinks and arbitrary workspace paths are rejected. URLs use opaque IDs. These private loopback links are not hosted report links, and a listed artifact does not prove its claims were verified.

The JSON API intentionally excludes full assignments, raw result/log text, executor configuration and credentials. Some identifying local project/session/path information is visible. Do not share screenshots or API responses without reviewing them.

## Troubleshooting

- **Cannot load configuration:** check that the file is valid JSON and includes an absolute `workspace`, `repository`, `project_node_id` and `user_login`
- **No saved state:** initialize the project using the normal coordinator workflow; opening the dashboard itself will not create a binding or job
- **Stale or unavailable:** check producer state files and scope. Do not overwrite or reconstruct live state just to remove a warning
- **Connection refused:** confirm the server is running and open its printed address on the same computer
- **Port in use:** choose another `--port` or use `--port 0`
- **Report unavailable:** check the supported extension, size and directory constraints; no arbitrary workspace browsing is provided

## Validation boundary

Offline backend tests exercise parsing, scope checks, filtering, HTTP routes and report restrictions. These tests do not establish real worker liveness, native Windows/macOS operation, live GitHub execution or end-to-end MCP installation.

The optional browser smoke script, `tests/browser_dashboard_smoke.py`, creates clearly labeled synthetic test projects in a temporary directory. It needs separately installed Playwright and Chromium. It never reads a live user project or contacts GitHub. Its output directory contains screenshots and a machine-readable pass summary. Only a successful run constitutes browser validation; the existence of the script does not.
