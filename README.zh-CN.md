# project-delegation

让你选定的原生 Codex 会话阅读项目、分派独立且持久的执行会话，并审阅结果。[English](README.md)

## 开始

对选定的会话说：**你作为这个项目的 coordinator，使用配置文件 /绝对路径/project.json**。

安装配置完成后，它会验证当前会话，启动或复用通知服务与本地看板，先读 `tasks_list`，分派独立 executor，然后结束本轮，等完成通知到达再审阅；后续看板变化也通知同一个 coordinator。

通知只提供输入；规划、跟进修改和验收仍由 coordinator 决定。服务健康、输入已排队、coordinator 一轮已开始或已结束，以及任务已验收，是不同的状态。

## 配置

需要 Python 3.9+、Node.js 26+、已认证的 Codex 和 GitHub CLI，以及另行安装的 [mcp-agents](https://github.com/thomaswitt/mcp-agents)。全部运行组件与所选 coordinator 的共享原生 AppServer 应放在同一台机器。

1. 按[安装说明](references/installation.md)安装 skill 和 executor 依赖
2. 填写并审阅[配置示例](assets/fresh-config.example.json)：仓库、Project、授权用户、精确看板映射及执行权限
3. 按 Codex 客户端支持的方式注册 `python3 /absolute/skill/scripts/delegation_mcp.py --config /absolute/project.json`，并在选定会话加载。宿主须逐次提供 `_meta.threadId`；不要把复制的线程 ID 写入全局配置
4. 发送上面的一句话。会话会从目标 workspace 运行 `coordinator_bootstrap.py --config /absolute/project.json init`，并实际调用 `tasks_list` 验证连接

Bootstrap 在 `.project-delegation/runtime` 创建或核验绑定，不会安装工具、新建共享 AppServer 或修改项目配置，也不会删除其他目录中的文件。示例默认关闭 GitHub 回写；真实执行前必须明确授权认领回写并核验看板映射。

检测到本机桌面时，看板会在默认浏览器打开。`--no-open` 只关闭自动打开浏览器，本地服务仍会启动。以返回的网址为准；[远程访问](references/web-dashboard.md)需要另行建立私有隧道。

Windows 通过配置中的 `codex.exe` 和官方 `app-server proxy` 连接已有 daemon。[Windows 前提与验证边界](references/windows-transport.md)也说明 WSL2 路径。原生 macOS、Windows 与 WSL2 均尚未完成真实端到端验证。

## 执行与审阅

`tasks_list` → `executor_start` → 结束本轮 → 完成通知 → `executor_status` / `executor_result` → 需要修正时 `executor_continue`，核验后 `task_finish`。

最多同时运行三个独立任务。依赖使用已验收的 job ID 和固定版本回执，不自动应用前序补丁。路径、资源、源版本和持久回执共同约束分派与恢复。可独立推进的任务分派完后就结束本轮，不要反复轮询或在工具调用中持续 sleep。

Executor 结束一轮只代表结果可以审阅。Coordinator 根据实际改动、相关测试和任务目标判断是否通过。运行时自动收集改动及检查结果，不要求 executor 另做产物清单、文件哈希或固定字段的验收表。隔离 worktree 中的改动仍需授权集成，不会自动 merge、push、部署或关闭 Issue。

Issue 评论简要说明做了什么、检查结果及重要限制，有可访问的报告链接时附上。报告按需要补充细节，不要求固定栏目。

私有 HTML 报告可在看板的隔离静态阅读器中查看或下载，并通过已核验的 GitHub 链接查看上下文。预览禁用 JavaScript 和外部资源，没有公开托管网址。

断开 MCP 不一定停止 executor 或本地服务。审阅前保留原始会话、worktree 和回执，只停止自己拥有且明确要停止的服务。

卸载时只移除自己添加的 skill 和 MCP 配置；审阅前保留原始会话、worktree 和私有状态。

## 文档与测试

- [独立示例数据演示](examples/dashboard-demo.html)：下载后在本机浏览器打开

- [Skill 工作流](SKILL.md)
- [协调工具契约](references/coordinator-tools.md)
- [本地看板与报告](references/web-dashboard.md)
- [验证证据与限制](VALIDATION.md)

运行 `python3 -m unittest discover -s tests -v` 和 `python3 scripts/scan_release.py`。离线 fixture 不能证明真实安装、通知唤醒或 GitHub 回写已完成验证。

MIT，见 [LICENSE](LICENSE) 和 [THIRD_PARTY.md](THIRD_PARTY.md)。
