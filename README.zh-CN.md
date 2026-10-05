# project-delegation

让你选定的 Codex 项目会话担任 coordinator：读取项目，通过 MCP 派发独立持久 Codex executor，跟进执行并验收真实结果。[English](README.md)

## 开始

在希望担任协调者的会话中说：

> 你作为这个项目的 coordinator

coordinator 会解析当前仓库、已配置的 GitHub Project 和真实会话身份，并持续负责项目管理：检查代码和工具、判断哪些工作可以并行、要求修正、验收并汇报。watcher 只把任务变化通知给这个会话，不从对话中的 JSON 规划或派发任务。

新的 coordinator 直调模式已实现并完成离线测试，但尚未验证真实 Codex MCP 加载、原生通知投递和这一模式下的 GitHub 端到端执行。安装不会自动注册 MCP、重启会话、启动 watcher 或切换现有生产绑定。见[配置与工具契约](references/coordinator-tools.md)。

## 工作流程

- 从选定看板读取当前 Issue 标题、正文、授权用户评论和相关仓库产物
- 用 `tasks_list` 核对已有任务，再用 `executor_start` 派发符合条件的工作；每项任务使用独立持久会话，最多三个并行
- 检查当前版本依赖、文件范围和共享资源，保留项目中的未提交改动
- 用 `executor_status`、`executor_result` 检查进度和产物，用 `executor_continue` 在原会话中修正
- 用 `task_finish` 记录 coordinator 基于证据作出的验收决定，并执行已配置的回写

executor 一轮结束不等于项目任务完成。验收通过的变更仍位于独立 worktree，状态为 `isolated_unmerged`，需要另行集成。不会自动合并、推送、部署或关闭 Issue。该模式生成私有本地 HTML 报告，不提供托管 URL。

## 环境与配置

需要 macOS 或 Linux、Python 3.9+、Node.js、已登录的 Codex CLI 和 GitHub CLI，以及独立安装的 [mcp-agents](https://github.com/thomaswitt/mcp-agents) 来运行 executor。原生看板通知使用受支持的共享 Codex app-server。acpx/codex-acp 通道和外部 HTML 渲染器属于旧控制器流程，不是新直调路径的依赖。

作为本地 skill 安装时，先备份旧版本，再将 SKILL.md、VALIDATION.md、scripts/、references/、assets/ 放入 `$HOME/.codex/skills/project-delegation/`。随后按[coordinator 配置说明](references/coordinator-tools.md)设置准确的项目/看板范围、会话登记、隔离 executor、已授权回写和 stdio MCP 连接。示例不是实际凭据，也不是可直接启用的生产配置。

迁移须等正在执行的工作妥善结束，再单独明确切换配置，并保留现有 owner、任务会话和回执。notifier 的 `--baseline current` 会有意跳过当前符合条件版本的通知；应先检查已有工作，不能假设自动重放。新旧派发 owner 不能同时运行。

## 停止和卸载

仅用 Ctrl-C 或 SIGTERM 停止自己启动的 notifier/watcher/controller；重启前检查显式配置的 supervisor。独立 executor 可能在 MCP 断开后继续运行，应观察并等待已接纳任务结束，再移除其运行环境。原会话、报告、worktree 和私有状态先保留供检查。

卸载时删除安装的 skill 目录，只移除自己添加的 MCP 或 hook 配置。独立依赖目录仅在没有其他项目使用时删除。

旧 watcher 读取真实本地文件，ChatGPT 侧栏 Page/Canvas 不会自动映射到 PROJECT.md。唤醒空闲 UI 会话需要受支持的主机接口；会话同步和 transport 支持取决于实际主机。

## 文档与测试

- [Skill 主流程](SKILL.md)
- [Coordinator MCP 工具、登记与迁移](references/coordinator-tools.md)
- [旧版当前会话绑定](references/manual-coordinator.md)
- [共用 GitHub 配置与旧版运行方式](references/github-acpx.md)
- [旧版 PROJECT.md watcher 与 hooks](references/file-watch.md)
- [验证证据与限制](VALIDATION.md)

在仓库根目录运行可移植的离线测试：

```sh
PROJECT_DELEGATION_TEST_NODE=python3 \
PROJECT_DELEGATION_TEST_HTML_CLI="$PWD/tests/backend_renderer.py" \
python3 -m unittest discover -s tests -v
python3 scripts/scan_release.py
```

fixture 通过不代表真实 MCP 安装、桌面同步、原生唤醒或 GitHub 实际回写已验证。

MIT 许可。见 [LICENSE](LICENSE) 和 [THIRD_PARTY.md](THIRD_PARTY.md)。
