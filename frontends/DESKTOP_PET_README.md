# Desktop Pet Skin System

## 快速开始

运行桌面宠物：

```bash
python frontends/desktop_pet_v2.pyw
```

默认皮肤是 `ameath`。如需指定皮肤，可设置环境变量：

```bash
set GA_DESKTOP_PET_SKIN=ameath
python frontends/desktop_pet_v2.pyw
```

HTTP 控制端口：`41983`。

## 功能特性

### 1. 多皮肤支持

- 自动发现 `frontends/skins/` 目录下的所有皮肤
- 右键菜单切换皮肤
- 支持 sprite sheet 皮肤格式

### 2. 多动画状态

基础状态：

- `idle` - 待机
- `walk` - 行走
- `run` - 跑步
- `sprint` - 冲刺

Ameath 额外支持 GA 语义动作：

- `thinking` - LLM 思考/生成
- `search` - 网络搜索，宠物拿放大镜查电脑
- `browse` - 浏览网页
- `code` - 运行代码
- `read` - 读取文件/资料
- `write` - 写入或 patch 文件
- `memory` - 更新工作记忆/长期记忆
- `ask` - 等待用户确认
- `fix` - 恢复或修复
- `success` - 工具成功
- `error` - 工具失败
- `done` - 任务完成
- `cancelled` - 任务取消

这些动作在 `frontends/skins/ameath/action_*.png` 中以独立精灵表保存，`skin.json` 中作为一等动画状态注册。Ameath 的语义动作主要通过角色本体姿势表达，例如侧身搜索、面向屏幕浏览、敲小终端、翻读资料、写板组织语言；状态文字会以头顶气泡显示，默认保留约 8 秒；气泡样式优先使用 `frontends/chat_bubble.png`，避免回到贴牌式状态图标或大号覆盖层。

### 3. 交互功能

- 单击拖动宠物
- 双击关闭程序
- 右键打开菜单切换皮肤

### 4. HTTP 远程控制

```bash
# 切换语义动作
curl "http://127.0.0.1:41983/?action=search&msg=正在搜索"

# 旧接口：切换基础动画状态
curl "http://127.0.0.1:41983/?state=run"
```

`msg` 参数和 POST 消息会显示为头顶气泡；人物动作仍由 `action` 或 `state` 控制。可用 `GA_DESKTOP_PET_TOAST_SECONDS` 调整气泡显示秒数。

## 与 GA 集成

`plugins/desktop_pet_status.py` 会随 `agentmain.py` 的插件发现机制自动加载。它监听 GA 的 hook：

- `llm_before` -> `thinking`
- `tool_before` -> 按工具名映射动作
- `tool_after` -> `success` / `error`，如下一轮继续则回到 `thinking`
- `agent_after` -> `done` / `ask` / `cancelled` / `error`，随后回到 `idle`

默认启用。可用环境变量关闭：

```bash
set GA_DESKTOP_PET_STATUS=0
```

桌面版 bridge 默认会把 `frontends/desktop_pet_v2.pyw` 作为 extra service 自动启动。

可用环境变量关闭自启：

```bash
set GA_DESKTOP_PET_AUTOSTART=0
```

## 工具到动作映射

| GA 工具 | 宠物动作 |
| --- | --- |
| `web_search` | `search` |
| `web_scan`, `web_execute_js` | `browse` |
| `code_run` | `code` |
| `file_read` | `read` |
| `file_write`, `file_patch` | `write` |
| `ask_user` | `ask` |
| `update_working_checkpoint`, `start_long_term_update` | `memory` |
| `restore_quarantine` | `fix` |

## 添加新皮肤

皮肤目录结构：

```text
frontends/skins/your-skin-name/
├── skin.json
├── skin.png
└── action_search.png
```

`skin.json` 动画项示例：

```json
{
  "animations": {
    "search": {
      "file": "action_search.png",
      "loop": true,
      "sprite": {
        "frameWidth": 164,
        "frameHeight": 198,
        "frameCount": 8,
        "columns": 8,
        "fps": 10,
        "startFrame": 0
      }
    }
  }
}
```

## 故障排查

### 皮肤不显示

1. 检查 `skin.json` 格式是否正确。
2. 确认图片文件存在。
3. 检查 sprite 配置参数是否匹配图片尺寸。

### GA 没有驱动宠物动作

1. 确认桌宠监听 `http://127.0.0.1:41983/`。
2. 确认未设置 `GA_DESKTOP_PET_STATUS=0`。
3. 检查 `plugins/desktop_pet_status.py` 是否可被 `agentmain.py` 插件发现机制导入。

### 桌面版不想自启宠物

设置：

```bash
set GA_DESKTOP_PET_AUTOSTART=0
```
