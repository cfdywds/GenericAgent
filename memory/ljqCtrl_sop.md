# ljqCtrl 使用与坐标转换 SOP

> 核心原则：`一律使用物理坐标｜禁 pyautogui｜操作前先激活窗口`

## 0. API 快速参考 (Signatures)
- `ljqCtrl.dpi_scale`: float (缩放系数 = 逻辑宽度 / 物理宽度)
- `ljqCtrl.Click(x, y=None)`: 模拟点击。支持 `Click((x, y))` 或 `Click(x, y)`
- `ljqCtrl.Press(cmd, staytime=0)`: 模拟按键。如 `Press('ctrl+c')`
- `ljqCtrl.FindBlock(fn, wrect=None, threshold=0.8)`: 找图。返回 `((center_x, center_y), is_found)`
- `ljqCtrl.GrabWindow(hwnd_or_name)`: 前台截图(先 Activate)，传 hwnd(int) 或窗口标题子串(str)，返回 PIL Image
- `ljqCtrl.GrabWindowBg(hwnd_or_name, timeout=5)`: WGC 后台截图(Win10+)
- `ljqCtrl.MouseDClick(staytime=0.05)`: 鼠标双击

## 1. 环境载入
```python
import ljqCtrl
```

## 2. 坐标规则
- `ljqCtrl.Click/MoveTo` 接收**物理像素坐标**。
- `pygetwindow`、未 DPI aware 的 win32 API 常返回逻辑坐标。
- 换算公式：`物理坐标 = 逻辑坐标 / ljqCtrl.dpi_scale`。
- 截图像素坐标本身就是物理坐标，不要重复换算。

## 3. 截图 bbox 转屏幕物理坐标
```python
# ui_detect 获取的是截图内物理坐标。
# ClientToScreen 拿客户区原点(逻辑)；除 dpi_scale 得物理偏移。
cx, cy = win32gui.ClientToScreen(hwnd, (0, 0))
ox, oy = int(cx / ljqCtrl.dpi_scale), int(cy / ljqCtrl.dpi_scale)
ljqCtrl.Click(ox + (bbox[0] + bbox[2]) // 2, oy + (bbox[1] + bbox[3]) // 2)
```
禁止全屏 ImageGrab；必须针对窗口截图。所有逻辑坐标都要转物理。

## 4. 避坑指南
- **窗口激活**：模拟操作前必须确保窗口已通过 `activate()` 置于前台。
- **客户区原点**：截图内容是客户区；点击截图内元素时，用 `win32gui.ClientToScreen(hwnd, (0, 0))` 取客户区屏幕原点，禁止直接用 `GetWindowRect` 或 `DwmGetWindowAttribute(hwnd, 9, ...)` 的窗口矩形左上角。
- **点击反馈**：`ljqCtrl.Click` 后若像素变化为 0% 或接近 0%，说明可能点歪；立即检查窗口原点、`dpi_scale`、客户区/窗口矩形混用，禁止盲目重试。
- **DPI aware**：未调用 `SetProcessDPIAware()` 时，`GetWindowRect/ClientToScreen/GetClientRect` 通常返回逻辑坐标，必须换算。
- **文本输入**：ljqCtrl 无 TypeText/SendKeys。先点击/三击选中字段，再 `pyperclip.copy(text); ljqCtrl.Press('ctrl+v')`。
- **Java/Swing 截图**：PyCharm/IntelliJ 等可能让 `GrabWindow*` 抓到桌面壁纸；改用 `PrintWindow(PW_RENDERFULLCONTENT=2)`。详见 `memory/ljqCtrl_cases.md#java-swing-printwindow`。
- **OCR 状态监控**：`Working` 可能被识别成 `Wor ing` / `W rking`，用 `re.search(r'Wo.*ing.*esc', text)` 宽松匹配；`Worked for` 表示完成。详见 `memory/ljqCtrl_cases.md#ocr-working-status`。
