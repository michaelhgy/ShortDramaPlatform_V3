"""Delete one original material and its owned finals/jobs without touching other inputs."""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import uuid

from server.ffmpeg_finals.lifecycle import final_job_lock
from server.publishing.service import RUN_LOCK, RUNS


def _service():
    from server import v2_file_service
    return v2_file_service


def _safe(path: Path, root: Path, *, directory=False):
    path, root = path.absolute(), root.absolute()
    if root.resolve() != root or path.resolve() != path or not path.is_relative_to(root) or path == root:
        raise ValueError('删除路径不属于本素材，或存在路径跳转，已停止操作：' + str(path))
    if path.exists():
        if directory:
            if not path.is_dir():
                raise ValueError('合成缓存路径类型异常：' + str(path))
            # Validate the complete tree before any recursive removal.
            for item in path.rglob('*'):
                if item.is_symlink() or item.resolve() != item.absolute():
                    raise ValueError('合成缓存包含路径跳转，已停止删除：' + str(item))
        elif not path.is_file():
            raise ValueError('视频文件路径类型异常：' + str(path))
    return path


def _attach(conn):
    db = Path(_service().DATA_ROOT) / 'database' / 'v3_template_library.db'
    if not db.is_file():
        return False
    conn.execute('ATTACH DATABASE ? AS material_library', (str(db),))
    return bool(conn.execute("SELECT 1 FROM material_library.sqlite_master WHERE name='final_jobs'").fetchone())


def _collect(conn, material_id, library):
    service = _service()
    row = conn.execute(
        "SELECT f.*,t.material_path,t.final_path,t.root_path,t.account_name,t.drama_name,t.cleanup_status,t.release_status "
        "FROM production_files f JOIN production_tasks t ON t.id=f.task_id "
        "WHERE f.id=? AND f.file_type='original_material'", (material_id,),
    ).fetchone()
    if row is None or row['status'] not in ('available', 'deletion_failed'):
        raise ValueError('素材不存在或已经删除，请刷新列表')
    if row['cleanup_status'] not in ('active', None, '') or row['release_status'] == 'registered':
        raise ValueError('该剧集已登记发布或已清理，不能删除素材')
    production_root = Path(service.WORKSPACE).absolute() / '生产文件'
    for key in ('root_path', 'material_path', 'final_path'):
        directory = Path(row[key]).absolute()
        if directory.resolve() != directory or production_root.resolve() != production_root or not directory.is_relative_to(production_root):
            raise ValueError('删除路径不属于当前生产文件工作区，已停止操作')
    if Path(row['material_path']).parent != Path(row['root_path']) or Path(row['final_path']).parent != Path(row['root_path']):
        raise ValueError('素材或成片目录不属于当前生产任务，已停止操作')
    source = _safe(Path(row['file_path']), Path(row['material_path']))
    if source.parent != Path(row['material_path']).absolute() or source.suffix.lower() not in service.VIDEO_EXTENSIONS:
        raise ValueError('素材路径不在当前扫描目录内')
    reason = ''
    others = conn.execute("SELECT id,account_name,drama_name,material_path FROM production_tasks WHERE id<>? AND COALESCE(cleanup_status,'active') IN ('active','partial')", (row['task_id'],)).fetchall()
    for other in others:
        if Path(other['material_path']).resolve() == source.parent:
            reason = f"此素材目录也被 {other['account_name']} × {other['drama_name']} 使用，不能单独删除文件"
    refs = conn.execute("SELECT f.file_path FROM production_files f JOIN production_tasks t ON t.id=f.task_id WHERE f.id<>? AND f.file_type='original_material' AND f.status<>'deleted' AND COALESCE(t.cleanup_status,'active') IN ('active','partial')", (material_id,)).fetchall()
    if any(Path(r[0]).resolve() == source for r in refs):
        reason = '其他生产任务也在使用此素材文件，不能单独删除'
    videos = [dict(v) for v in conn.execute('SELECT * FROM production_video_tasks WHERE source_material_id=?', (material_id,))]
    jobs = [dict(j) for j in conn.execute('SELECT * FROM material_library.final_jobs WHERE material_id=?', (material_id,))] if library else []
    if any(v['status'] in ('generating', 'exporting') for v in videos) or any(j['status'] == 'running' for j in jobs):
        reason = '本素材正在合成或导出，请等待当前任务结束后再删除'
    run = RUNS.get(row['task_id'])
    if run and run.get('thread') and run['thread'].is_alive():
        reason = '本剧集正在处理发布任务，请结束后再删除素材'
    ids = {v['id'] for v in videos} | {j['id'] for j in jobs}
    for doc in conn.execute("SELECT content FROM v3_publish_documents WHERE key=? AND kind IN ('publish_execution','execution')", (row['task_id'],)):
        state = json.loads(doc[0])
        for item in state.get('items', []):
            identity = item.get('video_id')
            matched = identity in ids or any(identity and str(identity) in str(item.get('key', '')) for identity in ids)
            if matched and (item.get('local_id') or item.get('draft_id') or item.get('status') in ('running','submitting','uncertain')):
                reason = '对应成片已提交外部发布或草稿任务，请先处理发布任务，避免删除仍在使用的视频'
    if conn.execute('SELECT 1 FROM v2_revenue_video_links WHERE source_material_id=?', (material_id,)).fetchone():
        reason = '对应成片已有正式作品关联，不能直接删除其本地生产记录'
    files, directories = set(), set()
    final_root = Path(row['final_path']).absolute()
    for v in videos:
        if v['output_path']:
            files.add(_safe(Path(v['output_path']), final_root))
        for export in conn.execute("SELECT j.status,a.status AS attempt_status,a.source_output_path FROM export_jobs j LEFT JOIN export_attempts a ON a.job_id=j.id WHERE j.subject_type='final' AND j.subject_id=?", (v['id'],)):
            if export['status'] == 'active' or export['attempt_status'] in ('preparing','awaiting_human_check','submitting','observing_output','finalizing'):
                reason = '对应成片仍有执行中的导出任务，请结束后再删除'
            if export['source_output_path']:
                p = Path(export['source_output_path'])
                # A legacy exported file can only be removed inside this task's final directory.
                files.add(_safe(p, final_root))
    for j in jobs:
        if j['task_id'] != row['task_id'] or not re.fullmatch(r'[a-f0-9]{32}', j['id']):
            raise ValueError('合成任务归属异常，已停止删除')
        plan = json.loads(j['plan'])
        if plan.get('material_id') != material_id or plan.get('task_id') != row['task_id']:
            raise ValueError('合成配方归属异常，已停止删除')
        for raw in (j['output_path'], plan.get('target')):
            if raw:
                files.add(_safe(Path(raw), final_root))
        fg = Path(service.DATA_ROOT).absolute() / 'fg'
        job_root = _safe(fg / j['id'][:12], fg, directory=True)
        if conn.execute('SELECT 1 FROM material_library.final_jobs WHERE substr(id,1,12)=? AND id<>?', (j['id'][:12], j['id'])).fetchone():
            raise ValueError('合成缓存目录归属冲突，已停止删除')
        history_root = job_root / 'regeneration_history'
        for history in history_root.glob('*.json'):
            previous = json.loads(history.read_text(encoding='utf-8'))
            if previous.get('id') != j['id'] or previous.get('material_id') != material_id:
                raise ValueError('历史成片记录归属冲突，已停止删除')
            previous_plan = json.loads(previous.get('plan') or '{}')
            for raw in (previous.get('output_path'), previous_plan.get('target')):
                if raw:
                    files.add(_safe(Path(raw), final_root))
        if job_root.exists():
            directories.add(job_root)
    for path in files:
        if path == source:
            raise ValueError('原素材与成片路径发生冲突，已停止删除')
        for ref in conn.execute('SELECT source_material_id FROM production_video_tasks WHERE output_path=? AND source_material_id<>?', (str(path), material_id)):
            reason = '对应成片文件被其他素材记录共用，不能删除'
        if library and conn.execute("SELECT 1 FROM material_library.final_jobs WHERE (output_path=? OR (json_valid(plan) AND json_extract(plan,'$.target')=?)) AND material_id<>?", (str(path), str(path), material_id)).fetchone():
            reason = '对应成片文件被其他合成任务共用，不能删除'
    specs = []
    for path in sorted(files | {source}):
        stat = path.stat() if path.exists() else None
        specs.append({'path': str(path), 'exists': bool(stat), 'size_bytes': stat.st_size if stat else 0,
                      'mtime_ns': stat.st_mtime_ns if stat else 0})
    fingerprint = {'material': material_id, 'files': specs, 'jobs': [(j['id'],j['status'],j['plan']) for j in jobs],
                   'videos': [(v['id'],v['status']) for v in videos],
                   'directories': [(str(d),d.stat().st_mtime_ns) for d in sorted(directories)]}
    token = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    public = {'material_id': material_id, 'file_name': row['file_name'], 'source_path': str(source),
              'can_delete': not reason, 'blocked_reason': reason, 'files': specs,
              'cache_directories': [str(d) for d in sorted(directories)],
              'video_count': len(videos), 'job_count': len(jobs) + sum(v['id'] not in {j['id'] for j in jobs} for v in videos),
              'confirmation_token': token}
    return row, videos, jobs, files, directories, public


def preview(material_id):
    service = _service()
    with service.SCAN_LOCK, final_job_lock(service.DATA_ROOT), RUN_LOCK, closing(service.connection()) as conn:
        library = _attach(conn)
        return _collect(conn, material_id, library)[-1]


def delete(material_id, confirmation_token):
    service = _service()
    with service.SCAN_LOCK, final_job_lock(service.DATA_ROOT), RUN_LOCK, closing(service.connection()) as conn:
        library = _attach(conn)
        conn.execute('BEGIN IMMEDIATE')
        row, videos, jobs, files, directories, plan = _collect(conn, material_id, library)
        if not plan['can_delete']:
            raise ValueError(plan['blocked_reason'])
        if not confirmation_token or confirmation_token != plan['confirmation_token']:
            raise ValueError('素材或合成任务在确认期间发生变化，请重新打开删除确认')
        # Audit paths and outcomes only; no copy of any video is made.
        audit_root = Path(service.DATA_ROOT).absolute() / 'diagnostics' / 'material-deletions'
        audit_root.mkdir(parents=True, exist_ok=True)
        audit = _safe(audit_root / (uuid.uuid4().hex + '.json'), audit_root)
        record = {**plan, 'task_id': row['task_id'], 'created_at': service.now_text(), 'deleted_paths': [], 'state': 'prepared'}
        def save():
            audit.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        save()
        try:
            # Stage relational changes first, so constraint errors cannot follow file removal.
            for video in videos:
                export_ids = [r[0] for r in conn.execute("SELECT id FROM export_jobs WHERE subject_type='final' AND subject_id=?", (video['id'],))]
                for export_id in export_ids:
                    conn.execute("DELETE FROM export_events WHERE attempt_id IN (SELECT id FROM export_attempts WHERE job_id=?)", (export_id,))
                    conn.execute("DELETE FROM export_attempts WHERE job_id=?", (export_id,))
                conn.execute("DELETE FROM export_jobs WHERE subject_type='final' AND subject_id=?", (video['id'],))
            conn.execute('DELETE FROM production_video_tasks WHERE source_material_id=?', (material_id,))
            if library:
                conn.execute('DELETE FROM material_library.final_jobs WHERE material_id=?', (material_id,))
                # outputs is the successful template-usage ledger: retain it after deleting a job.
            conn.execute("UPDATE production_files SET status='deleted',missing_scan_count=0,updated_at=? WHERE id=?", (service.now_text(), material_id))
            conn.execute('UPDATE production_tasks SET updated_at=? WHERE id=?', (service.now_text(), row['task_id']))
            for path in sorted(files):
                if path.exists():
                    path.unlink()
                    record['deleted_paths'].append(str(path)); save()
            for directory in sorted(directories):
                shutil.rmtree(directory)
                record['deleted_paths'].append(str(directory)); save()
            source = Path(row['file_path'])
            if source.exists():
                source.unlink()
                record['deleted_paths'].append(str(source)); save()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            record.update(state='failed', error=str(exc)); save()
            # Preserve all rows for retry. Keep the original until other files have been removed.
            if record['deleted_paths']:
                conn.execute("UPDATE production_files SET status='deletion_failed',updated_at=? WHERE id=?", (service.now_text(), material_id))
                for job in jobs:
                    conn.execute("UPDATE material_library.final_jobs SET status='error',stage='删除未完成',error=? WHERE id=?", (str(exc), job['id']))
                conn.execute("UPDATE production_video_tasks SET status='ffmpeg_error',updated_at=? WHERE source_material_id=?", (service.now_text(), material_id))
                conn.commit()
            raise ValueError('删除未完成，已删除的文件不会恢复；请解除文件占用后重试。原因：' + str(exc)) from exc
        record.update(state='completed', completed_at=service.now_text()); save()
        task_id = row['task_id']
    return {'task': service.get_task_details(task_id), 'deleted_paths': record['deleted_paths'], 'audit_path': str(audit)}
