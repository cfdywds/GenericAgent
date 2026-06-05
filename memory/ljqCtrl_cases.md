# ljqCtrl 案例库

低频、长代码或环境相关经验放在这里；主 SOP 只保留索引和高频规则。

## Java Swing PrintWindow

**触发条件**：PyCharm、IntelliJ 等 Java Swing 应用使用 `GrabWindow` / `GrabWindowBg` 截图时返回桌面壁纸或空白。

**处理方式**：改用 Windows `PrintWindow`，通常需要 `PW_RENDERFULLCONTENT = 2`。

```python
import ctypes

PW_RENDERFULLCONTENT = 2
hwndDC = user32.GetWindowDC(hwnd)
mfcDC = win32ui.CreateDCFromHandle(hwndDC)
saveDC = mfcDC.CreateCompatibleDC()
saveBitMap = win32ui.CreateBitmap()
saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
saveDC.SelectObject(saveBitMap)
user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), PW_RENDERFULLCONTENT)
# 后续读取位图数据，并释放 DC / bitmap 资源。
```

## OCR Working Status

**触发条件**：OCR 监控任务运行状态时，`Working` 被漏识别或拆字。

**处理方式**：用宽松正则匹配运行态；看到过去式 `Worked for` 时视为完成。

```python
import re

is_working = bool(re.search(r"Wo.*ing.*esc", text))
is_done = "Worked for" in text
```
