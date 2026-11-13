"""Explicit regeneration deletes prior finals immediately and reuses canonical names."""
from contextlib import closing
import json
import uuid
from pathlib import Path

from server.ffmpeg_templates.precompose import verified_file
from server.ffmpeg_templates.renderer import save


def regenerate(composer, *, task_id=None, identity=None):
    from server import v2_file_service as business
    from .service import _build_insertions

    # The worker claims jobs under the same lock. Validate the entire batch
    # before committing any new plans; a bad final item must not queue a subset.
    with composer.lock, closing(composer.lib.connect()) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if identity:
            rows = conn.execute('SELECT * FROM final_jobs WHERE id=?', (identity,)).fetchall()
            if not rows:
                raise ValueError('成片任务不存在')
            task_id = rows[0]['task_id']
        else:
            rows = conn.execute('SELECT * FROM final_jobs WHERE task_id=? ORDER BY rowid', (task_id,)).fetchall()
            if not rows:
                raise ValueError('本剧集没有可重新生成的 FFmpeg 成片，请先批量合成')
        task = composer.lib.task(task_id)
        if task.get('release_status') == 'registered' or task.get('cleanup_status', 'active') != 'active':
            raise ValueError('已结束任务不能重新生成')
        if any(row['status'] == 'running' for row in rows):
            raise ValueError('本剧集有正在合成的成片，请在任务中心暂停后续队列，等待当前一条结束后再重新生成')
        allowed = ('done', 'error', 'cancelled') if identity else ('done', 'error', 'cancelled', 'waiting')
        if any(row['status'] not in allowed for row in rows):
            raise ValueError('只可重新生成已完成、失败或已取消的成片')
        settings = business.get_v2_settings()
        with closing(composer.lib.business_connection()) as business_conn:
            materials = {m['id']: dict(m) for m in business_conn.execute(
                "SELECT * FROM production_files WHERE task_id=? AND file_type='original_material' AND status='available'", (task_id,))}
        root = Path(task['final_path']).resolve()
        if not root.is_relative_to(composer.lib.workspace.resolve()):
            raise ValueError('成片目录不属于当前工作区')
        plans = []
        reserved = set()
        deletions = {}
        for row in rows:
            material = materials.get(row['material_id'])
            if not material:
                raise ValueError('原素材不可用，请重新扫描；本次未提交任何重新生成任务')
            template = conn.execute('SELECT * FROM templates WHERE id=?', (row['template_id'],)).fetchone()
            if (not template or composer.lib.current_file(template) is None
                    or conn.execute('SELECT 1 FROM deleted_templates WHERE id=?', (row['template_id'],)).fetchone()):
                raise ValueError('原模板已删除或不可用')
            if not composer.lib.can_use(conn, row['template_id'], task['drama_key']):
                raise ValueError('原模板的剧集使用名额已满')
            plan = json.loads(row['plan'])
            source = Path(plan['source_path']).resolve()
            if (not source.is_relative_to(composer.lib.workspace.resolve())
                    or not source.is_file()
                    or source != Path(material['file_path']).resolve()
                    or not verified_file(source, plan['source_sha256'])):
                raise ValueError('原素材已变化或不可用，请重新扫描；本次未提交任何重新生成任务')
            source_frames = plan.get('source_frames', plan['frames'])
            insertions, frames, has_insert_audio = _build_insertions(
                task, material, source_frames, plan['source_sha256'], composer.lib.workspace, settings)
            version = int(plan.get('regeneration', 1)) + 1
            target = root / (Path(material['file_name']).stem + '.mp4')
            if target in reserved:
                raise ValueError('成片文件名冲突，本次未提交任何重新生成任务')
            reserved.add(target)
            job_root = composer.root / row['id'][:12]
            if job_root.resolve() != job_root or conn.execute(
                    'SELECT 1 FROM final_jobs WHERE substr(id,1,12)=? AND id<>?',
                    (row['id'][:12], row['id'])).fetchone():
                raise ValueError('成片临时目录归属冲突，停止重新生成')
            # Use recorded ownership, never glob-delete other users' similarly named videos.
            owned = {Path(value) for value in (row['output_path'], plan['target']) if value}
            history_root = job_root / 'regeneration_history'
            if history_root.resolve() != history_root:
                raise ValueError('成片历史目录存在路径跳转，停止重新生成')
            for history in history_root.glob('*.json'):
                if history.resolve() != history:
                    raise ValueError('成片历史记录存在路径跳转，停止重新生成')
                previous = json.loads(history.read_text(encoding='utf8'))
                if previous.get('id') != row['id'] or previous.get('material_id') != row['material_id']:
                    raise ValueError('成片历史记录归属冲突，停止重新生成')
                if previous.get('output_path'): owned.add(Path(previous['output_path']))
            for path in owned:
                if path.resolve() != path or path.parent != root or path == source or (path.exists() and not path.is_file()):
                    raise ValueError('旧成片路径不属于本剧集，停止重新生成')
            if target.exists() and target not in owned:
                raise ValueError('原文件名已被其他文件占用，停止以免删除无关视频')
            old_files = set(owned)
            # Remove the job's prior rendered finals too; keep diagnostic JSON and shared layers.
            for attempt in job_root.glob('a[0-9]*'):
                if attempt.resolve() != attempt or not attempt.is_dir():
                    raise ValueError('成片临时目录存在路径跳转，停止重新生成')
                cached_final = attempt / 'final.mp4'
                if cached_final.resolve() != cached_final or (cached_final.exists() and not cached_final.is_file()):
                    raise ValueError('成片临时视频路径异常，停止重新生成')
                old_files.add(cached_final)
            receipt = job_root / 'publication.json'
            if receipt.resolve() != receipt:
                raise ValueError('成片发布凭据路径异常，停止重新生成')
            deletions[row['id']] = [receipt, *sorted(old_files)]
            source_audio = plan.get('source_has_audio', plan.get('has_audio', False))
            plan.update(insertions=insertions, frames=frames, source_frames=source_frames,
                        source_has_audio=source_audio, has_audio=source_audio or has_insert_audio,
                        target=str(target), name=target.stem, automatic=False, regeneration=version)
            plans.append((json.dumps(plan, ensure_ascii=False), row['id']))
        # Keep the old policy, output identity and failure evidence even for
        # waiting/cancelled attempts that never created an on-disk render plan.
        for row in rows:
            save(composer.root / row['id'][:12] / 'regeneration_history' / (uuid.uuid4().hex + '.json'), dict(row))
        # All prerequisites are checked before deletion. Deletion is intentional and
        # irreversible; failures must leave affected jobs stopped, never auto-restored.
        touched = []
        try:
            for plan_json, job_id in plans:
                touched.append((plan_json, job_id))
                for path in deletions[job_id]:
                    path.unlink(missing_ok=True)
            conn.executemany("UPDATE final_jobs SET plan=?,status='waiting',stage='等待重新生成',progress=0,error='',output_path='',output_sha256='',package_path='',started_at=NULL,completed_at=NULL WHERE id=?", plans)
            conn.commit()
        except OSError as exc:
            message = '删除旧成品失败，已停止重新生成；已删除的视频不会恢复，请解除文件占用后重试：' + str(exc)
            conn.executemany("UPDATE final_jobs SET plan=?,status='error',stage='删除旧成品失败',progress=0,error=?,output_path='',output_sha256='',package_path='',started_at=NULL,completed_at=NULL WHERE id=?",
                             [(plan_json, message, job_id) for plan_json, job_id in touched])
            conn.commit()
            for _, job_id in touched: composer.project(job_id)
            raise ValueError(message) from exc
        for _, job_id in plans:
            composer.project(job_id)
    # Explicit submissions do not bypass the existing global pause switch.
    composer.start()
    composer.wake.set()
    return {'regenerated_count': len(plans)}
