from __future__ import annotations
from contextlib import contextmanager, closing
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
import uuid

from server.ffmpeg_templates.renderer import probe, sha, hidden
from server.tool_resolver import resolve_ffmpeg, resolve_ffprobe
from .planning import time_segments,processing_plan,validate_plan
from .media import SceneryMedia,remux_eligible

_locks = {}
_guard = threading.Lock()

def library_lock(data):
    with _guard:
        return _locks.setdefault(str(Path(data).resolve()), threading.RLock())

def now(): return datetime.now().isoformat(timespec='seconds')

VIDEO = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}

class SceneryLibrary:
    def __init__(self, workspace, data_root, render=None):
        self.workspace=Path(workspace).resolve(); self.data=Path(data_root).resolve()
        self.original=self.workspace/'生成资源'/'原始风景视频'
        self.ready=self.workspace/'生成资源'/'风景视频'
        self.root=self.data/'scenery_processing'; self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'library.db'; self.lock=library_lock(self.data)
        self.thread=None; self.stop=threading.Event(); self.wake=threading.Event()
        self.render=render or self.render_crop
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                INSERT OR IGNORE INTO settings VALUES('serial','0');
                INSERT OR IGNORE INTO settings VALUES('paused','false');
                CREATE TABLE IF NOT EXISTS originals(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,name TEXT NOT NULL,size INTEGER NOT NULL,mtime INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,source_id TEXT NOT NULL,source_path TEXT NOT NULL,source_hash TEXT NOT NULL,source_meta TEXT NOT NULL,crops TEXT NOT NULL,status TEXT NOT NULL,progress INTEGER NOT NULL,stage TEXT NOT NULL,error TEXT NOT NULL,created_at TEXT NOT NULL,started_at TEXT,completed_at TEXT);
                CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,ordinal INTEGER NOT NULL,name TEXT UNIQUE NOT NULL,path TEXT UNIQUE NOT NULL,sha256 TEXT NOT NULL DEFAULT '',frames INTEGER NOT NULL DEFAULT 0,width INTEGER NOT NULL,height INTEGER NOT NULL,size INTEGER NOT NULL DEFAULT 0,mtime INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'staging',error TEXT NOT NULL DEFAULT '');
            ''')

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30);c.row_factory=sqlite3.Row
        try: yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()

    def scan(self):
        # Unknown files in the old folder are inputs, never auto-approved assets.
        with self.lock,self.connect() as c:
            self.original.mkdir(parents=True,exist_ok=True);self.ready.mkdir(parents=True,exist_ok=True)
            known={r[0] for r in c.execute('SELECT path FROM assets')}; present=set()
            for root in (self.original,self.ready):
                for path in sorted(root.rglob('*')):
                    if not path.is_file() or path.suffix.lower() not in VIDEO or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or str(path) in known:continue
                    st=path.stat(); identity=hashlib.sha256(str(path).encode()).hexdigest();present.add(identity)
                    c.execute('INSERT INTO originals VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,name=excluded.name',(identity,str(path),path.name,st.st_size,st.st_mtime_ns))
            for r in c.execute('SELECT id FROM originals').fetchall():
                if r['id'] not in present:c.execute('DELETE FROM originals WHERE id=?',(r['id'],))
        return self.snapshot()

    def raw(self, identity):
        with self.connect() as c:r=c.execute('SELECT * FROM originals WHERE id=?',(identity,)).fetchone()
        if not r:raise ValueError('原片不存在，请刷新')
        path=Path(r['path']);self.check_raw_path(path)
        return dict(r),path

    def check_raw_path(self,path):
        if not path.is_file() or path.is_symlink() or not any(path.resolve().is_relative_to(root.resolve()) for root in (self.original,self.ready)):raise ValueError('原片路径已变化或不属于风景目录')
        with self.connect() as c:
            if c.execute('SELECT 1 FROM assets WHERE path=?',(str(path),)).fetchone():raise ValueError('处理后的素材不能作为待删原片')

    def details(self, identity):
        row,path=self.raw(identity);d=probe(path);v=next(s for s in d['streams'] if s['codec_type']=='video')
        w,h=int(v['width']),int(v['height'])
        rotation=next((int(s.get('rotation',0)) for s in v.get('side_data_list',[]) if 'rotation' in s),int(v.get('tags',{}).get('rotate',0)))
        if abs(rotation)%180==90:w,h=h,w
        duration=float(v.get('duration') or d['format']['duration'])
        if not math.isfinite(duration) or duration<1:raise ValueError('原片至少需要1秒有效视频')
        segments=time_segments(duration,f"{row['id']}:{row['size']}:{row['mtime']}")
        video={key:v.get(key) for key in ('codec_name','pix_fmt','avg_frame_rate','r_frame_rate','nb_frames','sample_aspect_ratio')}
        return {**row,'width':w,'height':h,'duration':duration,'rotation':rotation,'video':video,'time_segments':segments,
                'media_url':f'/api/v3/scenery/originals/{identity}/media'}

    @staticmethod
    def validate_crops(crops,meta):
        if not isinstance(crops,list) or not 1<=len(crops)<=12:raise ValueError('请选择1—12个裁切区域')
        result=[]
        for rect in crops:
            if not isinstance(rect,dict) or set(rect)!={'x','y','width','height'} or any(type(v) is not int or v%2 for v in rect.values()):raise ValueError('裁切坐标和尺寸必须是偶数整数')
            x,y,w,h=(rect[k] for k in ('x','y','width','height'))
            if min(x,y)<0 or min(w,h)<32 or w<=h or x+w>meta['width'] or y+h>meta['height']:raise ValueError('裁切框必须位于画面内，且宽度大于高度')
            if rect in result:raise ValueError('裁切区域重复')
            result.append(rect)
        return result

    def legacy_in_use(self,path):
        db=self.data/'template_generation/jobs.db'
        if not db.exists():return False
        with closing(sqlite3.connect(db)) as c:
            for (plan,) in c.execute("SELECT plan FROM jobs WHERE status IN ('waiting','running')"):
                if any(Path(m['path']).resolve()==path.resolve() for t in json.loads(plan)['tracks'] for m in t['materials']):return True
        return False

    def create(self,identity,crops,request_id):
        uuid.UUID(request_id)
        with self.lock,self.connect() as c:
            prior=c.execute('SELECT id FROM jobs WHERE request_id=?',(request_id,)).fetchone()
            if prior:return {'id':prior[0]}
            row,path=self.raw(identity)
            if c.execute("SELECT 1 FROM jobs WHERE source_id=? AND status IN ('waiting','running','error')",(identity,)).fetchone():raise ValueError('这条原片已有处理任务，请重试或取消原任务')
            if self.legacy_in_use(path):raise ValueError('旧模板任务仍在引用这条原片，请先结束对应模板任务')
            meta=self.details(identity);crops=self.validate_crops(crops,meta);digest=sha(path);job=uuid.uuid4().hex
            meta['processing_plan']=processing_plan(crops,meta['time_segments'])
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,0,?,?,?,NULL,NULL)',(job,request_id,identity,str(path),digest,json.dumps(meta),json.dumps(crops),'waiting','等待处理','',now()))
            serial=int(c.execute("SELECT value FROM settings WHERE key='serial'").fetchone()[0])
            for i,output in enumerate(meta['processing_plan']['outputs']):
                rect=crops[output['crop_index']]
                while True:
                    serial+=1;name=f'风景{serial:06d}.mp4'
                    if not (self.ready/name).exists() and not c.execute('SELECT 1 FROM assets WHERE name=?',(name,)).fetchone():break
                width=min(1080,rect['width']);width-=width%2;height=max(2,round(rect['height']*width/rect['width']/2)*2)
                # An already-compatible whole landscape clip can retain its
                # original resolution; downscaling it here would force encoding.
                if remux_eligible(rect,{'width':meta['width'],'height':meta['height']},meta,output):
                    width,height=meta['width'],meta['height']
                c.execute('INSERT INTO assets(id,job_id,ordinal,name,path,width,height) VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,job,i,name,str(self.ready/name),width,height))
            c.execute("UPDATE settings SET value=? WHERE key='serial'",(str(serial),))
        self.start();self.wake.set();return {'id':job}

    def create_batch(self,items):
        # One source remains one recoverable job; a bad source must not block its neighbours.
        if not isinstance(items,list) or not 1<=len(items)<=200:
            raise ValueError('每批请选择1—200条原片')
        sources=set();requests=set()
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get('source_id'),str):
                raise ValueError('批量原片参数无效')
            try:uuid.UUID(item.get('request_id'))
            except (ValueError,TypeError,AttributeError):raise ValueError('批量提交标识无效')
            if item['source_id'] in sources or item['request_id'] in requests:
                raise ValueError('同一批不能重复选择原片或提交标识')
            sources.add(item['source_id']);requests.add(item['request_id'])
        results=[]
        for item in items:
            try:
                result=self.create(item['source_id'],item.get('crops'),item['request_id'])
                results.append({'source_id':item['source_id'],**result})
            except Exception as exc:
                results.append({'source_id':item['source_id'],'error':str(exc)})
        return {'results':results}

    def usage(self):
        db=self.data/'template_generation/jobs.db';used={};reserved={};limit=5
        if db.exists():
            with closing(sqlite3.connect(db)) as c:
                tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                # The shared database may first be created by the photo inventory.
                if not {'settings','usages','reservations'}<=tables:return used,reserved,limit
                row=c.execute("SELECT value FROM settings WHERE key='config'").fetchone()
                if row:limit=json.loads(row[0]).get('scenery_usage_limit',5)
                used=dict(c.execute('SELECT source_id,COUNT(*) FROM usages GROUP BY source_id'))
                reserved=dict(c.execute('SELECT source_id,COUNT(*) FROM reservations GROUP BY source_id'))
        return used,reserved,limit

    def delete_original(self,identity):
        with self.lock,self.connect() as c:
            row,path=self.raw(identity)
            jobs=c.execute('SELECT id,status FROM jobs WHERE source_id=?',(identity,)).fetchall()
            if any(j['status'] in ('waiting','running') for j in jobs):
                raise ValueError('原片正在处理或排队，请先结束任务或取消排队')
            if self.legacy_in_use(path):raise ValueError('旧模板任务仍在引用这条原片，暂不能删除')
            st=path.stat()
            if (st.st_size,st.st_mtime_ns)!=(row['size'],row['mtime']):raise ValueError('原片已变化，请刷新并重新确认删除')
            path.unlink()
            for job in jobs:
                # Keep any fully published results as independent assets; remove failed-task bookkeeping.
                c.execute("UPDATE assets SET job_id='' WHERE job_id=? AND state='ready'",(job['id'],))
                c.execute("DELETE FROM assets WHERE job_id=? AND state!='ready'",(job['id'],))
                c.execute('DELETE FROM jobs WHERE id=?',(job['id'],))
            c.execute('DELETE FROM originals WHERE id=?',(identity,))
        for job in jobs:
            folder=self.root/'jobs'/job['id']
            if folder.resolve().parent==(self.root/'jobs').resolve() and not folder.is_symlink():shutil.rmtree(folder,ignore_errors=True)
        return self.snapshot()

    def delete_asset(self,identity):
        with self.lock,self.connect() as c:
            asset=next((a for a in self.ready_assets() if a['id']==identity),None)
            if not asset:raise ValueError('风景素材不存在或已清理，请刷新')
            if asset['job_id']:raise ValueError('对应原片的处理尚未完成，请先完成处理或删除原片')
            if asset['reserved']:raise ValueError('风景素材已被模板任务占用，请先结束任务或取消排队')
            if not asset['valid']:raise ValueError('风景文件缺失或已变化，暂不能删除')
            p=Path(asset['path'])
            if sha(p)!=asset['sha256']:raise ValueError('风景内容已变化，暂不能删除')
            p.unlink()
            # Preserve identity and the separate usage ledger, just as quota retirement does.
            c.execute("UPDATE assets SET state='retired',error='' WHERE id=?",(identity,))
        return self.snapshot()

    def ready_assets(self):
        used,reserved,limit=self.usage()
        with self.connect() as c:rows=[dict(r) for r in c.execute("SELECT * FROM assets WHERE state='ready'")]
        result=[]
        for r in rows:
            p=Path(r['path']);r.update(used=used.get(r['sha256'],0),reserved=reserved.get(r['sha256'],0),limit=limit)
            r['remaining']=max(0,limit-r['used']-r['reserved'])
            r['valid']=p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(self.ready.resolve()) and (p.stat().st_size,p.stat().st_mtime_ns)==(r['size'],r['mtime'])
            result.append(r)
        return result

    def snapshot(self):
        with self.connect() as c:
            originals=[dict(r) for r in c.execute("SELECT o.*, (SELECT status FROM jobs j WHERE j.source_id=o.id AND status IN ('waiting','running','error') LIMIT 1) AS job_status FROM originals o ORDER BY name")]
            jobs=[dict(r) for r in c.execute('SELECT id,status,progress,stage,error,created_at,started_at,completed_at,source_meta FROM jobs ORDER BY created_at DESC,rowid DESC')]
            paused=c.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]=='true'
        for j in jobs:
            meta=json.loads(j.pop('source_meta'))
            j['name']=meta.get('name') or '风景处理 '+j['created_at'][5:16];j['elapsed_seconds']=max(0,int((datetime.fromisoformat(j['completed_at'] or now())-datetime.fromisoformat(j['started_at'] or now())).total_seconds()))
        return {'originals':originals,'assets':self.ready_assets(),'jobs':jobs,'paused':paused,'counts':{s:sum(j['status']==s for j in jobs) for s in ('waiting','running','done','error','cancelled')},'original_directory':str(self.original),'output_directory':str(self.ready)}

    def progress(self,job,value,stage):
        with self.connect() as c:c.execute('UPDATE jobs SET progress=?,stage=? WHERE id=?',(int(value),stage,job))

    def render_crop(self,source,target,rect,asset,meta,update):
        if 'segment' in meta:
            return SceneryMedia().render(source,[{'target':target,'rect':rect,'asset':asset,'segment':meta['segment']}],meta,update)[asset['id']]
        graph=f"crop={rect['width']}:{rect['height']}:{rect['x']}:{rect['y']},scale={asset['width']}:{asset['height']},setsar=1,fps=30"
        # A short preparation job; deterministic software encoding avoids device-dependent availability.
        cmd=[str(resolve_ffmpeg()),'-hide_banner','-nostdin','-y','-i',str(source),'-vf',graph,'-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart','-progress','pipe:1','-nostats',str(target)]
        with (target.with_suffix('.log')).open('wb') as log:
            with subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=log,**hidden()) as proc:
                for line in iter(proc.stdout.readline,b''):
                    if line.startswith(b'frame='):update(min(.9,int(line.split(b'=')[1])/max(1,meta['duration']*30)*.9))
                if proc.wait():raise RuntimeError('风景处理失败：'+target.with_suffix('.log').read_text(errors='replace')[-600:])
        return self.validate_video(target,asset,meta)

    def validate_video(self,path,asset,meta):
        data=json.loads(subprocess.check_output([str(resolve_ffprobe()),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],**hidden()))
        v=next(s for s in data['streams'] if s['codec_type']=='video');frames=int(v['nb_read_frames'])
        if (v['width'],v['height'])!=(asset['width'],asset['height']) or abs(frames-meta['duration']*30)>2:raise ValueError('处理结果尺寸或完整时长校验失败')
        checked=subprocess.run([str(resolve_ffmpeg()),'-v','error','-xerror','-i',str(path),'-map','0:v:0','-f','null','-'],capture_output=True,**hidden())
        if checked.returncode:raise ValueError('处理结果完整解码失败')
        return frames

    def run_next(self):
        with self.lock,self.connect() as c:
            if c.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]=='true':return False
            if c.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():return False
            row=c.execute("SELECT * FROM jobs WHERE status='waiting' ORDER BY created_at,rowid LIMIT 1").fetchone()
            if not row:return False
            j=dict(row);c.execute("UPDATE jobs SET status='running',started_at=?,error='' WHERE id=?",(now(),j['id']))
            assets=[dict(r) for r in c.execute('SELECT * FROM assets WHERE job_id=? ORDER BY ordinal',(j['id'],))]
        job=j['id'];source=Path(j['source_path']);folder=self.root/'jobs'/job;folder.mkdir(parents=True,exist_ok=True)
        try:
            meta=json.loads(j['source_meta']);crops=json.loads(j['crops'])
            new_plan='processing_plan' in meta
            outputs=validate_plan(meta,crops) if new_plan else [{'crop_index':i} for i in range(len(crops))]
            if len(outputs)!=len(assets):raise ValueError('风景分段结果数量与保存配方不一致，保留原片')
            # A previous attempt may have published every result before original deletion failed.
            published=all(a['state']=='ready' for a in assets)
            if source.exists():
                self.check_raw_path(source)
                if sha(source)!=j['source_hash']:raise ValueError('原片内容发生变化，停止处理与删除')
            elif not published:raise ValueError('原片已不存在，无法完成处理')
            if not published:
                pending=[]
                for i,a in enumerate(assets):
                    target=folder/a['name'];dest=Path(a['path'])
                    reusable=dest if dest.exists() and a['sha256'] else target
                    if a['sha256'] and reusable.is_file() and sha(reusable)==a['sha256']:
                        if new_plan and a['frames']!=outputs[i]['frames']:raise ValueError('已完成片段与保存的分段帧数不符，保留原片')
                        continue
                    if dest.exists():raise ValueError('入库目标已被其他文件占用，停止覆盖')
                    pending.append({'asset':a,'target':target,'rect':crops[outputs[i]['crop_index']],
                                    'segment':outputs[i] if new_plan else None,'ordinal':i})
                groups={}
                for entry in pending:
                    segment=entry['segment'];key=(segment['start_frame'],segment['frames']) if segment else entry['ordinal']
                    groups.setdefault(key,[]).append(entry)
                completed=len(assets)-len(pending)
                def record(entry,frames):
                    if new_plan and frames!=entry['segment']['frames']:raise ValueError('风景短片帧数与分段配方不一致，保留原片')
                    with self.connect() as c:c.execute('UPDATE assets SET sha256=?,frames=? WHERE id=?',(sha(entry['target']),frames,entry['asset']['id']))
                for entries in groups.values():
                    count=len(entries)
                    update=lambda n:self.progress(job,(completed+n*count)/len(assets)*90,f'处理短片 · {completed}/{len(assets)}份')
                    if new_plan and self.render==self.render_crop:
                        SceneryMedia().render(source,entries,meta,update,on_verified=record)
                    else:
                        for entry in entries:
                            render_meta={**meta,'segment':entry['segment']} if new_plan else meta
                            record(entry,self.render(source,entry['target'],entry['rect'],entry['asset'],render_meta,update))
                    completed+=count
                with self.lock,self.connect() as c:
                    if sha(source)!=j['source_hash']:raise ValueError('原片内容发生变化，停止入库与删除')
                    self.ready.mkdir(parents=True,exist_ok=True)
                    for a in c.execute('SELECT * FROM assets WHERE job_id=?',(job,)).fetchall():
                        dest=Path(a['path']);target=folder/a['name']
                        if dest.exists():
                            if sha(dest)!=a['sha256']:raise ValueError('入库文件冲突')
                        else:target.rename(dest)
                        st=dest.stat();c.execute("UPDATE assets SET state='ready',size=?,mtime=? WHERE id=?",(st.st_size,st.st_mtime_ns,a['id']))
                self.progress(job,95,'全部入库，删除原片')
            # Revalidate EVERY published asset immediately before destructive source removal.
            with self.lock,self.connect() as c:
                for i,a in enumerate(c.execute('SELECT * FROM assets WHERE job_id=? ORDER BY ordinal',(job,))):
                    if a['state']!='ready' or not Path(a['path']).is_file() or sha(Path(a['path']))!=a['sha256']:raise ValueError('入库结果缺失或变化，保留原片')
                    if new_plan and a['frames']!=outputs[i]['frames']:raise ValueError('入库片段时长与保存配方不符，保留原片')
                if source.exists():
                    self.check_raw_path(source)
                    if self.legacy_in_use(source):raise ValueError('原片仍被旧模板引用，待任务结束后重试删除')
                    if sha(source)!=j['source_hash']:raise ValueError('原片已被替换，禁止删除')
                    source.unlink()
                c.execute('DELETE FROM originals WHERE id=?',(j['source_id'],))
                c.execute("UPDATE jobs SET status='done',progress=100,stage='已入库，原片已删除',error='',completed_at=?,source_id='',source_path='',source_hash='',source_meta='{}',crops='[]' WHERE id=?",(now(),job))
                c.execute("UPDATE assets SET job_id='' WHERE job_id=?",(job,))
            shutil.rmtree(folder,ignore_errors=True)
        except Exception as exc:
            with self.connect() as c:c.execute("UPDATE jobs SET status='error',stage='处理或原片删除未完成',error=?,completed_at=? WHERE id=?",(str(exc),now(),job))
        return True

    def clean_exhausted(self):
        # Called at template settlement / explicit refresh, never deletes original downloads.
        with self.lock:
            used,reserved,limit=self.usage()
            for a in self.ready_assets():
                if a['job_id'] or used.get(a['sha256'],0)<limit or reserved.get(a['sha256'],0):continue
                try:
                    p=Path(a['path'])
                    if p.exists():
                        if not a['valid'] or sha(p)!=a['sha256']:raise ValueError('素材已变化，未自动删除')
                        p.unlink()
                    with self.connect() as c:c.execute("UPDATE assets SET state='retired',error='' WHERE id=?",(a['id'],))
                except (ValueError,OSError) as exc:
                    with self.connect() as c:c.execute('UPDATE assets SET error=? WHERE id=?',(str(exc),a['id']))

    def action(self,action,identity=None):
        with self.lock,self.connect() as c:
            if action in ('pause','resume'):c.execute("UPDATE settings SET value=? WHERE key='paused'",('true' if action=='pause' else 'false',))
            else:
                r=c.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
                if not r:raise ValueError('处理任务不存在')
                if action=='retry' and r['status']=='error':c.execute("UPDATE jobs SET status='waiting',progress=0,error='',stage='等待重试',completed_at=NULL WHERE id=?",(identity,))
                elif action=='cancel' and r['status']=='waiting':c.execute("UPDATE jobs SET status='cancelled',stage='已取消' WHERE id=?",(identity,))
                else:raise ValueError('当前任务状态不支持此操作')
        if action in ('retry','resume'):self.start();self.wake.set()
        return self.snapshot()

    def recover(self):
        with self.connect() as c:c.execute("UPDATE jobs SET status='error',stage='处理已中断',error='请重试，已完成部分会复用，原片未确认删除前保留',completed_at=? WHERE status='running'",(now(),))

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self.thread=threading.Thread(target=self.loop,daemon=True,name='v3-scenery');self.thread.start()
    def loop(self):
        while not self.stop.is_set():
            if not self.run_next():self.wake.wait(2);self.wake.clear()

_instances={}
_instance_lock=threading.Lock()
def get_library():
    from server import v2_file_service as service
    workspace,data=service.require_configured_paths();key=(str(workspace),str(data))
    with _instance_lock:
        if key not in _instances:
            obj=SceneryLibrary(workspace,data);obj.recover();_instances[key]=obj
        return _instances[key]
