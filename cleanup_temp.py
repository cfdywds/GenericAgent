#!/usr/bin/env python3
"""Safe one-shot cleaner for GenericAgent's temp directory."""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEMP_DIR = ROOT / "temp"
CLIPBOARD_DIR = Path(tempfile.gettempdir()) / "genericagent_tui_clipboard"

PROTECTED_TOP_DIRS = {
    "model_responses",
    "weights",
    "reflect_logs",
    "quarantine",
    "file_backups",
}

PROTECTED_FILES = {
    "security_audit.jsonl",
}

TOP_FILE_PATTERNS = [
    "*.ai.py",
    "user_prompt_*.md",
    "*.tmp",
    "*.bak",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.webp",
    "*.log",
]

SCRIPT_PATTERNS = [
    "check_*.py",
    "fix_*.py",
    "deploy_*.py",
    "test_*.py",
    "monitor_*.py",
    "ssh_*.py",
    "*_task.py",
]


@dataclass(frozen=True)
class Deletion:
    path: Path
    reason: str
    is_dir: bool = False


def _age_seconds(path: Path) -> float:
    return max(0.0, time.time() - path.stat().st_mtime)


def _older_than(path: Path, seconds: float) -> bool:
    try:
        return _age_seconds(path) >= seconds
    except OSError:
        return False


def _inside(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _size(path: Path) -> int:
    try:
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        total = 0
        for item in path.rglob("*"):
            if item.is_file() or item.is_symlink():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def _format_size(num: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num} B"


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in patterns)


def _collect_pycache(temp_dir: Path) -> list[Deletion]:
    deletions: list[Deletion] = []
    if not temp_dir.exists():
        return deletions
    for path in temp_dir.rglob("__pycache__"):
        if path.is_dir() and _inside(path, temp_dir):
            deletions.append(Deletion(path, "__pycache__ cache directory", is_dir=True))
    return deletions


def _collect_empty_dirs(temp_dir: Path) -> list[Deletion]:
    deletions: list[Deletion] = []
    if not temp_dir.exists():
        return deletions
    for path in temp_dir.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        if path.name in PROTECTED_TOP_DIRS:
            continue
        if path.name.startswith("_tui_v2_"):
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            deletions.append(Deletion(path, "empty top-level temp directory", is_dir=True))
        except OSError:
            pass
    return deletions


def _collect_top_files(temp_dir: Path, days: float, include_scripts: bool) -> list[Deletion]:
    deletions: list[Deletion] = []
    if not temp_dir.exists():
        return deletions
    min_age = days * 86400
    patterns = TOP_FILE_PATTERNS + (SCRIPT_PATTERNS if include_scripts else [])
    for path in temp_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in PROTECTED_FILES:
            continue
        if not _matches_any(path.name, patterns):
            continue
        if _older_than(path, min_age):
            deletions.append(Deletion(path, f"top-level temp artifact older than {days:g} day(s)"))
    return deletions


def _collect_tui_signal_dirs(temp_dir: Path) -> list[Deletion]:
    deletions: list[Deletion] = []
    if not temp_dir.exists():
        return deletions
    for path in temp_dir.glob("_tui_v2_*"):
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            deletions.append(Deletion(path, "empty TUI v2 signal directory", is_dir=True))
        except OSError:
            pass
    return deletions


def _collect_clipboard(days: float) -> list[Deletion]:
    deletions: list[Deletion] = []
    if not CLIPBOARD_DIR.exists():
        return deletions
    min_age = days * 86400
    for path in CLIPBOARD_DIR.glob("clipboard_*.png"):
        if path.is_file() and _older_than(path, min_age):
            deletions.append(Deletion(path, f"TUI clipboard image older than {days:g} day(s)"))
    return deletions


def _delete(item: Deletion, allowed_roots: tuple[Path, ...]) -> bool:
    if not any(_inside(item.path, root) or item.path.resolve() == root.resolve() for root in allowed_roots):
        print(f"SKIP outside allowed roots: {item.path}")
        return False
    try:
        if item.is_dir:
            if item.path.is_symlink():
                item.path.unlink()
            else:
                shutil.rmtree(item.path)
        else:
            item.path.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError as exc:
        print(f"SKIP failed: {item.path} ({exc})")
        return False


def _run_model_response_archive(temp_dir: Path, dry_run: bool) -> None:
    raw_dir = temp_dir / "model_responses"
    if not raw_dir.is_dir():
        return
    sys.path.insert(0, str(ROOT / "memory" / "L4_raw_sessions"))
    try:
        from compress_session import batch_process
    except Exception as exc:
        print(f"[Archive] skipped: cannot import compress_session ({exc})")
        return
    print("[Archive] model_responses via L4 archiver")
    batch_process(str(raw_dir), dry_run=dry_run)


def _run_session_name_gc(dry_run: bool) -> None:
    if dry_run:
        print("[GC] session_names skipped in dry-run")
        return
    sys.path.insert(0, str(ROOT / "frontends"))
    try:
        import session_names

        removed = session_names.gc()
        print(f"[GC] session_names removed {removed} stale entrie(s)")
    except Exception as exc:
        print(f"[GC] session_names skipped: {exc}")


def build_plan(args: argparse.Namespace) -> list[Deletion]:
    temp_dir = Path(args.temp_dir).resolve()
    items: list[Deletion] = []
    items.extend(_collect_tui_signal_dirs(temp_dir))
    items.extend(_collect_pycache(temp_dir))
    items.extend(_collect_top_files(temp_dir, args.days, args.include_scripts))
    items.extend(_collect_clipboard(args.days))
    items.extend(_collect_empty_dirs(temp_dir))

    seen: set[Path] = set()
    unique: list[Deletion] = []
    for item in sorted(items, key=lambda x: (str(x.path).lower(), x.reason)):
        resolved = item.path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(item)
    return unique


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean safe GenericAgent temp artifacts.")
    parser.add_argument("--temp-dir", default=str(TEMP_DIR), help="temp directory to clean")
    parser.add_argument("--days", type=float, default=2.0, help="minimum age for top-level artifacts")
    parser.add_argument("--yes", action="store_true", help="delete without interactive confirmation")
    parser.add_argument("--dry-run", action="store_true", help="only print what would be cleaned")
    parser.add_argument("--skip-archive", action="store_true", help="skip model_responses L4 archive")
    parser.add_argument(
        "--include-scripts",
        action="store_true",
        help="also delete old top-level debug Python scripts matching check_/fix_/deploy_/test_ patterns",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    temp_dir = Path(args.temp_dir).resolve()
    if not temp_dir.exists():
        print(f"temp directory does not exist: {temp_dir}")
        return 0
    project_temp = TEMP_DIR.resolve()
    if temp_dir != project_temp and not _inside(temp_dir, project_temp):
        print(f"refusing to clean non-project temp dir: {temp_dir}")
        return 2

    dry_run = args.dry_run or not args.yes
    plan = build_plan(args)
    total = sum(_size(item.path) for item in plan)

    print(f"GenericAgent temp cleaner")
    print(f"temp: {temp_dir}")
    print(f"mode: {'dry-run' if dry_run else 'delete'}")
    print(f"planned deletions: {len(plan)} item(s), approx {_format_size(total)}")

    for item in plan:
        print(f"  - {_format_size(_size(item.path)):>9}  {item.path}  [{item.reason}]")

    if not args.skip_archive:
        _run_model_response_archive(temp_dir, dry_run=dry_run)

    if dry_run:
        print("\nDry-run only. Re-run with --yes to delete planned files.")
        return 0

    if not args.yes:
        answer = input("\nDelete these files? Type YES to continue: ").strip()
        if answer != "YES":
            print("cancelled")
            return 1

    allowed_roots = (temp_dir, CLIPBOARD_DIR)
    deleted = 0
    for item in plan:
        if _delete(item, allowed_roots):
            deleted += 1
    _run_session_name_gc(dry_run=False)
    print(f"\nDone. Deleted {deleted}/{len(plan)} planned item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
