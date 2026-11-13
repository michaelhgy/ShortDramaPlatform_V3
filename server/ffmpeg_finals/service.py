"""Serial FFmpeg final jobs share one transaction with template quota records."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import json
import math
import hashlib
import shutil
import threading
import time
import uuid
from pathlib import Path
from server.ffmpeg_diagnostics import AttemptDiagnostics, phase, plan_metadata, current, operation
from server.encoder_status import job_encoder_status
from server.ffmpeg_templates.renderer import read,save,sha,probe
from server.ffmpeg_templates.precompose import verified_file
from .renderer import FinalRenderer,load_template
from .lifecycle import final_job_lock, visible_task_ids, reconcile_detached_records
from server.production_order import ordered_tasks
from server.account_visibility import hide_cancelled_rows


def now():return datetime.now().isoformat(timespec='seconds')


def _insertion_strategy_for(task, material, settings=None):
    """Freeze the effective per-field inheritance at submission."""
    from server import v2_file_service as business_service
    settings = business_service.get_v2_settings() if settings is None else settings
    stored_global = settings.get(business_service.ENGINE_PARAMETER_KEY)
    base = business_service.resolve_midroll_endroll_strategy(stored_global)
    # An untouched FFmpeg installation had no insertion settings in use.
    # Explicitly saving the global card activates its displayed choices.
    if stored_global is None:
        for key in ('midroll', 'endroll'):
            base[key] = {**base[key], 'enabled': False}
    for owner in (task, material):
        raw = owner.get('midroll_endroll_strategy')
        if not raw:
            continue
        try:
            override = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(override, dict):
                raise ValueError('插片覆盖不是对象')
            override = business_service.normalize_insertion_override(override)
            base = business_service.merge_insertion_strategy(base, override)
        except (ValueError, TypeError) as exc:
            raise ValueError('插片覆盖记录无效，请重新保存设置') from exc
    mid = base['midroll']
    if float(mid['position_start_seconds']) <= 0 or float(mid['position_start_seconds']) > float(mid['position_end_seconds']):
        raise ValueError('中插位置必须大于0，且下限不能大于上限')
    return base


def _latest_insertion(root: Path, prefix: str) -> Path | None:
    from server import v2_file_service as business_service
    candidates = [path for path in root.iterdir()
                  if path.is_file() and path.name.startswith(prefix)
                  and path.suffix.lower() in business_service.VIDEO_EXTENSIONS] if root.is_dir() else []
    return sorted(candidates, key=lambda path: business_service.natural_key(path.name))[-1] if candidates else None


def _pick_insertion_path(root: Path, slot: dict[str, object], label: str) -> Path:
    if str(slot.get('mode') or 'latest') == 'locked':
        path = root / Path(str(slot.get('file') or '')).name
        if not path.is_file():
            raise ValueError(f'{label}指定的素材不存在：{path.name}')
    else:
        path = _latest_insertion(root, label)
        if path is None:
            raise ValueError(f'生成资源/引流视频缺少可用的{label}素材')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'{label}素材不属于引流视频目录')
    return path


def _build_insertions(task, material, source_frames: int, source_sha256: str, workspace: Path, settings=None):
    strategy = _insertion_strategy_for(task, material, settings)
    root = Path(workspace) / '生成资源' / '引流视频'
    source_seconds = source_frames / 30
    records = {'strategy': strategy, 'midroll': {'status': 'disabled'}, 'endroll': {'status': 'disabled'}}
    segments = []
    total_frames = source_frames
    has_insert_audio = False

    def insertion(slot_name, label):
        nonlocal total_frames, has_insert_audio
        path = _pick_insertion_path(root, strategy[slot_name], label)
        media = probe(path)
        video = next((stream for stream in media['streams'] if stream['codec_type'] == 'video'), None)
        if video is None:
            raise ValueError(f'{label}素材没有视频流')
        duration = float(video.get('duration') or media['format']['duration'])
        if not math.isfinite(duration) or duration <= 0 or duration > 7200:
            raise ValueError(f'{label}素材时长无效或超过120分钟')
        frames = max(1, math.ceil(duration * 30 - 1e-5))
        audio = any(stream['codec_type'] == 'audio' for stream in media['streams'])
        item = {'kind': 'insertion', 'slot': slot_name, 'path': str(path), 'sha256': sha(path), 'frames': frames, 'has_audio': audio}
        total_frames += frames
        has_insert_audio |= audio
        records[slot_name] = {'status': 'inserted', 'path': str(path), 'sha256': item['sha256'], 'duration_frames': frames}
        return item

    mid = strategy['midroll']
    threshold = float(mid['min_source_duration_seconds'])
    start, end = float(mid['position_start_seconds']), float(mid['position_end_seconds'])
    low_frame = max(1, math.ceil(start * 30 - 1e-5))
    high_frame = min(source_frames - 1, math.floor(end * 30 + 1e-5))
    if mid['enabled']:
        # Short/ineligible material needs no midroll resource at all.
        if source_seconds < threshold:
            records['midroll'] = {'status': 'skipped_short_source', 'source_duration_seconds': source_seconds, 'threshold_seconds': threshold}
        elif high_frame < low_frame:
            records['midroll'] = {'status': 'skipped_invalid_window', 'source_duration_seconds': source_seconds, 'range_seconds': [start, end]}
        else:
            digest = hashlib.sha256(f'{material["id"]}:{source_sha256}'.encode('utf-8')).digest()
            insert_frame = low_frame + int.from_bytes(digest[:8], 'big') % (high_frame - low_frame + 1)
            middle = insertion('midroll', '中插')
            records['midroll'].update(insert_at_seconds=insert_frame / 30, range_seconds=[start, end], threshold_seconds=threshold)
            segments.extend([{'kind': 'source', 'source_start_frame': 0, 'frames': insert_frame}, middle,
                             {'kind': 'source', 'source_start_frame': insert_frame, 'frames': source_frames - insert_frame}])
    if not segments:
        segments.append({'kind': 'source', 'source_start_frame': 0, 'frames': source_frames})
    if strategy['endroll']['enabled']:
        segments.append(insertion('endroll', '尾插'))
    records.update(segments=segments, total_frames=total_frames)
    return records, total_frames, has_insert_audio


class FinalComposer:
    def __init__(self,library,render=None):
        self.lib=library;self.root=library.data_root/'fg'
        self.render=render or (lambda folder,plan,progress:FinalRenderer(folder,progress).render(plan))
        self.lock=final_job_lock(library.data_root);self.wake=threading.Event();self.stop=threading.Event();self.thread=None
        self.auto_error='';self.auto_blocked={}
        self.session_id=uuid.uuid4().hex;self.sequence=0;self.last_finished=None;self.loop_timing={}
        with closing(self.lib.connect()) as c:
            c.execute("INSERT OR IGNORE INTO library_settings VALUES('final_paused','false')")
            c.execute("INSERT OR IGNORE INTO library_settings VALUES('final_automatic','false')")
            self.auto_enabled=c.execute("SELECT value FROM library_settings WHERE key='final_automatic'").fetchone()[0]=='true'
            c.commit()

    def snapshot(self):
        with closing(self.lib.connect()) as c:
            jobs=[dict(r) for r in c.execute("SELECT id,task_id,material_id,template_id,status,progress,stage,error,attempt,created_at,started_at,completed_at,output_path, json_extract(plan,'$.name') AS name,json_extract(plan,'$.account_name') AS account_name,json_extract(plan,'$.drama_name') AS drama_name,json_extract(plan,'$.frames') AS frames,json_extract(plan,'$.insertions') AS insertions,json_extract(plan,'$.automatic') AS automatic,rowid AS queue_sequence FROM final_jobs ORDER BY created_at DESC,rowid")]
            paused=c.execute("SELECT value FROM library_settings WHERE key='final_paused'").fetchone()[0]=='true'
        visible=visible_task_ids(self.lib.business_connection)
        jobs=[j for j in jobs if j['task_id'] in visible]
        with closing(self.lib.business_connection()) as b:
            jobs=hide_cancelled_rows(b,jobs)
            ranks={r['id']:index for index,r in enumerate(ordered_tasks(b))}
        waiting=iter(sorted((j for j in jobs if j['status']=='waiting'),key=lambda j:(ranks.get(j['task_id'],10**12),j['created_at'],j['queue_sequence'])))
        jobs=[next(waiting) if j['status']=='waiting' else j for j in jobs]
        for j in jobs:
            j.pop('queue_sequence',None)
            j['insertions'] = json.loads(j['insertions']) if j.get('insertions') else None
            j['auto_held']=bool(j['status']=='waiting' and j['automatic'] and not self.auto_enabled)
            j['elapsed_seconds']=max(0,int((datetime.fromisoformat(j['completed_at'] or now())-datetime.fromisoformat(j['started_at'] or now())).total_seconds()))
            j['encoding']=job_encoder_status(self.root,j)
        return {'jobs':jobs,'paused':paused,'auto_enabled':self.auto_enabled,'auto_error':self.auto_error,'counts':{s:sum(j['status']==s for j in jobs) for s in ('waiting','running','done','error','cancelled')}}

    def set_automatic(self,enabled):
        if not isinstance(enabled,bool):raise ValueError('自动合成开关无效')
        with self.lock,closing(self.lib.connect()) as c:
            c.execute("INSERT INTO library_settings(key,value) VALUES('final_automatic',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('true' if enabled else 'false',));c.commit()
            self.auto_enabled=enabled;self.auto_error=''
        if enabled:self.auto_blocked.clear();self.start()
        self.wake.set()
        return self.snapshot()

    def automatic_tick(self):
        """Queue ready cards in the same order, without selecting/scanning on behalf of the user."""
        if not self.auto_enabled:return False
        with closing(self.lib.business_connection()) as b,closing(self.lib.connect()) as c:
            if c.execute("SELECT value FROM library_settings WHERE key='final_paused'").fetchone()[0]=='true':return False
            tasks=[r for r in ordered_tasks(b) if r.get('release_status')!='registered']
            selections={r[0]:r[1] for r in c.execute('SELECT task_id,template_id FROM selections')}
            jobs=[dict(r) for r in c.execute('SELECT task_id,material_id,status FROM final_jobs')]
            known={r['material_id'] for r in jobs}
            failed={r['task_id'] for r in jobs if r['status'] in ('error','cancelled')}
            materials={}
            for r in b.execute("SELECT task_id,id,updated_at,midroll_endroll_strategy FROM production_files WHERE file_type='original_material' AND status='available'"):materials.setdefault(r[0],[]).append(r[1])
            material_rules=tuple((r[0],r[1],r[2],r[3]) for r in b.execute("SELECT task_id,id,updated_at,midroll_endroll_strategy FROM production_files WHERE file_type='original_material' AND status='available'"))
            templates={r['id']:(r['file_path'],r['mtime_ns'],r['present']) for r in c.execute('SELECT * FROM templates')}
            quota=c.execute('SELECT COUNT(*) FROM outputs').fetchone()[0]
            job_state=tuple(sorted((r['task_id'],r['material_id'],r['status']) for r in jobs))
        from server import v2_file_service as business_service
        settings_fingerprint=json.dumps(business_service.get_v2_settings().get(business_service.ENGINE_PARAMETER_KEY),sort_keys=True)
        insertion_root=Path(self.lib.workspace)/'生成资源'/'引流视频'
        resource_fingerprint=tuple(sorted((p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in insertion_root.iterdir() if p.is_file())) if insertion_root.is_dir() else ()
        for task in tasks:
            if not self.auto_enabled:return False
            identity=task['id'];ids=materials.get(identity,[])
            if identity not in selections or identity in failed or not any(i not in known for i in ids):continue
            fingerprint=(selections[identity],tuple(sorted(ids)),quota,templates.get(selections[identity],''),job_state,settings_fingerprint,task.get('midroll_endroll_strategy'),material_rules,resource_fingerprint)
            if self.auto_blocked.get(identity)==fingerprint:continue
            try:
                with self.lock:result=self._create_locked(identity,automatic=True)
                self.auto_error=''
                if result['created_count']:return True
                self.auto_blocked[identity]=fingerprint
            except Exception as exc:
                self.auto_blocked[identity]=fingerprint;self.auto_error=str(exc)
        return False

    def create(self,task_id):
        with self.lock:
            return self._create_locked(task_id)

    def _create_locked(self,task_id,automatic=False):
        with operation(self.root/'diagnostics','prepare_batch',task_id=task_id,automatic=automatic,session_id=self.session_id):
            return self._prepare_batch_locked(task_id,automatic)

    def _prepare_batch_locked(self,task_id,automatic=False):
        task=self.lib.task(task_id)
        if task.get('release_status')=='registered' or task.get('cleanup_status','active')!='active':raise ValueError('已结束任务不能再提交成片')
        from server import v2_file_service as business_service
        insertion_settings = business_service.get_v2_settings()
        with self.lock,closing(self.lib.business_connection()) as b,closing(self.lib.connect()) as c:
            materials=b.execute("SELECT * FROM production_files WHERE task_id=? AND file_type='original_material' AND status='available' ORDER BY sequence_no,file_name",(task_id,)).fetchall()
            pending=[];skipped=0
            for m in materials:
                prior=c.execute('SELECT * FROM final_jobs WHERE task_id=? AND material_id=?',(task_id,m['id'])).fetchone()
                if prior:
                    if prior['status'] in ('error','cancelled'):raise ValueError('本任务有失败或已取消成片，请先按对应记录重试')
                    skipped+=1;continue
                old=b.execute('SELECT * FROM production_video_tasks WHERE task_id=? AND source_material_id=?',(task_id,m['id'])).fetchone()
                if old:
                    if old['output_path'] and Path(old['output_path']).is_file():skipped+=1;continue
                    raise ValueError('本任务仍有旧剪映成片记录，请先处理旧任务；新素材可在独立生产任务中合成')
                pending.append(dict(m))
            if not pending:
                if skipped:
                    if not automatic:
                        c.execute("UPDATE final_jobs SET plan=json_set(plan,'$.automatic',0) WHERE task_id=? AND status='waiting'",(task_id,));c.commit()
                    self.start();self.wake.set()
                    return {'created_count':0,'skipped_count':skipped}
                raise ValueError('请先扫描有效素材')
            c.execute('BEGIN IMMEDIATE')
            selected=c.execute('SELECT template_id FROM selections WHERE task_id=?',(task_id,)).fetchone()
            if not selected:raise ValueError('请先在模板区域选用一个模板')
            template_id=selected[0];row=c.execute('SELECT * FROM templates WHERE id=?',(template_id,)).fetchone()
            if row is None or c.execute('SELECT 1 FROM deleted_templates WHERE id=?',(template_id,)).fetchone():raise ValueError('所选模板已删除，请重新选择')
            path=self.lib.current_file(row)
            if path is None:raise ValueError('所选模板文件已变化或不存在，请刷新模板')
            conflict=self.lib.conflict(c,template_id,task)
            if conflict:raise ValueError(conflict)
            if not self.lib.can_use(c,template_id,task['drama_key']):raise ValueError('模板的剧集使用名额已满，请选择其他模板')
            with operation(self.root/'diagnostics','template_recipe_check',task_id=task_id,template_id=template_id):
                template=load_template(path,template_id,self.lib.data_root)
            created=[]
            for m in pending:
                source=Path(m['file_path']).resolve();final_root=Path(task['final_path']).resolve()
                if not source.is_relative_to(self.lib.workspace) or not source.is_file():raise ValueError('素材文件不可用，请重新扫描')
                if not final_root.is_relative_to(self.lib.workspace):raise ValueError('成片目录不属于当前工作区')
                with operation(self.root/'diagnostics','source_probe',task_id=task_id,material_id=m['id']):
                    media=probe(source);video=next(s for s in media['streams'] if s['codec_type']=='video')
                frames=math.ceil(float(video.get('duration') or media['format']['duration'])*30-1e-5)
                if not 1<=frames<=30*60*120:raise ValueError('素材时长无效或超过120分钟')
                target=final_root/(Path(m['file_name']).stem+'.mp4')
                if target.exists():raise ValueError('成片文件已存在，已停止以免覆盖：'+target.name)
                with operation(self.root/'diagnostics','submission_source_hash',task_id=task_id,material_id=m['id'],bytes=source.stat().st_size):
                    source_digest = sha(source)
                insertion_plan, total_frames, has_insert_audio = _build_insertions(task, m, frames, source_digest, self.lib.workspace, insertion_settings)
                plan={'task_id':task_id,'material_id':m['id'],'name':target.stem,'account_name':task['account_name'],'drama_name':task['drama_name'],'drama_key':task['drama_key'],'source_path':str(source),'source_sha256':source_digest,'target':str(target),'frames':total_frames,'source_frames':frames,'source_has_audio':any(s['codec_type']=='audio' for s in media['streams']),'has_audio':any(s['codec_type']=='audio' for s in media['streams']) or has_insert_audio,'template_id':template_id,'template':template,'insertions':insertion_plan}
                plan['automatic']=automatic
                identity=uuid.uuid4().hex
                c.execute('INSERT INTO final_jobs(id,task_id,material_id,template_id,status,plan,created_at) VALUES(?,?,?,?,?,?,?)',(identity,task_id,m['id'],template_id,'waiting',json.dumps(plan,ensure_ascii=False),now()))
                created.append(identity)
            if not automatic:c.execute("UPDATE final_jobs SET plan=json_set(plan,'$.automatic',0) WHERE task_id=? AND status='waiting'",(task_id,))
            c.commit()
        for identity in created:self.project(identity)
        self.start();self.wake.set()
        return {'created_count':len(created),'skipped_count':skipped,'ids':created}

    def regenerate(self, task_id=None, identity=None):
        from .regeneration import regenerate
        return regenerate(self, task_id=task_id, identity=identity)

    def project(self,identity):
        with self.lock:
            return self._project_locked(identity)

    def _project_locked(self,identity):
        with closing(self.lib.connect()) as c:r=c.execute('SELECT * FROM final_jobs WHERE id=?',(identity,)).fetchone()
        if r is None:return
        with closing(self.lib.business_connection()) as b:
            if not b.execute("SELECT 1 FROM production_tasks WHERE id=? AND COALESCE(cleanup_status,'active')='active'",(r['task_id'],)).fetchone():return
            if not b.execute('SELECT 1 FROM production_files WHERE id=?',(r['material_id'],)).fetchone():return
            b.execute("INSERT OR IGNORE INTO production_video_tasks(id,task_id,source_material_id,status,draft_path,output_path,created_at,updated_at) VALUES(?,?,?,'ffmpeg_waiting','','',?,?)",(r['id'],r['task_id'],r['material_id'],r['created_at'],now()))
            b.execute("UPDATE production_video_tasks SET status=?,output_path=?,error_message=?,started_at=?,finished_at=?,updated_at=? WHERE id=?",('ffmpeg_'+r['status'],r['output_path'] or '',r['error'],r['started_at'] or '',r['completed_at'] or '',now(),r['id']))
            b.commit()

    def action(self,action,identity=None):
        with self.lock,closing(self.lib.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            if action in ('pause','resume'):
                c.execute("UPDATE library_settings SET value=? WHERE key='final_paused'",('true' if action=='pause' else 'false',))
            else:
                r=c.execute('SELECT * FROM final_jobs WHERE id=?',(identity,)).fetchone()
                if not r:raise ValueError('成片任务不存在')
                if action=='cancel':
                    if r['status']!='waiting':raise ValueError('只能取消等待中的成片，当前成片完成后可暂停后续任务')
                    c.execute("UPDATE final_jobs SET status='cancelled',stage='已取消',completed_at=? WHERE id=?",(now(),identity))
                elif action=='retry':
                    if r['status'] not in ('error','cancelled'):raise ValueError('只可重试失败或已取消的成片')
                    task=self.lib.task(r['task_id'])
                    if task.get('release_status')=='registered' or task.get('cleanup_status','active')!='active':raise ValueError('已结束任务不能重试')
                    t=c.execute('SELECT * FROM templates WHERE id=?',(r['template_id'],)).fetchone()
                    if not t or self.lib.current_file(t) is None or c.execute('SELECT 1 FROM deleted_templates WHERE id=?',(r['template_id'],)).fetchone():raise ValueError('原模板已删除或不可用')
                    if not self.lib.can_use(c,r['template_id'],task['drama_key']):raise ValueError('原模板的剧集使用名额已满')
                    c.execute("UPDATE final_jobs SET status='waiting',stage='等待重试',progress=0,error='',started_at=NULL,completed_at=NULL,plan=json_set(plan,'$.automatic',0) WHERE id=?",(identity,))
                else:raise ValueError('不支持的操作')
            c.commit()
        if identity:self.project(identity)
        if action in ('resume','retry'):self.start();self.wake.set()
        return self.snapshot()

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self.thread=threading.Thread(target=self.loop,name='v3-ffmpeg-finals',daemon=True);self.thread.start()

    def loop(self):
        while not self.stop.is_set():
            try:
                tick=time.monotonic()
                self.automatic_tick()
                self.loop_timing={'automatic_tick_seconds':round(time.monotonic()-tick,3)}
                if not self.run_next():self.wake.wait(2);self.wake.clear()
            except Exception as exc:
                self.auto_error=str(exc);self.wake.wait(2);self.wake.clear()

    def recover(self):
        with closing(self.lib.connect()) as c:
            c.execute("UPDATE final_jobs SET status='error',stage='合成中断',error='软件在合成过程中退出，可按原配方重试',completed_at=? WHERE status='running'",(now(),));c.commit()
        reconcile_detached_records(self.lib)
        with closing(self.lib.connect()) as c:
            ids=[r[0] for r in c.execute('SELECT id FROM final_jobs')]
        for identity in ids:self.project(identity)

    def run_next(self):
        claim_started=time.monotonic()
        with self.lock,closing(self.lib.connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT value FROM library_settings WHERE key='final_paused'").fetchone()[0]=='true':return False
            if c.execute("SELECT 1 FROM final_jobs WHERE status='running'").fetchone():return False
            visible=visible_task_ids(self.lib.business_connection)
            with closing(self.lib.business_connection()) as b:ranks={r['id']:index for index,r in enumerate(ordered_tasks(b))}
            candidates=[row for row in c.execute("SELECT * FROM final_jobs WHERE status='waiting' ORDER BY created_at,rowid") if row['task_id'] in visible and (self.auto_enabled or not json.loads(row['plan']).get('automatic'))]
            r=min(candidates,key=lambda row:ranks.get(row['task_id'],10**12)) if candidates else None
            if not r:return False
            row=dict(r);identity=row['id'];attempt=row['attempt']+1
            c.execute("UPDATE final_jobs SET status='running',stage='准备合成',started_at=?,attempt=? WHERE id=?",(now(),attempt,identity));c.commit()
        plan=json.loads(row['plan']);folder=self.root/identity[:12]/f'a{attempt}';target=Path(plan['target']);receipt=self.root/identity[:12]/'publication.json'
        self.sequence+=1
        metadata=plan_metadata(plan,job_id=identity,attempt=attempt,session_id=self.session_id,
            sequence=self.sequence,created_at=row['created_at'],claimed_at=now(),
            dispatch_seconds=round(time.monotonic()-claim_started,3),waiting_candidates=len(candidates),
            candidate_plan_chars=sum(len(item['plan']) for item in candidates),
            gap_since_previous_seconds=round(time.monotonic()-self.last_finished,3) if self.last_finished else None,
            loop_timing=self.loop_timing)
        def progress(value,stage):
            start=time.monotonic()
            try:
                with closing(self.lib.connect()) as c:
                    c.execute('UPDATE final_jobs SET progress=?,stage=? WHERE id=?',(value,stage,identity));c.commit()
            finally:
                if current(): current().progress_write(time.monotonic()-start)
        try:
            with AttemptDiagnostics(folder,self.root/'diagnostics',metadata):
                with phase('project_running_state'): self.project(identity)
                with phase('load_business_task'): task=self.lib.task(row['task_id'])
                if task.get('cleanup_status','active')!='active' or task.get('release_status')=='registered':raise ValueError('生产任务已结束，停止合成')
                with phase('source_hash_validation'):
                    if not Path(plan['source_path']).is_file() or not verified_file(Path(plan['source_path']),plan['source_sha256']):raise ValueError('原素材已变化，保留任务配方并停止')
                if target.exists():
                    if not receipt.is_file() or read(receipt).get('job_id')!=identity or read(receipt).get('target')!=str(target) or read(receipt).get('regeneration')!=plan.get('regeneration') or sha(target)!=read(receipt)['sha256']:raise ValueError('目标成片已存在且不属于本次任务，停止以免覆盖')
                    digest=read(receipt)['sha256']
                else:
                    folder.mkdir(parents=True,exist_ok=True);save(folder/'plan.json',plan)
                    with phase('render'): result=self.render(folder,plan,progress)
                    progress(99,'校验通过，正在保存到成片目录')
                    with phase('output_hash',bytes=Path(result).stat().st_size): digest=sha(result)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    pending=target.with_name('.'+identity+f'.a{attempt}.publishing')
                    if pending.exists():pending=target.with_name('.'+uuid.uuid4().hex+'.publishing')
                    with phase('publish_copy',bytes=Path(result).stat().st_size): shutil.copy2(result,pending)
                    with phase('publish_hash',bytes=pending.stat().st_size):
                        if sha(pending)!=digest:raise RuntimeError('成片发布校验失败')
                    save(receipt,{'job_id':identity,'sha256':digest,'target':str(target),'frames':plan['frames'],'package_path':str(folder),'regeneration':plan.get('regeneration')})
                    with phase('publish_rename'): pending.rename(target)
                with phase('commit_completion'),closing(self.lib.connect()) as c:
                    c.execute('BEGIN IMMEDIATE')
                    c.execute('INSERT OR IGNORE INTO outputs(output_id,task_id,template_id,account_key,account_name,drama_key,drama_name,output_path) VALUES(?,?,?,?,?,?,?,?)',(identity,row['task_id'],row['template_id'],task['account_key'],task['account_name'],task['drama_key'],task['drama_name'],str(target)))
                    c.execute('UPDATE outputs SET output_path=? WHERE output_id=?',(str(target),identity))
                    c.execute("UPDATE final_jobs SET status='done',stage='生成完成',progress=100,error='',completed_at=?,output_path=?,output_sha256=?,package_path=? WHERE id=?",(now(),str(target),digest,str(folder),identity));c.commit()
                with phase('project_completed_state'): self.project(identity)
        except Exception as exc:
            with closing(self.lib.connect()) as c:
                c.execute("UPDATE final_jobs SET status='error',stage='合成失败',error=?,completed_at=? WHERE id=?",(str(exc)[-2500:],now(),identity));c.commit()
            self.project(identity)
        self.last_finished=time.monotonic()
        return True


_instances={};_lock=threading.Lock()

def get_composer():
    from server import v2_file_service as service
    from server.template_library import TemplateLibrary
    workspace,data=service.require_configured_paths();key=(str(workspace),str(data))
    with _lock:
        if key not in _instances:
            composer=FinalComposer(TemplateLibrary(workspace,data,service.connection,service.probe_resource_metadata));composer.recover();_instances[key]=composer
        return _instances[key]
