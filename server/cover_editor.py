"""Versioned per-drama covers. Immutable images and SQLite CAS protect existing work."""
from __future__ import annotations
import base64
import copy
import hashlib
import io
import json
import math
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image, ImageOps


def initialize(conn):
    from server.flower_library import initialize as initialize_flowers
    initialize_flowers(conn)
    conn.execute('CREATE TABLE IF NOT EXISTS v3_cover_projects(drama_id TEXT PRIMARY KEY, content TEXT NOT NULL, revision INTEGER NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS v3_cover_templates(id INTEGER PRIMARY KEY CHECK(id=1), content TEXT NOT NULL, revision INTEGER NOT NULL)')


def stamp(): return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def token(path): return hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:32]

def show_sheep_cover(project):
    group=project['sheep']
    return group['activeId']!='original' and any(v['id']==group['activeId'] for v in group['versions'])
def active(group): return next((v['image'] for v in group['versions'] if v['id'] == group['activeId']), group['original'])
def paths(project):
    for kind in ('drama', 'sheep'):
        yield project[kind]['original']
        for version in project[kind]['versions']:
            yield version['image']; yield version['sourceImage']


class CoverStore:
    def __init__(self, workspace, connection):
        self.workspace = Path(workspace); self.connection = connection

    def _root(self, drama_id):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', drama_id): raise ValueError('剧集编号无效')
        return self.workspace / '剧集资料' / '_封面编辑' / drama_id

    def task_context(self, task_id):
        """Resolve a task cover without requiring usable publishing settings."""
        with closing(self.connection()) as conn:
            task=conn.execute('SELECT account_name,drama_name FROM production_tasks WHERE id=?',(task_id,)).fetchone()
            if not task:raise ValueError('制作任务不存在')
            settings={}
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_publish_documents' AND type='table'").fetchone():
                saved=conn.execute("SELECT content FROM v3_publish_documents WHERE kind='settings' AND key=?",(task_id,)).fetchone()
                if saved:
                    try:settings=json.loads(saved[0])
                    except (TypeError,ValueError):pass
            account=conn.execute('SELECT theater_id FROM accounts WHERE nickname=?',(task[0],)).fetchone()
            theater=account[0] if account else ''
            drama=None
            if isinstance(settings,dict) and settings.get('drama_id'):
                drama=conn.execute('SELECT id,current_name FROM dramas WHERE id=?'+(' AND theater_id=?' if theater else ''),(settings['drama_id'],theater) if theater else (settings['drama_id'],)).fetchone()
            if not drama:
                query='''SELECT d.id,d.current_name FROM dramas d WHERE
                    (d.current_name=? OR EXISTS(SELECT 1 FROM drama_aliases a WHERE a.drama_id=d.id AND a.alias_name=?))'''
                rows=conn.execute(query+(' AND d.theater_id=?' if theater else ''),(task[1],task[1],theater) if theater else (task[1],task[1])).fetchall()
                if len(rows)!=1:raise ValueError('制作任务未能唯一对应剧集档案，请核对剧名和所属剧场')
                drama=rows[0]
        return {'drama':{'id':drama[0],'name':drama[1]},**self.cover_info(drama[0])}

    def _load(self, conn, drama_id):
        drama = conn.execute('SELECT current_name FROM dramas WHERE id=?', (drama_id,)).fetchone()
        if not drama: raise ValueError('剧集不存在')
        row = conn.execute('SELECT content,revision FROM v3_cover_projects WHERE drama_id=?', (drama_id,)).fetchone()
        if row: return json.loads(row[0]), row[1], drama[0]
        profile = conn.execute('SELECT cover_path FROM drama_profiles WHERE drama_id=?', (drama_id,)).fetchone()
        original = str(profile[0] or '') if profile else ''
        group = {'original': original, 'versions': [], 'activeId': 'original'}
        return {'schema': 1, 'drama': copy.deepcopy(group), 'sheep': copy.deepcopy(group), 'sheepCustomOriginal': False}, 0, drama[0]

    def _front(self, project, drama_id, revision):
        result = copy.deepcopy(project)
        def image_url(path): return f'/api/v2/cover-editor/dramas/{drama_id}/assets/{token(path)}' if path else ''
        for kind in ('drama', 'sheep'):
            result[kind]['original'] = image_url(project[kind]['original'])
            for version in result[kind]['versions']:
                version['image'] = image_url(version['image']); version['sourceImage'] = image_url(version['sourceImage'])
        return {'project': result, 'revision': revision,
            'sheep_visible': show_sheep_cover(project)}

    def snapshot(self, drama_id):
        with closing(self.connection()) as conn:
            project, rev, _ = self._load(conn, drama_id)
        return self._front(project, drama_id, rev)

    def asset(self, drama_id, asset_id):
        with closing(self.connection()) as conn: project, _, _ = self._load(conn, drama_id)
        found = next((Path(p) for p in paths(project) if p and token(p) == asset_id), None)
        if not found or not found.is_file(): raise FileNotFoundError('封面文件不存在，可能已被移动或删除，请重新选择图片。')
        return found

    def cover_info(self, drama_id):
        with closing(self.connection()) as conn: project, rev, _ = self._load(conn, drama_id)
        def info(kind):
            path = active(project[kind]); exists = bool(path and Path(path).is_file())
            return {'path': path, 'exists': exists, 'url': f'/api/v2/cover-editor/dramas/{drama_id}/assets/{token(path)}?v={rev}' if exists else ''}
        return {'cover': info('drama'), 'sheep_cover': info('sheep'), 'sheep_cover_visible': show_sheep_cover(project)}

    def _write_image(self, drama_id, data):
        if len(data) > 20 * 1024 * 1024: raise ValueError('封面图片不能超过20MB')
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP', 'GIF'): raise ValueError('不支持的封面图片格式')
                if image.width * image.height > 24_000_000 or max(image.size) > 8192: raise ValueError('封面图片过大')
                image = ImageOps.exif_transpose(image).convert('RGBA')
                output = io.BytesIO(); image.save(output, format='PNG'); data = output.getvalue()
        except (OSError, Image.DecompressionBombError) as exc: raise ValueError('图片无法读取，请重新选择图片。') from exc
        directory = self._root(drama_id) / 'images'; directory.mkdir(parents=True, exist_ok=True)
        target = directory / (hashlib.sha256(data).hexdigest() + '.png')
        if not target.exists():
            temporary = directory / (uuid.uuid4().hex + '.tmp')
            temporary.write_bytes(data); temporary.replace(target)
        return str(target)

    def _image(self, value, drama_id, allowed):
        if not isinstance(value, str): raise ValueError('封面图片内容无效')
        if not value: return ''
        if value.startswith('data:image/'):
            try: return self._write_image(drama_id, base64.b64decode(value.split(',', 1)[1], validate=True))
            except (ValueError, IndexError) as exc: raise ValueError(f'封面图片无效：{exc}') from exc
        key = urlparse(value).path
        if key not in allowed: raise ValueError('封面引用已失效，请关闭编辑器后重新打开')
        return allowed[key]

    @staticmethod
    def layers(value):
        if not isinstance(value, list) or len(value) > 6: raise ValueError('每张封面最多6段文字')
        result = []
        for layer in value:
            if not isinstance(layer, dict) or not isinstance(layer.get('text'), str) or len(layer['text']) > 120: raise ValueError('文字内容无效或超过120字')
            row = {k: layer[k] for k in ('id', 'text', 'styleId', 'x', 'y', 'width', 'height', 'fontSize', 'rotation', 'align', 'verticalAlign', 'background', 'backgroundAlpha') if k in layer}
            for key in ('x', 'y', 'width', 'fontSize', 'rotation', 'backgroundAlpha'):
                n = row.get(key)
                if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or abs(n) > 24000: raise ValueError('文字尺寸或位置无效')
            if row['width'] <= 0 or row['fontSize'] <= 0 or not 0 <= row['backgroundAlpha'] <= 1: raise ValueError('文字尺寸或透明度无效')
            if 'height' in row and (not isinstance(row['height'], (int,float)) or not math.isfinite(row['height']) or not 0 < row['height'] <= 24000): raise ValueError('文本框高度无效')
            if row.get('align') not in ('left', 'center', 'right') or row.get('verticalAlign', 'middle') not in ('top', 'middle', 'bottom'): raise ValueError('文字对齐无效')
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(row.get('background', ''))): raise ValueError('文字底色无效')
            if not isinstance(row.get('id'), str) or not re.fullmatch(r'\d{1,30}', str(row.get('styleId', ''))): raise ValueError('文字或花字编号无效')
            result.append(row)
        return result

    def save(self, drama_id, payload):
        with closing(self.connection()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            old, revision, name = self._load(conn, drama_id)
            if payload.get('revision') != revision: raise ValueError('封面已在其他窗口更新，请关闭后重新打开，当前编辑可先导出保留。')
            incoming = payload.get('project')
            if not isinstance(incoming, dict): raise ValueError('封面内容无效')
            allowed = {f'/api/v2/cover-editor/dramas/{drama_id}/assets/{token(p)}': p for p in paths(old) if p}
            result = {'schema': 1, 'sheepCustomOriginal': bool(old.get('sheepCustomOriginal') or incoming.get('sheepCustomOriginal'))}
            for kind in ('drama', 'sheep'):
                group = incoming.get(kind)
                if not isinstance(group, dict) or not isinstance(group.get('versions'), list) or len(group['versions']) > 3: raise ValueError('每套封面最多保存3张修改版')
                normalized = {'original': self._image(group.get('original'), drama_id, allowed), 'activeId': group.get('activeId'), 'versions': []}
                if old[kind]['original'] and not normalized['original']: raise ValueError('原始封面可以替换，不能删除')
                ids = {'original'}
                for version in group['versions']:
                    identifier = version.get('id')
                    if not isinstance(identifier, str) or identifier in ids or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', identifier): raise ValueError('修改版编号无效或重复')
                    ids.add(identifier)
                    item = {'id': identifier, 'image': self._image(version.get('image'), drama_id, allowed), 'sourceImage': self._image(version.get('sourceImage'), drama_id, allowed), 'layers': self.layers(version.get('layers')), 'createdAt': str(version.get('createdAt') or stamp())[:60]}
                    if not item['image'] or not item['sourceImage']: raise ValueError('修改版缺少图片或底图')
                    normalized['versions'].append(item)
                if normalized['activeId'] not in ids: raise ValueError('正在使用的封面不存在')
                result[kind] = normalized
            if result['sheep']['original'] != old['sheep']['original']:
                auto_seed = not old['sheep']['original'] and result['sheep']['original'] == result['drama']['original']
                if not auto_seed: result['sheepCustomOriginal'] = True
            # Original-only copies stay separate references when normal original is replaced.
            if not result['sheep']['original'] and result['drama']['original']:
                result['sheep']['original'] = result['drama']['original']
            root = self._root(drama_id); history = root / 'history'; history.mkdir(parents=True, exist_ok=True)
            (history / f'{revision}-{uuid.uuid4().hex}.json').write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
            conn.execute('INSERT INTO v3_cover_projects VALUES(?,?,?) ON CONFLICT(drama_id) DO UPDATE SET content=excluded.content,revision=excluded.revision', (drama_id, json.dumps(result, ensure_ascii=False), revision + 1))
            current = active(result['drama']); profile_root = self.workspace / '剧集资料' / name
            if not conn.execute('SELECT 1 FROM drama_profiles WHERE drama_id=?', (drama_id,)).fetchone():
                if not profile_root.resolve().is_relative_to((self.workspace/'剧集资料').resolve()): raise ValueError('剧集资料目录无效')
                (profile_root/'封面').mkdir(parents=True, exist_ok=True)
            conn.execute('''INSERT INTO drama_profiles(id,drama_id,root_path,master_path,cover_path,updated_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(drama_id) DO UPDATE SET cover_path=excluded.cover_path,updated_at=excluded.updated_at''',
                (uuid.uuid4().hex, drama_id, str(profile_root), str(profile_root/'原片'), current, stamp()))
            from server.flower_library import used
            style_ids=set()
            for kind in ('drama','sheep'):
                previous={v['id']:v for v in old[kind]['versions']}
                for version in result[kind]['versions']:
                    if version != previous.get(version['id']):style_ids.update(l['styleId'] for l in version['layers'])
            used(conn,style_ids,f'cover:{drama_id}:{revision+1}')
            conn.commit()
            return self._front(result, drama_id, revision + 1)

    def replace_original(self, drama_id, payload, kind='drama'):
        if kind not in ('drama', 'sheep'): raise ValueError('封面类型无效')
        snapshot = self.snapshot(drama_id); project = snapshot['project']
        data = str(payload.get('content_base64') or '')
        if not data.startswith('data:'): data = 'data:image/png;base64,' + data
        project[kind]['original'] = data; project[kind]['activeId'] = 'original'
        if kind == 'sheep': project['sheepCustomOriginal'] = True
        if kind == 'drama' and not project['sheep']['original']: project['sheep']['original'] = data
        saved = self.save(drama_id, {'project': project, 'revision': snapshot['revision']})
        info = self.cover_info(drama_id)
        with closing(self.connection()) as conn: name = conn.execute('SELECT current_name FROM dramas WHERE id=?', (drama_id,)).fetchone()[0]
        return {'drama_id': drama_id, 'file_path': info['cover' if kind == 'drama' else 'sheep_cover']['path'], 'filename': name + '-封面' + (Path(str(payload.get('filename') or 'cover.png')).suffix.lower()), **saved}

    def templates(self):
        with closing(self.connection()) as conn:
            row = conn.execute('SELECT content,revision FROM v3_cover_templates WHERE id=1').fetchone()
        return {'templates': json.loads(row[0]) if row else [], 'revision': row[1] if row else 0}

    def save_templates(self, payload):
        values = payload.get('templates')
        if not isinstance(values, list) or len(values) > 5: raise ValueError('通用模板最多保存5个')
        cleaned = []; ids = set()
        for t in values:
            if not isinstance(t, dict) or not isinstance(t.get('name'), str) or not 1 <= len(t['name'].strip()) <= 24: raise ValueError('模板名称无效')
            if not isinstance(t.get('id'), str) or t['id'] in ids: raise ValueError('模板编号无效')
            ids.add(t['id'])
            for key in ('width', 'height'):
                if not isinstance(t.get(key), (int,float)) or not math.isfinite(t[key]) or not 0 < t[key] <= 8192: raise ValueError('模板画幅无效')
            cleaned.append({'id':t['id'],'name':t['name'].strip(),'width':t['width'],'height':t['height'],'layers':self.layers(t.get('layers')),'createdAt':str(t.get('createdAt') or stamp())[:60]})
        with closing(self.connection()) as conn:
            conn.execute('BEGIN IMMEDIATE'); row = conn.execute('SELECT revision FROM v3_cover_templates WHERE id=1').fetchone(); revision = row[0] if row else 0
            if payload.get('revision') != revision: raise ValueError('模板已在其他窗口更新，请重新打开编辑器')
            conn.execute('INSERT INTO v3_cover_templates VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content,revision=excluded.revision', (json.dumps(cleaned, ensure_ascii=False), revision + 1)); conn.commit()
        return {'templates': cleaned, 'revision': revision + 1}


def handle(handler, method, path, payload=None):
    if not path.startswith('/api/v2/cover-editor/'): return False
    from server.flower_library import handle as handle_flowers
    if handle_flowers(handler,method,path,payload):return True
    from server import v2_file_service as files
    store = CoverStore(files.WORKSPACE, files.connection)
    try:
        task_match=re.fullmatch(r'/api/v2/cover-editor/tasks/([a-zA-Z0-9_-]+)/context',path)
        if task_match and method=='GET':
            result=store.task_context(task_match[1])
        elif path == '/api/v2/cover-editor/templates':
            result = store.templates() if method == 'GET' else store.save_templates(payload or {})
        else:
            match = re.fullmatch(r'/api/v2/cover-editor/dramas/([a-zA-Z0-9_-]+)(?:/assets/([a-f0-9]+))?', path)
            if not match: raise ValueError('封面编辑入口不存在')
            drama_id, asset_id = match.groups()
            if asset_id:
                if method != 'GET': raise ValueError('图片入口只支持读取')
                file = store.asset(drama_id, asset_id)
                import mimetypes
                handler._binary(file, mimetypes.guess_type(file.name)[0] or 'image/png', cache_control='no-store'); return True
            result = store.snapshot(drama_id) if method == 'GET' else store.save(drama_id, payload or {})
        handler._json(200, result)
    except FileNotFoundError as exc: handler._json(404, {'error': str(exc)})
    except (ValueError, OSError, sqlite3.Error) as exc: handler._json(400, {'error': str(exc)})
    return True
