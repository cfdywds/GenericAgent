# Desktop Pet Skin System

## 快速开始

运行桌面宠物：

```bash
python frontends/desktop_pet_v2.pyw
```

运行 3D 桌面宠物：

```bash
python frontends/desktop_pet_3d.pyw
```

默认皮肤是 `ameath`。如需指定皮肤，可设置环境变量：

```bash
set GA_DESKTOP_PET_SKIN=ameath
python frontends/desktop_pet_v2.pyw
```

HTTP 控制端口：`41983`。

3D 版本使用 `pywebview` 承载本地 Three.js 场景，默认窗口为 `320x420`，仍然兼容同一个 HTTP 控制协议；GA 实时状态会同步到角色动作、状态光环、胸前核心和底部状态条。可用 `GA_DESKTOP_PET_3D_WIDTH` / `GA_DESKTOP_PET_3D_HEIGHT` 调整尺寸。

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

- `thinking` - LLM 思考
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

这些动作在 `frontends/skins/ameath/action_*.png` 中以独立精灵表保存，`skin.json` 中作为一等动画状态注册。Ameath 的语义动作通过角色动作和手边道具交互表达，例如记事板思考、卡片归档、翻书、写板、敲小终端；明确说明仍由气泡消息承载，避免回到贴牌式状态图标或大号文字。

### 3. 交互功能

- 单击拖动宠物
- 双击关闭程序
- 右键打开菜单切换皮肤

### 4. HTTP 远程控制

```bash
# 显示消息
curl "http://127.0.0.1:41983/?msg=Hello"

# 旧接口：切换基础动画状态
curl "http://127.0.0.1:41983/?state=run"

# 新接口：切换语义动作并显示气泡
curl "http://127.0.0.1:41983/?action=search&msg=正在搜索"

# POST 消息
curl -X POST -d "任务完成" http://127.0.0.1:41983/
```

## 与 GA 集成

`plugins/desktop_pet_status.py` 会随 `agentmain.py` 的插件发现机制自动加载。它监听 GA 的 hook：

- `llm_before` -> `thinking`
- `tool_before` -> 按工具名映射动作
- `tool_after` -> `success` / `error`
- `agent_after` -> `done`，随后回到 `idle`

默认启用。可用环境变量关闭：

```bash
set GA_DESKTOP_PET_STATUS=0
```

桌面版 bridge 默认会把 `frontends/desktop_pet_v2.pyw` 作为 extra service 自动启动；如果要自动启动 3D 版本，设置：

```bash
set GA_DESKTOP_PET_MODE=3d
```

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
