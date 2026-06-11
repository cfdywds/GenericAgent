import os, json, time as _time, socket as _socket, logging
from datetime import datetime, timedelta

INTERVAL = 120
ONCE = False

_dir = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.abspath(os.path.join(_dir, '../sche_tasks'))
DONE = os.path.abspath(os.path.join(_dir, '../sche_tasks/done'))
_LOG = os.path.abspath(os.path.join(_dir, '../sche_tasks/scheduler.log'))
_ATTEMPT_FILE = os.path.abspath(os.path.join(_dir, '../sche_tasks/.last_attempt.json'))
_NOTIFICATION_DIR = os.path.abspath(os.path.join(_dir, '../temp/scheduler_notifications'))
_NOTIFICATION_FILE = os.path.join(_NOTIFICATION_DIR, 'events.jsonl')

os.makedirs(DONE, exist_ok=True)
_logger = logging.getLogger('scheduler')
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(_LOG, encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s',
                                        datefmt='%Y-%m-%d %H:%M'))
    _logger.addHandler(_fh)

# 端口锁：防止重复启动；热重载时 mod.__dict__ 保留 _lock，跳过重复绑定。
try:
    _lock
except NameError:
    try:
        _lock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        _lock.bind(('127.0.0.1', 45762))
        _lock.listen(1)
        _logger.info(f'Scheduler port lock acquired (pid={os.getpid()})')
    except OSError as e:
        _logger.error('FATAL: another scheduler instance is running (port 45762 busy)')
        raise SystemExit(1) from e

# 默认最大延迟窗口（小时），超过此时间不触发
DEFAULT_MAX_DELAY = 6
DEFAULT_RETRY_COOLDOWN_MINUTES = 60
_l4_t = 0  # last L4 archive time
_current_task = None


def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_attempts():
    """加载持久化尝试记录。"""
    try:
        with open(_ATTEMPT_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return {k: datetime.fromisoformat(v) for k, v in data.items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def _save_attempt(tid, timestamp):
    attempts = _load_attempts()
    attempts[tid] = timestamp
    _atomic_write_json(_ATTEMPT_FILE, {k: v.isoformat() for k, v in attempts.items()})
    _logger.info(f'PERSIST attempt {tid} at {timestamp.isoformat()}')


def _cleanup_old_attempts(max_age_days=7):
    attempts = _load_attempts()
    cutoff = datetime.now() - timedelta(days=max_age_days)
    cleaned = {k: v for k, v in attempts.items() if v > cutoff}
    if len(cleaned) < len(attempts):
        _atomic_write_json(_ATTEMPT_FILE, {k: v.isoformat() for k, v in cleaned.items()})
        _logger.info(f'CLEANUP {len(attempts) - len(cleaned)} old attempts')


def _publish_event(event_type, task_id, task_config=None, result=None, metadata=None):
    """发布调度事件。Bot 订阅此 JSONL 文件，不直接耦合 scheduler。"""
    os.makedirs(_NOTIFICATION_DIR, exist_ok=True)
    event = {
        'event_id': f'{int(_time.time() * 1000000)}_{task_id}_{event_type}',
        'timestamp': datetime.now().isoformat(),
        'event_type': event_type,
        'task_id': task_id,
        'task_config': task_config or {},
        'result': result or {},
        'metadata': metadata or {},
    }
    with open(_NOTIFICATION_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n')
    _logger.info(f'PUBLISH {event_type} for {task_id}')


def _parse_cooldown(repeat):
    """解析 repeat 为冷却时间（比实际周期略短，防漂移）。"""
    if repeat == 'once': return timedelta(days=999999)
    if repeat in ('daily', 'weekday'): return timedelta(hours=20)
    if repeat == 'weekly': return timedelta(days=6)
    if repeat == 'monthly': return timedelta(days=27)
    if repeat.startswith('every_'):
        try:
            parts = repeat.split('_')
            n = int(parts[1].rstrip('hdm'))
            u = parts[1][-1]
            if u == 'h': return timedelta(hours=n)
            if u == 'm': return timedelta(minutes=n)
            if u == 'd': return timedelta(days=n)
        except (ValueError, IndexError):
            pass
    _logger.warning(f'Unknown repeat type: {repeat}, fallback to 20h cooldown')
    return timedelta(hours=20)


def _last_run(tid, done_files):
    """找最近一次执行时间。"""
    latest = None
    for df in done_files:
        if not df.endswith(f'_{tid}.md'): continue
        try:
            t = datetime.strptime(df[:15], '%Y-%m-%d_%H%M')
            if latest is None or t > latest: latest = t
        except Exception:
            continue
    return latest


def _run_l4_archive_cron():
    global _l4_t
    if _time.time() - _l4_t <= 43200:
        return
    _l4_t = _time.time()
    try:
        import sys
        sys.path.insert(0, os.path.join(_dir, '../memory/L4_raw_sessions'))
        from compress_session import batch_process
        raw_dir = os.path.join(_dir, '../temp/model_responses')
        r = batch_process(raw_dir, dry_run=False)
        print(f'[L4 cron] {r}')
    except Exception as e:
        _logger.error(f'L4 archive failed: {e}')


def _schedule_is_due(now, h, m):
    return now.hour > h or (now.hour == h and now.minute >= m)


def check():
    global _current_task

    _run_l4_archive_cron()
    _cleanup_old_attempts()

    if not os.path.isdir(TASKS):
        return None

    now = datetime.now()
    os.makedirs(DONE, exist_ok=True)
    done_files = set(os.listdir(DONE))
    attempts = _load_attempts()

    for f in sorted(os.listdir(TASKS)):
        if not f.endswith('.json'):
            continue
        tid = f[:-5]
        task_file = os.path.join(TASKS, f)
        try:
            with open(task_file, encoding='utf-8') as fp:
                task = json.loads(fp.read())
        except Exception as e:
            _logger.error(f'JSON parse error for {f}: {e}')
            continue
        if not task.get('enabled', False):
            continue

        repeat = task.get('repeat', 'daily')
        sched = task.get('schedule', '00:00')
        try:
            h, m = map(int, sched.split(':'))
        except Exception as e:
            _logger.error(f'Invalid schedule format in {f}: {sched!r} ({e})')
            continue

        if repeat == 'weekday' and now.weekday() >= 5:
            continue
        if not _schedule_is_due(now, h, m):
            continue

        max_delay = task.get('max_delay_hours', DEFAULT_MAX_DELAY)
        sched_minutes = h * 60 + m
        now_minutes = now.hour * 60 + now.minute
        if (now_minutes - sched_minutes) > max_delay * 60:
            _logger.info(f'SKIP {tid}: {now_minutes - sched_minutes}min past schedule, '
                         f'exceeds max_delay={max_delay}h')
            continue

        last = _last_run(tid, done_files)
        cooldown = _parse_cooldown(repeat)
        if last and (now - last) < cooldown:
            continue

        retry_minutes = int(task.get('retry_cooldown_minutes', DEFAULT_RETRY_COOLDOWN_MINUTES))
        retry_cooldown = timedelta(minutes=retry_minutes)
        last_attempt = attempts.get(tid)
        if last_attempt and (now - last_attempt) < retry_cooldown:
            continue

        trigger_time = now
        _save_attempt(tid, trigger_time)
        ts = now.strftime('%Y-%m-%d_%H%M')
        rpt = os.path.abspath(os.path.join(DONE, f'{ts}_{tid}.md'))
        task_meta = {
            'task_id': tid,
            'task_file': task_file,
            'task_config': task,
            'report_path': rpt,
            'trigger_time': trigger_time.isoformat(),
            'started_monotonic': _time.monotonic(),
        }
        _current_task = task_meta

        _logger.info(f'TRIGGER {tid} (repeat={repeat}, schedule={sched}, '
                     f'last_run={last}, last_attempt={last_attempt})')
        _publish_event('task_triggered', tid, task, metadata={
            'trigger_time': trigger_time.isoformat(),
            'last_run': last.isoformat() if last else None,
            'report_path': rpt,
        })

        prompt = task.get('prompt', '')
        return (f'[定时任务] {tid}\n'
                f'[报告路径] {rpt}\n\n'
                f'先读 scheduled_task_sop 了解执行流程，然后执行以下任务：\n\n'
                f'{prompt}\n\n'
                f'完成后将执行报告写入 {rpt}。')

    return None


def on_done(result_text):
    """agentmain --reflect 在任务结束后调用。"""
    global _current_task
    task = _current_task
    if not task:
        _logger.warning('on_done: no current task metadata')
        return

    tid = task['task_id']
    report_path = task['report_path']
    exists = os.path.isfile(report_path)
    size = os.path.getsize(report_path) if exists else 0
    success = exists and size > 0
    elapsed = max(0.0, _time.monotonic() - task.get('started_monotonic', _time.monotonic()))
    error = None if success else (result_text or '')[:2000]
    event_type = 'task_completed' if success else 'task_failed'

    _publish_event(event_type, tid, task.get('task_config') or {}, result={
        'success': success,
        'report_path': report_path if success else None,
        'report_size': size,
        'error': error,
    }, metadata={
        'trigger_time': task.get('trigger_time'),
        'complete_time': datetime.now().isoformat(),
        'execution_time_seconds': round(elapsed, 3),
    })
    _logger.info(f'{event_type.upper()} {tid} success={success} report={report_path} size={size}')
    _current_task = None
