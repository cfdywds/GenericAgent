from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_MANIFEST_KEY_TEXT = os.environ.get("GA_QUARANTINE_MANIFEST_KEY")
_MANIFEST_HMAC_KEY = (
    _MANIFEST_KEY_TEXT.encode("utf-8")
    if _MANIFEST_KEY_TEXT
    else secrets.token_bytes(32)
)


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    risk: str
    reason: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class FilePolicy:
    """Path policy for GA file side effects.

    The policy is intentionally conservative around deletion and whole-file
    writes. Precise patches remain usable, while broad writes/deletes outside
    temp require explicit confirmation at the agent layer.
    """

    SECRET_FILENAMES = {
        ".env",
        "auth.json",
        "mykey.json",
        "mykey.py",
    }
    SECRET_PATTERNS = (
        r"(^|/)\.env(?:[./]|$)",
        r"\.(?:pem|key|crt|p12|pfx)$",
        r"(^|/)id_(?:rsa|ed25519|ecdsa)(?:$|\.)",
        r"(^|/)(?:credentials|service-account|auth[^/]*)\.json$",
        r"(^|/)\.ssh(?:/|$)",
        r"(^|/)\.aws/credentials$",
    )
    CRITICAL_DIRS = {
        ".git",
        ".venv",
        "venv",
    }
    CORE_TOP_FILES = {
        "agent_loop.py",
        "agentmain.py",
        "ga.py",
        "llmcore.py",
        "pyproject.toml",
    }
    CORE_TOP_DIRS = {
        "assets",
        "docs",
        "frontends",
        "memory",
        "reflect",
        "security",
        "tests",
    }

    def __init__(self, root: str | os.PathLike[str], cwd: str | os.PathLike[str] | None = None):
        self.root = self._resolve(Path(root))
        self.cwd = self._resolve(Path(cwd or self.root))
        self.temp_dir = self.root / "temp"
        self.quarantine_dir = self.temp_dir / "quarantine"
        self.quarantine_manifest = self.quarantine_dir / "manifest.jsonl"
        self.backup_dir = self.temp_dir / "file_backups"
        self.audit_path = self.temp_dir / "security_audit.jsonl"

    @staticmethod
    def _resolve(path: Path) -> Path:
        return path.expanduser().resolve(strict=False)

    @staticmethod
    def _is_under(path: Path, base: Path) -> bool:
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False

    def resolve(self, path: str | os.PathLike[str]) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.cwd / p
        return self._resolve(p)

    def _absolute_no_follow(self, path: str | os.PathLike[str]) -> Path:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.cwd / p
        return Path(os.path.abspath(os.fspath(p)))

    def _rel_parts(self, path: Path) -> tuple[str, ...]:
        try:
            return tuple(part.lower() for part in path.relative_to(self.root).parts)
        except ValueError:
            return ()

    def _is_temp_path(self, path: Path) -> bool:
        return path == self.temp_dir or self._is_under(path, self.temp_dir)

    def _is_secret_path(self, path: Path) -> bool:
        if path.name.lower() in self.SECRET_FILENAMES:
            return True
        rel = "/".join(self._rel_parts(path)) or str(path).replace("\\", "/").lower()
        return any(re.search(pattern, rel, re.IGNORECASE) for pattern in self.SECRET_PATTERNS)

    def _has_critical_dir(self, path: Path) -> bool:
        return bool(set(self._rel_parts(path)) & self.CRITICAL_DIRS)

    def _is_core_path(self, path: Path) -> bool:
        parts = self._rel_parts(path)
        if not parts:
            return False
        if len(parts) == 1 and parts[0] in self.CORE_TOP_FILES:
            return True
        return parts[0] in self.CORE_TOP_DIRS

    def evaluate(self, operation: str, path: str | os.PathLike[str]) -> PolicyDecision:
        op = (operation or "").lower().strip()
        resolved = self.resolve(path)
        path_s = str(resolved)

        if not self._is_under(resolved, self.root):
            return PolicyDecision("deny", "critical", "path is outside repository root", path_s)

        if self._has_critical_dir(resolved):
            return PolicyDecision("deny", "critical", "path touches a critical runtime directory", path_s)

        if self._is_secret_path(resolved):
            return PolicyDecision("deny", "critical", "path is a configured secret file", path_s)

        if op in {"delete", "remove", "unlink", "rmtree"}:
            if self._is_temp_path(resolved):
                return PolicyDecision("allow", "medium", "delete stays inside temp", path_s)
            return PolicyDecision("quarantine", "high", "delete outside temp must move to quarantine", path_s)

        if op in {"overwrite", "write", "append", "prepend", "patch"}:
            exists = resolved.exists()
            if op == "overwrite" and exists and self._is_core_path(resolved):
                return PolicyDecision("confirm", "high", "whole-file overwrite of project-controlled path", path_s)
            if op in {"write", "overwrite"} and exists and not self._is_temp_path(resolved):
                return PolicyDecision("confirm", "medium", "whole-file write of existing non-temp file", path_s)
            return PolicyDecision("allow", "low", "operation stays within allowed repository path", path_s)

        return PolicyDecision("confirm", "medium", f"unknown file operation: {operation}", path_s)

    def log_event(
        self,
        operation: str,
        path: str | os.PathLike[str],
        decision: PolicyDecision,
        *,
        actor: str = "ga",
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "operation": operation,
            "actor": actor,
            "path": str(self.resolve(path)),
            "decision": decision.to_dict(),
        }
        if extra:
            record["extra"] = extra
        with open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def backup_existing(
        self,
        path: str | os.PathLike[str],
        *,
        actor: str = "ga",
        reason: str = "write backup",
    ) -> str | None:
        target = self.resolve(path)
        if not target.is_file():
            return None
        rel = target.relative_to(self.root)
        digest = hashlib.sha256(str(rel).encode("utf-8")).hexdigest()[:12]
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = self.backup_dir / stamp / f"{digest}_{target.name}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        decision = PolicyDecision("backup", "low", reason, str(target))
        self.log_event("backup", target, decision, actor=actor, extra={"backup_path": str(backup)})
        return str(backup)

    def _path_size(self, path: Path) -> int | None:
        if path.is_file() or path.is_symlink():
            return path.lstat().st_size
        if path.is_dir():
            total = 0
            for item in sorted(path.rglob("*")):
                try:
                    if item.is_file() or item.is_symlink():
                        total += item.lstat().st_size
                except OSError:
                    return None
            return total
        return None

    def _content_hash(self, path: Path) -> str | None:
        digest = hashlib.sha256()
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            return digest.hexdigest()
        if path.is_file():
            digest.update(b"file\0")
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        if path.is_dir():
            digest.update(b"dir\0")
            try:
                items = sorted(path.rglob("*"), key=lambda item: str(item.relative_to(path)).replace("\\", "/"))
                for item in items:
                    rel = str(item.relative_to(path)).replace("\\", "/")
                    digest.update(rel.encode("utf-8", errors="surrogateescape"))
                    digest.update(b"\0")
                    child_hash = self._content_hash(item)
                    if child_hash is None:
                        return None
                    digest.update(child_hash.encode("ascii"))
                    digest.update(b"\0")
            except OSError:
                return None
            return digest.hexdigest()
        return None

    def _file_hash(self, path: Path) -> str | None:
        return self._content_hash(path)

    @staticmethod
    def _manifest_payload(record: dict[str, Any]) -> bytes:
        payload = {k: v for k, v in record.items() if k != "signature"}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _sign_quarantine_record(self, record: dict[str, Any]) -> str:
        return hmac.new(_MANIFEST_HMAC_KEY, self._manifest_payload(record), hashlib.sha256).hexdigest()

    def _verify_quarantine_record(self, record: dict[str, Any]) -> bool:
        sig = record.get("signature")
        if not isinstance(sig, str) or not sig:
            return False
        expected = self._sign_quarantine_record(record)
        return hmac.compare_digest(sig, expected)

    def _is_windows_reparse_point(self, path: Path) -> bool:
        if os.name != "nt":
            return False
        try:
            attrs = path.lstat().st_file_attributes
        except (AttributeError, OSError):
            return False
        return bool(attrs & 0x400)

    def _remove_link_or_reparse_point(self, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        else:
            path.unlink()

    def _manifest_integrity_error(self, reason: str = "quarantine manifest integrity check failed") -> dict[str, Any]:
        return {"status": "blocked", "reason": reason}

    def _validate_quarantine_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        if not self._verify_quarantine_record(record):
            return self._manifest_integrity_error()
        required = {"id", "original_path", "quarantine_path", "size", "sha256", "restored"}
        if not required.issubset(record):
            return self._manifest_integrity_error()
        return None

    def _validate_quarantined_source(self, record: dict[str, Any], source: Path) -> dict[str, Any] | None:
        if record.get("size") != self._path_size(source):
            return self._manifest_integrity_error("quarantine file integrity check failed: size mismatch")
        if record.get("sha256") != self._content_hash(source):
            return self._manifest_integrity_error("quarantine file integrity check failed: hash mismatch")
        return None

    def _append_quarantine_manifest(self, record: dict[str, Any]) -> None:
        self.quarantine_manifest.parent.mkdir(parents=True, exist_ok=True)
        record = dict(record)
        record["signature"] = self._sign_quarantine_record(record)
        with open(self.quarantine_manifest, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _read_quarantine_manifest(self) -> list[dict[str, Any]]:
        try:
            with open(self.quarantine_manifest, encoding="utf-8") as fh:
                records = []
                for line in fh:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        records.append(record)
                return records
        except FileNotFoundError:
            return []

    def safe_delete(
        self,
        path: str | os.PathLike[str],
        *,
        actor: str = "ga",
        reason: str = "delete",
    ) -> dict[str, Any]:
        target = self._absolute_no_follow(path)
        if not self._is_under(target, self.root):
            decision = PolicyDecision("deny", "critical", "path is outside repository root", str(target))
        elif self._has_critical_dir(target):
            decision = PolicyDecision("deny", "critical", "path touches a critical runtime directory", str(target))
        elif self._is_secret_path(target):
            decision = PolicyDecision("deny", "critical", "path is a configured secret file", str(target))
        elif self._is_temp_path(target):
            decision = PolicyDecision("allow", "medium", "delete stays inside temp", str(target))
        else:
            decision = PolicyDecision("quarantine", "high", "delete outside temp must move to quarantine", str(target))
        if decision.action == "deny":
            self.log_event("delete", target, decision, actor=actor, extra={"reason": reason})
            return {"status": "blocked", "decision": decision.to_dict()}
        if not target.exists() and not target.is_symlink():
            return {"status": "missing", "path": str(target)}

        if decision.action == "allow":
            if target.is_symlink() or self._is_windows_reparse_point(target):
                self._remove_link_or_reparse_point(target)
            elif target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            self.log_event("delete", target, decision, actor=actor, extra={"reason": reason})
            return {"status": "deleted", "path": str(target)}

        rel = target.relative_to(self.root)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = self.quarantine_dir / stamp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest = dest.with_name(f"{dest.name}.{time.time_ns()}")
        quarantine_id = hashlib.sha256(f"{time.time_ns()}:{rel}".encode("utf-8")).hexdigest()[:16]
        size = self._path_size(target)
        digest = self._content_hash(target)
        shutil.move(str(target), str(dest))
        manifest_record = {
            "id": quarantine_id,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "actor": actor,
            "reason": reason,
            "original_path": str(target),
            "quarantine_path": str(dest),
            "size": size,
            "sha256": digest,
            "decision": decision.to_dict(),
            "restored": False,
        }
        self._append_quarantine_manifest(manifest_record)
        self.log_event(
            "delete",
            target,
            decision,
            actor=actor,
            extra={"reason": reason, "quarantine_id": quarantine_id, "quarantine_path": str(dest)},
        )
        return {
            "status": "quarantined",
            "quarantine_id": quarantine_id,
            "path": str(target),
            "quarantine_path": str(dest),
            "decision": decision.to_dict(),
        }

    def restore_quarantine(self, quarantine_id: str, *, actor: str = "ga") -> dict[str, Any]:
        records = self._read_quarantine_manifest()
        record = next((item for item in reversed(records) if item.get("id") == quarantine_id), None)
        if not record:
            return {"status": "missing", "reason": "quarantine id not found"}
        integrity_error = self._validate_quarantine_record(record)
        if integrity_error:
            return integrity_error
        if record.get("restored"):
            return {"status": "already_restored", "quarantine_id": quarantine_id}

        source = self.resolve(record.get("quarantine_path", ""))
        target = self.resolve(record.get("original_path", ""))
        if not self._is_under(source, self.quarantine_dir):
            return {"status": "blocked", "reason": "manifest source is outside quarantine"}
        if not self._is_under(target, self.root):
            return {"status": "blocked", "reason": "manifest target is outside repository root"}
        if target.exists():
            return {"status": "blocked", "reason": "restore target already exists", "path": str(target)}
        if not source.exists():
            return {"status": "missing", "reason": "quarantined path is missing", "path": str(source)}
        source_error = self._validate_quarantined_source(record, source)
        if source_error:
            return source_error

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        decision = PolicyDecision("restore", "medium", "restored quarantined file", str(target))
        self.log_event(
            "restore",
            target,
            decision,
            actor=actor,
            extra={"quarantine_id": quarantine_id, "quarantine_path": str(source)},
        )
        restored_record = dict(record)
        restored_record["restored"] = True
        restored_record["restored_ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        restored_record["restored_by"] = actor
        self._append_quarantine_manifest(restored_record)
        return {"status": "restored", "quarantine_id": quarantine_id, "path": str(target)}
