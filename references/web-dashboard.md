# Local project dashboard

The dashboard is a read-only view of saved coordinator, task, executor and report state. It does not launch workers, contact GitHub, change a board, accept work, merge branches or publish reports.

## Run

From the skill checkout, use Python 3.9 or later:

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

The server reads each configured workspace's `.project-delegation/runtime` files and direct files in its `reports` directory. The project configuration supplies the exact workspace, repository, project ID and authorized login used to check state scope.

- Saved job state is not a heartbeat. A job recorded as running may no longer have a live process
- Coordinator and executor liveness is shown as unknown unless it has actually been observed; this view does not perform that observation
- Tasks come from locally saved jobs and notification entries, not a newly fetched GitHub board
- Executor turn completion and coordinator acceptance are different lifecycle stages
- Missing, mismatched or malformed state is reported as unavailable. After a successful read, the server may retain that last good snapshot and mark it stale
- Unknown values are not silently converted into success or activity

The page refreshes saved data automatically and offers a manual refresh button. Select a project, filter or search its task list, and open an executor card to inspect saved session identity, workspace, owned paths and check outcomes. Close the detail panel with its close button or Escape. The appearance control switches between light and dark themes; the initial appearance follows the browser's preference.

## Reports and safety

Reports are available only from the selected workspace's direct `reports` directory. Supported extensions are HTML, HTM, PDF, TXT and MD. Oversized files, symlinks and paths outside the allowed directory are rejected. Report URLs use opaque IDs rather than arbitrary filesystem paths.

Reports download as attachments. HTML is not executed inside the dashboard: report responses carry a restrictive sandbox policy and are served as binary downloads. Treat downloaded report content as untrusted before opening it separately. A listed report is an artifact, not proof that its claims were verified.

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
