# 代码审查报告

**审查日期**: 2026-06-06  
**审查模型**: Codex (后端安全审查)  
**审查范围**: 本地 Git 变更  
**审查员**: 哈雷酱（傲娇大小姐工程师）

---

## 执行摘要

### 审查范围
- **变更文件**: 12 个文件修改
- **代码行数**: +约 200 行 / -约 20 行
- **审查模型**: Codex（Gemini 因缺少 API Key 未能执行）
- **总体评分**: 59/100 (Codex)

### 总体评价
- **代码质量**: 需要改进 (59/100)
- **安全性**: 存在严重漏洞 (2 个 Critical 问题)
- **是否可合并**: ❌ **必须修复 Critical 和 Major 问题后才能合并**

### 主要变更内容
1. 新增文件操作安全策略 (`security/file_policy.py`)
2. 新增隔离区恢复功能 (`restore_quarantine`)
3. Bridge 接口增强 CORS 和 Token 安全控制
4. LLM 日志增加敏感信息脱敏
5. 代码执行安全检查增强（shell/Python）
6. 新增多个安全相关测试用例

---

## 🚨 关键问题 (Critical)

> **必须修复才能合并！这些是安全漏洞。**

### 1. 隔离区恢复机制存在安全漏洞

**文件**: `security/file_policy.py:279`

**问题描述**:  
`restore_quarantine()` 完全信任 `temp/quarantine/manifest.jsonl` 中的路径信息，而该文件可被 agent/tool 写入。攻击者可以：
1. 伪造 manifest 记录
2. 在 `temp/quarantine/` 下放置恶意文件
3. 通过 `restore_quarantine` 将文件恢复到 repo 内任意位置

**风险等级**: Critical

**影响范围**: 可能导致任意文件写入攻击，破坏代码库完整性

**修复建议**:
```python
# 恢复时必须验证完整性！
def restore_quarantine(self, quarantine_id: str):
    # 1. 校验 id、原始路径、隔离路径、sha256、size 与删除时记录一致
    record = self._load_quarantine_record(quarantine_id)
    if not record:
        return {"status": "error", "msg": "quarantine_id not found"}
    
    # 2. 验证文件完整性
    if not self._verify_file_hash(record["quarantine_path"], record["sha256"]):
        return {"status": "error", "msg": "quarantine file integrity check failed"}
    
    # 3. 限制恢复目标必须为原删除路径（不允许修改）
    target = record["original_path"]  # 不从 manifest 读取可变路径
    
    # 4. 检查目标路径是否已存在
    if Path(target).exists():
        return {"status": "error", "msg": "target path already exists"}
    
    # 5. 执行恢复
    shutil.move(record["quarantine_path"], target)
    
    # 6. 更新 manifest（标记为已恢复，不删除记录）
    self._mark_quarantine_restored(quarantine_id)
```

**额外建议**:
- 对 manifest 做追加完整性校验（HMAC 或签名）
- 或将 manifest 放到 agent 无法直接写入的位置（如数据库或加密文件）

---

### 2. Bridge Token 暴露给未鉴权端点

**文件**: `frontends/desktop_bridge.py:516`

**问题描述**:  
`/status` 通过未鉴权的 GET 请求返回 `bridgeToken`。虽然状态变更请求需要 token，但 token 本身由未鉴权 GET 暴露，导致：
- token 更像"公开 bootstrap 值"而不是授权凭据
- 任何能访问本地 bridge 的同源页面都能获取 token
- 被允许 origin 页面可以获取 token
- 本机任意进程都能通过 HTTP 获取 token 并执行 POST/DELETE

**风险等级**: Critical

**影响范围**: 授权机制形同虚设，任何本地进程都能控制 Bridge

**修复建议**:
```python
# 方案 1: 启动时注入 token 到静态页面
# 在启动 bridge 时，动态生成包含 token 的 index.html
def start_bridge():
    token = secrets.token_urlsafe(32)
    with open("static/index.html.template") as f:
        template = f.read()
    with open("static/index.html", "w") as f:
        f.write(template.replace("{{BRIDGE_TOKEN}}", token))
    # 启动服务器...

# 方案 2: 拆分 /status 为 public/private
@routes.get('/status/public')
async def status_public_handler(request):
    return json_ok({
        "ok": True,
        "sessionCount": len(manager.sessions),
        # 不返回 token
    })

@routes.get('/status/private')
async def status_private_handler(request):
    # 需要已有 token 或本地 IPC 校验
    if not _bridge_token_allowed(request):
        return web.Response(status=403, text="Forbidden")
    return json_ok({
        "bridgeToken": manager.bridge_token,
        # 完整信息
    })

# 方案 3: 使用 HttpOnly Cookie
# 首次访问时通过安全渠道（本地文件/命令行）获取初始 token
# 后续通过 cookie 维护会话

# 方案 4: 命令行启动参数
# bridge 启动时打印 token，用户手动复制到前端
# 或通过 IPC（如 stdin）传递给前端进程
```

---

## ⚠️ 主要问题 (Major)

### 3. 代码执行拦截容易被绕过

**文件**: `ga.py:30`

**问题描述**:  
`code_run` 的危险命令拦截依赖正则黑名单，容易绕过：

**PowerShell 绕过示例**:
```powershell
# 使用别名
ri -r docs  # Remove-Item 别名

# 字符串拼接
$cmd = "Remove-" + "Item"; & $cmd -Recurse docs

# Start-Process
Start-Process powershell -ArgumentList "rm -r docs"

# .NET 直接调用
[System.IO.Directory]::Delete("docs", $true)
```

**Python 绕过示例**:
```python
# Path().rename() 可以删除
Path("file.txt").rename("/dev/null")  # Unix
Path("file.txt").rename("NUL")  # Windows

# open 覆盖
open("important.txt", "w").close()

# getattr 动态调用
getattr(shutil, "rmtree")("docs")

# importlib 动态导入
rmtree = importlib.import_module("shutil").rmtree
rmtree("docs")
```

**风险等级**: High

**影响范围**: 黑名单式防御不可靠，无法真正阻止恶意代码执行

**修复建议**:
```
不要把该检查作为安全边界！应该：

1. 代码执行放入真实沙箱
   - Docker 容器
   - VM
   - gVisor/Firecracker
   - Windows Sandbox

2. 受限工作目录
   - chroot/pivot_root (Linux)
   - 临时目录 + 权限限制
   - 文件系统隔离

3. 文件副作用统一通过 FilePolicy 控制
   - 所有文件操作通过工具函数
   - 不直接暴露 Python/Shell 执行

4. 黑名单只作为 UX 预警
   - 提示用户"这个命令看起来很危险"
   - 要求用户二次确认
   - 但不作为唯一安全保障
```

---

### 4. safe_delete 缺少 symlink 和 TOCTOU 防护

**文件**: `security/file_policy.py:124`

**问题描述**:  
对 `temp` 内路径直接 `shutil.rmtree()`/`unlink()`，缺少：
1. symlink/junction/reparse point 检查
2. TOCTOU (Time-of-check to time-of-use) 防护
3. Windows 特殊路径处理

**风险等级**: High

**影响范围**: 可能删除预期外的文件，特别是 symlink 指向的目标

**攻击场景**:
```python
# 攻击者创建 symlink
os.symlink("../../important_file.txt", "temp/malicious_link")

# 调用 safe_delete
policy.safe_delete("temp/malicious_link")

# 如果未检查 symlink，可能删除了 important_file.txt
```

**修复建议**:
```python
def safe_delete(self, path: str, actor: str = "system", reason: str = ""):
    path_obj = Path(path).resolve()
    
    # 1. 使用 lstat 检查（不跟随 symlink）
    try:
        stat_info = path_obj.lstat()
    except FileNotFoundError:
        return {"status": "not_found"}
    
    # 2. 检查是否为 symlink
    if path_obj.is_symlink():
        # 只删除 symlink 本身，不跟随
        path_obj.unlink()
        return {"status": "deleted", "note": "symlink removed"}
    
    # 3. Windows reparse point 检查
    if sys.platform == "win32":
        import win32file
        attrs = win32file.GetFileAttributes(str(path_obj))
        if attrs & win32file.FILE_ATTRIBUTE_REPARSE_POINT:
            # 特殊处理 junction/reparse point
            pass
    
    # 4. 验证 resolved path 和 original path 都在允许根内
    original = Path(path).resolve()
    if not self._inside(original, self.root):
        return {"status": "blocked", "reason": "path outside root"}
    
    # 5. 使用 fd/handle based 删除（更安全）
    # 或先隔离再删除
    if path_obj.is_dir():
        # 先移动到隔离区，再删除
        quarantine_path = self._move_to_quarantine(path_obj)
        shutil.rmtree(quarantine_path)
    else:
        path_obj.unlink()
    
    return {"status": "deleted"}
```

---

### 5. new_session_handler 接受任意 cwd

**文件**: `frontends/desktop_bridge.py:553`

**问题描述**:  
接收任意 `cwd/path` 并传给 agent session，扩大了本地文件访问/执行范围。

**风险等级**: High

**影响范围**: 目录遍历风险，可能访问/修改系统敏感目录

**攻击场景**:
```javascript
// 恶意前端请求
fetch('/session', {
  method: 'POST',
  body: JSON.stringify({
    cwd: 'C:/Windows/System32',  // 危险目录
    // 或
    cwd: '../../../../../../etc',  // 目录遍历
  })
})
```

**修复建议**:
```python
async def new_session_handler(request):
    data = await read_json(request)
    cwd = data.get("cwd", manager.ga_root)
    
    # 1. 解析为绝对路径
    cwd_path = Path(cwd).resolve()
    ga_root_path = Path(manager.ga_root).resolve()
    
    # 2. 检查是否在允许范围内
    try:
        cwd_path.relative_to(ga_root_path)
    except ValueError:
        return json_ok({
            "ok": False,
            "error": f"cwd outside allowed workspace: {cwd}"
        }, status=403)
    
    # 3. 检查目录是否存在
    if not cwd_path.exists() or not cwd_path.is_dir():
        return json_ok({
            "ok": False,
            "error": f"cwd does not exist or is not a directory: {cwd}"
        }, status=400)
    
    # 4. 记录审计事件
    logger.info(f"New session created with cwd={cwd}, origin={request.headers.get('Origin')}")
    
    # 继续创建 session...
```

**额外建议**:
- 考虑维护一个显式的"允许工作区"列表
- 支持多个项目根目录，但需要明确配置
- 记录所有 cwd 变更到审计日志

---

### 6. Query 参数未验证

**文件**: `frontends/desktop_bridge.py:579`

**问题描述**:  
`messages_handler()` 直接 `int()` 解析 query 参数，非数字会抛异常返回 500。

**风险等级**: Medium

**影响范围**: 输入验证不足，错误处理不当

**修复建议**:
```python
async def messages_handler(request):
    try:
        after = int(request.query.get("after", 0))
        limit = int(request.query.get("limit", 100))
        
        # 范围验证
        if after < 0:
            return json_ok({"error": "after must be >= 0"}, status=400)
        
        # 限制 limit 范围，防止过大查询
        limit = min(max(limit, 1), 1000)
        
    except ValueError as e:
        return json_ok({
            "error": "Invalid parameter",
            "detail": str(e)
        }, status=400)
    
    # 继续处理...
```

---

### 7. cleanup_temp 未保护新增目录

**文件**: `cleanup_temp.py:21`

**问题描述**:  
新增的安全相关目录和文件未加入保护列表：
- `temp/quarantine/` - 隔离区文件
- `temp/file_backups/` - 文件备份
- `temp/security_audit.jsonl` - 安全审计日志

这些可能被 cleanup 脚本误删，导致：
- 无法恢复被隔离的文件
- 丢失审计记录
- 无法回滚文件修改

**风险等级**: Medium

**影响范围**: 审计数据和恢复能力丢失

**修复建议**:
```python
PROTECTED_TOP_DIRS = {
    "model_responses",
    "screenshots",
    "browser_data",
    "quarantine",        # 新增：隔离区
    "file_backups",      # 新增：备份目录
}

PROTECTED_FILES = {
    "security_audit.jsonl",  # 新增：安全审计日志
}

def _should_keep(path: Path, protected_dirs: set, protected_files: set) -> bool:
    """检查文件/目录是否应该保留"""
    if path.name in protected_files:
        return True
    
    if path.is_dir() and path.name in protected_dirs:
        return True
    
    return False

# 在清理逻辑中使用
for item in temp_dir.iterdir():
    if _should_keep(item, PROTECTED_TOP_DIRS, PROTECTED_FILES):
        continue
    # 清理逻辑...
```

**测试建议**:
```python
def test_cleanup_preserves_security_dirs():
    """测试 cleanup 保留安全相关目录"""
    create_file("temp/quarantine/test.txt")
    create_file("temp/file_backups/backup.txt")
    create_file("temp/security_audit.jsonl")
    
    cleanup_temp.main()
    
    assert Path("temp/quarantine/test.txt").exists()
    assert Path("temp/file_backups/backup.txt").exists()
    assert Path("temp/security_audit.jsonl").exists()
```

---

## 📝 次要问题 (Minor)

### 8. Secret 文件检测范围偏窄

**文件**: `security/file_policy.py:121`

**问题描述**:  
只按文件名匹配，无法拦截常见敏感文件：
- `.env.local`, `.env.production`
- `*.pem`, `*.key`, `*.crt`
- `id_rsa`, `id_ed25519`
- `credentials.json`, `service-account.json`
- `.ssh/` 目录

**风险等级**: Medium

**修复建议**:
```python
SECRET_PATTERNS = [
    # 环境变量文件
    r"^\.env",           # .env, .env.local, .env.production
    r"\.env$",
    
    # 密钥文件
    r"\.pem$",
    r"\.key$",
    r"\.p12$",
    r"\.pfx$",
    
    # SSH 密钥
    r"^id_rsa",
    r"^id_ed25519",
    r"^id_ecdsa",
    
    # 凭据文件
    r"credentials",
    r"service-account",
    r"auth.*\.json$",
    
    # 配置文件
    r"^\.aws/credentials$",
    r"^\.ssh/",
]

def _is_secret_file(self, path: Path) -> bool:
    """检查是否为敏感文件"""
    path_str = str(path).replace("\\", "/")
    
    for pattern in SECRET_PATTERNS:
        if re.search(pattern, path_str, re.IGNORECASE):
            return True
    
    return False
```

---

### 9. mode 未校验枚举值

**文件**: `ga.py:573`

**问题描述**:  
`file_write` 的 `mode` 参数未在运行时校验，schema 限制不等于运行时保证。未知 mode 会走 `operation=mode`，错误语义不清晰。

**风险等级**: Low

**修复建议**:
```python
def do_file_write(self, args, response):
    mode = args.get("mode", "overwrite")
    
    # 运行时显式校验
    VALID_MODES = {"overwrite", "append", "prepend"}
    if mode not in VALID_MODES:
        yield f"[Status] ❌ 无效的写入模式: {mode}\n"
        return StepOutcome({
            "status": "error",
            "msg": f"Invalid mode '{mode}'. Must be one of: {VALID_MODES}"
        }, next_prompt="\n")
    
    # 继续处理...
```

---

### 10. 日志脱敏规则可能遗漏

**文件**: `llmcore.py:909`

**问题描述**:  
日志脱敏规则覆盖常见 key，但仍可能漏掉：
- 多行 secret
- URL query 中的 token (`?token=xxx&api_key=yyy`)
- JWT (eyJ...)
- GitHub token (ghp_..., gho_...)
- AWS key (AKIA...)
- 其他 API key 格式

**风险等级**: Medium

**修复建议**:
```python
def _redact_sensitive_text(content):
    text = str(content)
    
    patterns = [
        # 现有规则...
        
        # JWT
        (r'\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\b', '[REDACTED_JWT]'),
        
        # GitHub tokens
        (r'\bgh[ps]_[A-Za-z0-9]{36,}\b', '[REDACTED_GITHUB_TOKEN]'),
        (r'\bgho_[A-Za-z0-9]{36,}\b', '[REDACTED_GITHUB_OAUTH]'),
        
        # AWS keys
        (r'\bAKIA[0-9A-Z]{16}\b', '[REDACTED_AWS_KEY]'),
        
        # URL query parameters
        (r'([?&](?:token|api_key|apikey|secret|password|access_token)=)[^&\s]+', r'\1[REDACTED]'),
        
        # 多行 secret (JSON 中的 base64 等)
        (r'("(?:data|content|payload)"\s*:\s*")[^"]{100,}(")', r'\1[REDACTED_LARGE_DATA]\2'),
    ]
    
    for pattern, repl in patterns:
        text = re.sub(pattern, repl, text)
    
    return text
```

**测试建议**:
```python
def test_redact_sensitive_patterns():
    """测试敏感信息脱敏"""
    test_cases = [
        ("JWT: eyJhbGc.eyJzdWI.signature", "JWT: [REDACTED_JWT]"),
        ("token ghp_1234567890abcdefghijklmnopqrstuv", "token [REDACTED_GITHUB_TOKEN]"),
        ("AKIAIOSFODNN7EXAMPLE", "[REDACTED_AWS_KEY]"),
        ("url?api_key=secret123&foo=bar", "url?api_key=[REDACTED]&foo=bar"),
    ]
    
    for input_text, expected in test_cases:
        result = _redact_sensitive_text(input_text)
        assert expected in result
```

---

## 💡 建议改进 (Suggestion)

### 11. restore_quarantine schema 缺少 required

**文件**: `assets/tools_schema.json:39`, `assets/tools_schema_cn.json:39`

**问题描述**:  
schema 未声明 `required: ["quarantine_id"]`，模型可能调用空参数，运行时才报错。

**风险等级**: Low

**修复建议**:
```json
{
  "type": "function",
  "function": {
    "name": "restore_quarantine",
    "description": "Restore a file moved to temp/quarantine by the safety policy. Use the quarantine_id returned by a quarantined delete.",
    "parameters": {
      "type": "object",
      "properties": {
        "quarantine_id": {
          "type": "string",
          "description": "Quarantine id returned by safe delete"
        }
      },
      "required": ["quarantine_id"],
      "additionalProperties": false
    }
  }
}
```

---

### 12. 测试覆盖不足

**文件**: `tests/test_file_policy.py:93`

**问题描述**:  
恢复测试只覆盖正常路径，未覆盖关键安全场景：
- manifest 篡改
- target 已存在
- hash 不匹配
- source symlink/reparse point
- 并发恢复

**风险等级**: Medium

**修复建议**:
```python
def test_restore_quarantine_manifest_tampered():
    """测试 manifest 被篡改时拒绝恢复"""
    policy = FilePolicy(root=ROOT, cwd=ROOT)
    
    # 创建文件并隔离
    test_file = ROOT / "test.txt"
    test_file.write_text("original")
    result = policy.safe_delete(str(test_file))
    qid = result["quarantine_id"]
    
    # 篡改 manifest
    manifest_path = ROOT / "temp/quarantine/manifest.jsonl"
    lines = manifest_path.read_text().splitlines()
    # 修改最后一条记录的路径
    record = json.loads(lines[-1])
    record["original_path"] = str(ROOT / "malicious.txt")  # 改到其他路径
    lines[-1] = json.dumps(record)
    manifest_path.write_text("\n".join(lines) + "\n")
    
    # 尝试恢复应该失败
    result = policy.restore_quarantine(qid)
    assert result["status"] == "error"
    assert "integrity" in result["msg"].lower()

def test_restore_quarantine_target_exists():
    """测试目标路径已存在时拒绝恢复"""
    policy = FilePolicy(root=ROOT, cwd=ROOT)
    
    test_file = ROOT / "test.txt"
    test_file.write_text("original")
    result = policy.safe_delete(str(test_file))
    qid = result["quarantine_id"]
    
    # 重新创建同名文件
    test_file.write_text("new content")
    
    # 恢复应该失败
    result = policy.restore_quarantine(qid)
    assert result["status"] == "error"
    assert "already exists" in result["msg"].lower()

def test_restore_quarantine_hash_mismatch():
    """测试隔离文件被修改时拒绝恢复"""
    policy = FilePolicy(root=ROOT, cwd=ROOT)
    
    test_file = ROOT / "test.txt"
    test_file.write_text("original")
    result = policy.safe_delete(str(test_file))
    qid = result["quarantine_id"]
    
    # 修改隔离区文件
    quarantine_file = Path(result["quarantine_path"])
    quarantine_file.write_text("tampered content")
    
    # 恢复应该失败（hash 不匹配）
    result = policy.restore_quarantine(qid)
    assert result["status"] == "error"
    assert "hash" in result["msg"].lower() or "integrity" in result["msg"].lower()
```

---

## ✨ 优点 (Positive Notes)

虽然存在一些问题，但本次变更在以下方面做得很好：

### 1. 安全架构方向正确
- ✅ **文件操作统一接入 FilePolicy** - 建立了集中的安全控制点
- ✅ **隔离删除而非直接删除** - 提供了恢复能力
- ✅ **备份机制** - 文件修改前自动备份

### 2. Bridge 安全性显著提升
- ✅ **CORS 限制** - 从 `Access-Control-Allow-Origin: *` 改为受限 origin
- ✅ **Token 认证** - 对状态变更方法增加 token 验证
- ✅ **Origin 检查** - 验证请求来源

### 3. 日志安全改进
- ✅ **敏感信息脱敏** - 防止 API key/token 泄露到日志
- ✅ **正则覆盖多种格式** - Bearer token、API key、Cookie 等

### 4. 测试覆盖增加
- ✅ **新增 6 个测试文件** - 测试意识在提升
- ✅ **安全测试用例** - `test_process_safety.py` 增加了多个危险操作检测测试

### 5. 代码执行防护增强
- ✅ **扩展危险模式检测** - 覆盖 PowerShell、Git、find 等更多命令
- ✅ **Python 导入检测** - 识别 shutil、pathlib 等危险模块

---

## 🎯 修复优先级和行动计划

### P0 - 立即修复（阻塞合并）

#### 1. 修复 `restore_quarantine()` 安全漏洞
- [ ] 添加 manifest 完整性验证
- [ ] 限制恢复目标为原路径
- [ ] 验证文件 hash
- [ ] 添加恶意 manifest 测试用例

**预计工作量**: 4-6 小时

#### 2. 修复 `/status` Token 暴露问题
- [ ] 选择安全 token 传递方案（建议方案 1 或 2）
- [ ] 实现 token 安全传递
- [ ] 移除 `/status` 中的 token 返回
- [ ] 更新前端 token 获取逻辑

**预计工作量**: 3-4 小时

---

### P1 - 合并前修复（高优先级）

#### 3. 加强 `safe_delete()` symlink 防护
- [ ] 添加 lstat 检查
- [ ] Windows reparse point 处理
- [ ] 路径验证增强
- [ ] 添加 symlink 攻击测试

**预计工作量**: 2-3 小时

#### 4. 限制 `new_session_handler` cwd 范围
- [ ] 添加路径验证
- [ ] 限制在允许工作区内
- [ ] 添加审计日志
- [ ] 添加目录遍历测试

**预计工作量**: 1-2 小时

#### 5. Query 参数验证
- [ ] 添加 try-except 处理
- [ ] 范围验证
- [ ] 返回 400 错误而非 500

**预计工作量**: 1 小时

#### 6. 保护新增安全目录
- [ ] 更新 `PROTECTED_TOP_DIRS`
- [ ] 添加 `PROTECTED_FILES`
- [ ] 添加保护测试

**预计工作量**: 1 小时

**P1 总计**: 5-7 小时

---

### P2 - 后续改进（可延迟）

#### 7. Secret 文件检测扩展
- [ ] 扩展 secret 模式列表
- [ ] 添加目录级检测
- [ ] 添加测试覆盖

**预计工作量**: 2 小时

#### 8. 日志脱敏规则完善
- [ ] 添加 JWT、GitHub token、AWS key 检测
- [ ] URL query 参数脱敏
- [ ] 标准 secret detector 测试集

**预计工作量**: 2-3 小时

#### 9. 测试覆盖补充
- [ ] 补充 manifest 篡改测试
- [ ] 补充并发边界测试
- [ ] 补充攻击场景测试

**预计工作量**: 3-4 小时

**P2 总计**: 7-9 小时

---

### P3 - 架构改进（长期）

#### 10. 代码执行沙箱化
- [ ] 评估沙箱方案（Docker/gVisor/Windows Sandbox）
- [ ] 设计沙箱架构
- [ ] 实现原型
- [ ] 性能测试和调优

**预计工作量**: 2-3 天

---

## 📊 评分详情（Codex 审查）

| 维度 | 得分 | 满分 | 说明 |
|------|------|------|------|
| **Root Cause Resolution** | 12 | 20 | 新增了策略层，但删除/恢复和执行边界仍可绕过 |
| **Code Quality** | 14 | 20 | 结构清晰，但确认语义、token 生命周期和异常处理不完整 |
| **Side Effects** | 11 | 20 | 可能误删审计/隔离数据，也可能阻断合法修改 |
| **Edge Cases** | 10 | 20 | symlink、manifest 篡改、GET 参数异常未覆盖 |
| **Test Coverage** | 12 | 20 | 有新增测试，但缺少关键攻击面和回归场景 |
| **总分** | **59** | **100** | **需要改进** |

---

## 📈 建议的合并流程

### 阶段 1: 紧急修复 (1-2 天)
1. 修复 Critical 问题 #1 和 #2
2. 本地测试验证
3. 代码审查（另一位工程师）

### 阶段 2: 高优先级修复 (1 天)
1. 修复 Major 问题 #3-#7
2. 运行完整测试套件
3. 更新文档

### 阶段 3: 合并和部署
1. 创建 PR，附上本审查报告
2. CI/CD 流水线验证
3. 合并到主分支
4. 部署到测试环境
5. 监控和验证

### 阶段 4: 持续改进
1. 创建 P2 任务工单
2. 规划下个迭代
3. 定期安全审计

---

## 🔍 相关文件清单

### 修改的文件 (12)
1. `assets/tools_schema.json` - 新增 restore_quarantine 工具
2. `assets/tools_schema_cn.json` - 中文 schema
3. `cleanup_temp.py` - 清理逻辑修复
4. `frontends/desktop/static/app.js` - Bridge token 支持
5. `frontends/desktop/static/ga-web.js` - Token 管理
6. `frontends/desktop_bridge.py` - 安全增强
7. `ga.py` - 文件操作安全策略集成
8. `ga_cli/cli.py` - CLI 元数据
9. `llmcore.py` - 日志脱敏
10. `memory/L4_raw_sessions/compress_session.py` - 安全删除
11. `pyproject.toml` - 添加 psutil 依赖
12. `tests/test_process_safety.py` - 扩展测试

### 新增的文件 (7)
1. `docs/GENERICAGENT_FULL_CAPABILITY_ACTIVATION.md`
2. `security/` - 新模块
3. `tests/test_cleanup_temp.py`
4. `tests/test_cli_metadata.py`
5. `tests/test_desktop_bridge_security.py`
6. `tests/test_file_policy.py`
7. `tests/test_llm_log_redaction.py`
8. `tests/test_project_metadata.py`

---

## 📚 参考资料

### 安全最佳实践
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [NIST Secure Software Development Framework](https://csrc.nist.gov/publications/detail/sp/800-218/final)

### Python 安全
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [Bandit - Python AST Security Linter](https://github.com/PyCQA/bandit)

### 文件系统安全
- [Symlink Attack Prevention](https://en.wikipedia.org/wiki/Symlink_race)
- [TOCTOU Vulnerabilities](https://en.wikipedia.org/wiki/Time-of-check_to_time-of-use)

---

## 结论

本次代码变更在**安全架构方向上是正确的**，引入了 `FilePolicy` 统一管理文件操作，增强了 Bridge 的安全控制，并开始关注日志脱敏等安全细节。

然而，**实现细节存在严重安全漏洞**：
- **Critical**: 隔离区恢复机制可被绕过，Bridge token 暴露
- **Major**: symlink 防护不足，代码执行沙箱缺失，输入验证不完整

**建议**:
1. **不要直接合并** - 必须先修复 2 个 Critical 和 5 个 Major 问题
2. **预计修复时间** - P0: 1-2 天，P1: 1 天
3. **长期改进** - 考虑引入真实沙箱环境，扩展安全测试覆盖

**评分**: 59/100 - **NEEDS_IMPROVEMENT**

---

**审查完成时间**: 2026-06-06  
**下次审查建议**: 修复完成后重新审查
