# 手机服务器安全检查记录 - 2026-06-11

## 检查范围

通过 ADB 检查的设备：OnePlus 6 / `ONEPLUS A6000`。

本文档记录这台 Android 手机服务器的安全检查结论、整改建议、已执行操作和验证结果。服务器主要运行在 Android 上的 Ubuntu chroot 环境中。

## 当前状态

- Android 版本：10
- Android 安全补丁：2021-07-01
- 局域网 IP：`192.168.2.12`
- 检查时已连续运行：约 5 天
- 检查时电量：75%，温度约 29.9 C
- `/data` 分区使用率：约 9%
- 内存：7.4 GB，总体正常，swap 未使用
- Ubuntu chroot：Ubuntu 24.04.3 LTS
- `cloudflared`：2026.5.2
- OpenSSH：OpenSSH_9.6p1 Ubuntu-3ubuntu13.16
- Python：3.12.3

## 公网和远程暴露面

Cloudflare named tunnel 当前映射：

- `resin.obxunil.eu.cc` -> `http://127.0.0.1:10080`
- `grok.obxunil.eu.cc` -> `http://127.0.0.1:8000`
- `deeix.obxunil.eu.cc` -> `http://127.0.0.1:8080`

此前发现的额外临时 Cloudflare tunnel：

- `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000`

Tailscale Serve 当前在 tailnet 内暴露以下端口：

- `2222`
- `8000`
- `8001`
- `8080`
- `10080`

重点局域网监听端口：

- `2222`：`sshd`
- `8000`：`uvicorn app.main:app`
- `8001`：`/home/cfdywds/mimi3/main.py`
- `8080`：`deeix-chat`
- `10080`：`resin`
- `50708`：`tailscaled`

## 安全发现

高优先级问题：

- SELinux 当前是 `Permissive`。
- 已安装 Magisk root，且 `su` 可用。
- SSH 在 `2222` 端口监听所有网卡。
- SSH 配置允许 `PermitRootLogin yes`。
- SSH 配置允许 `PasswordAuthentication yes`。
- 防火墙默认策略是 `INPUT ACCEPT`。
- 多个公网相关服务通过 supervisor 以 `root` 身份运行。
- 之前存在一个冗余的临时 Cloudflare tunnel，对 `127.0.0.1:8000` 做了额外暴露。

中优先级问题：

- `grok.obxunil.eu.cc/docs` 和 `grok.obxunil.eu.cc/openapi.json` 曾可从公网访问。
- 局域网 `8001/docs` 和 `8001/openapi.json` 曾可访问。
- `8001/api/auth/session` 会暴露认证已开启以及默认用户名为 `admin`。
- 多个服务绑定到 `0.0.0.0`，局域网访问不需要经过 Cloudflare 或 Tailscale。

正向检查结果：

- ADB TCP 未开启：`service.adb.tcp.port=-1`。
- ADB 安全模式已开启：`ro.adb.secure=1`。
- `grok` 的公开 admin 状态接口返回 `401 Unauthorized`。
- `8001` 的局域网系统状态接口返回 `401 Unauthorized`。
- Tailscale 暴露范围是 tailnet only，不是公网 Funnel。

## 建议整改计划

1. 禁用冗余的临时 `cloudflared --url http://127.0.0.1:8000` tunnel，只保留 named tunnel。
2. 在不影响正常 API 的前提下，关闭 FastAPI `/docs` 和 `/openapi.json` 暴露。
3. 在确认密钥登录可用后加固 SSH：
   - 继续保留 `2222` 端口也可以；
   - 设置 `PermitRootLogin no`；
   - 设置 `PasswordAuthentication no`；
   - 保留 `PubkeyAuthentication yes`；
   - 可选：让 SSH 只监听 `127.0.0.1`，通过 Tailscale 或 Cloudflare 访问。
4. 对只准备通过 Cloudflare Tunnel 或 Tailscale Serve 访问的应用服务，把监听地址从 `0.0.0.0` 收敛到 `127.0.0.1`。
5. 在检查文件、日志、数据库、缓存目录权限后，把业务服务从 `root` 迁移到专用普通用户运行。
6. 给 Web UI/API 域名加 Cloudflare Access。
7. 先临时测试 SELinux `Enforcing`，确认服务不受影响后再考虑持久化。

## 执行状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 记录检查结论和建议 | 已完成 | 本文档已创建并改为中文。 |
| 禁用冗余临时 Cloudflare tunnel | 已完成 | supervisor 配置中只剩 `cloudflared-grok2api-named`；一个卡住的诊断用 `cloudflared tunnel list/info` 进程已停止。 |
| 关闭 FastAPI docs/openapi 暴露 | 已完成 | `grok2api` 和 `mimi3` 的 FastAPI app 已设置 `docs_url=None`、`redoc_url=None`、`openapi_url=None`。 |
| 验证 named Cloudflare 域名 | 已完成 | `grok`、`resin`、`deeix` 域名在修改后仍有响应。 |
| 验证 Tailscale Serve 状态 | 已完成 | Tailscale Serve 仍为 tailnet only，覆盖 `2222`、`8000`、`8001`、`8080`、`10080`。 |
| SSH 加固 | 未开始 | 需要先验证密钥登录，避免锁定远程访问。 |
| 服务监听地址收敛 | 未开始 | 建议在确认 Cloudflare/Tailscale 访问路径稳定后执行。 |
| 服务降权运行 | 未开始 | 需要逐个服务做权限审计。 |
| SELinux enforcing 测试 | 未开始 | 建议安排维护窗口执行。 |

## 验证日志

- 修改源码前创建了备份：
  - `/home/cfdywds/grok2api/app/main.py.bak_docs_20260611_005006`
  - `/home/cfdywds/mimi3/mimo2api/web_service.py.bak_docs_20260611_005006`
- 源码改动：
  - `/home/cfdywds/grok2api/app/main.py`：在 `FastAPI(...)` 中加入 `docs_url=None`、`redoc_url=None`、`openapi_url=None`。
  - `/home/cfdywds/mimi3/mimo2api/web_service.py`：在 `FastAPI(...)` 中加入 `docs_url=None`、`redoc_url=None`、`openapi_url=None`。
- 语法检查：
  - `python3 -m py_compile /home/cfdywds/grok2api/app/main.py`：退出码 0。
  - `python3 -m py_compile /home/cfdywds/mimi3/mimo2api/web_service.py`：退出码 0。
- supervisor 重启：
  - `supervisorctl restart gork mimi3`：两个服务均成功停止并启动。
  - `supervisorctl status`：`gork`、`mimi3`、`cloudflared-grok2api-named`、`resin`、`deeix-chat` 均为运行状态。
- Cloudflare tunnel 验证：
  - 当前运行中的 `cloudflared` 命令行为：`/usr/local/bin/cloudflared tunnel --config /etc/cloudflared/grok2api-named.yml --no-autoupdate run`。
  - `grep cloudflared /etc/supervisor/supervisord.conf` 只显示 `cloudflared-grok2api-named`。
  - `grep url /etc/supervisor/supervisord.conf` 只显示 supervisor 的 UNIX socket URL，没有临时 Cloudflare `--url` tunnel。
- FastAPI 文档暴露验证：
  - `GET https://grok.obxunil.eu.cc/docs`：`404 Not Found`。
  - `GET https://grok.obxunil.eu.cc/openapi.json`：`404 Not Found`。
  - `GET http://192.168.2.12:8000/docs`：`404 Not Found`。
  - `GET http://192.168.2.12:8000/openapi.json`：`404 Not Found`。
  - `HEAD http://192.168.2.12:8001/docs`：`404 Not Found`。
  - `HEAD http://192.168.2.12:8001/openapi.json`：`404 Not Found`。
- 服务可用性检查：
  - `GET https://grok.obxunil.eu.cc/admin/api/status`：`401 Unauthorized`，说明服务仍有响应且仍要求鉴权。
  - `HEAD https://resin.obxunil.eu.cc/`：`302 Found`，跳转到 `/ui/`。
  - `HEAD https://deeix.obxunil.eu.cc/`：`200 OK`。
  - `GET http://192.168.2.12:8001/api/auth/session`：`200 OK`。
  - `tailscale serve status`：仍为 tailnet only，不是公网 Funnel。
