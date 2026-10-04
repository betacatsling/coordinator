# project-delegation

Codex 项目协调 skill，以及本地 `PROJECT.md` 文件监听器。[English](README.md)

## GitHub 输入模式：基础能力发布

本版已纳入固定 acpx coordinator 绑定、GitHub 输入解析与持久版本队列，以及可选 executor 实现和原 coordinator 验收流程。见[配置与命令](references/github-acpx.md)、[通用配置模板](assets/github-acpx.example.json)及[验证范围](VALIDATION.md)。原有文件监听和原生提醒 hook 保留为可选模式。

绑定一个 GitHub Project 和一个仓库，由显式初始化创建固定 acpx coordinator，后续恢复同一身份。范围内配置用户的 Issue 正文和评论作为输入，不按标签筛选，无标签也处理。`run` 默认每 15 秒用普通 API polling 检测变化，无 10 秒静默条件，不让模型调用承担等待。真实 GitHub 初始化会记录历史版本基线；绑定变更或中断任务需要明确排查，不自动替换 coordinator 或重放任务。

coordinator 只派发并验收。显式配置 executor 时，独立 MCP executor 实现并运行固定检查，再把实际源码和观察结果交给原 coordinator 验收。未配置 executor 时只提供协调建议，不代表 Issue 完成。文件清单约束派发和产物检查，但不构成独立的操作系统文件访问边界。

**生产回写尚未完成。** Issue 结果评论、Project 状态回写、可访问 HTML 托管链接及生产 executor 文件所有权仍未完成或配置。本版报告只有本地路径，`url` 为 null。主实现任务没有启动真实 Project 事件循环。macOS/Linux 固定会话恢复、隔离 executor 与验收已分别验证，不能据此声称生产闭环已交付。最终目标仍是 Issue 简短结论、实际证据和可访问 HTML 详情链接；外部 HTML skill 不改动。

另需已认证 GitHub CLI、独立安装的 acpx 0.19.4 和 @agentclientprotocol/codex-acp 2.1.1。使用显式运行路径，不复制认证或真实绑定状态。`init` 创建固定 coordinator；`once` 处理队列；`run` 持续 polling，Ctrl-C/SIGTERM 后等待已接纳回合结束再释放锁。补齐生产设置并检查其他输入所有者后，才启用真实事件循环。

每个唯一 `##` 标题下面写一个自然语言任务。连续 **10 秒** 没有修改后，监听器默认只写待处理队列，不调用模型。显式 `--thread-id` 绑定合格的已有 MCP thread 才执行；监听器不会创建 coordinator。执行结果生成 HTML，在文档中追加日期链接。

查看[两任务示例](examples/simple-two-task-demo/PROJECT.md)、[脱敏报告 HTML 源码/下载](examples/simple-two-task-demo/reports/report.html)和[可运行代码](examples/simple-two-task-demo/example.py)。GitHub 展示 HTML 源码，下载后可本地打开。

## 依赖与安装

需要 macOS/Linux、Python 3.9+、Node.js 26+、已登录且位于 PATH 的 Codex CLI。Python 部分仅使用标准库和 POSIX `fcntl`，暂不支持 Windows。源实现使用 Codex CLI 0.159.0。

外部依赖分别安装，不打包第三方源码：

- [mcp-agents](https://github.com/thomaswitt/mcp-agents)：测试版本 0.33.1，使用异步 Codex MCP 工具。
- [answer-me-with-html](https://github.com/QingYunA/answer-me-with-html)：按上游说明安装，使用 `scripts/am.mjs` 生成报告。

克隆仓库，将 `SKILL.md`、`scripts/`、`references/`、`assets/` 复制到 `$HOME/.codex/skills/project-delegation/`。已有安装先备份。本仓库不自动修改配置或认证。

```sh
npm install --prefix "$HOME/.local/share/project-delegation-deps" mcp-agents@0.33.1
export PROJECT_DELEGATION_SERVER="$HOME/.local/share/project-delegation-deps/node_modules/mcp-agents/server.js"
export PROJECT_DELEGATION_HTML_CLI="$HOME/.codex/skills/answer-me-with-html/scripts/am.mjs"
```

确认两个路径存在。Codex 保管认证，不要把 token 写进文档。

## 使用

将 [示例 PROJECT.md](examples/PROJECT.md) 放到目标项目，填写目标、范围、验收，再启动：

```sh
python3 scripts/watch_project.py --project /absolute/path/to/workspace
```

默认只响应后续输入修改；加 `--run-current` 可在 10 秒静默后提交当前内容。可用 `--server`、`--html-cli`、`--node` 指定路径，也可用上述环境变量及 `PROJECT_DELEGATION_NODE`。监听器有自己的 stdio MCP 连接，不会配置桌面 MCP。

默认命令只写 `.project-delegation/pending.json`，本身不会送入当前 UI session；队列模式不需要 bridge 或 renderer。加 `--thread-id EXISTING_THREAD_ID` 只能继续同工作目录、未加载且 MCP 可访问的已有 thread。绑定不可用、已加载或目录不符时阻塞，不创建替代 coordinator。

提醒当前 coordinator 可使用[原生同步 hook 模板](assets/reminder-hooks.example.json)。替换脚本和项目路径，仅合并新增条目到目标项目 `.codex/hooks.json`，用 Codex `/hooks` 审核并信任具体定义。监听器保持队列模式；工具/用户输入事件通过 `hookSpecificOutput.additionalContext` 将待处理任务提醒注入同一会话。Stop 可对每个版本请求一次继续执行。提醒要求 coordinator 验收、发布 HTML 报告，再确认处理准确版本；送达提醒本身不算任务完成，新修改仍待处理。

**没有 hook 事件就没有提醒；完全 idle 的会话不会自动唤醒。** 当前回合需要主动等待时可用 `python3 scripts/wait_for_pending.py --project /absolute/project --timeout 45`；它是有界等待，不是后台唤醒服务。安装 skill 不会启用或信任 hook。原生实测仅覆盖 PreToolUse，其他事件仅做协议测试，见 [VALIDATION.md](VALIDATION.md)。

唯一 H2 标题标识任务，改标题视为新任务；成功完成且未变化的任务跳过。代码围栏中的标题及 `## 执行报告` 不算任务。旧 `delegation:input` 标记仍兼容。执行期间修改合并为最新输入，失败不自动重试。手动协调遵循 executor 简报和文件所有权；监听器执行有界步骤，禁止递归派发。

HTML 历史存于 `reports/`，文档底部追加日期链接；`DELEGATION-RESULTS.md` 是辅助最新文本记录。`.project-delegation/` 保存 thread、日志和报告索引。编辑器旧版本覆盖链接后，监听器可从索引恢复。报告、状态和日志可能包含敏感项目内容，请勿直接提交。

## 停止与卸载

Ctrl-C 或 SIGTERM 停止自己启动的监听器。关闭其私有 MCP 连接会取消活动任务，重试前检查文件。停止后再删除状态。卸载时删除安装的 skill 目录；若配置了 hook，仅移除新增条目，保留其他 hook。专用依赖目录不再被其他项目使用时可删除。报告默认保留。

可选 hook 见 [hooks.example.json](assets/hooks.example.json)。替换项目与 skill 路径，确保 CLI 继承依赖环境变量，使用 Codex `/hooks` 审核并信任具体定义。本仓库不安装后台服务、登录项或全局 hook。hook 能力取决于 CLI 版本；切换标签页不保证触发 SessionEnd。

## 真实限制

这是本地文件监听与待处理队列。显式绑定可继续合格的已有 MCP thread。**ChatGPT 侧栏 Page/Canvas 不会自动映射成此文件**；需要真实文件映射或获授权的事件适配器。相对链接能否点击取决于前端。

监听器必须持续运行；旧状态中的 thread 不会自动续接，必须显式 `--thread-id`；job 仅在连接内有效。审批策略是 `on-request`，监听器不能自动批准请求；停止后在交互审批界面处理。提示词要求 coordinator 不使用网络、不安装依赖、不改认证/设置及监听器输出，但提示词不构成安全边界，仍以实际沙箱和宿主策略为准。

文件事件不能判断修改者身份。追加报告会检查原子替换，但不能对任意并发原地写入提供事务保证。

## 测试与许可

```sh
python3 -m unittest discover -s tests -v
python3 scripts/scan_release.py
```

测试覆盖任务解析去重、旧标记兼容、报告恢复、renderer 调用、MCP 封装、默认队列和假 MCP 显式绑定；**不能声称这些是模型实测**。主实现任务另有本次两任务真实 MCP 验证与 HTML 渲染，属于当时环境的结果，详情见 [VALIDATION.md](VALIDATION.md)。

自有 skill/胶水代码采用 [MIT](LICENSE)。第三方依赖保留各自许可，见 [THIRD_PARTY.md](THIRD_PARTY.md)。此项目独立于 OpenAI 官方产品。
