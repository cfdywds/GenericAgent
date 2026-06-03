# GenericAgent 项目功能说明与改造计划

> 生成日期：2026-06-03  
> 分析范围：后端运行时、LLM 适配、工具系统、前端交互、记忆/SOP、长期任务、工程质量与安全治理  
> 参考文档：`.claude/plan/project-analysis-and-refactor.md`

## 1. 项目定位

GenericAgent 是一个本地自主 Agent 运行时，不是单一前端项目。核心能力是把 LLM、工具调用、本地文件和命令、浏览器控制、长期记忆、多前端接入组合成一个可持续执行任务的系统。

README 中强调的“约 3K 行核心代码”更适合理解为 seed runtime 的设计理念；当前仓库实际已经包含较多外围模块，包括桌面端、TUI、Bot 前端、浏览器桥、记忆/SOP、长期任务、插件和工具脚本。因此后续文档和架构应明确区分：

- **Core runtime**：Agent loop、任务队列、LLM 调用、工具分发。
- **Tool layer**：文件、命令、浏览器、记忆、用户确认等原子工具。
- **Frontend layer**：CLI、TUI、桌面端、Streamlit、IM Bot。
- **Memory and skill layer**：L0-L4 记忆、SOP、Skill、会话归档。
- **Operations layer**：配置、诊断、日志、审计、插件、安装升级。

## 2. 当前架构概览

### 2.1 主要组成

- Agent 核心循环：`agent_loop.py`
- Agent 会话与任务队列：`agentmain.py`
- 工具实现：`ga.py`
- LLM 适配层：`llmcore.py`
- 浏览器控制：`TMWebDriver.py`、`simphtml.py`
- 桌面 HTTP/WebSocket 桥：`frontends/desktop_bridge.py`
- 桌面 Web UI：`frontends/desktop/static/app.js`
- Tauri 桌面壳：`frontends/desktop/src-tauri/src/lib.rs`
- TUI v3：`frontends/tui_v3.py`
- Slash 命令：`frontends/slash_cmds.py`
- 公共聊天逻辑：`frontends/chatapp_common.py`
- 记忆与 SOP：`memory/`
- 反思、定时与 Goal 模式：`reflect/`
- 插件与观测：`plugins/`

### 2.2 分层视图

```text
frontends
  CLI / TUI / Desktop / Streamlit / IM Bots

runtime
  GenericAgent task queue
  agent_runner_loop
  StepOutcome
  handler dispatch

llm
  Native Claude
  Native OpenAI
  OpenAI-compatible
  text tool protocol
  MixinSession failover

tools
  code_run
  file_read / file_write / file_patch
  web_scan / web_execute_js
  ask_user
  working checkpoint
  long-term memory update

memory and long-running modes
  L0-L4 memory
  SOP / Skill
  reflect / scheduler / goal / hive / autonomous
```

### 2.3 典型执行链路

```text
用户输入
  -> 前端适配器
  -> GenericAgent.put_task()
  -> 后台任务队列
  -> agent_runner_loop()
  -> llmclient.chat()
  -> tool call 解析
  -> GenericAgentHandler.do_xxx()
  -> tool result
  -> 下一轮 LLM 或结束输出
```

## 3. 功能说明

### 3.1 Agent 执行引擎

`agent_loop.py` 提供统一循环：

- 构造 system/user 消息。
- 调用 LLM。
- 解析 tool calls。
- 分发给 handler。
- 收集 tool result。
- 根据 `StepOutcome` 决定继续、退出、用户中断或下一轮提示。

关键对象：

- `StepOutcome`：工具执行后的标准结果。
- `BaseHandler.dispatch()`：根据工具名调用 `do_<tool>`。
- `agent_runner_loop()`：主循环入口。

### 3.2 任务队列与会话管理

`agentmain.py` 的 `GenericAgent` 负责：

- 加载模型配置。
- 维护任务队列。
- 管理流式输出。
- 处理 slash 命令。
- 支持 LLM 切换。
- 支持一次性任务模式。
- 支持 reflect 模式。
- 将模型请求和响应写入 `temp/model_responses/`。

每个用户输入会进入 `task_queue`，后台线程从队列取出任务并执行。输出通过 `display_queue` 逐步返回给前端。

### 3.3 LLM 兼容层

`llmcore.py` 支持多种模型协议：

- Native Claude。
- Native OpenAI。
- OpenAI-compatible API。
- 旧版文本工具协议。
- MixinSession 多模型故障转移。

主要职责：

- 加载 `mykey.py` 或 `mykey.json`。
- 解析 Claude SSE。
- 解析 OpenAI SSE。
- 解析 JSON 响应。
- 转换 OpenAI/Claude 工具格式。
- 维护 backend history。
- 压缩和裁剪上下文。
- 记录 token usage。
- 处理 prompt cache 标记。

核心会话类：

- `NativeClaudeSession`
- `NativeOAISession`
- `ClaudeSession`
- `LLMSession`
- `ToolClient`
- `NativeToolClient`
- `MixinSession`

### 3.4 工具系统

`ga.py` 实现 9 个原子工具能力：

| 工具 | 功能 | Handler 方法 |
| --- | --- | --- |
| `code_run` | 执行 Python、PowerShell、bash 等代码或命令 | `do_code_run` |
| `file_read` | 读取文件，支持行号、关键字定位和截断 | `do_file_read` |
| `file_write` | 写入、覆盖、追加或前置写入文件 | `do_file_write` |
| `file_patch` | 基于唯一旧文本块进行局部替换 | `do_file_patch` |
| `web_scan` | 扫描当前浏览器页面内容和标签页 | `do_web_scan` |
| `web_execute_js` | 在浏览器中执行 JavaScript | `do_web_execute_js` |
| `ask_user` | 请求用户确认或输入 | `do_ask_user` |
| `update_working_checkpoint` | 更新短期工作记忆 | `do_update_working_checkpoint` |
| `start_long_term_update` | 触发长期记忆沉淀 | `do_start_long_term_update` |

特殊能力：

- `{{file:path:start:end}}` 文件引用展开。
- 文件读取时的路径建议和模糊发现。
- plan mode 下的完成声明拦截。
- 长任务轮次过多时的风险提示。
- 对 memory/SOP 文件读取的额外上下文提示。

### 3.5 浏览器控制

`TMWebDriver.py` 与 `simphtml.py` 组成真实浏览器控制能力：

- 发现浏览器标签页。
- 连接 CDP 会话。
- 简化 HTML。
- 执行 JS。
- 监控页面变化。
- 尽量保留真实浏览器登录态。

这套机制适合处理需要网页登录态、页面交互和开放网页探索的任务。

### 3.6 记忆系统

`memory/` 包含全局记忆、SOP 和能力脚本。`get_global_memory()` 会把 memory insight 注入 system prompt。

当前记忆层可以按 README 中的设计理解：

| 层级 | 名称 | 说明 |
| :---: | --- | --- |
| L0 | Meta Rules | Agent 的基础行为规则和系统约束 |
| L1 | Insight Index | 极简索引层，用于快速路由与召回 |
| L2 | Global Facts | 长期运行积累的稳定知识 |
| L3 | Task Skills / SOPs | 完成特定任务类型的可复用流程 |
| L4 | Session Archive | 从已完成任务中提炼的归档记录 |

相关能力脚本包括：

- ADB UI 控制：`memory/adb_ui.py`
- OCR：`memory/ocr_utils.py`
- UI 检测：`memory/ui_detect.py`
- 视觉 API 模板：`memory/vision_api.template.py`
- 进程内存扫描：`memory/procmem_scanner.py`
- 技能搜索：`memory/skill_search/`
- L4 会话压缩：`memory/L4_raw_sessions/compress_session.py`

### 3.7 多前端生态

项目提供多种前端：

| 前端类型 | 入口文件 | 特性 |
| --- | --- | --- |
| CLI | `agentmain.py` | 直接命令行对话与一次性任务 |
| TUI v2 | `frontends/tuiapp_v2.py` | Textual 前端 |
| TUI v3 | `frontends/tui_v3.py` | prompt_toolkit + rich，scrollback-first |
| Streamlit | `launch.pyw`、`frontends/stapp*.py` | Web UI |
| 桌面 GUI | `frontends/desktop/` | Tauri + Python bridge + Web UI |
| Telegram | `frontends/tgapp.py` | Telegram Bot |
| 微信 | `frontends/wechatapp.py` | 微信 Bot |
| QQ | `frontends/qqapp.py` | QQ Bot |
| 飞书/Lark | `frontends/fsapp.py` | 飞书 Bot |
| 企业微信 | `frontends/wecomapp.py` | 企业微信 Bot |
| 钉钉 | `frontends/dingtalkapp.py` | 钉钉 Bot |

公共聊天逻辑集中在 `frontends/chatapp_common.py`，包含：

- `/help`
- `/status`
- `/stop`
- `/new`
- `/restore`
- `/continue`
- `/btw`
- `/review`
- `/llm`

### 3.8 桌面端

桌面端分为三层：

1. `frontends/desktop/src-tauri/src/lib.rs`：Tauri 壳，负责启动 Python bridge、窗口显示和配置发现。
2. `frontends/desktop_bridge.py`：HTTP API 和 WebSocket 状态通知。
3. `frontends/desktop/static/app.js`：Web UI 渲染和交互。

桌面 bridge 提供：

- `GET /status`
- `GET /config`
- `POST /config`
- `GET /model-profiles`
- `GET /sessions`
- `POST /session/new`
- `GET /session/{sid}`
- `DELETE /session/{sid}`
- `POST /session/{sid}/prompt`
- `GET /session/{sid}/messages`
- `POST /session/{sid}/cancel`
- `POST /path/open`
- `GET /ws`

桌面 Web UI 负责：

- 多 session 管理。
- 消息轮询。
- Markdown 渲染。
- 工具调用折叠。
- LLM Running 分段折叠。
- 图片粘贴预览。
- 搜索。
- 设置弹窗。
- bridge 诊断。
- Stop/Send 状态切换。

### 3.9 TUI v3

`frontends/tui_v3.py` 是一个高度集成的终端 UI。主要功能包括：

- 多语言界面。
- slash 命令面板。
- 多行输入。
- 粘贴图片和文件占位符。
- ask_user 单选和多选。
- 历史恢复。
- LLM 切换。
- token 成本展示。
- scheduler 服务启动和停止。
- 工具调用折叠。
- 原生终端 scrollback。

当前文件非常大，承担了渲染、输入法、命令、状态、会话、picker、导出、成本统计等多类职责，是前端侧最高维护风险区域之一。

### 3.10 Slash 命令与长期任务

`frontends/slash_cmds.py` 负责构造部分 slash 命令的 prompt 或启动服务：

- `/update`
- `/autorun`
- `/morphling`
- `/goal`
- `/hive`
- `/conductor`
- `/scheduler`
- `/resume`

其中 `/scheduler` 会扫描 `reflect/*.py` 和 `frontends/*app*.py`，并能启动或停止服务。

`reflect/` 提供持续任务能力：

- `goal_mode.py`：按预算持续推进目标。
- `scheduler.py`：定时任务调度。
- `autonomous.py`：自主探索。
- `checklist_master.py`：清单驱动任务协调。
- `agent_team_worker.py`：worker 任务。

### 3.11 插件与观测

`plugins/hooks.py` 提供轻量 hook 系统：

- `agent_before`
- `agent_after`
- `turn_before`
- `turn_after`
- `llm_before`
- `llm_after`
- `tool_before`
- `tool_after`

`plugins/langfuse_tracing.py` 是 Langfuse 追踪插件示例，会在存在 `langfuse_config` 时自动启用。

## 4. 当前主要问题

### 4.1 模块边界不清

`ga.py` 同时负责工具实现、路径解析、工作记忆、计划模式、安全拦截和部分运行时提示。`llmcore.py` 同时负责配置、协议、流解析、上下文、日志和多模型 failover。职责混杂导致：

- 难以测试和维护。
- 修改风险高。
- 新人理解成本高。
- 局部 bug 难定位。

### 4.2 核心文件过大

以下文件承担了过多职责：

- `llmcore.py`
- `ga.py`
- `frontends/tui_v3.py`
- `frontends/desktop/static/app.js`

前端侧尤其明显：TUI 输入、渲染、session、slash command、picker、cost tracker、导出逻辑混在一个大文件中；桌面端 renderer 也同时承担状态、渲染、bridge、设置和诊断逻辑。

### 4.3 会话模型不统一

CLI、TUI、桌面端和 IM 前端各自处理：

- 历史恢复。
- 消息展示。
- 工具调用折叠。
- LLM Running 分段。
- slash 命令。
- 任务中断。
- ask_user 候选项。
- 文件产物展示。

这带来重复逻辑，也容易造成不同前端行为不一致。

### 4.4 工具权限边界偏弱

`code_run`、`file_write`、`file_patch`、`web_execute_js` 都是强能力工具，但目前缺少统一的：

- 权限等级。
- 风险分级。
- 可写路径策略。
- 用户确认策略。
- 审计日志。
- 命令白名单或黑名单。
- 敏感路径保护。

风险包括误改系统文件、执行危险命令、泄露敏感文件、浏览器中执行不受控脚本等。

### 4.5 桌面端状态分散

桌面 bridge 有自己的 session 状态，前端也维护 local session、runtime、partial message 和 bridge session 映射。

当前同步方式以 HTTP 轮询为主，WebSocket 只推送轻量状态事件，容易出现：

- partial 状态不同步。
- 前端 busy 状态和后端 status 不一致。
- bridge 重启后 session 映射复杂。
- session 恢复和 UI replay 逻辑重复。

### 4.6 测试覆盖偏窄

当前可见测试主要覆盖：

- LLM session 选择。
- 少量 Node CLI 测试。

核心行为缺少系统测试：

- Agent loop。
- 工具 dispatch。
- 文件工具。
- slash 命令。
- desktop bridge API。
- `/continue` 恢复。
- 取消任务。
- 长期记忆触发。
- 浏览器工具。

### 4.7 配置体验复杂

`mykey_template.py` 信息非常完整，但新用户入口较重。配置发现依赖变量名包含 `api`、`config`、`cookie`、`native`、`claude`、`oai`、`mixin` 等隐式约定，灵活但容易误配。

常见风险：

- 配置项命名不当导致 session 类型不符合预期。
- mixin 引用不存在。
- API 路径不匹配。
- 流式配置不兼容。
- Python 版本或依赖不满足。
- 错误提示滞后到运行时才出现。

### 4.8 性能与上下文管理隐患

当前上下文裁剪主要以字符长度粗估 token。对于不同模型、不同 tokenizer 和不同 cache 策略，这种估算可能偏差较大。

其他隐患：

- `web_scan` 默认可能返回较大的 HTML，截断后可能丢失关键信息。
- 部分 I/O、subprocess、浏览器等待是同步阻塞。
- 多前端共享 agent 时并发模型较弱。
- 缺少统一超时和取消机制。
- model response 日志按文件散落，恢复和检索成本较高。

### 4.9 文档与代码现实存在偏差

README 的“极简核心”表达对核心 seed code 成立，但仓库现实已经包含大量外围模块。文档需要明确：

- 什么属于核心 runtime。
- 什么属于前端扩展。
- 什么属于 memory skills。
- 什么属于桌面/Bot/extensions。

否则新用户和贡献者容易误解项目边界。

## 5. 改造目标与路线选择

### 5.1 总体目标

推荐目标不是一次性大重构，而是把项目逐步收敛成四个稳定边界：

```text
runtime
  Agent loop、session、LLM、tool dispatch

tools
  文件、命令、浏览器、记忆、用户确认等工具

frontends
  TUI、桌面、IM，只消费统一会话 API

ops
  配置、日志、审计、测试、插件、安装升级
```

核心原则：

- 保持现有行为兼容。
- 先加测试护栏，再拆模块。
- 优先统一协议，不急于统一 UI。
- 高风险工具先加策略层。
- 前端只做展示，不重复推断 Agent 内部状态。
- 保留“极简核心”的使用体验，避免把个人 Agent 框架改成重型平台。

### 5.2 三种改造路线

#### 路线 A：保守整理

保持单体结构，先补边界和测试。

优点：

- 改动小，风险低。
- 最符合当前“极简核心”理念。
- 可快速提升稳定性。

缺点：

- 无法根治 `llmcore.py`、TUI 大文件、工具权限混杂的问题。

适合：

- 近期发布。
- 稳定现有用户体验。
- 为后续重构建立测试护栏。

#### 路线 B：模块化重构

拆分 core、tools、llm、memory、frontends，保留兼容入口。

优点：

- 架构边界清晰。
- 便于测试、插件化、安全治理和长期演进。

缺点：

- 改造周期中等。
- 需要兼容现有入口和前端。
- 迁移不慎会破坏用户技能和 SOP。

适合：

- 作为主线改造方案。

#### 路线 C：产品化重构

统一 API Server，多客户端接入。

优点：

- 桌面、TUI、Bot、Web 可共享同一运行时 API。
- 更利于权限控制、任务观测、会话持久化。

缺点：

- 架构变化最大。
- 部署复杂度上升。
- 可能背离“零部署/极简”定位。

适合：

- 当目标从个人 Agent 框架转向稳定产品平台时采用。

### 5.3 推荐路线

推荐采用：**路线 A 起步，逐步过渡到路线 B**。

即先补测试、协议和安全护栏，再按模块边界渐进拆分。路线 C 可以把桌面 bridge 作为局部试点，但不建议在当前阶段把整个项目改造成统一 API Server。

## 6. 分阶段改造计划

### Phase 1：代码质量 Quick Wins

预计周期：2-3 周  
目标：不改变用户可见行为，先提高后续改造安全性。

#### 1.1 核心模块单元测试

优先级：高

建议新增：

- `tests/test_agent_loop.py`
- `tests/test_ga_tools.py`
- `tests/test_continue_cmd.py`
- `tests/test_desktop_bridge.py`

覆盖重点：

- `agent_runner_loop()` 的正常结束、tool call、no_tool、bad_json、max_turns。
- `BaseHandler.dispatch()` 的已知工具、未知工具、多工具调用。
- `file_read` 的行号、关键字、截断、缺失文件提示。
- `file_patch` 的唯一匹配、无匹配、多匹配。
- `expand_file_refs` 的正常展开、越界、缺失文件。
- `/continue` 的 list、search、restore。
- desktop bridge 的 create session、prompt、messages、cancel。

阶段目标：

- 核心路径测试覆盖率达到 60% 以上。
- 能支持后续模块拆分的回归验证。

#### 1.2 代码规范检查

优先级：中

建议：

- 在 `pyproject.toml` 增加最小 `ruff` 配置。
- 先只检查明显错误，不一次性格式化全仓库。
- 增加 `.pre-commit-config.yaml`。
- CI 中先以 warn 或局部路径方式引入，避免大规模历史问题阻断开发。

#### 1.3 异常处理改进

优先级：中

建议：

- 将密集的 `except: pass` 改为明确忽略原因或最小日志。
- 统一异常格式。
- 在关键路径记录上下文：工具名、参数摘要、session id、turn id。

重点文件：

- `ga.py`
- `llmcore.py`
- `agentmain.py`
- `frontends/desktop_bridge.py`

#### 1.4 文档完善

优先级：中

建议：

- 更新 README，明确“约 3K 行核心”的适用范围。
- 新增 `docs/ARCHITECTURE.md`。
- 新增或完善开发者指南。
- 将 core runtime、frontends、memory skills、desktop/bot extensions 分开说明。

### Phase 2：架构优化

预计周期：4-6 周  
目标：拆分大文件，明确边界，便于测试和维护。

#### 2.1 工具模块拆分

优先级：高

建议结构：

```text
tools/
  __init__.py
  files.py
  code.py
  browser.py
  memory.py
  user.py
  registry.py

handler.py
```

职责：

- `tools/files.py`：`file_read`、`file_write`、`file_patch`、`expand_file_refs`。
- `tools/code.py`：`code_run`。
- `tools/browser.py`：`web_scan`、`web_execute_js`。
- `tools/memory.py`：checkpoint、long-term update。
- `tools/user.py`：`ask_user`。
- `tools/registry.py`：工具注册、schema 校验、权限元数据。
- `handler.py`：`GenericAgentHandler` 和公共调度逻辑。

兼容策略：

- `ga.py` 保留向后兼容导入。
- 先移动纯函数，再移动 handler 方法。
- 每移动一个工具同步迁移测试。

#### 2.2 LLM 模块拆分

优先级：高

建议结构：

```text
llm/
  __init__.py
  config.py
  history.py
  usage.py
  tool_protocol.py
  parsers/
    claude_sse.py
    openai_sse.py
    text_tools.py
  sessions/
    base.py
    claude.py
    openai.py
    mixin.py
  clients/
    native_tool.py
    text_tool.py
```

兼容策略：

- `llmcore.py` 保留 facade。
- 原有 `from llmcore import ...` 不立即破坏。
- 配置加载、SSE 解析、history 裁剪优先拆。

#### 2.3 工具注册机制

优先级：中

建议新增 `ToolRegistry`：

- 工具函数注册。
- schema 与 handler 双向校验。
- 工具元数据声明。
- 自动发现缺失 handler 或 schema 漂移。

示例元数据：

```text
ToolSpec
  name
  description
  schema
  risk_level
  requires_confirmation
  allowed_roots
  timeout
  output_limit
  audit_enabled
```

#### 2.4 前端模块瘦身

优先级：高

建议：

- 将 TUI 输入、渲染、picker、session、slash command、export、cost tracker 拆为更小模块。
- 将桌面 `app.js` 拆为 bridge、sessions、renderer、commands、settings、diagnostics、images。
- 扩展 `frontends/chatapp_common.py`，但避免让它成为新的巨型文件。

目标：

- TUI 主入口只保留组合和生命周期。
- 桌面 renderer 不直接推断 Agent 内部状态。
- 前端共享逻辑集中到协议和组件层。

### Phase 3：安全治理

预计周期：2-3 周  
目标：建立统一工具安全策略，保护用户系统安全，增加审计能力。

#### 3.1 执行策略层

优先级：高

建议新增：

```text
security/
  policy.py
  permissions.py
  audit.py
  config.json
```

策略能力：

- 文件根目录限制。
- 敏感路径保护，例如系统目录、凭证文件、`.git` 关键文件。
- 命令白名单或黑名单。
- 超时控制。
- 写入确认。
- 不同模式权限分级。

重点接入：

- `code_run`
- `file_write`
- `file_patch`
- `web_execute_js`
- `path_open`

#### 3.2 审计日志

优先级：中

建议：

- 高风险工具输出 JSON Lines 审计日志。
- 记录 tool name、参数摘要、路径、cwd、session、turn、耗时、exit code、错误类型。
- 日志轮转和归档。

#### 3.3 权限分级

优先级：中

建议区分：

- 普通对话。
- plan mode。
- autonomous mode。
- goal mode。
- scheduler/reflect 长期任务。

不同模式可拥有不同默认权限，高风险动作进入 `ask_user` 或前端确认流。

### Phase 4：性能改进

预计周期：2-3 周  
目标：优化上下文、浏览器扫描、日志恢复和取消机制。

#### 4.1 Token 精确估算

优先级：中

建议：

- 引入 `TokenCounter`。
- 按模型类型选择 tokenizer 或近似策略。
- 替代纯字符长度裁剪。
- 在 `/cost` 和上下文裁剪中使用同一估算层。

#### 4.2 浏览器扫描优化

优先级：中

建议给 `web_scan` 增加模式：

- `tabs`：仅标签页列表。
- `text`：纯文本内容。
- `main_content`：主体内容，默认。
- `raw_debug`：原始 HTML，仅调试使用。

目标：

- 降低 token 消耗。
- 避免截断后丢失关键信息。
- 让模型更明确地选择扫描模式。

#### 4.3 统一超时和取消机制

优先级：中

建议：

- 统一 subprocess、浏览器等待、前端推送的 timeout。
- cancel signal 从 runtime 传到工具层。
- 工具返回结构化取消状态。

#### 4.4 会话日志和恢复优化

优先级：中

建议：

- 将 model response 日志按 session/task 索引。
- 支持快速恢复和检索。
- 将 prompt/response 日志结构化。
- `/continue` 使用索引和缓存，而不是频繁扫描大文件。

### Phase 5：功能增强

预计周期：3-4 周  
目标：增强记忆、Skill、报告和插件能力。

#### 5.1 记忆系统规范化

优先级：中

建议：

- 为 L0-L4 增加文件约定。
- 增加 schema。
- 标准化索引字段。
- 记录更新时间和可信度。
- 提供 validator。

可能新增：

```text
memory/schema.json
memory/validator.py
```

#### 5.2 Skill 调用 API

优先级：中

建议：

- 增加显式 `SkillRegistry`。
- 支持 skill 搜索、匹配、参数绑定。
- 减少纯 prompt 驱动的不确定性。

可能新增：

```text
skills/registry.py
skills/executor.py
```

#### 5.3 任务报告模板

优先级：低

建议报告字段：

- 目标。
- 已执行工具。
- 产物。
- 验证。
- 风险。
- 后续建议。

可能新增：

```text
templates/task_report.md
reporting/generator.py
```

#### 5.4 插件系统增强

优先级：低

建议扩展为声明式插件：

```text
plugins/
  plugin_name/
    plugin.json
    hooks.py
```

manifest 字段：

- name
- version
- description
- hooks
- config_schema
- enabled_by_default

### Phase 6：交互体验优化

预计周期：2-3 周  
目标：统一前端体验，减少重复逻辑。

#### 6.1 统一会话协议

优先级：高

建议定义：

```text
RunEvent
  type: message_delta | tool_call | tool_result | turn_start | turn_end | status | error | done
  session_id
  run_id
  sequence
  payload
  timestamp
```

建议统一对象：

- `SessionState`
- `Message`
- `ToolEvent`
- `RunEvent`
- `RunStatus`

收益：

- TUI 和桌面端不用重复解析 `LLM Running` 文本。
- 工具调用折叠可以由统一事件驱动。
- IM 前端可以更稳定地展示状态。
- bridge 可以从轮询 partial message 逐步升级为事件流。

#### 6.2 交互组件标准化

优先级：中

统一协议对象：

- ask_user 单选/多选。
- 任务进度。
- 工具调用折叠。
- 文件产物展示。
- 错误展示。
- 取消状态。

#### 6.3 桌面 Runtime API 试点

优先级：低

建议：

- 桌面 bridge 作为未来统一 runtime API 的试点。
- HTTP 保留命令型 API。
- WS/SSE 推送完整 `RunEvent`。
- 不在当前阶段强制所有前端迁移到 API Server。

## 7. 优先级与时间规划

### 7.1 优先级矩阵

| 阶段 | 优先级 | 预计耗时 | 依赖 | 影响范围 |
| --- | --- | --- | --- | --- |
| Phase 1：代码质量 Quick Wins | 高 | 2-3 周 | 无 | 全项目 |
| Phase 2：架构优化 | 高 | 4-6 周 | Phase 1 | 核心模块 |
| Phase 3：安全治理 | 高 | 2-3 周 | Phase 1/2 | 工具层 |
| Phase 4：性能改进 | 中 | 2-3 周 | Phase 2 | 全项目 |
| Phase 5：功能增强 | 中 | 3-4 周 | Phase 2/3 | 记忆、Skill、插件 |
| Phase 6：交互体验优化 | 中 | 2-3 周 | Phase 2 | 前端 |

### 7.2 时间线

总周期预计 15-22 周，约 4-6 个月。

```text
Week 1-3:   Phase 1 - 代码质量 Quick Wins
Week 4-9:   Phase 2 - 架构优化
Week 10-12: Phase 3 - 安全治理
Week 13-15: Phase 4 - 性能改进
Week 16-19: Phase 5 - 功能增强
Week 20-22: Phase 6 - 交互体验优化
```

### 7.3 里程碑

- M1：测试覆盖率达到 60% 以上，核心测试可稳定运行。
- M2：工具层和 LLM 层拆分完成，保留兼容入口。
- M3：高风险工具具备安全策略和审计日志。
- M4：Token 估算、浏览器扫描和会话恢复性能改善。
- M5：记忆 schema 和 Skill API 初版可用。
- M6：前端共享统一会话协议，桌面和 TUI 行为显著一致。

## 8. 验证标准

### 8.1 代码质量

- 单元测试覆盖率达到 60% 以上。
- 集成测试覆盖核心流程。
- Lint 检查通过。
- 大文件拆分后职责清晰。
- 关键模块具备开发文档。

### 8.2 架构质量

- 模块职责单一，依赖关系清晰。
- 无明显循环依赖。
- 原有入口保持向后兼容。
- 工具 schema 与 handler 不漂移。
- 插件和前端消费稳定接口。

### 8.3 安全标准

- 高风险工具有权限检查。
- 审计日志可追溯。
- 敏感路径保护生效。
- 取消和超时机制可用。
- 配置验证能提前发现常见错误。

### 8.4 性能指标

- Token 估算比字符裁剪更稳定。
- 浏览器扫描支持低 token 模式。
- `/continue` 不因大日志明显卡顿。
- 任务取消能在合理时间内传递到工具层。
- 桌面端消息同步减少轮询依赖。

### 8.5 用户体验

- CLI/TUI/Desktop/Bot 的基础命令行为一致。
- ask_user、工具折叠、文件产物展示协议统一。
- 桌面端 busy/cancel/partial 状态可靠。
- 新用户配置诊断更清晰。
- 文档明确区分 core runtime 与扩展模块。

## 9. 风险与缓解

### 9.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
| --- | --- | --- | --- |
| 模块拆分破坏兼容性 | 高 | 中 | 保留 facade 和兼容导入，分阶段迁移，先补测试 |
| 安全策略过严影响体验 | 中 | 中 | 支持模式分级、白名单和用户配置 |
| 异步化复杂度过高 | 高 | 高 | 先统一超时和取消，同步优化优先，异步作为长期目标 |
| 前端协议迁移造成展示回归 | 中 | 中 | 桌面端先试点，保留旧文本渲染 fallback |
| Skill/SOP 依赖旧路径 | 高 | 低 | 保持旧入口，提供迁移文档和兼容层 |

### 9.2 资源风险

| 风险 | 影响 | 概率 | 缓解措施 |
| --- | --- | --- | --- |
| 开发时间不足 | 高 | 中 | 优先 Phase 1-3，性能和功能增强可延后 |
| 测试资源不足 | 中 | 中 | 自动化测试优先覆盖核心路径 |
| 社区贡献分散 | 中 | 中 | 用模块边界和 issue 拆分降低协作成本 |

### 9.3 用户影响

| 风险 | 影响 | 概率 | 缓解措施 |
| --- | --- | --- | --- |
| 用户配置格式变化 | 中 | 中 | 保留旧格式支持，提供配置校验和迁移脚本 |
| 前端体验短期不一致 | 中 | 中 | 先统一协议，再逐步迁移 UI |
| 安全确认过多打断任务 | 中 | 中 | 仅高风险动作确认，提供任务模式权限配置 |

## 10. 下一步行动

### 10.1 立即执行

1. 创建或整理 issue，将 Phase 1-6 拆成可跟踪任务。
2. 启动 Phase 1.1：补核心模块单元测试。
3. 明确测试命令和最小 CI。
4. 增加 `docs/ARCHITECTURE.md` 草案，区分 core runtime 与扩展模块。
5. 设计 `RunEvent` 草案，但先不强制迁移所有前端。

### 10.2 短期目标

周期：2-4 周。

目标：

- 完成 Phase 1。
- 核心测试覆盖率达到 60% 以上。
- README 和架构文档修正项目边界。
- 启动工具模块拆分试点。

### 10.3 中期目标

周期：2-3 个月。

目标：

- 完成工具层和 LLM 层初步拆分。
- 高风险工具具备安全策略。
- 桌面 bridge 事件流试点。
- `/continue` 和会话日志恢复优化。

### 10.4 长期目标

周期：4-6 个月。

目标：

- 完成主要模块化改造。
- 建立统一会话协议。
- 完成记忆系统规范化和 Skill API 初版。
- 插件系统具备 manifest、配置和生命周期管理。

## 11. 最小可落地版本

如果只做一个小版本，建议先做五件事：

1. 补 `agent_loop.py`、`ga.py`、`continue_cmd.py`、`desktop_bridge.py` 的核心测试。
2. 定义 `RunEvent` 和 `SessionProtocol` 草案。
3. 给高风险工具增加最小 `ExecutionPolicy` 和审计日志。
4. 将 `web_scan` 增加明确模式，降低 token 消耗。
5. 将 README 和架构文档中的 core 与 extensions 边界写清楚。

这五项收益最大，风险相对可控，并且能为后续后端、前端、交互、安全和插件改造提供基础。

