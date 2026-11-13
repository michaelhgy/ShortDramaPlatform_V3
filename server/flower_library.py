"""User-curated flower styles, read-only Jianying discovery, favorites and durable usage."""
from __future__ import annotations
import base64
import copy
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import uuid
from urllib.parse import parse_qs, urlparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from server.application_resources import application_resource_path


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS v3_flower_assets(id TEXT PRIMARY KEY,content TEXT NOT NULL)')
    conn.execute('''CREATE TABLE IF NOT EXISTS v3_flower_preferences(
        id TEXT PRIMARY KEY, favorite INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
        usage_count INTEGER NOT NULL DEFAULT 0, last_used TEXT NOT NULL DEFAULT '')''')
    conn.execute('CREATE TABLE IF NOT EXISTS v3_flower_usage_events(id TEXT PRIMARY KEY,created_at TEXT NOT NULL)')


def used(conn, identifiers, event_id):
    ids=sorted(set(identifiers))
    if not ids:return
    now=datetime.now(timezone.utc).isoformat(timespec='microseconds')
    if conn.execute('INSERT OR IGNORE INTO v3_flower_usage_events VALUES(?,?)',(event_id,now)).rowcount==0:return
    for identifier in ids:
        conn.execute('''INSERT INTO v3_flower_preferences(id,usage_count,last_used) VALUES(?,1,?)
            ON CONFLICT(id) DO UPDATE SET usage_count=usage_count+1,last_used=excluded.last_used''',(identifier,now))


def validate_style(raw, folder=None):
    """Validate drawable parameters and embed supported texture images independently of cache."""
    if not isinstance(raw,dict) or not isinstance(raw.get('fill'),dict):raise ValueError('样式参数不完整')
    result=copy.deepcopy(raw)
    def paint(value):
        if not isinstance(value,dict):raise ValueError('缺少文字材质参数')
        kind=value.get('render_type')
        if kind=='texture':
            texture=value.get('texture')
            if not isinstance(texture,dict):raise ValueError('纹理参数不完整')
            count=texture.get('range',1)
            if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=6:raise ValueError('纹理分格数量暂未适配')
            texture['range']=count
            if texture.get('blend','no') not in ('no','solid','gradient'):raise ValueError('纹理混合方式暂未适配')
            for key in ('scale','alpha','angle'):
                n=texture.get(key,1 if key!='angle' else 0)
                if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n):raise ValueError('纹理尺寸或角度无效')
            if not 0<texture.get('scale',1)<=20 or not 0<=texture.get('alpha',1)<=1:raise ValueError('纹理缩放或透明度无效')
            if folder is None:raise ValueError('缺少纹理图片，需从缓存完整导入')
            root=Path(folder).resolve();source=(root/str(texture.get('path')or'')).resolve()
            if not source.is_relative_to(root) or not source.is_file():raise ValueError('纹理图片缺失或路径无效')
            if source.stat().st_size>10_000_000:raise ValueError('纹理图片过大')
            try:
                with Image.open(source) as im:
                    if im.width*im.height>16_000_000:raise ValueError('纹理图片像素过大')
                    im.thumbnail((1024,1024));out=io.BytesIO();im.convert('RGBA').save(out,format='PNG')
                    texture['source']='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
            except (OSError,Image.DecompressionBombError) as exc:raise ValueError('纹理图片无法读取')from exc
            blend=texture.get('blend','no')
            if blend!='no':paint({**value,'render_type':blend})
            return
        if kind not in ('solid','gradient'):raise ValueError('材质类型暂不支持')
        data=value.get(kind)
        if not isinstance(data,dict):raise ValueError('文字颜色参数不完整')
        colors=[data.get('color')] if kind=='solid' else data.get('color')
        if not isinstance(colors,list) or not 1<=len(colors)<=16:raise ValueError('颜色参数无效')
        for color in colors:
            if not isinstance(color,list) or len(color)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in color):raise ValueError('颜色值无效')
        if kind=='gradient':
            for key in ('percent','alpha'):
                values=data.get(key)
                if not isinstance(values,list) or len(values)!=len(colors) or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in values):raise ValueError('渐变参数无效')
            if not isinstance(data.get('angle'),(int,float)) or not math.isfinite(data['angle']):raise ValueError('渐变角度无效')
    def walk(layer,shadow=False):
        if not isinstance(layer,dict):raise ValueError('图层参数无效')
        paint(layer.get('content'))
        for key in ('alpha','width','distance','feather','diffuse','angle'):
            if key in layer and (isinstance(layer[key],bool) or not isinstance(layer[key],(int,float)) or not math.isfinite(layer[key]) or abs(layer[key])>10000):raise ValueError('图层数值无效')
        if shadow:
            for stroke in layer.get('strokes',[]):walk(stroke)
    walk(result['fill'])
    for key in ('strokes','shadows','inner_shadows'):
        result.setdefault(key,[])
        if not isinstance(result[key],list) or len(result[key])>24:raise ValueError('花字图层过多或格式无效')
        for layer in result[key]:walk(layer,key!='strokes')
    return result


class FlowerLibrary:
    def __init__(self,workspace,connection,settings=None,*,environ=None,builtins=None,machine_path=None):
        self.workspace=Path(workspace);self.connection=connection;self.settings=settings or {}
        self.environ=os.environ if environ is None else environ
        self.machine_path=machine_path or (Path(self.environ.get('LOCALAPPDATA') or Path.home())/'ShortDramaPlatform/flower-cache-source.json')
        if builtins is not None:self.builtins=copy.deepcopy(builtins)
        else:
            source=application_resource_path('dist','cover-flower-styles.json')
            if not source.is_file():source=application_resource_path('src','coverEditor','simpleFlowerStyles.json')
            self.builtins=json.loads(source.read_text(encoding='utf-8')) if source.is_file() else []

    def _machine_directory(self):
        try:
            value=str(json.loads(self.machine_path.read_text(encoding='utf-8')).get('directory') or '')
            return value if value and self._find_cache(value) else ''
        except (OSError,ValueError,TypeError):return ''

    def _remember(self,directory):
        self.machine_path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.machine_path.with_name(self.machine_path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps({'directory':directory},ensure_ascii=False),encoding='utf-8');temp.replace(self.machine_path)

    @staticmethod
    def _find_cache(path):
        path=Path(path).expanduser()
        # Accept a user-data root, Cache, artistEffect, installation root or a selected package.
        candidates=[path,path/'artistEffect',path/'Cache/artistEffect',path/'User Data/Cache/artistEffect']
        for parent in (path,*list(path.parents)[:5]):
            if parent.name.casefold()=='user data':candidates.append(parent/'Cache/artistEffect')
            if parent.name.casefold() in ('apps','jianyingpro'):candidates.append(parent.parent/'User Data/Cache/artistEffect' if parent.name.casefold()=='apps' else parent/'User Data/Cache/artistEffect')
        for candidate in candidates:
            if candidate.name.casefold()=='artisteffect' and candidate.is_dir():return candidate.resolve()
        return None

    def discover(self,directory=''):
        if directory:
            found=self._find_cache(directory)
            if not found:raise ValueError('所选目录没有找到 artistEffect 缓存，可选择剪映用户目录、Cache或artistEffect目录。')
            return [found]
        candidates=[self._machine_directory()]
        for key in ('jianying_user_data_root','jianying_draft_root','jianying_executable'):
            value=str(self.settings.get(key) or '')
            if value:candidates.append(str(Path(value).parent) if key.endswith('executable') else value)
        for key in ('LOCALAPPDATA','APPDATA'):
            if self.environ.get(key):candidates.append(str(Path(self.environ[key])/'JianyingPro/User Data'))
        roots=[]
        for candidate in candidates:
            if not candidate:continue
            found=self._find_cache(candidate)
            if found and found not in roots:roots.append(found)
        return roots

    def _metadata(self,roots):
        result={s['id']:{'name':s['name'],'tags':s.get('tags',[])} for s in self.builtins}
        bundled=application_resource_path('server','template_engine','jianying59_template','resources','flower_style_catalog.json')
        try:
            for row in json.loads(bundled.read_text(encoding='utf-8'))['styles']:result.setdefault(row['effect_id'],{'name':row['name'],'tags':row.get('category_tags',[])})
        except (OSError,ValueError,KeyError):pass
        for root in roots:
            database=root.parent/'rp.db'
            if not database.is_file():continue
            try:
                with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=1)) as conn:
                    rows=conn.execute("SELECT response_body FROM http_cache WHERE url LIKE '%flower%' ORDER BY id DESC LIMIT 200").fetchall()
                seen=set()
                for (raw,) in rows:
                    try:items=(json.loads(raw).get('data') or {}).get('effect_item_list') or []
                    except (ValueError,AttributeError):continue
                    for item in items:
                        common=item.get('common_attr') or {};identifier=str(common.get('effect_id') or common.get('id') or '')
                        if identifier and identifier not in seen and common.get('title'):
                            result[identifier]={'name':str(common['title']),'tags':result.get(identifier,{}).get('tags',[])};seen.add(identifier)
            except sqlite3.Error:pass
        return result

    @staticmethod
    def _icon(folder):
        for filename in ('cover_icon.png','icon.png','cover.png'):
            f=folder/filename
            if not f.is_file() or f.stat().st_size>2_000_000:continue
            try:
                with Image.open(f) as im:
                    im.thumbnail((160,90));out=io.BytesIO();im.convert('RGBA').save(out,format='PNG')
                    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
            except (OSError,Image.DecompressionBombError):pass
        return ''

    def _scan(self,directory='',only_ids=None):
        roots=self.discover(directory);meta=self._metadata(roots);found={}
        for root in roots:
            for package in root.glob('*/*'):
                identifier=package.parent.name
                if only_ids is not None and identifier not in only_ids:continue
                if not re.fullmatch(r'\d{1,30}',identifier) or not package.is_dir() or not package.resolve().is_relative_to(root):continue
                source=package/'effectStyle.json';config=package/'config.json'
                if not source.is_file() and not config.is_file():continue
                if not source.is_file() and identifier not in meta:continue
                name=meta.get(identifier,{}).get('name',f'缓存花字 {identifier}')
                status='unsupported';reason='需要剪映特效引擎，暂不能直接加入';style=None
                if source.is_file():
                    try:
                        if source.stat().st_size>512_000:raise ValueError('样式文件过大')
                        style=validate_style(json.loads(source.read_text(encoding='utf-8-sig')),package);status='ready';reason=''
                    except (OSError,ValueError,TypeError) as exc:reason=str(exc) or '样式文件无法读取'
                row={'id':identifier,'name':name,'tags':meta.get(identifier,{}).get('tags',[]),'icon':self._icon(package),'status':status,'reason':reason,'source_folder':str(package),'style':style,'mtime':source.stat().st_mtime_ns if source.is_file() else config.stat().st_mtime_ns}
                old=found.get(identifier)
                if old is None or (old['status']!='ready' and status=='ready') or (old['status']==status and row['mtime']>old['mtime']):found[identifier]=row
        return roots,sorted(found.values(),key=lambda s:(s['status']!='ready',s['name'],s['id']))

    def scan(self,directory='',remember=False):
        roots,rows=self._scan(directory)
        if remember:self._remember(directory)
        library=self.load();known={s['id']:s for s in library['styles']}
        for row in rows:
            row.pop('style',None);row['imported']=bool(known.get(row['id'],{}).get('enabled'))
        return {'roots':[str(p) for p in roots],'items':rows,'ready_count':sum(r['status']=='ready' for r in rows),
            'message':'' if roots else '未找到剪映花字缓存。请先在剪映里下载花字，或手动选择用户/缓存目录。'}

    def load(self):
        definitions={s['id']:{**copy.deepcopy(s),'builtin':True} for s in self.builtins}
        with closing(self.connection()) as conn:
            for identifier,raw in conn.execute('SELECT id,content FROM v3_flower_assets'):
                definitions[identifier]={**json.loads(raw),'builtin':False}
            prefs={r[0]:r for r in conn.execute('SELECT id,favorite,enabled,usage_count,last_used FROM v3_flower_preferences')}
        for identifier,row in definitions.items():
            p=prefs.get(identifier);row.update(favorite=bool(p[1]) if p else False,enabled=bool(p[2]) if p else True,usageCount=p[3] if p else 0,lastUsed=p[4] if p else '')
        return {'styles':list(definitions.values()),'custom_directory':self._machine_directory()}

    @staticmethod
    def compact(result):
        """Keep definitions fresh but send texture pixels separately, on demand."""
        digests={}
        def walk(value,identifier):
            if isinstance(value,dict):
                if value.get('render_type')=='texture':
                    texture=value.get('texture',{});source=texture.get('source','')
                    if source.startswith('data:image/png;base64,'):
                        digest=digests.get(source)
                        if digest is None:digest=hashlib.sha256(source.encode()).hexdigest();digests[source]=digest
                        texture['source']=f'/api/v2/cover-editor/flowers/textures/{identifier}/{digest}.png'
                for child in value.values():walk(child,identifier)
            elif isinstance(value,list):
                for child in value:walk(child,identifier)
        for style in result.get('styles',[]):walk(style.get('style'),style['id'])
        return result

    def texture(self,identifier,digest):
        if not re.fullmatch(r'\d{1,30}',identifier) or not re.fullmatch(r'[a-f0-9]{64}',digest):raise FileNotFoundError('纹理不存在')
        with closing(self.connection()) as conn:row=conn.execute('SELECT content FROM v3_flower_assets WHERE id=?',(identifier,)).fetchone()
        definition=json.loads(row[0]) if row else next((s for s in self.builtins if s['id']==identifier),None)
        def find(value):
            if isinstance(value,dict):
                if value.get('render_type')=='texture':
                    source=value.get('texture',{}).get('source','')
                    if source.startswith('data:image/png;base64,') and hashlib.sha256(source.encode()).hexdigest()==digest:return base64.b64decode(source.split(',',1)[1],validate=True)
                for child in value.values():
                    found=find(child)
                    if found is not None:return found
            elif isinstance(value,list):
                for child in value:
                    found=find(child)
                    if found is not None:return found
            return None
        data=find(definition)
        if data is None:raise FileNotFoundError('纹理不存在或样式已更新，请重新打开花字库')
        return data

    def import_styles(self,identifiers,directory=''):
        if not isinstance(identifiers,list) or not identifiers or len(identifiers)>200 or any(not isinstance(i,str) for i in identifiers):raise ValueError('请勾选1至200款要加入的花字')
        roots,rows=self._scan(directory,set(identifiers));available={r['id']:r for r in rows};selected=[]
        for identifier in set(identifiers):
            row=available.get(identifier)
            if not row or row['status']!='ready':raise ValueError('所选花字缓存已变化或暂不支持，请重新扫描后选择')
            selected.append({k:v for k,v in row.items() if k in ('id','name','tags','icon','style')})
        with closing(self.connection()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            for row in selected:
                conn.execute('INSERT INTO v3_flower_assets VALUES(?,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content',(row['id'],json.dumps(row,ensure_ascii=False)))
                conn.execute('INSERT INTO v3_flower_preferences(id,enabled) VALUES(?,1) ON CONFLICT(id) DO UPDATE SET enabled=1',(row['id'],))
            conn.commit()
        return self.load()

    def preference(self,payload):
        identifier=payload.get('id')
        if identifier not in {s['id'] for s in self.load()['styles']}:raise ValueError('花字尚未加入库')
        with closing(self.connection()) as conn:
            conn.execute('INSERT OR IGNORE INTO v3_flower_preferences(id) VALUES(?)',(identifier,))
            for key in ('favorite','enabled'):
                if key in payload:
                    if not isinstance(payload[key],bool):raise ValueError('收藏或显示设置无效')
                    conn.execute(f'UPDATE v3_flower_preferences SET {key}=? WHERE id=?',(int(payload[key]),identifier))
            conn.commit()
        return self.load()

    def record_export(self,payload):
        identifiers=payload.get('ids');event=payload.get('eventId')
        if not isinstance(identifiers,list) or len(identifiers)>6 or any(not isinstance(i,str) for i in identifiers) or not isinstance(event,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',event):raise ValueError('使用记录无效')
        known={s['id'] for s in self.load()['styles']}
        if not set(identifiers)<=known:raise ValueError('使用的花字不在库中')
        with closing(self.connection()) as conn:used(conn,identifiers,'export:'+event);conn.commit()
        return self.load()


def handle(handler,method,path,payload=None):
    prefix='/api/v2/cover-editor/flowers'
    if not path.startswith(prefix):return False
    from server import v2_file_service as files
    library=FlowerLibrary(files.WORKSPACE,files.connection,files.get_v2_settings());payload=payload or {}
    try:
        action=path[len(prefix):]
        texture_match=re.fullmatch(r'/textures/(\d{1,30})/([a-f0-9]{64})\.png',action)
        if method=='GET' and texture_match:
            data=library.texture(*texture_match.groups());etag='"'+texture_match[2]+'"'
            if handler.headers.get('If-None-Match')==etag:
                handler.send_response(304);handler.send_header('ETag',etag);handler.send_header('Cache-Control','private, max-age=31536000, immutable');handler.end_headers();return True
            handler.send_response(200);handler.send_header('Content-Type','image/png');handler.send_header('Content-Length',str(len(data)));handler.send_header('ETag',etag);handler.send_header('Cache-Control','private, max-age=31536000, immutable');handler.end_headers();handler.wfile.write(data);return True
        if method=='GET' and not action:result=library.load()
        elif method=='POST' and action=='/scan':result=library.scan(str(payload.get('directory') or ''),bool(payload.get('remember')))
        elif method=='POST' and action=='/import':result=library.import_styles(payload.get('ids'),str(payload.get('directory') or ''))
        elif method=='POST' and action=='/preference':result=library.preference(payload)
        elif method=='POST' and action=='/usage':result=library.record_export(payload)
        else:raise ValueError('花字管理入口不存在')
        if parse_qs(urlparse(handler.path).query).get('compact')==['1']:result=library.compact(result)
        handler._json(200,result)
    except FileNotFoundError as exc:handler._json(404,{'error':str(exc)})
    except (ValueError,OSError,sqlite3.Error) as exc:handler._json(400,{'error':str(exc)})
    return True
