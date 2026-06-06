# GenericAgent 全能力激活指南

生成日期：2026-06-06

本文基于当前仓库结构、`memory/` 下的 SOP/工具脚本、安装文档、`pyproject.toml`、`agentmain.py`、`ga.py`、`llmcore.py`、`frontends/` 与 `reflect/` 入口整理。目标不是把所有依赖一次性塞进环境，而是让 GenericAgent 的核心先可运行，再按任务激活对应能力，并把成功经验沉淀为可复用记忆。

重要结论：GenericAgent 的“全部能力”不是一个固定安装包，而是“核心 9 类原子工具 + 分层记忆 + SOP + 按需自举环境”。`pyproject.toml` 和安装文档都明确倾向于先安装最小核心，缺什么再由 Agent 读取 SOP、安装依赖、验证、沉淀。

## 1. 当前项目能力图谱

| 能力域 | 入口/文件 | 激活方式 |
|---|---|---|
| 核心 Agent 循环 | `agentmain.py`、`agent_loop.py`、`ga.py` | 配好 `mykey.py` 后运行 `python agentmain.py` |
| LLM 后端 | `llmcore.py`、`mykey_template.py`、`assets/configure_mykey.py` | 配置 native Claude/native OAI/mixin |
| 原子工具 | `assets/tools_schema*.json`、`ga.py` | 启动 Agent 后自动挂载 |
| 分层记忆 | `memory/global_mem_insight.txt`、`memory/global_mem.txt`、`memory/*_sop.md` | 系统提示注入 L1；任务中按 SOP 读 L2/L3 |
| 前端 | `frontends/tui_v3.py`、`frontends/tuiapp_v2.py`、`launch.pyw`、`frontends/desktop_bridge.py` | 安装 UI extras 后按入口启动 |
| Web 自动化 | `TMWebDriver.py`、`assets/tmwd_cdp_bridge/`、`memory/web_setup_sop.md`、`memory/tmwebdriver_sop.md` | 安装浏览器扩展并验证 `web_scan`/`web_execute_js` |
| 桌面/视觉 | `memory/computer_use.md`、`memory/ljqCtrl.py`、`memory/ocr_utils.py`、`memory/ui_detect.py`、`memory/vision_sop.md` | 按窗口枚举 -> UIA/OCR -> vision 顺序激活 |
| Android/远程设备 | `memory/adb_ui.py`、`memory/adb_magisk_sop.md`、`memory/chroot_ssh_tailscale_sop.md`、`memory/cockpit_sop.md` | 安装 ADB/连接设备/root 后按 SOP 执行 |
| 子代理/并行 | `memory/subagent.md`、`agentmain.py --task`、`reflect/agent_team_worker.py` | 文件 IO 协议启动独立 Agent |
| 规划/验证/评审 | `memory/plan_sop.md`、`memory/verify_sop.md`、`memory/review_sop.md` | 复杂任务先计划；完成前独立验证；代码改动可 `/review` |
| 自主/目标/蜂群 | `reflect/autonomous.py`、`reflect/goal_mode.py`、`memory/goal_hive_sop.md` | 通过 TUI slash 命令或 `--reflect` 后台启动 |
| 定时任务 | `reflect/scheduler.py`、`memory/scheduled_task_sop.md`、`sche_tasks/*.json` | 启动 scheduler reflect 服务 |
| 能力吸收 | `memory/skill_search/`、`memory/morphling_sop.md` | 检索外部 skill，或 Morphling 吞噬外部项目 |
| 观测插件 | `plugins/hooks.py`、`plugins/langfuse_tracing.py` | `mykey.py` 配置 `langfuse_config` 后自动加载 |

### 1.1 memory 目录覆盖索引

| 文件/目录 | 归类 | 用途 |
|---|---|---|
| `global_mem_insight.txt` | L1 记忆 | 每轮注入的极简能力索引和高 ROI 规则 |
| `global_mem.txt` | L2 记忆 | 环境事实、固定端口、设备路径、长期配置 |
| `memory_management_sop.md` | L0 记忆治理 | 决定信息写入 L1/L2/L3/L4 的规则 |
| `memory_cleanup_sop.md` | 记忆治理 | 压缩 L1、清理冗余指针 |
| `file_access_stats.json` | 记忆访问统计 | `ga.py` 读取 memory 时记录访问频次，用于判断 SOP 热度 |
| `plan_sop.md` | 高可靠执行 | 复杂任务的探索、计划、执行和验证门 |
| `verify_sop.md` | 高可靠执行 | 独立验证规则，要求实际运行和工具证据 |
| `review_sop.md`、`review_sop/` | 代码审查 | `/review` 的只读对抗评审协议和内联 prompt |
| `code_review_principles.md` | 代码审查 | review finding 必须映射的代码质量原则 |
| `checklist_sop.md`、`checklist_helper.py` | 并行协作 | Checklist/MapReduce 模式的 master-worker 状态管理 |
| `subagent.md` | 并行协作 | `agentmain.py --task` 文件 IO 协议、监察和 Map 模式 |
| `supervisor_sop.md` | 并行协作 | 只读监察者模式，用 `_intervene` / `_keyinfo` 纠偏工作 Agent |
| `goal_mode_sop.md` | 长程目标 | 预算驱动的持续自驱模式 |
| `goal_hive_sop.md`、`goal_hive_master_duty.md` | 长程目标 | 多 worker 蜂群协作与 master 职责 |
| `autonomous_operation_sop.md`、`autonomous_operation_sop/` | 自主运行 | 用户离开后的低副作用自主探索、报告、待办管理 |
| `scheduled_task_sop.md` | 定时任务 | `sche_tasks/*.json` 定时触发与报告约定 |
| `morphling_sop.md` | 能力吸收 | 项目级能力吞噬：目标、测例、组件行为选择 |
| `skill_search/` | 能力吸收 | 105K skill 卡语义检索，成功执行后再沉淀 |
| `github_contribution_sop.md` | 开源贡献 | Fork、分支、测试、PR、CI、review 跟进流程 |
| `web_setup_sop.md` | Web 初始化 | 安装并验证 `tmwd_cdp_bridge` 扩展 |
| `tmwebdriver_sop.md` | Web 自动化 | CDP 桥、真实浏览器、cookie、iframe、文件上传、Vue 组件坑点 |
| `vue3_component_sop.md` | Web 自动化 | 直接操作 Vue3 vnode/proxy、表单和富文本编辑器 |
| `computer_use.md` | 桌面自动化 | GUI 操作顺序：窗口枚举、UIA、OCR、vision、键鼠 |
| `ljqCtrl.py`、`ljqCtrl_sop.md`、`ljqCtrl_cases.md` | Windows GUI | 物理坐标、窗口截图、键鼠、OCR 状态案例 |
| `ocr_utils.py` | 本地视觉 | RapidOCR 窗口/区域 OCR |
| `ui_detect.py` | 本地视觉 | YOLO + OCR 的 UI 元素检测 |
| `vision_sop.md`、`vision_api.template.py` | 远程视觉模型 | 复制模板后接 Claude/OAI/ModelScope vision |
| `adb_ui.py` | Android | dump/解析 Android UI，优先 uiautomator2，fallback 原生 ADB |
| `adb_magisk_sop.md` | Android root | ADB + Magisk + chroot-distro 的路径、push、su 引号规则 |
| `chroot_ssh_tailscale_sop.md` | Android 远程服务 | chroot Ubuntu、sshd、Tailscale serve 访问 |
| `cockpit_sop.md` | Android 远程服务 | chroot Cockpit/supervisor 持久化 |
| `incubator_sop.md` | 远程 GA 节点 | 自我复制到远端节点，按 subagent/reflect 通信 |
| `procmem_scanner.py`、`procmem_scanner_sop.md` | 进程分析 | Windows 进程内存特征扫描和 LLM 友好上下文 |
| `keychain.py` | 本地秘密管理 | 简易本地 keychain，`SecretStr.use()` 使用原文但不要打印 |
| `L4_raw_sessions/` | 历史记忆 | 会话压缩与历史重点挖掘 |

## 2. 最小可用安装

### 2.1 推荐环境

- Python：3.11 或 3.12。不要使用 Python 3.14。
- Git：推荐安装，用于升级和自我进化。
- LLM API Key：至少一个 OpenAI 兼容接口或 Anthropic Claude 原生接口。
- Windows 用户：TUI 推荐 Git Bash 或支持 Unicode 的现代终端。

### 2.2 开发者安装

```bash
git clone https://github.com/lsdefine/GenericAgent.git
cd GenericAgent
uv venv
uv pip install -e ".[ui]"
python assets/configure_mykey.py
```

如果不使用 `uv`：

```bash
python -m venv .venv
python -m pip install -e ".[ui]"
python assets/configure_mykey.py
```

### 2.3 核心验证

```bash
python -c "import agent_loop; print('OK')"
python -c "import agentmain; print('AGENTMAIN OK')"
python -m ga_cli list
git rev-parse --short HEAD
```

启动最轻量 REPL：

```bash
python agentmain.py
```

启动终端界面：

```bash
python frontends/tui_v3.py
# 或
python frontends/tuiapp_v2.py
```

启动 Web/桌面壳：

```bash
python launch.pyw
```

## 3. LLM 配置策略

`agentmain.py` 会扫描 `mykey.py` / `mykey.json` 中变量名包含 `api`、`config`、`cookie` 的配置；`llmcore.py` 根据变量名决定 Session 类型。

推荐顺序：

1. 优先使用 `native_claude_config` 或 `native_oai_config`，让工具调用走 API 原生 tool/function 字段。
2. 多模型时使用 `mixin_config` 做故障转移。
3. 旧式 `claude_config` / `oai_config` 文本协议保留兼容，但不作为新配置首选。
4. 配置后在 TUI 中可用 `/llm` 或 `/session.xxx=value` 切换模型和运行时参数。

关键规则：

- 不要读取或输出真实 API Key。
- 不要把示例 Key 当真。
- `fake_cc_system_prompt=True` 只用于 CC switch/反代类 Claude Code 透传渠道；官方 Anthropic 通常不需要。
- `apibase` 支持自动补全 `/v1/chat/completions` 或 `/v1/responses`，具体规则见 `mykey_template.py`。

## 4. 依赖安装分层

### 4.1 必装核心

`pyproject.toml` 当前核心依赖：

```bash
python -m pip install requests beautifulsoup4 bottle simple-websocket-server aiohttp psutil
```

通常直接执行：

```bash
python -m pip install -e .
```

### 4.2 常用 UI

```bash
python -m pip install -e ".[ui]"
```

包含：

- `streamlit`
- `pywebview`
- `textual`
- `prompt_toolkit`
- `rich`
- `pillow`

### 4.3 IM 前端

```bash
python -m pip install -e ".[all-frontends]"
```

包含 Telegram、QQ、飞书、企业微信、钉钉等常见依赖。具体平台仍需要在 `mykey.py` 中配置对应 token/app secret/allowlist。

### 4.4 可选专项依赖矩阵

不要默认安装整张表。按任务触发，读对应 SOP 后再安装和验证。

| 能力 | 相关文件 | 可能依赖 | 验证 |
|---|---|---|---|
| Qt GUI | `frontends/qtapp.py` | `PySide6`、`markdown` | `python frontends/qtapp.py` |
| Tauri 桌面前端 | `frontends/desktop/` | Node.js、Rust、`@tauri-apps/cli` | `cd frontends/desktop && npm install && npx tauri dev` |
| Conductor | `frontends/conductor.py` | `fastapi`、`uvicorn`、`pydantic` | `python frontends/conductor.py` |
| Discord | `frontends/dcapp.py` | `discord.py` | 配置 token 后启动 |
| 微信个人 Bot | `frontends/wechatapp.py` | `requests`、`qrcode`、`pycryptodome`、`pillow` | 扫码登录并发测试消息 |
| 飞书 | `frontends/fsapp.py`、`docs/SETUP_FEISHU.md` | `lark-oapi` | `python frontends/fsapp.py` |
| Langfuse | `plugins/langfuse_tracing.py` | `langfuse` | `mykey.py` 配 `langfuse_config` 后观察 trace |
| OCR | `memory/ocr_utils.py` | `rapidocr-onnxruntime`、`pillow`、`numpy` | 对窗口局部截图运行 OCR |
| UI 检测 | `memory/ui_detect.py` | `ultralytics`、`rapidocr-onnxruntime`、`pillow`、`numpy` | `from ui_detect import detect` |
| Windows 键鼠/截图 | `memory/ljqCtrl.py` | `pywin32`、`numpy`、`opencv-python`、`pillow`、可选 `windows-capture` | 枚举窗口、激活、截图、点击后验证像素变化 |
| Vision API | `memory/vision_sop.md`、`memory/vision_api.template.py` | `requests`、`pillow`、可用视觉模型配置或 ModelScope token | 复制模板为 `memory/vision_api.py` 后调用 `ask_vision` |
| Android UI | `memory/adb_ui.py` | Android platform-tools、可选 `uiautomator2` | `adb devices`，dump UI |
| 进程内存扫描 | `memory/procmem_scanner.py` | `yara-python`，Windows 进程读取权限 | 指定 PID 和 pattern 扫描 |

如果确实要准备一个“实验室式全量开发环境”，可以在虚拟环境中集中安装：

```bash
python -m pip install -e ".[ui,all-frontends]"
python -m pip install PySide6 markdown fastapi uvicorn pydantic discord.py langfuse
python -m pip install rapidocr-onnxruntime ultralytics numpy opencv-python pywin32 windows-capture pyperclip uiautomator2 yara-python
```

注意：上面命令跨平台不一定全部成功，`pywin32`、`windows-capture`、进程内存扫描等是 Windows 偏向能力；`uiautomator2` 需要 Android 设备和 ADB；`ultralytics` 可能下载模型文件。

### 4.5 SOP 环境准备总表

这张表按 `memory/` 当前 SOP 归纳“要跑起来还缺什么”。标准流程是：先读 SOP，再检查环境，再装最小依赖，再跑验证。

| SOP/能力 | 前置环境 | 安装/准备 | 最小验证 |
|---|---|---|---|
| `memory_management_sop.md`、`memory_cleanup_sop.md` | Git 工作区、可 patch 文件 | 无额外依赖 | `file_read` L1/L2/L3，确认只做局部修改 |
| `plan_sop.md`、`verify_sop.md`、`review_sop.md` | 核心 Agent、文件读写、命令执行 | 无额外依赖；代码 review 需要 Git 仓库 | `git status --short`、读取目标 diff、验证命令实际运行 |
| `checklist_sop.md`、`subagent.md`、`supervisor_sop.md` | 可后台启动 Python 子进程 | 核心依赖即可，Windows 确认可隐藏窗口启动 | `python agentmain.py --task test --input "..."` 产生 `temp/test/output.txt` |
| `goal_mode_sop.md` | `reflect/goal_mode.py`、可写 `temp/goal_state.json` | 无额外依赖 | `python agentmain.py --reflect reflect/goal_mode.py` 能读取 state |
| `goal_hive_sop.md`、`goal_hive_master_duty.md` | 本地 HTTP 端口、BBS、requests | 核心 `requests` 已包含；选空闲端口和 board key | `assets/agent_bbs.py` 启动后可访问 `/readme?key=...` |
| `scheduled_task_sop.md` | 可写 `sche_tasks/`、后台 reflect | 无额外依赖 | `python agentmain.py --reflect reflect/scheduler.py`，日志写入 `sche_tasks/scheduler.log` |
| `autonomous_operation_sop.md` | 可写 `temp/autonomous_reports/` | 无额外依赖 | helper 能读取 history/todo，报告能移动到 reports |
| `github_contribution_sop.md` | Git、GitHub 账号、可选 GitHub CLI | 安装 `git` 和 `gh`，登录 `gh auth login` | `git remote -v`、`gh auth status`、项目测试命令通过 |
| `skill_search/SKILL.md` | 网络访问技能搜索 API | 零 Python 依赖；可配 `SKILL_SEARCH_API` / `SKILL_SEARCH_KEY` | `python -m skill_search "python testing" --top 3` |
| `morphling_sop.md` | Git/下载目标项目、测试运行环境 | 按目标项目语言安装依赖；大型任务用 Goal Hive | 能提取目标 tests/benchmark 并跑通最小测例 |
| `web_setup_sop.md`、`tmwebdriver_sop.md` | Chrome/Edge、扩展管理权限 | 加载 `assets/tmwd_cdp_bridge/`；核心依赖含 `bottle` 和 WS server | `web_scan(tabs_only=True)`、`web_execute_js` 返回 `document.title` |
| `vue3_component_sop.md` | 已可控制目标网页 | 无额外依赖 | 在 Vue3 页检测 `__vue_app__` 或 vnode，并用 native setter/组件方法改无风险字段 |
| `computer_use.md`、`ljqCtrl_sop.md` | Windows 桌面、有目标窗口 | `pip install pywin32 pillow numpy opencv-python pyperclip` | 枚举窗口、激活窗口、局部截图尺寸正确 |
| `ocr_utils.py` | 可截图窗口/区域 | `pip install rapidocr-onnxruntime pillow numpy` | 对局部截图 OCR，返回文字和 bbox |
| `ui_detect.py` | 本地图像、可下载/加载 YOLO 模型 | `pip install ultralytics rapidocr-onnxruntime pillow numpy` | `detect(PIL.Image)` 返回元素列表 |
| `vision_sop.md` | 可用视觉模型或 ModelScope token | 复制 `vision_api.template.py` 为 `vision_api.py`，配置变量名或 token | `ask_vision(局部截图)` 返回非 Error |
| `adb_ui.py` | Android 设备、USB/WiFi 调试 | 安装 platform-tools；可选 `pip install uiautomator2` | `adb devices`、dump UI XML 成功 |
| `adb_magisk_sop.md` | 已 root 的 Android + Magisk | ADB、root 授权；脚本 LF 行尾 | `adb shell su -c id` 返回 root，push 两步法可验证文件大小 |
| `chroot_ssh_tailscale_sop.md` | Android + Magisk + chroot Ubuntu + Tailscale | chroot 内装 `openssh-server`、Tailscale；配置 2222 端口 | `ssh -tt -p 2222 root@...` 可执行非交互命令 |
| `cockpit_sop.md` | chroot Ubuntu、supervisor、开放 9090 | chroot 内 `apt install cockpit cockpit-ws supervisor` | `curl http://localhost:9090/` 返回 200，`supervisorctl status` RUNNING |
| `incubator_sop.md` | 远程节点 Python 环境、可复制 GA 文件 | `requests beautifulsoup4`，复制核心 py/assets/memory/mykey | 远端 `python agentmain.py --task ...` 能产出 output |
| `procmem_scanner_sop.md` | Windows 目标进程读取权限 | `pip install yara-python` | `python memory/procmem_scanner.py <PID> "pattern" --mode string` |
| `keychain.py` | 本机用户目录可写 | 无额外依赖；仅弱加密本地保存 | `keys.set("name", file="path"); keys.ls()`，禁止打印 raw |
| `L4_raw_sessions/salient_mining_sop.md` | `temp/model_responses/` 有历史日志 | 无额外依赖 | `compress_session.batch_process(..., dry_run=True)` 能列出候选 |

## 5. 记忆系统如何激活和沉淀

GenericAgent 的长期能力来自 `memory/`，不是来自一次性大 prompt。当前结构：

```text
L1: memory/global_mem_insight.txt     极简索引层
L2: memory/global_mem.txt             全局事实库
L3: memory/*.md / *.py                SOP 与工具脚本
L4: memory/L4_raw_sessions/           历史会话压缩与重点挖掘
```

### 5.1 记忆写入铁律

来自 `memory/memory_management_sop.md` 的核心规则：

1. No Execution, No Memory。只有经过工具调用验证成功的信息才可写入。
2. 不写易变状态，如当前 PID、临时 session、一次性时间戳。
3. L1 只写存在性指针，不写教程细节。
4. L2 写环境事实，如非标路径、固定端口、设备特殊配置。
5. L3 写专项 SOP 或工具脚本，必须短、可复用、包含关键坑。
6. 修改 `memory` 要局部 patch，避免 overwrite 造成持久性损伤。

### 5.2 用户如何触发记忆沉淀

可以直接对 Agent 说：

```text
把这个记到你的记忆里：<已经验证成功的事实或流程>
```

更好的说法：

```text
刚才这个任务已经验证成功。请按 memory_management_sop 判断应写入 L1/L2/L3 的内容，只记录长期有效、行动验证过的信息。
```

长任务完成后，Agent 应调用 `start_long_term_update`。这个工具会提示它读取 `memory/memory_management_sop.md`，再决定是否更新：

- 环境事实 -> `memory/global_mem.txt`，必要时同步 L1 指针。
- 复杂经验 -> 新建或 patch `memory/*_sop.md`。
- 高复用复杂逻辑 -> `memory/*.py` 工具脚本。
- 无长期价值 -> 不写。

### 5.3 记忆整理

`memory/memory_cleanup_sop.md` 定义了 L1 的“存在性编码”原则。整理时只保留能触发检索的最短指针，不保留翻译、普通描述、实现细节。

适用命令：

```text
请读取 memory_cleanup_sop.md，整理 global_mem_insight.txt，只做词级别最小 patch，保持 L1 不超过 30 行。
```

### 5.4 L4 历史会话

`reflect/scheduler.py` 中有 L4 cron：启动 scheduler 后大约每 12 小时会尝试调用 `memory/L4_raw_sessions/compress_session.py` 归档 `temp/model_responses/`。`memory/L4_raw_sessions/salient_mining_sop.md` 用于从历史会话中挖掘重点。

## 6. SOP 如何被发现、执行和转化为能力

### 6.1 SOP-first

`memory/global_mem_insight.txt` 已把高频 SOP 映射到触发词。Agent 执行复杂任务时应先读 L1，再读具体 SOP，不凭印象执行。

典型提示：

```text
这是一个多步骤任务。请先读 global_mem_insight.txt 匹配 SOP，再读相关 SOP，更新 working checkpoint 后执行。
```

### 6.2 工作记忆

工具 `update_working_checkpoint` 用于短期任务便签，适合保存：

- 用户原始需求。
- 已匹配 SOP。
- 关键路径和约束。
- 当前进度。
- 下一步计划。

不适合保存：

- 任务已完成后的长期经验。
- 显而易见的上下文。
- 临时变量和一次性状态。

### 6.3 复杂任务启用 Plan Mode

当任务超过 3 步、有多文件协同、依赖关系或条件分支时，按 `memory/plan_sop.md`：

1. 创建 `plan_XXX/` 工作目录。
2. 先探索环境并形成 `exploration_findings.md`。
3. 写 `plan.md`，每步有完成判据和 SOP 标注。
4. 用户确认后执行。
5. 执行完成后必须启动独立验证 subagent。

当前 SOP 中提到的 `inline_eval=True` 已在当前工具 schema 中标注为禁用；实际使用时应以当前代码/工具约束为准。如果内联进入 plan 模式不可用，就使用普通文件计划和 `plan_sop.md` 的执行协议。

### 6.4 Review 和 Verify

- `/review` 或“code review”触发 `memory/review_sop.md`，只读评审，不改代码，重点输出 P0-P3 findings。
- `memory/verify_sop.md` 要求“能跑必须跑”，配置/文档也要完整读取和格式检查。

复杂任务完成前的最低门槛：

```text
请按 verify_sop.md 独立验证本次交付物。每项 PASS 必须有工具调用证据，最后输出 VERDICT: PASS/FAIL/PARTIAL。
```

## 7. 能力吸收流程

GenericAgent 的能力吸收有三条路径。

### 7.1 从一次任务沉淀 SOP

流程：

1. 完成真实任务。
2. 验证结果可用。
3. 判断失败点是否未来仍有价值。
4. 写入 L3 SOP 或工具脚本。
5. 必要时把 SOP 文件名写入 L1 作为存在性指针。

SOP 应包含：

- 触发场景。
- 最短可执行步骤。
- 已验证的关键坑。
- 验证方式。
- 不该做什么。

SOP 不应包含：

- 大段过程日志。
- 未验证猜测。
- 通用常识。
- 只对当前会话有效的状态。

### 7.2 从 Skill Search 吸收外部技能

`memory/skill_search/SKILL.md` 提供 105K 技能卡检索。要求英文查询。

```python
import sys
sys.path.append('../memory/skill_search')
from skill_search import search

results = search("python send email", top_k=10)
for r in results:
    print(r.final_score, r.skill.name, r.skill.key)
```

CLI：

```bash
cd memory/skill_search
python -m skill_search "docker deployment" --top 5
```

吸收规则：

1. 先搜索，不直接信结果。
2. 选一个 skill 后，在当前项目/任务中实际执行。
3. 执行成功并验证后，提炼成本项目 SOP。
4. 若只是一次性任务，不沉淀。

### 7.3 Morphling 吞噬外部项目

`memory/morphling_sop.md` 定义 Morphling：给定外部项目，抽取目标和测例，按组件决定调用、重写或舍弃。

适合：

- 吞噬一个 GitHub 项目的核心能力。
- 把外部工具封装进 GenericAgent。
- 重写一个更小、更可测的替代版本。

最低完成标准：

- 有目标。
- 有测例或构造的最小测例。
- 每个核心组件都有调用/重写/舍弃理由。
- 在同一测试上对比目标与新产物。

大型 Morphling 任务建议通过 Goal Hive 执行。

## 8. Web 能力激活

Web 能力由 `web_scan`、`web_execute_js`、`TMWebDriver.py` 和 Chrome 扩展 `assets/tmwd_cdp_bridge/` 组成，不是 Selenium/Playwright。它控制真实浏览器，可保留登录态。

### 8.1 初次设置

```text
执行 web_setup_sop，解锁 web 工具。
```

按 `memory/web_setup_sop.md`：

1. 打开 Chrome/Edge 扩展管理页。
2. 开启开发者模式。
3. 加载 `assets/tmwd_cdp_bridge/` 未打包扩展。
4. 打开一个普通网页，不要用 `about:blank`。
5. 调用 `web_scan` 验证标签页可见。

### 8.2 验证

让 Agent 执行：

```text
请打开一个普通网页，用 web_scan 列出 tabs_only，再用 web_execute_js 返回 document.title。
```

`web_scan` 显示“没有可用标签页”时，不要直接重装扩展。按 `tmwebdriver_sop.md` 排查：

1. 浏览器是否运行，是否有普通网页。
2. `TMWebDriver` master 是否在 18765/18766 附近端口运行。
3. 扩展是否安装在当前浏览器。
4. 仍失败再请求用户协助。

### 8.3 使用顺序

- 普通页面读取：`web_scan`。
- 页面操作：优先 `web_execute_js`。
- JS 事件被 `isTrusted=false` 拦截：用 CDP 桥。
- Vue3 自定义组件：先读 `memory/vue3_component_sop.md`，优先直接操作 Vue 组件实例。
- 文件上传：优先 DataTransfer API，必要时 CDP 或物理点击。
- 跨域 iframe：按 `tmwebdriver_sop.md` 的 CDP isolated world 方法处理。

## 9. 桌面、OCR 和视觉能力激活

### 9.1 操作顺序

来自 `memory/computer_use.md`：

1. 先枚举窗口，确认标题、类名、rect、前台状态。
2. UIA 可用时优先 UIA。
3. UIA 不可用时用 `ui_detect.py`。
4. `ui_detect` 不足时用本地 OCR。
5. OCR 不足时才用 vision。
6. 禁止全屏截图；优先窗口局部截图。
7. Windows 键鼠使用 `memory/ljqCtrl.py`，禁止 pyautogui。

### 9.2 Windows GUI 基础依赖

```bash
python -m pip install pywin32 pillow numpy opencv-python pyperclip
```

可选后台截图：

```bash
python -m pip install windows-capture
```

验证：

```text
请读取 computer_use.md 和 ljqCtrl_sop.md，枚举当前窗口，选择一个无风险窗口截图，输出窗口标题、客户区大小和截图尺寸。不要点击。
```

### 9.3 OCR

```bash
python -m pip install rapidocr-onnxruntime pillow numpy
```

验证：

```text
请用 ocr_utils.py 对一个窗口局部截图做 OCR，报告识别到的文字和 bbox，不要全屏截图。
```

### 9.4 UI 检测

```bash
python -m pip install ultralytics rapidocr-onnxruntime pillow numpy
```

验证：

```text
请读取 ui_detect.py，对一个窗口截图运行 detect，列出元素 bbox。只探测不操作。
```

### 9.5 Vision API

按 `memory/vision_sop.md`：

1. 复制 `memory/vision_api.template.py` 为 `memory/vision_api.py`。
2. 只看 `mykey.py` 的配置变量名，禁止输出 apikey 值。
3. 填 `CLAUDE_CONFIG_KEY` / `OPENAI_CONFIG_KEY` 或 ModelScope token。
4. 先窗口截图，再调用 `ask_vision`。

验证提示：

```text
请按 vision_sop.md 配置 vision_api.py。只截取目标窗口局部，不要全屏截图。测试 ask_vision 能否描述这张局部图。
```

## 10. Android 和远程设备能力激活

### 10.1 ADB

Windows 可用 winget 安装 platform-tools：

```powershell
winget install Google.PlatformTools
adb devices
```

如果 PATH 未刷新，`memory/adb_magisk_sop.md` 记录了 winget 默认路径，可直接调用其中的 `adb.exe`。

可选：

```bash
python -m pip install uiautomator2
```

验证：

```text
请读取 adb_ui.py 和 adb_magisk_sop.md，检查 adb devices，然后只 dump UI，不点击、不输入、不改设备。
```

### 10.2 Magisk/root 场景

按 `memory/adb_magisk_sop.md`：

- 受保护目录用两步法：先 push 到 `/data/local/tmp`，再 `su -c mv`。
- `subprocess.run` 用列表参数，禁止 `shell=True` 嵌套引号。
- 复杂脚本先 push 到设备，再 `su -c "/system/bin/sh /data/local/tmp/x.sh 2>&1"`。
- `service.d` 脚本必须 LF 行尾和 755 权限。

### 10.3 chroot、Tailscale、Cockpit

这些能力对应本机 L2 中的手机服务事实和以下 SOP：

- `memory/chroot_ssh_tailscale_sop.md`
- `memory/cockpit_sop.md`
- `memory/adb_magisk_sop.md`

它们是高风险专项能力，只有在用户明确授权并确认设备属于自己时使用。验证要包含端口监听、服务状态、日志和连接测试。

## 11. 前端与远程入口

### 11.1 本地前端

```bash
python agentmain.py
python frontends/tui_v3.py
python frontends/tuiapp_v2.py
python launch.pyw
python frontends/stapp2.py
python frontends/qtapp.py
python hub.pyw
```

也可使用 CLI 分发：

```bash
python -m ga_cli list
python -m ga_cli configure
python -m ga_cli cli
python -m ga_cli tui2
python -m ga_cli web
python -m ga_cli launch
python -m ga_cli pet
```

### 11.2 IM Bot

可配置平台见 `mykey_template.py` 和 `assets/configure_mykey.py`：

- Telegram：`frontends/tgapp.py`
- QQ：`frontends/qqapp.py`
- 飞书：`frontends/fsapp.py`、`docs/SETUP_FEISHU.md`
- 企业微信：`frontends/wecomapp.py`
- 钉钉：`frontends/dingtalkapp.py`
- 微信个人 Bot：`frontends/wechatapp.py`
- Discord：`frontends/dcapp.py`

安全要求：

1. 必须配置 allowlist，不建议留空允许所有用户。
2. 远程消息等价于给本机 Agent 下指令。
3. 浏览器、文件、ADB、键鼠、支付、公司系统相关操作必须二次确认。
4. 不要把 IM token 写入公开仓库。

## 12. 自主、目标、蜂群和定时任务

### 12.1 Slash 命令

`frontends/slash_cmds.py` 中的高阶命令会注入普通 Agent 任务，并要求先读 SOP：

| 命令 | SOP/入口 |
|---|---|
| `/autorun` | `memory/autonomous_operation_sop.md` |
| `/morphling` | `memory/morphling_sop.md` |
| `/goal` | `memory/goal_mode_sop.md` |
| `/hive` | `memory/goal_hive_sop.md` |
| `/conductor` | `frontends/conductor.py` |
| `/scheduler` | `reflect/*.py` 与 `sche_tasks/*.json` 服务管理 |

### 12.2 Subagent

`memory/subagent.md` 定义文件 IO 协议：

```bash
python agentmain.py --task task_name --input "目标和约束"
```

通信目录：

```text
temp/task_name/input.txt
temp/task_name/output.txt
temp/task_name/reply.txt
temp/task_name/_stop
temp/task_name/_keyinfo
temp/task_name/_intervene
```

用途：

- 独立上下文做验证。
- MapReduce 处理多个同构输入。
- 观察 Agent 真实行为来改进 SOP。

### 12.3 Goal Mode

`reflect/goal_mode.py` 通过 `temp/goal_state.json` 驱动持续推进。

```json
{
  "objective": "用户原话目标",
  "budget_seconds": 10800,
  "start_time": 0,
  "turns_used": 0,
  "max_turns": 200,
  "status": "running",
  "done_prompt": ""
}
```

启动示例：

```bash
python agentmain.py --reflect reflect/goal_mode.py
```

Windows 后台启动可参考 `goal_mode_sop.md` 中的 `start /b` 示例。

### 12.4 Goal Hive

`memory/goal_hive_sop.md` 用 BBS + hive master + workers 推进大型开放目标。

最低要素：

1. 启动 `assets/agent_bbs.py`。
2. 创建第一帖，包含目标和 Hive Master 职责。
3. 启动 worker：`reflect/agent_team_worker.py`。
4. 启动 Goal master：`reflect/goal_mode.py`。
5. 时间预算耗尽后收口，关闭 worker。

### 12.5 定时任务

创建 `sche_tasks/*.json`：

```json
{
  "schedule": "08:00",
  "repeat": "daily",
  "enabled": true,
  "prompt": "要执行的任务",
  "max_delay_hours": 6
}
```

启动 scheduler：

```bash
python agentmain.py --reflect reflect/scheduler.py
```

执行报告写入 `sche_tasks/done/`，日志写入 `sche_tasks/scheduler.log`。

## 13. 安全边界

GenericAgent 的优势是强执行，风险也来自强执行。激活全部能力时必须保留边界。

默认低风险：

- 只读文件和目录。
- 当前工作区内创建临时实验文件。
- 读取 SOP。
- 本地无副作用验证。

需要确认：

- 安装软件或全局依赖。
- 修改 `memory/`、`global_mem*`、核心代码。
- 覆盖、删除、移动非临时文件。
- 浏览器真实账号中的提交、付款、审批、发消息、上传下载。
- ADB 操作手机、root、Magisk、chroot、远程端口暴露。
- 启动长期后台任务、IM bot、远程服务。

禁止或强烈不建议：

- 读取和输出 API Key、cookie、密码。
- 无条件 kill Python 进程。
- 在未知窗口盲目点击。
- 直接按 vision 坐标点击。
- 全屏截图。
- 不读 SOP 凭印象执行专项能力。
- 未验证就写入长期记忆。

## 14. 一条完整激活路线

### 阶段 1：核心跑通

```bash
uv venv
uv pip install -e ".[ui]"
python assets/configure_mykey.py
python -c "import agent_loop; print('OK')"
python agentmain.py
```

对 Agent 说：

```text
请读取 README、docs/GETTING_STARTED.md 和 global_mem_insight.txt，确认你当前能使用哪些核心工具。不要安装额外依赖。
```

### 阶段 2：前端可用

```bash
python frontends/tui_v3.py
```

验证 `/llm`、`/help`、`/review`、`/scheduler` 等命令是否出现。

### 阶段 3：记忆体系可用

对 Agent 说：

```text
请读取 memory_management_sop.md，解释当前 L1/L2/L3/L4 分层，并检查 global_mem_insight.txt 是否能导航到 plan_sop、tmwebdriver_sop、computer_use、vision_sop、subagent。
```

### 阶段 4：Web 可用

```text
执行 web_setup_sop，解锁 web 工具。完成后用 web_scan tabs_only 和 web_execute_js document.title 验证。
```

### 阶段 5：桌面视觉可用

```text
请读取 computer_use.md、ljqCtrl_sop.md、vision_sop.md。先只做窗口枚举和局部截图，再配置 OCR。禁止全屏截图，禁止点击。
```

### 阶段 6：高级工作流可用

```text
这是一个复杂任务。请按 plan_sop.md 规划，完成后按 verify_sop.md 启动独立验证。
```

代码改动后：

```text
/review
```

### 阶段 7：按需扩展专项能力

按实际任务触发：

- 手机 App：读 `adb_ui.py`、`adb_magisk_sop.md`。
- 外部项目能力吸收：读 `morphling_sop.md`，必要时 Goal Hive。
- 长期优化：读 `goal_mode_sop.md`。
- 定时巡检：读 `scheduled_task_sop.md`。
- IM 远程入口：读 `mykey_template.py` 和对应 `frontends/*app.py`。

## 15. 面向 Agent 的总提示词模板

可以把下面这段发给已启动的 GenericAgent：

```text
请激活你当前项目的能力，但不要一次性安装所有依赖。

执行顺序：
1. 读取 README.md、docs/GETTING_STARTED.md、docs/installation_zh.md、pyproject.toml。
2. 读取 memory/global_mem_insight.txt 和 memory/memory_management_sop.md，建立当前能力索引。
3. 检查核心环境：Python 版本、pip/uv、git、mykey.py 是否存在且可 import。不要打印任何密钥值。
4. 验证核心：import agent_loop，启动或说明一个可用前端。
5. 生成一份能力状态表：已可用、需安装依赖、需用户授权、暂不适合启用。
6. 对每个待启用能力，先读取对应 SOP，再安装最小依赖并运行验证命令。
7. 所有成功配置且长期有效的信息，按 memory_management_sop 最小化写入 L2/L3；必要时仅把存在性指针写入 L1。
8. 遇到高风险操作、密钥、真实账号、手机 root、删除覆盖、后台长期任务时先 ask_user。
```

## 16. 完成判据

一台机器上的 GenericAgent 可以认为“全能力路线已激活”，不是指所有依赖都已安装，而是满足：

1. 核心 Agent 能运行并调用工具。
2. 至少一个 LLM native 或 mixin 配置可用。
3. 至少一个前端可用。
4. `memory/global_mem_insight.txt` 能导航到关键 SOP。
5. Agent 能按 `memory_management_sop.md` 正确沉淀记忆。
6. 复杂任务能使用 Plan/Verify/Review。
7. Web、桌面视觉、ADB、IM、Goal/Hive、Scheduler 等专项能力都有明确 SOP、依赖、验证步骤和安全边界。
8. 未启用的专项能力不是“缺失”，而是处于按需激活状态。

这样才符合 GenericAgent 的设计：不要预加载所有技能，而是在真实任务中自举、验证、沉淀、复用。
