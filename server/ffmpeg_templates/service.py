"""Durable, serial template jobs. Only successful published templates consume scenery quota."""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import json
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from server.encoder_status import job_encoder_status
from .config import DEFAULTS, validate
from . import renderer
from .scenery_usage import scheduled_scenery


SCHEMA_VERSION = 3


def now(): return datetime.now().isoformat(timespec='seconds')


class TemplateMaker:
    def __init__(self, workspace, data_root, publish=None, render=None):
        self.workspace=Path(workspace).resolve();self.root=Path(data_root)/'template_generation'
        self.root.mkdir(parents=True,exist_ok=True);self.db=self.root/'jobs.db'
        self.output=self.workspace/'内容资产/公共模板'
        self.publish=publish or (lambda: None)
        self.render=render or (lambda folder,plan,progress:renderer.Renderer(folder,progress).render(plan))
        from server.scenery.service import library_lock
        self.lock=library_lock(data_root);self.thread=None;self.stop=threading.Event();self.wake=threading.Event()
        from .photo_library import PhotoLibrary
        self.photos=PhotoLibrary(self.workspace,self.root.parent)
        with self.lock,self.connect() as c:
            if c.execute('PRAGMA user_version').fetchone()[0]>SCHEMA_VERSION:
                raise ValueError('模板制作记录来自更新版本，请使用对应的软件版本')
            c.executescript('''
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,created_at TEXT NOT NULL,config TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,ordinal INTEGER NOT NULL,status TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,stage TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',plan TEXT NOT NULL,created_at TEXT NOT NULL,started_at TEXT,completed_at TEXT,attempt INTEGER NOT NULL DEFAULT 0,output_path TEXT,output_sha256 TEXT,package_path TEXT);
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,path TEXT NOT NULL,name TEXT NOT NULL,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,frames INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS reservations(job_id TEXT NOT NULL,source_id TEXT NOT NULL,PRIMARY KEY(job_id,source_id));
            CREATE TABLE IF NOT EXISTS usages(job_id TEXT NOT NULL,source_id TEXT NOT NULL,PRIMARY KEY(job_id,source_id));
            ''')
            if 'display_name' not in {r[1] for r in c.execute('PRAGMA table_info(jobs)')}:
                c.execute("ALTER TABLE jobs ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
            counters={}
            for row in c.execute('SELECT id,created_at,display_name FROM jobs ORDER BY created_at,rowid').fetchall():
                day=row['created_at'][:10];counters[day]=counters.get(day,0)+1
                if not row['display_name']:
                    c.execute('UPDATE jobs SET display_name=? WHERE id=?',(f'模板{day[5:7]}{day[8:10]}-{counters[day]:03d}',row['id']))
            c.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
            c.execute("INSERT OR IGNORE INTO settings VALUES('config',?)",(json.dumps(DEFAULTS),))
            c.execute("INSERT OR IGNORE INTO settings VALUES('paused','false')")
            # Upgrade waiting jobs' reservations without changing their saved
            # recipes or already-settled historical usage.
            for row in c.execute("SELECT id,plan FROM jobs WHERE status='waiting'").fetchall():
                try:played={m['id'] for m in scheduled_scenery(json.loads(row['plan']))}
                except (ValueError,KeyError,TypeError):continue
                for reserved in c.execute('SELECT source_id FROM reservations WHERE job_id=?',(row['id'],)).fetchall():
                    if reserved[0] not in played:
                        c.execute('DELETE FROM reservations WHERE job_id=? AND source_id=?',(row['id'],reserved[0]))

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30);c.row_factory=sqlite3.Row
        try:
            yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()

    def config(self):
        with self.connect() as c:value={**deepcopy(DEFAULTS),**json.loads(c.execute("SELECT value FROM settings WHERE key='config'").fetchone()[0])}
        from contextlib import closing
        from server.template_library import TemplateLibrary
        library=TemplateLibrary(self.workspace,self.root.parent,None,None)
        with closing(library.connect()) as c:value['template_usage_limit']=library.usage_limit(c)
        return value

    def save_config(self,values):
        value=validate(values)
        from server.template_library import TemplateLibrary
        TemplateLibrary(self.workspace,self.root.parent,None,None).set_usage_limit(value['template_usage_limit'])
        with self.connect() as c:c.execute("UPDATE settings SET value=? WHERE key='config'",(json.dumps(value),))
        from server.scenery.service import SceneryLibrary
        SceneryLibrary(self.workspace,self.root.parent).clean_exhausted()
        self.photos.clean_exhausted()
        return value

    def scan(self):
        from server.scenery.service import SceneryLibrary
        library=SceneryLibrary(self.workspace,self.root.parent)
        library.clean_exhausted()
        files=[];errors=[];seen=set()
        for a in library.ready_assets():
            if not a['valid']:
                errors.append(a['name']+'：文件缺失或变化');continue
            if not a['remaining'] or a['sha256'] in seen:continue
            seen.add(a['sha256'])
            files.append({'id':a['sha256'],'path':a['path'],'name':a['name'],'size':a['size'],'mtime_ns':a['mtime'],'frames':a['frames']})
        with self.connect() as c:
            for m in files:c.execute('INSERT OR REPLACE INTO sources VALUES(:id,:path,:name,:size,:mtime_ns,:frames)',m)
        return files,errors

    def create(self,count,request_id):
        if type(count) is not int or not 1<=count<=500:raise ValueError('生成数量必须为1—500的整数')
        try:uuid.UUID(request_id)
        except (ValueError,TypeError,AttributeError):raise ValueError('生成请求编号无效')
        with self.lock:
            with self.connect() as c:
                prior=c.execute('SELECT id FROM batches WHERE request_id=?',(request_id,)).fetchone()
                if prior:return {'batch_id':prior[0],'reused':True}
            config=self.config();materials,warnings=self.scan();batch=uuid.uuid4().hex;created=now()
            if config['photo_layer_enabled']:self.photos.refresh()
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                used={r[0]:r[1] for r in c.execute('SELECT source_id,COUNT(*) FROM (SELECT * FROM usages UNION ALL SELECT * FROM reservations) GROUP BY source_id')}
                c.execute('INSERT INTO batches VALUES(?,?,?,?,?)',(batch,request_id,'模板制作 '+created,created,json.dumps(config)))
                for i in range(count):
                    candidates=[m for m in materials if used.get(m['id'],0)<config['scenery_usage_limit']]
                    photos=self.photos.candidates(c,config['photo_usage_limit']) if config['photo_layer_enabled'] else []
                    plan=renderer.make_plan(deepcopy(config),candidates,secrets.randbits(60),photos=photos);job=uuid.uuid4().hex
                    c.execute('INSERT INTO jobs(id,batch_id,ordinal,status,plan,created_at) VALUES(?,?,?,?,?,?)',(job,batch,i+1,'waiting',json.dumps(plan,ensure_ascii=False),created))
                    serial=c.execute('SELECT COUNT(*) FROM jobs WHERE substr(created_at,6,5)=?',(created[5:10],)).fetchone()[0]
                    name=f'模板{created[5:7]}{created[8:10]}-{serial:03d}'
                    while (self.output/(name+'.mp4')).exists() or c.execute('SELECT 1 FROM jobs WHERE display_name=?',(name,)).fetchone():
                        serial+=1;name=f'模板{created[5:7]}{created[8:10]}-{serial:03d}'
                    c.execute('UPDATE jobs SET display_name=? WHERE id=?',(name,job))
                    for m in scheduled_scenery(plan):
                        used[m['id']]=used.get(m['id'],0)+1
                        c.execute('INSERT INTO reservations VALUES(?,?)',(job,m['id']))
                    from .fullscreen_layers import photo_sources
                    self.photos.reserve(c,job,photo_sources(plan),config['photo_usage_limit'])
            self.start();self.wake.set()
            return {'batch_id':batch,'count':count,'warnings':warnings,'reused':False}

    def snapshot(self):
        with self.connect() as c:
            rows=[dict(r) for r in c.execute("SELECT j.id,j.display_name,j.batch_id,j.ordinal,j.status,j.progress,j.stage,j.error,j.created_at,j.started_at,j.completed_at,j.attempt,j.output_path,j.output_sha256,j.package_path,b.name AS batch_name,json_extract(j.plan, '$.seconds') AS seconds,json_extract(j.plan, '$.stickers.family') AS family FROM jobs j JOIN batches b ON b.id=j.batch_id ORDER BY j.created_at DESC,j.batch_id,j.ordinal")]
            paused=json.loads(c.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0])
        from contextlib import closing
        from server.template_library import TemplateLibrary
        library=TemplateLibrary(self.workspace,self.root.parent,None,None)
        with closing(library.connect()) as c:
            deleted={r[0] for r in c.execute('SELECT id FROM deleted_templates')}
            exhausted={r[0] for r in c.execute('SELECT template_id FROM outputs GROUP BY template_id HAVING COUNT(DISTINCT drama_key)>=?',(library.usage_limit(c),))}
        # Only the visible projection changes; job, recipe and usage history stay intact.
        rows=[r for r in rows if r['status']!='done' or (r['output_sha256'] not in deleted and Path(r['output_path'] or '').is_file())]
        for r in rows:
            r['elapsed_seconds']=int((datetime.fromisoformat(r.get('completed_at') or now())-datetime.fromisoformat(r.get('started_at') or now())).total_seconds())
            r['encoding']=job_encoder_status(self.root.parent/'tg',r)
            r['availability']='exhausted' if r['output_sha256'] in exhausted else 'available'
            r['preview_url']=f"/api/v3/template-generation/jobs/{r['id']}/preview" if r['status']=='done' and r['output_sha256'] not in exhausted and Path(r['output_path'] or '').is_file() else None
        counts={s:sum(j['status']==s for j in rows) for s in ['waiting','running','done','error','cancelled']}
        return {'jobs':rows,'paused':paused,'counts':counts,'output_directory':str(self.output)}

    def pause(self,paused):
        with self.connect() as c:c.execute("UPDATE settings SET value=? WHERE key='paused'",(json.dumps(bool(paused)),))
        if not paused:self.start()
        self.wake.set();return self.snapshot()

    def retry(self,job):
        with self.lock,self.connect() as c:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
            if not r or r['status']!='error':raise ValueError('仅可重试失败的模板任务')
            plan=json.loads(r['plan'])
            from .fullscreen_layers import photo_sources
            self.photos.reserve(c,job,photo_sources(plan),min(plan['config'].get('photo_usage_limit',self.photos.limit(c)),self.photos.limit(c)))
            for m in scheduled_scenery(plan):
                n=c.execute('SELECT COUNT(*) FROM (SELECT * FROM usages UNION ALL SELECT * FROM reservations) WHERE source_id=?',(m['id'],)).fetchone()[0]
                if n>=plan['config']['scenery_usage_limit']:raise ValueError('原风景素材已达到使用上限，无法按原配方重试')
                c.execute('INSERT OR IGNORE INTO reservations VALUES(?,?)',(job,m['id']))
            c.execute("UPDATE jobs SET status='waiting',error='',progress=0,stage='等待重试',started_at=NULL,completed_at=NULL WHERE id=?",(job,))
        self.start();self.wake.set();return self.snapshot()

    def cancel(self,job):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute("UPDATE jobs SET status='cancelled',stage='已取消' WHERE id=? AND status='waiting'",(job,))
            if not r.rowcount:raise ValueError('仅可取消尚未开始的模板；正在制作时可暂停后续队列')
            c.execute('DELETE FROM reservations WHERE job_id=?',(job,))
            c.execute('DELETE FROM photo_reservations WHERE job_id=?',(job,))
        from server.scenery.service import SceneryLibrary
        SceneryLibrary(self.workspace,self.root.parent).clean_exhausted()
        self.photos.clean_exhausted()
        return self.snapshot()

    def recover(self):
        with self.connect() as c:
            c.execute("DELETE FROM reservations WHERE job_id IN (SELECT id FROM jobs WHERE status='running')")
            c.execute("DELETE FROM photo_reservations WHERE job_id IN (SELECT id FROM jobs WHERE status='running')")
            c.execute("UPDATE jobs SET status='error',stage='制作中断',error='软件在制作过程中退出，请重试；已有过程文件保留',completed_at=? WHERE status='running'",(now(),))

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self.thread=threading.Thread(target=self._loop,name='v3-ffmpeg-templates',daemon=True);self.thread.start()

    def _loop(self):
        while not self.stop.is_set():
            if not self.run_next():self.wake.wait(2);self.wake.clear()

    def run_next(self):
        with self.lock,self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if json.loads(c.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]):return False
            if c.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():return False
            row=c.execute("SELECT * FROM jobs WHERE status='waiting' ORDER BY created_at,batch_id,ordinal LIMIT 1").fetchone()
            if not row:return False
            row=dict(row);attempt=row['attempt']+1
            c.execute("UPDATE jobs SET status='running',started_at=?,stage='准备制作',attempt=? WHERE id=?",(now(),attempt,row['id']))
        job=row['id'];plan=json.loads(row['plan']);folder=self.root.parent/'tg'/job[:12]/f'a{attempt}'
        def progress(value,stage):
            with self.connect() as c:c.execute('UPDATE jobs SET progress=?,stage=? WHERE id=?',(value,stage,job))
        try:
            # Validate immutable inputs even if renderer has cached intermediate layers.
            scenery=scheduled_scenery(plan)
            for m in scenery:
                if renderer.sha(m['path'])!=m['id']:raise ValueError('原风景素材已变化，保留任务配方并停止：'+m['name'])
            from .fullscreen_layers import photo_sources
            for photo in photo_sources(plan):
                if not self.photos.valid(photo,content=True):raise ValueError('真人图片缺失或已变化，保留任务配方并停止：'+photo['name'])
            folder.mkdir(parents=True,exist_ok=True);renderer.save(folder/'plan.json',plan)
            result=self.render(folder,plan,progress)
            digest=renderer.sha(result);self.output.mkdir(parents=True,exist_ok=True)
            target=self.output/f'{row["display_name"]}.mp4'
            legacy=self.output/f'模板_{row["created_at"][:10]}_{job[:12]}.mp4'
            if legacy.is_file():target=legacy
            sidecar=target.with_suffix('.template.json')
            if target.exists():
                # Recover a prior publication window without replacing a completed MP4.
                if not sidecar.is_file() or renderer.read(sidecar).get('job_id')!=job:raise FileExistsError('模板输出已存在且身份不符')
                digest=renderer.sha(target)
                if digest!=renderer.read(sidecar)['preview_sha256']:raise ValueError('已发布预览发生变化，保留现场并停止重试')
            else:
                pending=self.output/f'.{job}.publishing'
                if pending.exists():pending=self.output/f'.{job}.{attempt}.publishing'
                shutil.copy2(result,pending)
                if renderer.sha(pending)!=digest:raise RuntimeError('模板发布校验失败')
                renderer.save(sidecar,{'job_id':job,'display_name':row['display_name'],'format':'v3_layered_template_v1','package_path':str(folder),'preview_sha256':digest,'preview_only':True,'final_compositor_connected':True})
                pending.rename(target)
            progress(99,'登记到公共模板区域')
            published=self.publish()
            if isinstance(published,set) and digest not in published:raise RuntimeError('视频完成但公共模板索引未登记成功，请重试入库')
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                reserved={r[0] for r in c.execute('SELECT source_id FROM reservations WHERE job_id=?',(job,))}
                settled={r[0] for r in c.execute('SELECT source_id FROM usages WHERE job_id=?',(job,))}
                if not {m['id'] for m in scenery}<=reserved|settled:
                    raise RuntimeError('实际上屏风景的预留记录不完整，已保留发布结果，请重试')
                for m in scenery:c.execute('INSERT OR IGNORE INTO usages VALUES(?,?)',(job,m['id']))
                c.execute('DELETE FROM reservations WHERE job_id=?',(job,))
                c.execute('INSERT OR IGNORE INTO photo_usages SELECT * FROM photo_reservations WHERE job_id=?',(job,))
                c.execute('DELETE FROM photo_reservations WHERE job_id=?',(job,))
                package=renderer.read(sidecar)['package_path']
                c.execute("UPDATE jobs SET status='done',progress=100,stage='已入库',completed_at=?,output_path=?,output_sha256=?,package_path=?,error='' WHERE id=?",(now(),str(target),digest,package,job))
        except Exception as exc:
            with self.connect() as c:
                c.execute("UPDATE jobs SET status='error',stage='制作失败',error=?,completed_at=? WHERE id=?",(str(exc)[-3000:],now(),job))
                c.execute('DELETE FROM reservations WHERE job_id=?',(job,))
                c.execute('DELETE FROM photo_reservations WHERE job_id=?',(job,))
        from server.scenery.service import SceneryLibrary
        SceneryLibrary(self.workspace,self.root.parent).clean_exhausted()
        self.photos.clean_exhausted()
        return True

    def preview(self,job):
        with self.connect() as c:r=c.execute("SELECT output_path,output_sha256 FROM jobs WHERE id=? AND status='done'",(job,)).fetchone()
        if not r:raise ValueError('模板尚未完成')
        p=Path(r['output_path'])
        if not p.is_file() or not p.resolve().is_relative_to(self.output.resolve()):raise ValueError('模板文件不可用')
        return p


_instances={};_instance_lock=threading.Lock()

def get_maker():
    from server import v2_file_service as service
    from server.template_library import TemplateLibrary
    workspace,data=service.require_configured_paths();key=(str(workspace),str(data))
    with _instance_lock:
        if key not in _instances:
            lib=TemplateLibrary(workspace,data,service.connection,service.probe_resource_metadata)
            def publish():
                from contextlib import closing
                lib.refresh()
                with closing(lib.connect()) as conn:
                    return {r[0] for r in conn.execute('SELECT id FROM templates WHERE present=1')}
            maker=TemplateMaker(workspace,data,publish=publish);maker.recover();_instances[key]=maker
        return _instances[key]
