# Coordinator — Pi GitHub Project extension

One Pi extension and one short Manager skill. The extension reads a single
GitHub Project, observes Issue/status/comment changes, wakes its fixed Manager
session and provides scoped GitHub tools. The Manager decides what to delegate,
reviews native Herdsman handoffs and writes concise results to the original Issue.

This is a development candidate. No production installation or live dispatch was
performed. It contains no Codex AppServer, MCP server, plugin compatibility
layer, worker launcher, supervisor, HTML renderer or separate polling service.

## Runtime and ownership

Use Node >=22.19, Pi >=1.0.1 and the separately managed Pi Herdsman v0.21.0 /
Herdr >=0.9.3 stack. Herdsman provides `staff_delegate`, `staff_resume`,
`staff_message`, `staff_stop`, `staff_list` and `staff_inspect`. The extension
uses none of its internal RPCs. Delegation and review stay in the Manager skill. Dependencies were prepared separately in isolated prefixes; this extension
does not install runtimes or alter global Pi settings. SSH disconnect persistence belongs to Herdsman/Herdr; machine reboot
does not guarantee unattended restoration.

The `gh` executable owns existing GitHub authentication. This extension never
reads, copies or prints credentials. Its transport calls `gh api --hostname
github.com graphql --input -` with JSON variables on stdin, never a shell
command assembled from Issue content.

To prepare a later reviewed trial, put the reviewed configuration in the target
workspace's `.pi/github-project.json`; use [examples/github-project.json](examples/github-project.json).
Record the exact existing Manager session ID from Pi, not a worker or fork ID.
After separately entering Herdsman Manager mode, first launch that existing
session inside its Herdr-owned pane with this extension and the explicit
`--github-project-manager` flag. See [startup and reconnect](STARTUP.md) for the
separate first-enable and attach-only Termius paths.
The package manifest exposes only `extensions/github-project/index.ts` and the
short skill. Do not install pi-subagents alongside this workflow.

The watcher starts only when all of these hold: an explicit initial flag or a
persisted enabled owner record; the exact configured session ID; and active
`staff_delegate`, `staff_resume`, `staff_message`, `staff_list` tools. This
capability check does not claim to prove Herdsman's internal Manager lease.
Lead/Agent/new/fork sessions cannot poll or use these GitHub tools, even if the
extension or flag is inherited. Restoring an exited Pi process uses the same
Pi `--session`; it does not need the enable flag again. Reconnecting to a
running Manager only attaches to its Herdr terminal and must not launch Pi again.

## Tools

| Tool | Purpose |
| --- | --- |
| `github_project_read` | Read scoped cards/statuses; pass `issueId` for the full Issue, every comment, revision and source authority labels. |
| `github_issue_comment` | Add an ordinary comment, with a stable request ID for retry. |
| `github_project_status` | Write an explicitly mapped status; comment and status writes are independent. |
| `github_project_watch` | Inspect/start/stop the in-process watcher, or explicitly retry an unconfirmed notice. |

The Manager must call `github_project_read` with `issueId` before comment or status writes.
Pass its `revision` as `expectedRevision` and the current `statusId` as
`expectedStatusId` for status writes. Changes invalidate stale writes. A status
write only changes status; it never posts a comment or asks for an acceptance
boolean. The short skill instructs the Manager to review, write the result
comment, then mark done. Comment retries reuse a stable `requestId` and an
own-author invisible marker; forged external markers cannot satisfy recovery.

All Issues in the configured repository that belong to the selected Project
are observable, across all statuses. Other repositories, DraftIssues and pull
requests are excluded. This version does not interpret arbitrary saved-view
filters or create/close Issues. Status field/option IDs and names are explicit,
and incomplete pages or changed mappings fail closed. GitHub contents are
untrusted task data. `authorizedUsers` labels author provenance and admits the
authenticated write author; it does not make any comment a new user approval.
Every remote mutation checks the current authenticated author immediately
before writing, including every status change.

## Lifecycle and state

The factory only registers APIs. `session_start` starts/reconciles the owner;
`before_agent_start` and tool results recheck Manager capabilities after role
activation. Configuration is read and validated once when the controller is
created; reload the session to apply file edits. An active controller keeps its
original binding until then. Shutdown, reload and session replacement abort the old request,
invalidate its generation and stop its single self-scheduling timer. Explicit
stop persists pause across reload. Role loss stops polling. Polling requests
and extension read/write operations are serialized; no second poll overlaps.

First successful startup wakes the Manager to inspect current tasks, including
an empty board. Thereafter unchanged content stays silent. A restored owner wakes for undelivered/new changes. The
Manager puts the Issue URL first in native delegation task text and uses
`staff_list`/`staff_inspect` (or `staff_transcript` for full context) to recover
ownership before deciding to resume or delegate; the extension never dispatches work itself.

Busy sessions and pending user input hold changes in one merged batch. Once
idle, the extension uses public `sendUserMessage(..., {deliverAs:'followUp',
expandPromptTemplates:false})`, preserving Herdsman's `before_agent_start`
Manager charter. Its void return is not a delivery receipt. A small in-flight
batch retains its stable ID until that ID appears in a persisted user message
on the current Pi branch. More changes merge into a second pending batch while
that notice is in flight. `agent_settled` only drains existing batches.

`.pi/github-project-state.json` stores scope/enabled/pause, per-Issue hashes,
pending/delivery metadata and own-comment hashes. It
stores no Issue text or credentials, uses atomic replacement and mode 0600,
and rejects symlink escapes. Own unchanged comments and confirmed own status
writes do not cause notification loops. Reload refuses to overwrite state with an incompatible scope, author allowlist
or status mapping. Poll-interval changes preserve delivery history. When
upgrading old state, first load and save it with the unchanged configuration
before changing the interval. Confirm a state write: loading a paused watcher
alone does not save its upgraded fingerprint. Do not delete pending history
to bypass a binding mismatch.

Delivery is crash-recoverable, not a distributed exactly-once dispatch lock.
A crash before transcript persistence can repeat the same notice ID. Neither
GitHub state nor the small local record is a cross-instance atomic claim.
Run one owner process per Project. A failed user-message preflight keeps its batch;
after fixing the cause, use `retryNotice` or restart the bound session.

## Validation

Run `npm test`; it uses fake Pi/GitHub only, with no network or credentials.
An optional offline loader check accepts the absolute path to an existing Pi
package: `node tests/pi-loader-smoke.mjs /absolute/pi/package`.
See [VALIDATION.md](VALIDATION.md) for evidence and remaining runtime limits.

## Install and configure

Install Node, Pi, `gh`, PiHerdsman and Herdr separately using their official
instructions in [DEPENDENCIES.md](DEPENDENCIES.md). Authenticate `gh` yourself;
this package does not set up authentication. Clone this repository, then install
its local Pi package:

```sh
git clone https://github.com/betacatsling/coordinator.git
cd coordinator
npm test
pi install .
```

Copy `examples/github-project.json` to `.pi/github-project.json` in your target
workspace. Replace every placeholder with your repository, Project node ID,
Status field/option IDs, allowed GitHub authors and exact existing Manager
session ID. This file is configuration, not a credential file. Follow
[the startup guide](STARTUP.md) to bind that fixed Pi session inside Herdr once
and configure Termius to attach to it on later connections. Creating or restoring
a Pi process is a separate setup/recovery action, never a reconnect fallback.
The extension does not create or select the Manager for you. One owner process
per Project is required. This package has no npm runtime dependencies; Pi supplies
the extension APIs, and PiHerdsman/Herdr remain external dependencies.

## Stop and uninstall

Use `github_project_watch` with `{ "action": "stop" }` to persist a pause, or
exit Pi to stop its in-process timer. Stopping the watcher does not stop native
Herdsman work; use `staff_stop` for work you intend to pause. Run `pi list`, then
`pi remove <installed-source>` using the exact source it shows. Remove the
workspace's `.pi/github-project.json` and `.pi/github-project-state.json` only
when you intend to discard that binding and delivery history.

## Coordinator 中文说明

这是一个 Pi 扩展和一个简短 Manager skill：读取单个 GitHub Project，合并变化后
通知固定 Manager；Manager 用 PiHerdsman 原生工具派工、审阅结果并回写 Issue。
依赖 Node >=22.19、Pi >=1.0.1、PiHerdsman 0.21.0、Herdr >=0.9.3 和已登录的 gh。
依赖需另行安装，步骤见上文与 [依赖说明](DEPENDENCIES.md)。克隆仓库后运行
`npm test`、`pi install .`，再填写目标工作区的 `.pi/github-project.json`。
按 [启动与重连说明](STARTUP.md) 在 Herdr 中绑定固定 Manager 会话并显式启用。
之后 Termius 只 attach 到仍在运行的主 Pi，不要每次 SSH 连接都启动 Pi。
仅在原进程确实退出后，才单独恢复同一个已记录的 Pi 会话。

工具共四个：`github_project_read` 无参数读取看板，带 `issueId` 读取完整 Issue
和评论；回写前必须完成后者。`github_issue_comment`、`github_project_status`
分别评论和改状态，`github_project_watch` 保留 status/start/stop/retryNotice 操作。
配置只在会话 reload 后生效；运行中沿用原绑定。新状态绑定不受轮询间隔及语义相同
的字段顺序影响。旧 schema-2 状态需先用原配置加载并确认保存，再修改轮询间隔；
暂停状态仅加载未必会保存。范围、授权作者或状态映射变化仍拒绝自动重绑。

用 `github_project_watch` 的 stop 操作持久暂停；卸载用 `pi list` 查明来源，再运行
`pi remove <installed-source>`。本项目没有 ChatGPT 侧栏映射、独立 WebUI 或
旧 Codex/MCP 兼容层。尚未验证真实模型派工、真实 GitHub 写入、生产安装和重启
后的无人值守恢复；崩溃时通知可能重放，不能当作分布式派工锁。

## License

MIT; see [LICENSE](LICENSE). External dependencies retain their own licenses;
no third-party source is vendored. The public repository's Git history is retained.
