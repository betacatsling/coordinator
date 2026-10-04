# 在所选项目会话登记固定协调者

本版只证明了隔离同线程恢复与 fixture 登记/交接约束。真实用户目标未登记，桌面可见性和实时同步未验证，不能宣称生产交接完成。下列路径、仓库和 ID 标签均为占位说明，不包含真实部署记录。

在所选项目的目标会话发送以下 prompt。此步骤只登记候选，不抢占当前后台协调者：

```text
请使用 project-delegation 的手动登记入口，将当前这个会话登记为 所选 GitHub Project的候选固定 coordinator。
绑定 Project 配置中已选定的 Project、仓库 OWNER/REPOSITORY，项目根 /absolute/repository/workspace。
先检查当前工具确实运行在这个项目根，且运行时提供 CODEX_THREAD_ID；不要猜测、手填或覆写会话 ID。
在项目根执行：
python3 ~/.codex/skills/project-delegation/scripts/register_coordinator.py --config /absolute/private/config.json
只返回登记文件、实际 native thread ID 与 pending 状态，随后结束本轮，等后台验证及交接。
我只担任任务协调和验收，实现交给独立 executor。不要创建第二个协调会话，不启动控制器，不自动执行历史 Issue。
```

注册程序仅接受当前进程继承的 `CODEX_THREAD_ID`，没有 `--thread-id` 参数。根目录或 scope 不匹配时拒绝。这里的环境变量是 Codex 运行时身份线索，并非密码学证明；登记文件也不是激活凭据。验证会通过官方 ACP `session/load` 加载确切 native ID，并在同一 ID 上完成两次无工具回复，第二次跨 acpx TTL 恢复并读回第一轮 nonce。若目标会话工具不在 目标主机的该项目根，或缺少此环境变量，登记失败，不另建会话替代。

后台管理员在目标会话完成登记且当前 turn 已结束之后执行：

```sh
python3 ~/.codex/skills/project-delegation/scripts/adopt_coordinator.py \
  --config /absolute/private/config.json \
  --registration /absolute/repository/workspace/.project-delegation/github-acpx/enrollments/实际native线程ID.json
```

第一次仅验证，原控制器仍为 owner。加载适配器的 guard 已绑定候选 native ID，禁止 `session/new` fallback 和 fork。验证成功后保持候选会话 idle，等待原控制器完成在途任务并正常停止，再执行交接：

```sh
python3 ~/.codex/skills/project-delegation/scripts/adopt_coordinator.py \
  --config /absolute/private/config.json \
  --registration /absolute/repository/workspace/.project-delegation/github-acpx/enrollments/实际native线程ID.json \
  --commit --expected-old-thread 当前已核验的旧native线程ID
```

交接必须取得项目 canonical controller.lock、旧绑定仍匹配、无 running task、验证未超过15分钟。配置及状态先备份，只替换协调者 binding/guard 命令，queue、baseline、评论去重及看板观察保留。旧 ledger 不移动、旧 native 会话不关闭；工具不会自行启动控制器。配置/状态两文件写入中断会造成身份不匹配而拒绝启动，需从明确备份恢复。随后由部署管理员正常启动原控制器服务，并校验两次后台请求仍使用新绑定的同一 native ID。

登记不是任意时刻可同时操控会话的保证。交接后的协调会话归后台串行 owner 使用，用户在桌面发新 prompt 前需暂停后台并等在途 turn 完成，避免两端争用。ACP 加载确切 ID 支持后台恢复；桌面列表展示或实时同步未验证，不能承诺。没有使用桌面 UI 自动化、私有数据库或隐藏会话注入接口。

本机隔离 QA 使用已有测试 native 会话，不触及生产会话。登记 provenance 在 QA 中为人工构造 fixture；真实目标桌面会话须由上方 prompt 运行 register 程序，并在结束 turn 后完成验证与交接。
