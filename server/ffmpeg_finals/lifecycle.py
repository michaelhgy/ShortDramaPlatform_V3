"""Production-task ownership for the separately stored FFmpeg queue.

Queue rows and selections are disposable task data. Successful outputs are the
template's usage ledger and must survive task deletion. Public template layers
never belong to an account/drama cleanup.
"""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import threading

_locks = {}
_registry_lock = threading.Lock()


def final_job_lock(data_root):
    key = str(Path(data_root).resolve()) if data_root else ''
    with _registry_lock:
        return _locks.setdefault(key, threading.RLock())


def _database(data_root):
    return Path(data_root) / 'database' / 'v3_template_library.db' if data_root else None


def task_jobs(data_root, task_id):
    path = _database(data_root)
    if path is None or not path.is_file():
        return []
    with closing(sqlite3.connect(path, timeout=15)) as conn:
        conn.row_factory = sqlite3.Row
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='final_jobs'").fetchone():
            return []
        return [dict(row) for row in conn.execute('SELECT id,task_id,status FROM final_jobs WHERE task_id=?', (task_id,))]


def active_task_jobs(data_root, task_id):
    return [row for row in task_jobs(data_root, task_id) if row['status'] in ('waiting', 'running')]


def task_cache_paths(data_root, task_id):
    """Only the canonical fg/<job-prefix> directory, never a recipe's paths."""
    jobs = task_jobs(data_root, task_id)
    if not jobs:
        return []
    root = Path(data_root).resolve() / 'fg'
    if root.resolve() != root:
        raise ValueError('成片临时目录存在路径跳转，停止清理')
    paths = []
    with closing(sqlite3.connect(_database(data_root), timeout=15)) as conn:
        for job in jobs:
            identity = job['id']
            if not re.fullmatch(r'[a-f0-9]{32}', identity):
                raise ValueError('成片任务编号异常，停止清理其临时目录')
            prefix = identity[:12]
            candidate = root / prefix
            if candidate.resolve() != candidate:
                raise ValueError('成片临时目录存在路径跳转，停止清理')
            if conn.execute('SELECT 1 FROM final_jobs WHERE substr(id,1,12)=? AND task_id<>?', (prefix, task_id)).fetchone():
                raise ValueError('成片临时目录归属冲突，停止清理')
            paths.append(candidate)
    return list(dict.fromkeys(paths))


def purge_task_records(data_root, task_id):
    """Called after successful file cleanup and parent transaction commit."""
    path = _database(data_root)
    if path is None or not path.is_file():
        return {'final_jobs': 0, 'selections': 0}
    with final_job_lock(data_root), closing(sqlite3.connect(path, timeout=15)) as conn:
        conn.execute('BEGIN IMMEDIATE')
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'final_jobs' in tables and conn.execute("SELECT 1 FROM final_jobs WHERE task_id=? AND status IN ('waiting','running')", (task_id,)).fetchone():
            raise ValueError('当前剧集仍有排队或运行的成片任务，不能移除记录')
        removed = {}
        for table in ('final_jobs', 'selections'):
            removed[table] = conn.execute(f'DELETE FROM {table} WHERE task_id=?', (task_id,)).rowcount if table in tables else 0
        conn.commit()
        return removed


def visible_task_ids(business_connection):
    with closing(business_connection()) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM production_tasks WHERE COALESCE(cleanup_status,'active') IN ('active','partial')")}


def reconcile_detached_records(library, task_ids=None):
    """Repair old missed cascades on startup. No file deletion or usage refund.

    Normal cleanup already removes fg folders before deleting queue records.
    Historical filesystem evidence remains untouched by this metadata repair.
    """
    with final_job_lock(library.data_root), closing(library.business_connection()) as business, closing(library.connect()) as conn:
        parents = {r['id']: r['cleanup_status'] for r in business.execute('SELECT id,cleanup_status FROM production_tasks')}
        candidates = {r[0] for r in conn.execute('SELECT task_id FROM final_jobs UNION SELECT task_id FROM selections')}
        detached = {identity for identity in candidates if (task_ids is None or identity in task_ids) and (identity not in parents or parents[identity] in ('process_cleaned', 'raw_cleaned', 'raw_partial'))}
        removed = {'final_jobs': 0, 'selections': 0}
        conn.execute('BEGIN IMMEDIATE')
        for identity in detached:
            # Startup recovery marks interrupted jobs before calling here. Live
            # repair must never remove an actually running renderer's record.
            if conn.execute("SELECT 1 FROM final_jobs WHERE task_id=? AND status='running'", (identity,)).fetchone():
                continue
            for table in removed:
                removed[table] += conn.execute(f'DELETE FROM {table} WHERE task_id=?', (identity,)).rowcount
        conn.commit()
        return removed
