"""Template-scoped photo quotas, reservations and checked retirement."""
from __future__ import annotations
from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from PIL import Image
from server.scenery.service import library_lock
from .config import DEFAULTS
from .fullscreen_layers import digest

EXTENSIONS={'.jpg','.jpeg','.png','.webp','.bmp'}
SCHEMA='''
CREATE TABLE IF NOT EXISTS photo_sources(id TEXT PRIMARY KEY,path TEXT NOT NULL,name TEXT NOT NULL,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'ready',error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS photo_reservations(job_id TEXT NOT NULL,source_id TEXT NOT NULL,PRIMARY KEY(job_id,source_id));
CREATE TABLE IF NOT EXISTS photo_usages(job_id TEXT NOT NULL,source_id TEXT NOT NULL,PRIMARY KEY(job_id,source_id));
'''


class PhotoLibrary:
    def __init__(self,workspace,data_root):
        self.workspace=Path(workspace).resolve();self.root=self.workspace/'生成资源/真人图片'
        self.data=Path(data_root);self.db=self.data/'template_generation/jobs.db'
        self.lock=library_lock(data_root)
        self.db.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:c.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30);c.row_factory=sqlite3.Row
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()

    def limit(self,c):
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone():
            row=c.execute("SELECT value FROM settings WHERE key='config'").fetchone()
            if row:return json.loads(row[0]).get('photo_usage_limit',DEFAULTS['photo_usage_limit'])
        return DEFAULTS['photo_usage_limit']

    def valid(self,row,content=False):
        p=Path(row['path'])
        return (not self.root.is_symlink() and not p.is_symlink() and p.is_file()
                and p.resolve().is_relative_to(self.root.resolve())
                and (p.stat().st_size,p.stat().st_mtime_ns)==(row['size'],row['mtime_ns'])
                and (not content or digest(p)==row['id']))

    def sync(self):
        if not self.root.is_dir() or self.root.is_symlink():return
        with self.lock,self.connect() as c:
            known={r['path']:dict(r) for r in c.execute('SELECT * FROM photo_sources')}
            for p in sorted(self.root.rglob('*')):
                if p.suffix.lower() not in EXTENSIONS or p.name.startswith('已使用') or p.is_symlink() or not p.is_file():continue
                st=p.stat();previous=known.get(str(p))
                if previous and (st.st_size,st.st_mtime_ns)==(previous['size'],previous['mtime_ns']):continue
                try:
                    identity=digest(p)
                    with Image.open(p) as im:im.verify()
                    after=p.stat()
                    if (st.st_size,st.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):continue
                except (OSError,ValueError):continue
                existing=c.execute('SELECT * FROM photo_sources WHERE id=?',(identity,)).fetchone()
                # Reimporting the same pixels never resets a retired identity's quota.
                if existing and (existing['state']=='retired' or self.valid(existing)):continue
                c.execute("INSERT INTO photo_sources(id,path,name,size,mtime_ns) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path,name=excluded.name,size=excluded.size,mtime_ns=excluded.mtime_ns,error=''",
                          (identity,str(p),p.name,st.st_size,st.st_mtime_ns))

    def items(self,c,limit=None,include_retired=False):
        limit=self.limit(c) if limit is None else limit
        used=dict(c.execute('SELECT source_id,COUNT(*) FROM photo_usages GROUP BY source_id'))
        reserved=dict(c.execute('SELECT source_id,COUNT(*) FROM photo_reservations GROUP BY source_id'))
        result=[]
        query="SELECT * FROM photo_sources"+("" if include_retired else " WHERE state='ready'")+" ORDER BY name,id"
        for row in c.execute(query):
            r=dict(row);r.update(used=used.get(r['id'],0),reserved=reserved.get(r['id'],0),limit=limit)
            r['remaining']=max(0,limit-r['used']-r['reserved']) if r['state']=='ready' else 0;r['valid']=self.valid(r)
            result.append(r)
        return result

    def candidates(self,c,limit):
        return [{k:r[k] for k in ('id','path','name','size','mtime_ns')} for r in self.items(c,limit) if r['valid'] and r['remaining']]

    def reserve(self,c,job,photos,limit):
        for source in photos:
            r=c.execute('SELECT * FROM photo_sources WHERE id=?',(source['id'],)).fetchone()
            if not r or r['state']!='ready' or not self.valid(r,content=True) or str(r['path'])!=source['path']:
                raise ValueError('真人图片缺失或已变化，请新建模板：'+source['name'])
            used=c.execute('SELECT COUNT(*) FROM (SELECT * FROM photo_usages UNION ALL SELECT * FROM photo_reservations) WHERE source_id=?',(source['id'],)).fetchone()[0]
            if used>=limit:raise ValueError('真人图片已达到使用上限或被排队任务占用：'+source['name'])
            c.execute('INSERT INTO photo_reservations VALUES(?,?)',(job,source['id']))

    def clean_exhausted(self):
        with self.lock,self.connect() as c:
            for r in self.items(c):
                if r['used']<r['limit'] or r['reserved']:continue
                try:
                    p=Path(r['path'])
                    if p.exists():
                        if not self.valid(r,content=True):raise ValueError('真人图片已变化，未自动删除')
                        p.unlink()
                    c.execute("UPDATE photo_sources SET state='retired',error='' WHERE id=?",(r['id'],))
                except (OSError,ValueError) as exc:
                    c.execute('UPDATE photo_sources SET error=? WHERE id=?',(str(exc),r['id']))

    def refresh(self):
        self.sync();self.clean_exhausted()
        with self.connect() as c:return self.items(c,include_retired=True)
