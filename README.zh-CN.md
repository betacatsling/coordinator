# project-delegation

让当前 Codex 项目会话协调 GitHub 看板任务，由独立持久 executor 执行，并验收真实结果。[English](README.md)

## 开始

在希望担任协调者的会话中说：

> 你作为这个项目的 coordinator

skill 会解析当前工作目录、仓库、已配置的 Project 和运行时会话身份，复用已有绑定，或把当前会话登记为 pending。只有配置缺失或存在歧义时，才询问缺少的选择。不会另建协调者来替代当前会话，也不会抢占现有 owner。

pending 不等于已激活。后台使用此会话前，须由受支持的控制器通道确认真实会话身份和安全所有权。见[绑定与激活](references/manual-coordinator.md)。

## 默认流程

- 从选定 GitHub 看板的已配置待做状态领取任务，排除配置中的项目跟踪类型
- 读取当前 Issue 正文和授权用户评论，不要求另建 PROJECT.md
- 协调者负责规划与验收；每项独立任务使用独立持久 Codex 会话，默认最多三个并行
- 按当前版本检查依赖、文件重叠和共享资源冲突，未满足时等待
- 只有实际获准执行的任务才发布领取评论，再把真实 executor ID 更新到同一条评论
- 检查产物与实际测试结果，发布结果和 HTML 报告，只更新已配置的看板状态
- 保留未提交工作和原任务会话；独立 worktree 的变更留待审阅，不自动合并或推送

指定角色不代表授权选择无关任务。开始实际执行前，须明确看板、执行范围、权限和回写配置。安装本身不启用后台。

## 环境与配置

需要 macOS 或 Linux、Python 3.9+、Node.js，以及已登录的 Codex CLI 和 GitHub CLI。后台还使用独立安装的 acpx、codex-acp、[mcp-agents](https://github.com/thomaswitt/mcp-agents) 和 [answer-me-with-html](https://github.com/QingYunA/answer-me-with-html)。已测试版本与证据见 [VALIDATION.md](VALIDATION.md)；安装不保证外部工具兼容性。

作为本地 skill 安装时，先备份旧版本，再将 SKILL.md、VALIDATION.md、scripts/、references/、assets/ 复制到 $HOME/.codex/skills/project-delegation/。安装不会修改 hooks、凭据或服务。

按[配置说明](references/github-acpx.md)和[配置示例](assets/github-acpx.example.json)填写实时核实的 Project/看板字段及运行时路径。示例禁用 executor 和实际回写，并启用 dry-run。只开启已获授权的范围；映射缺失或变化时停止相关操作。

HTML 默认是本地文件。只有现有私有端点返回相同内容时，才生成已验证 URL；控制器端验证不等于读者可访问。不得把机密报告上传到公开服务。

## 停止和卸载

仅用 Ctrl-C 或 SIGTERM 停止自己启动的 watcher/controller，并等待已接纳任务结束；重启前检查显式配置的 supervisor。卸载时删除安装的 skill 目录，只移除自己添加的 hook。报告和私有状态先保留供检查；独立依赖目录仅在没有其他项目使用时删除。

旧 watcher 读取真实本地文件，ChatGPT 侧栏 Page/Canvas 不会自动映射到 PROJECT.md。唤醒空闲 UI 会话需要受支持的主机接口；会话同步和 transport 支持取决于实际主机。

## 文档

- [Skill 主流程](SKILL.md)
- [当前会话绑定](references/manual-coordinator.md)
- [GitHub 配置与运行](references/github-acpx.md)
- [旧版 PROJECT.md watcher 与 hooks](references/file-watch.md)，仅在明确选择时使用
- [验证范围与限制](VALIDATION.md)

运行离线测试：`python3 -m unittest discover -s tests -v`。fixture 通过不代表桌面同步、真实用户接管或 GitHub 实际回写已验证。

MIT 许可。见 [LICENSE](LICENSE) 和 [THIRD_PARTY.md](THIRD_PARTY.md)。
