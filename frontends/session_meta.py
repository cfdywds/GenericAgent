"""Session relationship metadata for model_responses logs.

JSON sidecar at `temp/model_responses/session_meta.json` maps log-file
basename -> metadata. It is intentionally separate from model response logs so
restore/parsing code keeps the existing Prompt/Response format untouched.
"""
from __future__ import annotations

import glob
import json
import os
import threading
import time

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'temp', 'model_responses')
_REG_PATH = os.path.join(_LOG_DIR, 'session_meta.json')
_lock = threading.Lock()

KNOWN_ROLES = {
    'main',
    'goal_launcher',
    'goal_child',
    'goal_master',
    'hive_launcher',
    'hive_master',
    'hive_worker',
    'worker',
    'reflect',
    'conductor',
    'task',
}


def _load() -> dict:
    try:
        with open(_REG_PATH, encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)
    tmp = _REG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, _REG_PATH)


def _key(log_path: str) -> str:
    return os.path.basename(log_path or '')


def normalize_role(role: str) -> str:
    role = (role or '').strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'goal': 'goal_child',
        'goal_mode': 'goal_child',
        'goal_reflect': 'goal_child',
        'hive': 'hive_master',
        'goal_hive': 'hive_master',
        'subagent': 'worker',
        'agent_worker': 'hive_worker',
    }
    role = aliases.get(role, role)
    return role if role in KNOWN_ROLES else 'main'


def set_meta(log_path: str, **meta) -> None:
    key = _key(log_path)
    if not key:
        return
    clean = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, str):
            v = v.strip()
            if not v:
                continue
        clean[k] = v
    if 'role' in clean:
        clean['role'] = normalize_role(str(clean['role']))
    clean.setdefault('updated_at', time.time())
    with _lock:
        d = _load()
        cur = d.get(key)
        if not isinstance(cur, dict):
            cur = {}
        cur.update(clean)
        d[key] = cur
        _save(d)


def get_meta(log_path: str) -> dict:
    data = _load().get(_key(log_path), {})
    return dict(data) if isinstance(data, dict) else {}


def migrate(old_path: str, new_path: str) -> None:
    if old_path == new_path:
        return
    old_key, new_key = _key(old_path), _key(new_path)
    if not old_key or not new_key:
        return
    with _lock:
        d = _load()
        if old_key in d:
            d[new_key] = d.pop(old_key)
            _save(d)


def gc() -> int:
    with _lock:
        d = _load()
        bad = []
        for key in d:
            path = os.path.join(_LOG_DIR, key)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                continue
            if glob.glob(os.path.join(_LOG_DIR, key.replace('.txt', '_*.txt'))):
                continue
            bad.append(key)
        for key in bad:
            d.pop(key, None)
        if bad:
            _save(d)
        return len(bad)


def register_from_env(log_path: str, *, default_role: str = 'main') -> None:
    role = os.environ.get('GA_SESSION_ROLE') or default_role
    meta = {
        'role': role,
        'parent_log': os.environ.get('GA_PARENT_LOG', ''),
        'goal_state': os.environ.get('GOAL_STATE', ''),
        'objective': os.environ.get('GA_SESSION_OBJECTIVE', ''),
        'pid': os.getpid(),
        'created_at': time.time(),
    }
    set_meta(log_path, **meta)
