# 安装与首次运行 / Installation

完成一次安装后，只需对选定的 Codex 会话说：**你作为这个项目的 coordinator，使用配置文件 /绝对路径/project.json**。它会验证当前会话，启动或复用本地看板与通知服务，读取任务并协调执行。英文工具契约见 [coordinator-tools.md](coordinator-tools.md)。

## 1. 选择运行位置

选一台机器承载全部运行组件：目标 Git 仓库、Codex 原生会话及其共享 AppServer、Python、Node、GitHub CLI、MCP 服务、executor 和项目状态。可以选 Mac 或 Linux 服务器；如果选服务器，Mac 只作为客户端和浏览器。不要把 Mac 的配置路径、线程身份或 socket 复制到服务器。

原生 Windows 是移植候选，尚无完整实机端到端验证；下面给出 PowerShell 安装方法，传输限制见 [Windows 文档](windows-transport.md)。WSL2 应把全部组件放在同一个 Linux 发行版中。

准备：

- Python 3.9+、Git、GitHub CLI `gh`
- Node.js 26+ 与 npm；当前外部依赖 `mcp-agents@0.33.1` 的 [package.json](https://github.com/thomaswitt/mcp-agents/blob/main/package.json) 声明 `node >=26`
- 已登录的 Codex；客户端必须支持当前原生共享 AppServer 和 MCP 每次调用的 `_meta.threadId`。宿主 smoke 已验证的版本及范围见 [VALIDATION.md](../VALIDATION.md)
- 已有目标 Git 仓库、GitHub Project V2 看板，以及对应读取权限；实际执行还需要明确授权的 Issue 评论和 Project 状态写回权限

在所选机器本地按 [Codex 官方安装文档](https://developers.openai.com/codex/cli/) 和 [GitHub CLI 文档](https://cli.github.com/manual/gh_auth_login) 安装、登录；不要从其他机器复制凭据文件。先检查：

```sh
python3 --version
node --version
npm --version
git --version
codex --version
codex login status
gh auth status
```

Windows 将 `python3` 换为 `python`，并确认 `Get-Command python,node,git,gh,codex.exe` 能找到真实程序。

## 2. 下载并安装 skill

### macOS / Linux

```sh
mkdir -p "$HOME/src"
git clone https://github.com/betacatsling/project-delegation.git "$HOME/src/project-delegation"
SRC="$HOME/src/project-delegation"
SKILL="$HOME/.agents/skills/project-delegation"
mkdir -p "$(dirname "$SKILL")"
# 已安装则先保留完整副本；不删除项目运行状态
if [ -e "$SKILL" ]; then
  BACKUP="$HOME/.local/share/project-delegation-backups"
  mkdir -p "$BACKUP"
  mv "$SKILL" "$BACKUP/skill.$(date +%Y%m%d%H%M%S)"
fi
mkdir -p "$SKILL"
cp -R "$SRC/SKILL.md" "$SRC/scripts" "$SRC/references" "$SRC/assets" "$SRC/web" \
  "$SRC/VALIDATION.md" "$SRC/LICENSE" "$SRC/THIRD_PARTY.md" "$SKILL/"
```

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force "$HOME/src" | Out-Null
git clone https://github.com/betacatsling/project-delegation.git "$HOME/src/project-delegation"
$Src = "$HOME/src/project-delegation"
$Skill = "$HOME/.agents/skills/project-delegation"
if (Test-Path $Skill) {
  $Backup = "$HOME/.local/share/project-delegation-backups"
  New-Item -ItemType Directory -Force $Backup | Out-Null
  Move-Item $Skill "$Backup/skill.$(Get-Date -Format yyyyMMddHHmmss)"
}
New-Item -ItemType Directory -Force $Skill | Out-Null
'SKILL.md','scripts','references','assets','web','VALIDATION.md','LICENSE','THIRD_PARTY.md' |
  ForEach-Object { Copy-Item -Recurse (Join-Path $Src $_) $Skill }
```

`web/` 必须一起安装。源码仓库保留测试，安装目录保留运行文件。`~/.agents/skills` 是 [官方用户级 skill 路径](https://developers.openai.com/codex/skills/)；skill 文件安装不等于 MCP 已接入，也不会自动刷新正在运行的客户端。

## 3. 安装 executor 依赖

macOS / Linux：

```sh
DEPS="$HOME/.local/share/project-delegation-deps"
mkdir -p "$DEPS"
npm install --prefix "$DEPS" mcp-agents@0.33.1
node "$DEPS/node_modules/mcp-agents/server.js" --help
```

PowerShell：

```powershell
$Deps = "$HOME/.local/share/project-delegation-deps"
New-Item -ItemType Directory -Force $Deps | Out-Null
npm install --prefix $Deps mcp-agents@0.33.1
node "$Deps/node_modules/mcp-agents/server.js" --help
```

配置里的 `executor.server` 使用这里实际生成的 `node_modules/mcp-agents/server.js` **绝对路径**。运行 MCP 的环境也必须能从 PATH 找到已登录的 Codex 和 `gh`。此依赖由本项目私有启动，不需要另把它注册成 coordinator 的 MCP 服务。

当前服务自己生成简洁 HTML 验收报告，Web 看板也不需要 npm 构建。`answer-me-with-html` 是可选的独立展示工具，不是当前运行必需项；本项目没有 `renderer` 配置项。第三方说明见 [THIRD_PARTY.md](../THIRD_PARTY.md)。

## 4. 填写项目配置

将模板复制到仓库外的私人配置目录。macOS / Linux：

```sh
mkdir -p "$HOME/.config/project-delegation"
CONFIG="$HOME/.config/project-delegation/project.json"
# 仅用于新配置；若已有文件，保留原文件并另选名称
[ ! -e "$CONFIG" ] && cp "$SKILL/assets/fresh-config.example.json" "$CONFIG"
```

PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME/.config/project-delegation" | Out-Null
$Config = "$HOME/.config/project-delegation/project.json"
if (-not (Test-Path $Config)) { Copy-Item "$Skill/assets/fresh-config.example.json" $Config }
```

用编辑器填完 [模板](../assets/fresh-config.example.json) 的全部占位符：

- `workspace`：真正要处理的 Git 仓库绝对路径，不是 skill 目录；仓库应有已提交的 HEAD
- `repository`、`project_node_id`、`user_login`：目标 `OWNER/REPOSITORY`、Project 节点 ID、被授权提供任务文本的 GitHub 登录名
- `codex`、`node`：可执行文件绝对路径；Unix 可用 `command -v codex`、`command -v node` 查找。Windows 的 `codex` 必须指向真实 `codex.exe`，不能是 npm 的 `.cmd` 包装器；JSON 路径可用 `/`
- `board`：所选 BOARD_LAYOUT 视图 ID、完全一致的 filter、Status/Type 字段 ID、待做及排除类型选项的 ID 和精确名称。不能凭显示标签猜 ID
- `writeback.status`：同一状态字段以及已领取、已验收选项的真实 ID 和名称；“已验收”仍不表示已合并或已部署
- `executor.server`：上一步的 `server.js`；`bridge_state_root`：仓库及其 worktree 之外的私人绝对目录
- `executor.checks`：项目验收命令的参数数组，例如 `[["python3", "-m", "unittest", "discover", "-s", "tests"]]`，须适合实际目标仓库；`allowed_resources` 默认空；并行数 1–3

获取映射可先用只读命令（将 OWNER 和 NUMBER 换成实际值）：

```sh
gh api user --jq .login
gh project view NUMBER --owner OWNER --format json
gh project field-list NUMBER --owner OWNER --format json
```

视图 ID 和精确 filter 可用与源码相同的 GraphQL 字段读取，替换 Project ID：

```sh
gh api graphql -f id=REPLACE_PROJECT_NODE_ID -f 'query=query($id:ID!){node(id:$id){... on ProjectV2{id views(first:100){pageInfo{hasNextPage} nodes{id name filter layout}} fields(first:100){pageInfo{hasNextPage} nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}}}}'
```

这条命令也可在 PowerShell 使用。出现分页、权限不足或字段缺失时先解决映射，不能跳过范围校验。任务只吸收指定用户的 Issue 标题、正文及评论；其他用户的信息不会自动成为执行授权。

模板默认 `writeback.enabled=false`、`dry_run=true`，只支持安装和只读核对。如要真实执行，应在**首次 `init` 前**审阅并授权评论及状态回写，再设为 `enabled=true`、`dry_run=false`；仅改配置不代表取得授权。通知历史会固定这份配置，不能在初始化后直接切换写回设置。

## 5. 注册 MCP，然后选择 coordinator

在同一台机器、同一用户的 Codex 配置中注册。macOS / Linux：

```sh
codex mcp add project-delegation -- "$(command -v python3)" \
  "$SKILL/scripts/delegation_mcp.py" --config "$CONFIG"
codex mcp list
```

PowerShell：

```powershell
codex mcp add project-delegation -- (Get-Command python).Source `
  "$Skill/scripts/delegation_mcp.py" --config "$Config"
codex mcp list
```

这是 [官方 stdio MCP 注册方式](https://developers.openai.com/codex/mcp/)。如已有同名条目，先检查它，不要覆盖另一个项目的连接；多个项目用不同名称。配置属于实际运行宿主，Mac 上的注册不会自动配置服务器上的 Codex。

不要在 MCP 配置加 `CODEX_THREAD_ID`。启动握手和 `tools/list` 不需要线程 ID；每次业务调用必须由宿主发送 `_meta.threadId`。手工在工具参数中补 ID 无效。

让所选客户端按其支持的方式重新加载 MCP 配置，然后在**目标 workspace 的原生 Codex 会话**中确认真实可用的六个工具：`tasks_list`、`executor_start`、`executor_status`、`executor_result`、`executor_continue`、`task_finish`。`codex mcp list` 只证明配置存在，不证明工具已被当前会话加载。TUI 可用 `/mcp` 查看活跃连接；其他客户端按自身 MCP 管理入口操作，不假设热加载。

工具可见后，对你选定的会话说：

> 你作为这个项目的 coordinator，使用配置文件 /绝对路径/project.json。

该会话应在自己的工具运行环境中，从配置的 workspace 执行以下命令（绝对路径替换为真实路径）：

```sh
python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/project.json init
python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/project.json status
```

Windows 用 `python`。这里必须使用实际会话注入的 `CODEX_THREAD_ID`，普通终端手工粘贴 ID 不属于安装步骤。bootstrap 会校验共享 AppServer 中的同一个已加载线程及 workspace；它不会启动新 AppServer。确认返回 `initialized` 或 `reused`，再让 coordinator 实际调用一次只读 `tasks_list`。当前已有卡片会成为通知基线，因此首次读取不能省略。有绑定但调用缺少身份元数据，仍然没有接通；没有授权真实执行时，停在只读核对。

`init` 绑定成功后默认启动或复用一个本地服务，负责 Web 看板、看板变化通知和完成通知协调；不需要再单独启动 watcher。检测到本机桌面时，会在默认浏览器打开对应项目。重复初始化不会为同一个 coordinator 重复打开已成功请求打开的页面。`--no-open` 或配置 `"dashboard": {"auto_open": false}` **只关闭自动打开浏览器**，仍会启动或复用看板。以返回的 `dashboard_url` 为准；`opened` 只表示浏览器接受了打开请求。`status` 只检查绑定和服务状态，不启动服务或打开浏览器。服务启动失败会返回警告，不会使已成功的绑定失效，但此时不能声称通知已经可用。

已有绑定属于另一会话、scope 不匹配或未绑定目录里已有运行数据时，应停下来核对。已有通知历史也固定原配置，后续修改会被拒绝；应恢复原配置，不要删除状态绕过检查。临时不打开浏览器可用 `--no-open`，无须改配置。

## 6. 分派后结束本轮，等通知再审阅

Coordinator 首次通过 `tasks_list` 读取当前任务，按授权范围分派可独立执行的 executor，然后结束当前一轮。不要通过长时间 sleep 或反复轮询占住会话。Executor 结果与完成通知先持久保存，再尝试送回同一个 coordinator；后续看板变化也送到这个会话。

完成通知到达后，coordinator 用 `executor_status` / `executor_result` 检查结果，需要修正时用 `executor_continue` 继续原会话，核验后才调用 `task_finish`。看板变化通知到达时，先重新调用 `tasks_list` 对照当前版本和已有任务。通知服务不替 coordinator 做规划、分派或验收。

用前面的 bootstrap `status` 命令检查本地服务。服务健康、通知已排队、coordinator 一轮已开始或已结束、任务已验收应分别核对。`queued` 只表示收到排队回执；`delivered` 表示原线程里已找到这条输入，还要看 `turn_status` 是处理中、完成、失败还是中断。结果不明确的提交保留待核对，不盲目重发，也不另建 coordinator。

## 7. 查看 Web 看板

正常 `init` 已自动启动看板与通知服务，无须再开一个服务。它在后台运行，直到显式停止或运行机器关机；关闭浏览器标签页不会停止服务，也不会安装登录或系统启动项。运行信息在项目的 `.project-delegation/runtime/dashboard.json`，通知健康记录在 `notifier-service.json`，启动日志在同目录的 `dashboard.log`。从绑定会话的原 workspace 运行 `coordinator_bootstrap.py --config /absolute/project.json stop`，可一起停止看板和 watcher；`stopping` 表示尚未确认退出。它不会停止 executor 或删除历史，再次 `init` 可启动服务。

本机浏览器使用 `init` 返回的 `dashboard_url`，保留 `?project=...` 项目选择。默认优先使用端口 18766，被占用时自动选择空闲端口。SSH、CI 或无桌面环境不会自动打开浏览器，返回地址只属于实际运行机器，不能直接从 Mac 访问。如果运行在 Linux 服务器，需要在 Mac 另开终端，使用**自己已经配置好的 SSH 主机别名**建立私有隧道。假设返回端口为 18766：

```sh
ssh -N -L 127.0.0.1:18766:127.0.0.1:18766 YOUR_SERVER_ALIAS
```

保持隧道运行，再用 Mac 浏览器打开完整的 `dashboard_url`。如果返回其他端口，将命令两处 18766 都替换为该端口；两端端口必须一致，因为看板会校验 HTTP Host。服务器示例别名可以叫 `server1`，这里只是占位，不包含任何真实地址或用户名。不要为此开放防火墙、绑定公网或使用公开隧道。

仅需独立只读视图或多项目视图时，可手动运行前台看板；`--port 0` 避免与自动服务抢占端口：

```sh
python3 /absolute/skill/scripts/web_dashboard.py --config /absolute/project.json --port 0
```

PowerShell 用 `python`。此手动模式不启动 watcher；打开打印的实际地址，用 Ctrl+C 停止前台视图。多个项目重复传入 `--config`。

想先看界面，可下载并在浏览器打开[独立演示页](../examples/dashboard-demo.html)；它只展示示例数据，不连接真实项目。

看板显示已保存状态，不是 executor 的进程心跳。HTML 报告可直接进入隔离静态阅读器，查看任务关联、下载原文件或打开 GitHub 来源；预览禁用脚本和外部资源，不提供公开报告链接。看板不启动任务、不写 GitHub、不合并代码。详情见 [Web 看板说明](web-dashboard.md)。

## 8. 验证到哪一步

从源码目录运行离线测试（Windows 用 `python`）：

```sh
cd "$HOME/src/project-delegation"
python3 -m unittest discover -s tests -v
python3 scripts/scan_release.py
# 可选：真实 Codex 宿主 + 临时 fixture，不启动模型或 executor
python3 tests/codex_host_smoke.py --codex "$(command -v codex)"
```

- **离线测试通过**：证明受测代码和 fixture 契约，不证明客户端已连接
- **原生宿主 smoke 通过**：证明此 Codex 版本真实走了握手、工具发现、逐次线程身份及授权检查；仍使用临时 fixture，不是你的项目
- **当前项目真实可用**：所选原生会话 bootstrap 成功、真实 `tools/list` 有六项、真实 `tasks_list` 成功。完整执行还须观察授权的 GitHub 领取、独立 executor、结果检查及验收写回

原生 Windows 尚未完成实机端到端验证，不能把跨平台文件锁或 Windows 传输合同测试当作可直接生产执行的证明。可选择单一 WSL2 环境，但同样需要本机真实验证。遇到报错请保留原始错误和收据，按 [工具工作流](coordinator-tools.md) 恢复，不能用另建会话掩盖失败。

明确授权的任务范围与回写权限后，coordinator 才能实际分配和验收。验收只说明隔离 worktree 中的实现通过检查；merge、push、部署和关闭 Issue 需要另行授权。
