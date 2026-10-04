# 在当前项目会话指定固定协调者

用户只需在希望担任协调者的项目会话发送：

> 你作为这个项目的 coordinator

“请把当前会话设为本项目协调者”或 “Be the coordinator for this project” 等自然表达使用同一入口。用户不必填写 Project ID、会话 ID、配置路径或粘贴命令。这里的“这个项目”指当前工具实际运行的工作目录及其对应 Git 仓库，不根据桌面截图、会话标题或截断主机地址推测。

## Agent 内部入口

识别上述请求后，agent 使用安装中的 `project-delegation/scripts/coordinator_bootstrap.py`：

```text
python3 <installed skill>/scripts/coordinator_bootstrap.py
```

这是 agent 内部工具调用，不是交给用户执行的步骤。程序默认读取当前 cwd 和进程继承的 `CODEX_THREAD_ID`，从当前目录的祖先查找 `.project-delegation/github-acpx/config.json`、`.project-delegation/config.json`，并检查个人 `~/.local/share/project-delegation/projects/*/config.json` 中匹配实际 workspace/Git 根的绑定。采用唯一、最深的匹配范围；多个候选返回 `needs_selection`，缺少绑定返回 `needs_configuration`。agent 只针对返回的具体缺失项询问，不猜测仓库、Project 或会话身份，也不自动创建配置、下载运行时或初始化另一个协调会话。

`CODEX_THREAD_ID` 是运行时提供的身份线索，不是密码学证明。不能从用户 prompt 获取、手填或覆盖该变量。缺少信号、根目录或范围不匹配、读取或工具权限失败时，报告具体原因并停止相关步骤；不改用隐藏接口、私有数据库或桌面自动化绕过限制。

## 复用和登记

若当前会话已是 active owner，入口核对持久绑定及 ledger 后复用该身份，不重复登记或交接。若当前 native ID 已有 pending 登记，继续返回同一登记和状态，不新建候选。其他未登记会话通过 `register_coordinator.enroll` 仅登记为 pending；bootstrap 不验证 ACP、不提交交接、不启动控制器，也不派发真实任务。

返回 pending 时，agent 应简短说明“当前会话已登记，尚未接管后台”，给出工具实际返回的登记记录和后续状态，然后结束当前 turn。登记文件不是激活凭据。不要在该会话自身尚未结束的 turn 内调用 ACP 加载或验证它：这会争用同一会话，可能形成等待自身结束的死锁。

## 首任激活与已有 owner 交接

目标 turn 结束后，由外部部署流程取得官方提供的 idle 证据，再通过受支持 ACP `session/load` 加载登记的确切 native ID。验证同一 ID 上的无工具往返及恢复能力；guard 必须禁止 `session/new`、fork 和新 native fallback。无法加载或身份不一致时保持 pending 并报告失败，不能以新建替代会话掩盖失败。只有静态写入 session ID 不足以证明 GitHub 后台可以续接或唤醒该会话。

首次 owner 激活也需要上述结束 turn、idle 证据和实际恢复验证。有现任 owner 时，现任继续持有生产绑定，直到候选通过验证、现任已接纳任务完成且控制器正常停止，再进行明确交接。提交须取得项目 canonical controller lock，确认预期旧身份、没有在途任务且验证仍有效；先备份再变更绑定，保留 queue、baseline、看板观察、评论去重和 executor 记录。不得关闭用户会话、抢占正在执行的 turn 或自行迁移运行中的控制器。

交接后由正常部署流程启动原控制器，并验证后台请求仍使用新绑定的同一 native ID。权限不足或缺少官方 idle 证明时，保留现任 owner 和 pending 记录，返回具体阻碍。当前 role 或工具绑定本身不自动授权真实研究任务派发、看板状态批量调整或历史任务回放。

后台持有协调会话时，用户再次交互前应暂停后台 intake，等待在途 turn 结束，避免两端争用。官方 ACP 恢复验证与桌面会话列表展示是不同证据；未验证桌面同步时不得承诺其列表或实时内容必然更新。

## 协调者工作规则

完整执行规则见 [GitHub/acpx 工作流](github-acpx.md)：固定协调者负责规划、依赖与冲突判定、验收；独立持久 executor 默认最多三个并发，后续工作恢复各自原线程。领取评论、真实执行标识、结果评论与 HTML 报告沿用同一去重、权限和验收流程。只在已绑定 Project/repository、用户授权的当前任务范围内工作；登记 coordinator 不扩大该范围。行为或研究结论需要相应证据，静态检查和协调回复不等于任务完成。

本文只说明入口和安全交接协议；修改或阅读文档不会改变实际生产 binding。

当前发布验证包含离线入口和 owner 测试；桌面自然触发端到端流程、真实用户接管尚未验证。发布或安装此包不改变生产绑定，也不派发真实任务。
