# project-delegation

让你选定的原生 Codex 会话担任项目 coordinator：阅读看板和代码，通过 MCP 分派独立、持久的执行会话，跟进修改并验收结果。[English](README.md)

## 开始

在你选定的会话里说：**你作为这个项目的 coordinator**。

配置确认后，入口读取工具运行环境中的真实 `CODEX_THREAD_ID`，向原生 AppServer 核验该线程的身份、工作目录和加载状态，再建立全新的项目绑定。规划、分派、跟进和验收都由这个会话直接调用工具完成。可选的看板 watcher 只发送变更通知。

这是实验性的全新运行链路，没有状态转换、接管或兼容模式。状态只存入 `.project-delegation/runtime`，不会删除其他目录的现有文件，也不会自动安装工具、启动新的共享 AppServer 或修改线上配置。Windows 连接会启动并清理自己使用的官方字节转发子进程。

## 配置

需要 macOS、Linux 或原生 Windows 移植候选版本、Python 3.9+、Node.js、已认证的 Codex 和 GitHub CLI，以及另行安装的 [mcp-agents](https://github.com/thomaswitt/mcp-agents)。所选 coordinator 必须已加载在受支持的共享原生 Codex AppServer 中。

1. 参考[配置示例](assets/fresh-config.example.json)，填写仓库、Project、授权用户及精确的看板字段映射，确认执行器和回写权限
2. 在所选项目目录运行 `python3 /absolute/skill/scripts/coordinator_bootstrap.py --config /absolute/config.json init`
3. 按实际 Codex 客户端支持的方式显式注册 `python3 /absolute/skill/scripts/delegation_mcp.py --config /absolute/config.json`。使用会话真实运行环境，不要将复制的线程 ID 写进全局 MCP 配置
4. 确认当前会话实际发现六个协调工具，并成功调用只读的 `tasks_list`
5. 如需通知，先运行 `board_notifier.py --config /absolute/config.json init --baseline current`，再启动其 `watch` 命令

示例默认关闭回写。实际 GitHub 分派要求经过授权的在线认领回写和已核验的看板映射，必须确认后再启用。复制 skill 不代表 MCP 已注册，也不会刷新已经运行的客户端。

Windows 通过配置中的 `codex.exe` 和官方 `app-server proxy` 连接已有 daemon。请参阅 [Windows 前提、WSL2 替代路径与验证边界](references/windows-transport.md)。Linux 环境中的协议契约测试已通过，原生 Windows 与 WSL2 的真实端到端运行尚未验证。

## 工作与验收

`tasks_list` → `executor_start` → `executor_status` / `executor_result` → 需要修正时 `executor_continue` → 核验后 `task_finish`。

最多同时运行三个独立任务。依赖使用已验收的 job ID，只传递固定版本的验收材料，不自动应用前序补丁。路径、共享资源、源版本和持久回执共同约束分派与恢复。

执行器完成一轮不代表项目完成。验收记录实现证据，修改仍留在隔离 worktree 中，需要另外完成集成。不会自动 merge、push、部署或关闭 Issue。报告是本地私有 HTML 文件，没有托管网址。

只停止你自己启动且明确要停止的 watcher。断开 MCP 不一定停止执行器；审阅前保留原始会话、worktree 和回执。卸载时只移除自己添加的 MCP 配置和 skill 文件。

## 本地 WebUI

运行 `python3 scripts/web_dashboard.py --config /absolute/project-config.json`，再用同一台电脑的浏览器打开打印的地址，默认 `http://127.0.0.1:18766`。可重复 `--config` 查看多个项目，用 `--port 0` 自动选择空闲本地端口。见 [WebUI 使用与限制](references/web-dashboard.md)。

页面只读展示已保存的项目、任务、执行器状态及报告下载，不派发、不验收、不回写 GitHub，也不探测实时存活状态。HTTP/API 和 DOM fixture 测试不等于真实浏览器渲染验证；桌面/手机视觉 QA 尚未完成。

## 文档与测试

- [Skill 工作流](SKILL.md)
- [配置和工具契约](references/coordinator-tools.md)
- [验证证据与限制](VALIDATION.md)

在仓库根目录运行 `python3 -m unittest discover -s tests -v` 和 `python3 scripts/scan_release.py`。离线测试不能证明真实 MCP 连接、原生通知唤醒或 GitHub 回写已经可用。

MIT，见 [LICENSE](LICENSE) 和 [THIRD_PARTY.md](THIRD_PARTY.md)。
