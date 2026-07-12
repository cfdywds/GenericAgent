"""GA privacy plugin — bootstrap for llm-privacy-guard.

这是 llm-privacy-guard 进入 GA 仓库的唯一文件（新增文件，upstream 无同名，
merge 零冲突）。删除本文件 = 完全卸载，GA 行为回归原生。

防护内容（详见 D:/navy_code/llm-privacy-guard/README.md）：
  L1  file_read 源头门：凭证类文件 block（不可授权）、受保护目录 ask（经
      ask_user 征求用户同意，注入无法伪造授权）
  L2  工具结果 DLP：code_run/web_* 等所有工具输出中的凭证自动 [REDACTED]
  L3  出口兜底：发送给 LLM 前对 messages / HTTP payload 做增量扫描

可选配置：在本地 mykey.py 中添加 privacy_config = {...}（见 README），
不配置时使用安全默认。诚实声明：本插件只覆盖确定性类别（密钥/卡号/身份证
等）；人名地址类自由文本 PII 不在覆盖范围（需外挂 NER 代理）。
"""
import os
import sys

_GA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from plugins import hooks
    from privacy_guard.integrations.generic_agent import install

    install(hooks, ga_root=_GA_ROOT)
except ImportError as e:
    sys.stderr.write(
        f"[privacy_guard] NOT ACTIVE — engine not installed ({e}).\n"
        f"[privacy_guard] fix: pip install -e D:/navy_code/llm-privacy-guard\n")
