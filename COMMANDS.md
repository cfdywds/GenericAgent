# GenericAgent 斜杠命令使用指南

> 位置：本文件与 `README.md` 同级。  
> 依据：`frontends/tui_v3.py` 的命令表与处理逻辑、`frontends/slash_cmds.py` 的 prompt builder、`agentmain.py` 的核心 slash 处理、`frontends/chatapp_common.py` 的聊天前端命令。

## 1. 快速选择：什么情况下用哪个命令？

| 需求 / 场景 | 首选命令 | 说明 |
|---|---|---|
| 想让 Agent 自主推进一个目标，不想每步都手动指挥 | `/autorun [任务种子]` | 进入 autonomous 模式，适合长期、自驱、探索式任务。 |
| 更新本仓库到上游最新版 | `/update [额外要求]` | 自动生成安全更新流程提示，强调先检查差异、备份、优先上游、不提交。 |
| 想让 Agent 吞噬/蒸馏外部项目能力 | `/morphling <仓库/路径/能力描述>` | 适合把外部项目的方法、工具、SOP迁移进本项目。 |
| 只有一个大目标，需要拆解、规划、持续推进 | `/goal <目标>` | 适合目标导向任务，通常比普通提问更强调阶段性推进。 |
| 需要多个 worker 并行协作 | `/hive <目标>` | 适合调研、编码、排障等可拆分并行任务。 |
| 需要通过 conductor 编排多个 subagent | `/conductor <任务>` | 适合更明确的多 agent 编排和委派。 |
| 启动/停止定时或后台服务 | `/scheduler` 或 `/scheduler start <name>` | 交互式选择 reflect/frontend 服务；也可直接启动指定服务。 |
| 当前任务跑偏或太慢，想停止 | `/stop` 或 `/abort` | 中止正在运行的主任务。 |
| 想问一个旁路小问题，但不打断主任务 | `/btw <问题>` | 后台回答，不改变主会话主线。 |
| 想做代码审查 | `/review [范围/要求]` | 在当前会话内触发代码 review。 |
| 想换模型 | `/llm` 或 `/llm <编号>` | 无参数打开选择/列表；带编号直接切换。 |
| 想看当前会话状态 | `/status` 或 `/sessions` | 查看运行状态、模型、轮数、上下文、cwd。 |
| 想恢复历史会话 | `/continue` 或 `/resume` | `/continue` 是前端恢复器；`/resume` 会让 Agent 总结最近日志供选择。 |
| 想新开干净会话 | `/new [会话名]` | 清空当前上下文并可设置会话名。 |
| 想撤回最近几轮 | `/rewind [N]` | 删除最近 N 轮上下文；无参数打开菜单。 |
| 想导出回答 | `/export`、`/export clip`、`/export file <name>`、`/export all` | 导出最后回复到剪贴板/文件，或给出完整日志路径。 |
| 想查看工具调用审计 | `/verbose`、`/tools`、`/trace` | 查看工具调用明细。 |
| 想看 token 用量 | `/cost` | 汇总当前会话 token/请求统计。 |
| 想清屏/重置当前对话 | `/clear` | 注意当前实现会重置会话；不是单纯 UI 清屏。 |
| 想设置项目工作目录 | `/workspace <绝对路径>` 或 `/workspace off` | 进入/退出项目工作目录模式。 |
| 想改界面语言或宠物动画 | `/language`、`/emoji` | UI 个性化设置。 |
| 想退出 | `/quit`、`/exit`、`/q` | 退出 TUI；核心 agent 队列还识别 `/exit`。 |

---

## 2. 命令分层：哪些是“前端命令”，哪些会交给 Agent？

### 2.1 TUI v3 直接处理的命令

这些命令主要由 `frontends/tui_v3.py` 在前端层处理，不一定会把原始文本交给 LLM：

- `/help`
- `/status`、`/sessions`
- `/llm`
- `/btw`
- `/review`
- `/rewind`
- `/continue`
- `/workspace`
- `/new`
- `/rename`
- `/clear`
- `/cost`
- `/verbose`、`/tools`、`/trace`
- `/export`
- `/stop`、`/abort`
- `/language`
- `/emoji`
- `/scheduler`
- `/quit`、`/exit`、`/q`

### 2.2 slash_cmds 生成长提示词后交给 Agent 的命令

这些命令由 `frontends/slash_cmds.py` 生成一段“模式提示词”，再作为普通用户任务提交给 Agent：

- `/update`
- `/autorun`
- `/morphling`
- `/goal`
- `/hive`
- `/conductor`

特点：它们不是简单执行一个固定函数，而是把 Agent 引导到对应工作模式，让 Agent 读取相关 SOP、调用工具、执行实际任务。

### 2.3 核心 Agent 层识别的命令

`agentmain.py` 里还直接识别：

- `/session.<属性>=<值>`：动态设置当前 LLM backend session 属性。
- `/resume`：转换为“读取最近 model_responses 日志并总结可恢复会话”的提示词。
- `/exit`：用于 agent 队列退出逻辑。

### 2.4 聊天/微信等简化前端命令

`frontends/chatapp_common.py` 中的通用聊天前端支持：

- `/help`
- `/stop`
- `/status`
- `/llm [编号]`
- `/restore`
- `/continue`
- `/new`
- `/btw`
- `/review`

微信入口还会把普通消息加上文件展示提示；以 `/` 开头的文本会作为命令/任务进入处理链。

### 2.5 `agentmain.py` CLI 模式：不是 slash 命令，但常被 slash 工作流调用

这次上游更新新增/整理了 subagent 启动方式。它们不是在聊天框输入的 `/xxx` 命令，而是在代码根目录用命令行启动 `agentmain.py`。

#### `--func PROMPT_FILE`：纯函数模式

```bash
python agentmain.py --func prompt.txt [--llm_no N]
python agentmain.py --func prompt.txt --nobg [--llm_no N]
```

行为：

- 读取 `prompt.txt`
- 执行一次任务
- 将结果写到同名输出文件：`prompt.out.txt`
- 完成后退出，不等待 `reply.txt`
- 不加 `--nobg` 时会后台启动并打印 PID；加 `--nobg` 时前台同步执行，便于脚本等待结果

适合：

- 单次子任务
- Map/Reduce 中的并行 map 子任务
- 不需要追问、不需要多轮协作的旁路分析

#### `--task NAME`：持续协作模式

```bash
python agentmain.py --task task_name [--input "短任务"] [--llm_no N]
```

行为：

- 使用目录 `temp/task_name/`
- 输入为 `input.txt` 或 `--input` 写入的短文本
- 输出为 `output.txt`、`output1.txt`、`output2.txt` ...
- 当轮完成后等待 `reply.txt` 继续下一轮；长时间没有 `reply.txt` 才退出
- stdout/stderr 写入 `temp/task_name/stdout.log`、`temp/task_name/stderr.log`

注意：

- 持续协作模式一般**不要加 `--nobg`**，否则前台会卡在等待 `reply.txt` 的循环中。
- 主 Agent 空闲时应读取 output 观察进度，必要时用 `_stop`、`_keyinfo`、`_intervene` 等文件干预。
- 多个 subagent 并行时，键鼠/同一浏览器 tab 等物理资源不可共享。

---

## 3. 逐条命令说明与最佳使用场景

### `/help`

显示当前前端支持的命令说明。

**最适合：**
- 忘记命令名称或参数格式。
- 刚切换到新前端，不确定支持哪些命令。

---

### `/status`、`/sessions`

查看当前会话状态，包括是否运行中、当前 LLM、对话轮数、上下文使用情况、当前工作目录等。TUI v3 中 `/sessions` 与 `/status` 输出同类信息。

**最适合：**
- 不确定 Agent 是否还在运行。
- 想确认当前模型、上下文轮数、cwd。
- 长任务前做状态检查。

---

### `/llm`、`/llm <编号>`

查看或切换 LLM 后端。

**用法：**

```text
/llm
/llm 0
/llm 4
```

**最适合：**
- 当前模型太慢、太贵或能力不足。
- 想从轻量模型切到强模型处理复杂任务。
- 调试不同模型表现。

**建议：**
- 简单问答/低风险任务用便宜或快速模型。
- 大规模改代码、复杂排障、长规划任务用更强模型。

---

### `/btw <问题>`

旁路提问，不打断主 Agent 任务。TUI 实现中 `/btw` 可以在主任务运行时触发，后台回答，适合“顺便问一下”。

**用法：**

```text
/btw 这个报错可能和什么有关？
/btw 总结一下刚才工具输出里的关键点
```

**最适合：**
- 主任务正在运行，但你想问一个小问题。
- 想让 Agent 解释某段日志，不改变当前主线任务。
- 需要并行获得参考意见。

**不适合：**
- 需要修改文件、执行复杂操作的主任务；这类应直接正常输入或用 `/autorun`、`/goal`。

---

### `/review [范围/要求]`

触发当前会话内代码审查。TUI 中会调用 `frontends/review_cmd.py`，聊天前端也允许 `/review` 进入 agent 执行链。

**用法：**

```text
/review
/review 检查 frontends/tui_v3.py 的命令处理有没有边界问题
/review 重点看并发和资源释放
```

**最适合：**
- 改完代码后做安全性、可维护性、边界条件检查。
- 合并前审查某个模块。
- 想要一份风险列表而不是直接改代码。

---

### `/update [额外要求]`

让 Agent 执行 GenericAgent 仓库更新流程。`slash_cmds.py` 生成的提示强调：

1. 添加/检查 `upstream`。
2. `git fetch upstream main`。
3. 更新前汇报本地分支、未提交改动、上游差异。
4. 优先上游，必要时备份本地改动。
5. 不自动 commit。

**用法：**

```text
/update
/update 更新后重点检查 TUI 是否还能启动
```

**最适合：**
- 想同步官方上游代码。
- 当前仓库疑似落后。
- 需要在保留少量本地改动的同时更新。

**注意：**
- 这是高影响操作，会改工作区文件；Agent 应先检查和备份。
- 不适合在你有大量未整理本地改动时盲目执行。

---

### `/autorun [任务种子]`

进入“自主探索 / autonomous 模式”。`slash_cmds.py` 会提示 Agent 先读 `memory/autonomous_operation_sop.md`，全程自驱推进；不可逆/高风险动作先询问用户；结案给出做了什么、产物在哪、下一步。

**用法：**

```text
/autorun 帮我全面检查项目命令系统并补齐文档
/autorun 自动排查为什么测试失败，能修就修，不能修给出最小复现
```

**最适合：**
- 目标明确，但过程需要 Agent 自己探索。
- 需要多步探测、读文件、运行脚本、修复、验证闭环。
- 你不想每一步都手动下指令。

**不适合：**
- 你只想问一个具体问题。
- 涉及删除、部署、转账、覆盖重要数据等高风险操作且没有明确边界。

**使用建议：**
- 给清楚的“成功标准”和“禁止事项”。例如：

```text
/autorun 修复导出命令的 bug。要求：不改公共 API；改前先定位原因；最后运行相关测试。
```

---

### `/morphling <目标技能/仓库>`

进入 Morphling 模式，用于“吞噬/蒸馏”外部项目能力到本仓库。提示会要求 Agent 先读 `memory/morphling_sop.md`；如果没有目标，会先询问 GitHub 仓库、本地路径或能力描述。

**用法：**

```text
/morphling https://github.com/example/project
/morphling D:\\some\\local\\tool
/morphling 学习某项目的插件系统设计并迁移可复用能力
```

**最适合：**
- 想把外部工具、算法、架构模式吸收到 GenericAgent。
- 想提炼一个项目的能力，而不是完整复制。
- 做“竞品/开源项目能力迁移”。

**注意：**
- 应关注许可协议、依赖体积、安全边界。
- 最好明确希望吸收的是“能力/设计/接口”，还是“代码实现”。

---

### `/goal <目标>`

进入目标导向模式。适合把一个较大的目标交给 Agent，让它规划、拆解、持续推进。

**用法：**

```text
/goal 把命令系统文档补齐，并检查 README 是否需要链接过去
/goal 调研当前项目的测试覆盖短板，给出可执行改进计划
```

**最适合：**
- 目标比普通问答更大，但还不一定需要多 worker。
- 你希望 Agent 先规划再行动。
- 任务需要阶段性检查和产出。

**与 `/autorun` 的区别：**
- `/goal` 更偏“目标规划与推进”。
- `/autorun` 更偏“自主探索执行”，适合让 Agent 在较宽边界内自驱操作。

---

### `/hive <目标>`

进入 Hive 多 worker 协作模式。提示会要求读取 `memory/hive_sop.md`，用于多个 worker 分工并行处理。

**用法：**

```text
/hive 调研命令系统：一个 worker 查 TUI，一个查聊天前端，一个查 README，然后汇总
/hive 并行排查三个可能导致启动失败的方向
```

**最适合：**
- 任务天然可拆分。
- 需要并行调研多个模块。
- 时间紧，愿意用更多调用换速度。

**不适合：**
- 很小的单点修改。
- 强依赖串行状态的任务。

---

### `/conductor <任务>`

让 Agent 调用 `frontends/conductor.py` 执行多 subagent 编排。与 `/hive` 类似，但更明确地走 conductor 编排入口。

**用法：**

```text
/conductor 组织多个 subagent 审查前端命令、Agent核心命令、文档一致性
```

**最适合：**
- 你明确需要“编排多个 subagent”。
- 任务需要角色分工、结果汇总、冲突协调。

---

### `/scheduler`、`/scheduler start <name>`

管理可启动服务，包括 `reflect/*.py` 任务和部分 frontend app。无参数时 TUI 会打开交互式多选菜单，显示正在运行的服务；确认后启动/停止。带 `start/run` 可直接启动指定服务。

**用法：**

```text
/scheduler
/scheduler start scheduler
/scheduler start task_a task_b
```

**最适合：**
- 启停定时任务、反射任务、后台前端服务。
- 检查哪些任务正在运行。
- 不想手动找脚本路径和启动命令。

**注意：**
- 涉及后台进程；停止服务时要确认不是你仍需要的任务。
- 桌面版 bridge 默认会把 `frontends/desktop_pet_v2.pyw` 作为额外服务自动启动；设置 `GA_DESKTOP_PET_MODE=3d` 时改为自启 `frontends/desktop_pet_3d.pyw`；如需关闭桌宠自启，设置 `GA_DESKTOP_PET_AUTOSTART=0`。
- 手动启动可用 `ga pet` 启动 2D 桌宠，或用 `ga pet3d` 启动 3D 桌宠。

---

### `/rewind [N]`

回退最近 N 轮对话上下文。无参数时打开菜单，展示可回退轮次预览；带数字时直接回退。

**用法：**

```text
/rewind
/rewind 1
/rewind 3
```

**最适合：**
- Agent 被错误指令带偏。
- 想删除最近几轮错误上下文后重新问。
- 想避免错误信息继续污染上下文。

**注意：**
- 这是上下文层面的撤回，不等同于自动撤销文件系统改动。
- 如果刚才已经改了文件，需要另行让 Agent 检查/回滚文件差异。

---

### `/continue`

列出并恢复历史会话快照。TUI 会读取历史会话，选择后重放对话到 scrollback 并恢复 workspace。

**最适合：**
- 继续之前没完成的任务。
- 找回上下文和工作目录。
- 重启前端后恢复现场。

---

### `/resume`

核心 Agent 会把 `/resume` 转换为一个提示：读取 `model_responses/` 目录最近 10 个日志，从每个文件里提取最后的 `<history>...</history>`，总结每个会话供用户选择。

**最适合：**
- 不确定要恢复哪个会话。
- 想先看最近会话摘要。
- `/continue` 的列表不够语义化时。

**与 `/continue` 的区别：**
- `/continue` 是前端恢复功能，偏“直接恢复”。
- `/resume` 是让 Agent 分析日志并总结，偏“帮我挑哪个会话”。

---

### `/new [会话名]`

开启新会话，清空当前上下文；如果带参数，会设置新会话名。

**用法：**

```text
/new
/new 命令文档编写
```

**最适合：**
- 开始一个完全无关的新任务。
- 当前上下文太乱或太长。
- 想用会话名区分任务。

---

### `/rename <名称>`

重命名当前会话，并更新终端标题。

**用法：**

```text
/rename 修复导出命令
```

**最适合：**
- 任务主题变了。
- 想让历史记录更容易识别。

---

### `/workspace <绝对路径>`、`/workspace off`

设置或关闭当前工作目录/项目模式。

**用法：**

```text
/workspace D:\\navy_code\\GenericAgent
/workspace /home/me/project
/workspace off
```

**最适合：**
- 要让 Agent 在某个项目根目录内工作。
- 多项目切换前明确 cwd。
- 希望恢复会话时同时恢复工作目录。

**建议：**
- 使用绝对路径，避免相对路径歧义。

---

### `/clear`

当前 TUI 实现中会调用 `_reset_session(ag)`，并显示 cleared。也就是说它不只是视觉清屏，而是会重置当前会话/上下文。

**最适合：**
- 想彻底清空当前对话上下文。
- 当前上下文污染严重，且不需要保留。

**注意：**
- 如果你只是想隐藏屏幕内容但保留上下文，需谨慎使用；当前实现语义更接近“重置会话”。

---

### `/cost`

显示当前会话 token 使用统计。对于 mixin/多后端模型，会聚合多个 tracker。

**最适合：**
- 长任务中检查成本。
- 比较不同模型/任务的 token 消耗。
- 判断是否需要新开会话降低上下文成本。

---

### `/verbose`、`/tools`、`/trace`

查看工具调用审计/详细轨迹。

**最适合：**
- 想知道 Agent 到底执行了哪些工具调用。
- 排查为什么任务失败。
- 审计文件读写、脚本执行、网页操作等物理行为。

---

### `/export`

导出最后一次助手回复或当前完整日志。

**用法：**

```text
/export
/export clip
/export copy
/export file result.md
/export all
/export result.md
```

**行为：**
- `/export`：打开导出菜单。
- `/export clip` 或 `/export copy`：复制最后助手回复到剪贴板。
- `/export file <name>`：导出最后助手回复到 temp 文件。
- `/export all`：输出当前完整日志路径。
- `/export <name>`：兼容旧用法，按文件名导出最后回复。

**最适合：**
- 保存长回答、方案、报告。
- 把结果复制到外部文档。
- 需要完整会话日志路径时。

---

### `/stop`、`/abort`

中止当前正在运行的主任务。如果当前空闲，会提示没有任务。

**最适合：**
- Agent 明显跑偏。
- 工具调用卡住或耗时过长。
- 你想修改需求后重新提交。

**注意：**
- 中止不保证撤销已经完成的外部副作用，例如已写入的文件、已启动的进程。

---

### `/language [语言]`

查看或切换界面语言。无参数通常进入选择/处理逻辑，带参数可直接切换，具体支持值取决于实现。

**用法示例：**

```text
/language
/language zh
/language en
```

**最适合：**
- 中英文界面切换。
- 需要让命令说明、提示语言与使用习惯一致。

---

### `/emoji [style|off]`

选择或关闭 TUI spinner pet face。无参数打开选择器；带 style 直接切换；`off` 隐藏。

**用法：**

```text
/emoji
/emoji off
```

**最适合：**
- 个性化界面。
- 录屏/严肃场景中关闭动画。

---

### `/quit`、`/exit`、`/q`

退出 TUI。核心 agent 队列逻辑也识别 `/exit` 作为退出信号。

**最适合：**
- 当前任务结束，关闭前端。

---

### `/session.<属性>=<值>`

底层调试命令。`agentmain.py` 会把它解析为：设置当前 `llmclient.backend` 上的某个 session 属性。值会尝试按 JSON 解析；如果 `temp/<值>` 是文件，还会读取该文件内容作为值。

**用法示例：**

```text
/session.temperature=0.2
/session.max_tokens=4096
/session.some_flag=true
```

**最适合：**
- 调试 LLM backend session 参数。
- 临时修改模型行为。
- 开发者验证后端属性。

**注意：**
- 这是危险/底层命令，属性名错误或值不合适可能导致后续请求异常。
- 普通用户通常不需要使用。

---

## 4. 推荐工作流

### 4.1 普通单轮问题

直接输入问题，不需要 slash 命令。

```text
帮我解释这个错误日志
```

### 4.2 中等复杂任务

使用 `/goal`，让 Agent 先规划再推进。

```text
/goal 分析当前测试失败原因，给出修复方案并实现最小修复
```

### 4.3 长程自主任务

使用 `/autorun`，并写清边界。

```text
/autorun 全面检查命令系统文档。要求：只新增/修改文档，不改代码；最后说明文件路径和覆盖范围。
```

### 4.4 多模块并行调研

聊天里可以使用 `/hive` 或 `/conductor`：

```text
/hive 并行分析 TUI、聊天前端、Agent核心三处命令处理，并汇总差异
```

如果是在开发/脚本层面直接启动 subagent，优先选择这次新增的 `--func` 纯函数模式：

```bash
python agentmain.py --func temp/map_job_001.txt --llm_no 1 --nobg
```

推荐模式：

1. 主 Agent 准备多个独立输入文件。
2. 每个输入文件启动一个 `--func` 子任务。
3. 等待对应的 `*.out.txt` 出现。
4. 主 Agent 汇总所有输出。

只有需要多轮追问、持续协作或人工介入时，再使用 `--task`。

注意：并行 subagent 可共享文件系统，但不能共享键鼠；浏览器任务也应避免共用同一个 tab。

### 4.5 桌面端与 GUI 操作注意事项

这次上游更新还同步了两个非 slash 命令层面的使用提示：

- Tauri 桌面端默认启动不再最大化，窗口配置从 `maximized: true` 改为 `maximized: false`。
- GUI 自动化前必须先 `import ljqCtrl`，之后统一使用物理坐标；涉及 OCR/控件识别时，优先使用 `ui_detect`，因为它已经附带 OCR 能力，不要无必要地单独再跑 OCR。

这类内容主要影响 Agent 自己执行桌面操作、窗口截图、物理坐标点击和视觉识别时的 SOP，不改变聊天框 slash 命令语法。

### 4.6 任务跑偏后的恢复

推荐顺序：

1. `/stop` 停止当前任务。
2. `/verbose` 查看做过什么。
3. `/rewind 1` 或 `/rewind` 清理错误上下文。
4. 如果涉及文件，要求 Agent 检查 git diff 或文件差异。
5. 重新提交更清晰的任务。

### 4.7 会话太乱或上下文过长

- 如果还要保留历史：先 `/export all` 或 `/continue` 确认可恢复。
- 然后 `/new 新任务名`。

---

## 5. 命令选择口诀

- **问状态**：`/status`
- **换模型**：`/llm`
- **停任务**：`/stop`
- **旁路问**：`/btw`
- **撤上下文**：`/rewind`
- **新任务**：`/new`
- **续历史**：`/continue` 或 `/resume`
- **导结果**：`/export`
- **看成本**：`/cost`
- **看工具**：`/verbose`
- **自驱干活**：`/autorun`
- **目标推进**：`/goal`
- **多工协作**：`/hive` / `/conductor`
- **吞噬项目**：`/morphling`
- **更新仓库**：`/update`
- **后台任务**：`/scheduler`
