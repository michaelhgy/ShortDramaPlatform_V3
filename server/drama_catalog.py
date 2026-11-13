"""Incremental Xiao V drama catalogue. Reads Xiao V; writes only V3 metadata/cache."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import re
import sqlite3
import threading
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageOps
from server.publishing.matching import normalized_name
from server.publishing.vcat import VcatClient

SOURCES = {'mini_drama': '小程序短剧', 'channels_drama': '视频号剧集'}
JOBS = {}
JOB_LOCK = threading.RLock()
CAT_LOCK = threading.Lock()
AVATAR_FILE_LOCK = threading.Lock()
SCHEMA_LOCK = threading.RLock()
LOGGER = logging.getLogger(__name__)


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def initialize(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS v3_catalog_entries(
            source TEXT NOT NULL,external_id TEXT NOT NULL,content TEXT NOT NULL,updated_at TEXT NOT NULL,
            PRIMARY KEY(source,external_id));
        CREATE TABLE IF NOT EXISTS v3_catalog_links(
            theater_id TEXT NOT NULL,source TEXT NOT NULL,external_id TEXT NOT NULL,
            drama_id TEXT REFERENCES dramas(id) ON DELETE SET NULL,issue TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(theater_id,source,external_id));
        CREATE INDEX IF NOT EXISTS idx_catalog_drama ON v3_catalog_links(drama_id);
        CREATE TABLE IF NOT EXISTS v3_catalog_availability(
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            source TEXT NOT NULL,external_id TEXT NOT NULL,usable INTEGER,
            reason TEXT NOT NULL DEFAULT '',checked_at TEXT NOT NULL,
            PRIMARY KEY(account_id,source,external_id));
        CREATE INDEX IF NOT EXISTS idx_catalog_account ON v3_catalog_availability(account_id,source,usable);
        CREATE TABLE IF NOT EXISTS v3_catalog_avatars(
            account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            remote_url TEXT NOT NULL,path TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS v3_catalog_task_mounts(
            task_id TEXT PRIMARY KEY REFERENCES production_tasks(id) ON DELETE CASCADE,
            source TEXT NOT NULL,external_id TEXT NOT NULL DEFAULT '',content TEXT NOT NULL);
    ''')
    ensure_availability_schema(conn)


def ensure_availability_schema(conn):
    """Also repair existing current-version DBs; table existence alone is insufficient."""
    with SCHEMA_LOCK:
        if 'present' not in {row[1] for row in conn.execute('PRAGMA table_info(v3_catalog_availability)')}:
            conn.execute('ALTER TABLE v3_catalog_availability ADD COLUMN present INTEGER NOT NULL DEFAULT 1')


def account_metadata(conn, item):
    row = conn.execute('SELECT path,updated_at FROM v3_catalog_avatars WHERE account_id=?', (item['id'],)).fetchone()
    if row and Path(row['path']).is_file():
        item['avatar_url'] = f"/api/v3/drama-catalog/accounts/{item['id']}/avatar?v={row['updated_at']}"
    return item


def all_drama_metadata(conn):
    result = {}
    for row in conn.execute('''SELECT l.drama_id,e.source,e.external_id,e.content,e.updated_at
        FROM v3_catalog_links l JOIN v3_catalog_entries e USING(source,external_id)
        WHERE l.drama_id IS NOT NULL ORDER BY e.source,e.external_id'''):
        entry = json.loads(row['content'])
        result.setdefault(row['drama_id'], []).append({
            'source': row['source'], 'external_id': row['external_id'], **entry,
            'updated_at': row['updated_at'],
        })
    return result


def drama_metadata(item, records):
    # Profile rows have a different id from the business drama. Catalogue
    # metadata is keyed by drama_id, otherwise official episode counts vanish.
    sources = records.get(item.get('drama_id') or item.get('id'), [])
    counts = sorted({r['mediaCount'] for r in sources if isinstance(r.get('mediaCount'), int) and r['mediaCount'] > 0})
    item.update(platform_sources=sources, official_total_episodes=counts[0] if len(counts) == 1 else 0,
                episode_count_conflict=len(counts) > 1)
    return item


def task_metadata(conn, task_id):
    row = conn.execute('SELECT source,external_id,content FROM v3_catalog_task_mounts WHERE task_id=?', (task_id,)).fetchone()
    return {'mount_source': row['source'], 'mount_external_id': row['external_id'],
            'mount_snapshot': json.loads(row['content'])} if row else {'mount_source': '', 'mount_external_id': ''}


def validate_mount(conn, payload, account_name, drama_name):
    source = str(payload.get('mount_source') or '')
    if not source:  # Existing callers/tasks retain their original publishing behaviour.
        return None
    if source not in {*SOURCES, 'plugin'}:
        raise ValueError('请选择小程序、视频号或插件挂载方式')
    account = conn.execute('SELECT id,theater_id FROM accounts WHERE nickname=?', (account_name,)).fetchone()
    drama = conn.execute('SELECT id,theater_id FROM dramas WHERE current_name=?', (drama_name,)).fetchone()
    if not account or not drama or account['theater_id'] != drama['theater_id']:
        raise ValueError('账号与剧集必须属于同一剧场，请重新选择')
    if source == 'plugin':
        return {'source': source, 'external_id': '', 'content': '{}'}
    external_id = str(payload.get('mount_external_id') or '')
    rows = conn.execute('''SELECT e.external_id,e.content FROM v3_catalog_links l
        JOIN v3_catalog_entries e USING(source,external_id)
        JOIN v3_catalog_availability a ON a.source=e.source AND a.external_id=e.external_id
        WHERE l.drama_id=? AND l.theater_id=? AND l.source=? AND a.account_id=? AND a.usable=1 AND a.present=1''',
        (drama['id'], account['theater_id'], source, account['id'])).fetchall()
    if external_id:
        rows = [r for r in rows if r['external_id'] == external_id]
    if len(rows) != 1:
        raise ValueError('当前账号没有唯一且可挂载的对应剧集，请先获取并选择具体挂载剧集')
    return {'source': source, 'external_id': rows[0]['external_id'], 'content': rows[0]['content']}


def save_task_mount(conn, task_id, mount):
    if mount:
        conn.execute('INSERT INTO v3_catalog_task_mounts VALUES(?,?,?,?)',
                     (task_id, mount['source'], mount['external_id'], mount['content']))


def guard_legacy_drafts(conn, path):
    """Validate the effective task choice; the publisher validates its typed binding."""
    match = re.fullmatch(r'/api/v2/publishing/tasks/([a-f0-9]+)/drafts', path)
    if not match: return
    from server.publishing.mounting import task_mount, resolve_source
    row = conn.execute("SELECT content FROM v3_publish_documents WHERE kind='settings' AND key=?", (match[1],)).fetchone()
    resolve_source(json.loads(row[0]) if row else {}, task_mount(conn, match[1]))


def download_image(url):
    if urlparse(url).scheme not in ('https', 'http'):
        raise ValueError('平台图片地址无效')
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError('平台图片超过20MB')
    with Image.open(io.BytesIO(data)) as im:
        if im.width * im.height > 24_000_000 or max(im.size) > 8192:
            raise ValueError('平台图片尺寸过大')
        image = ImageOps.exif_transpose(im).convert('RGBA')
        output = io.BytesIO()
        image.save(output, format='PNG')
    return output.getvalue()


class Catalogue:
    def __init__(self, workspace, connection, client_factory=VcatClient, downloader=download_image):
        self.workspace = Path(workspace)
        self.connection = connection
        self.client_factory = client_factory
        self.downloader = downloader
        with closing(self.connection()) as conn:
            with SCHEMA_LOCK:
                ensure_availability_schema(conn)
                conn.commit()

    def accounts(self, ids):
        with closing(self.connection()) as conn:
            rows = [dict(r) for r in conn.execute('SELECT a.*,t.name AS theater_name FROM accounts a JOIN theaters t ON t.id=a.theater_id') if r['id'] in ids]
        if len(rows) != len(set(ids)) or not rows:
            raise ValueError('请选择有效的运营账号')
        return rows

    def ingest(self, account, source, items, mode):
        """One transactional page: remote identifiers first, unique same-theater names next."""
        stats = dict(created=0, linked=0, updated=0, skipped=0, conflicts=0)
        cover_candidates = []
        with closing(self.connection()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            current_account = conn.execute('SELECT theater_id,channel_id FROM accounts WHERE id=?', (account['id'],)).fetchone()
            if not current_account or current_account['theater_id'] != account['theater_id'] or current_account['channel_id'] != account['channel_id']:
                raise ValueError('账号归属或平台ID已变化，请重新获取')
            theater = conn.execute('SELECT name FROM theaters WHERE id=?', (account['theater_id'],)).fetchone()
            if not theater:
                raise ValueError('账号所属剧场不存在')
            theater_name = theater[0]
            # Names are read once per page, never a whole catalogue scan for each item.
            names = {}
            for row in conn.execute('''SELECT d.id,d.current_name AS name FROM dramas d WHERE d.theater_id=?
                UNION ALL SELECT d.id,a.alias_name AS name FROM dramas d JOIN drama_aliases a ON a.drama_id=d.id WHERE d.theater_id=?''', (account['theater_id'], account['theater_id'])):
                names.setdefault(normalized_name(row['name']), set()).add(row['id'])
            for row in conn.execute('''SELECT l.drama_id,json_extract(e.content,'$.name') AS name
                FROM v3_catalog_links l JOIN v3_catalog_entries e USING(source,external_id)
                JOIN dramas d ON d.id=l.drama_id AND d.theater_id=l.theater_id
                WHERE l.theater_id=? AND l.drama_id IS NOT NULL''', (account['theater_id'],)):
                names.setdefault(normalized_name(row['name']), set()).add(row['drama_id'])
            for raw in items:
                if not isinstance(raw, dict) or not raw.get('id') or not str(raw.get('name') or '').strip():
                    stats['skipped'] += 1
                    continue
                external_id = str(raw['id'])
                old = conn.execute('SELECT content FROM v3_catalog_entries WHERE source=? AND external_id=?', (source, external_id)).fetchone()
                content = json.loads(old[0]) if old else {}
                # Never erase an old field merely because a successful response omitted it.
                fields = ('id','name','coverUrl','mediaCount','miniAppName','miniAppIconUrl','srcMiniAppName','srcMiniAppIconUrl','questFlag')
                for key in fields:
                    if key in raw and raw[key] is not None and not (isinstance(raw[key], str) and not raw[key].strip()):
                        content[key] = raw[key]
                content['id'] = external_id
                if 'mediaCount' in content:
                    try: content['mediaCount'] = max(0, int(content['mediaCount']))
                    except (ValueError, TypeError):
                        previous_count = json.loads(old[0]).get('mediaCount') if old else None
                        if isinstance(previous_count, int): content['mediaCount'] = previous_count
                        else: content.pop('mediaCount')
                serialized = json.dumps(content, ensure_ascii=False, sort_keys=True)
                if not old or old[0] != serialized:
                    conn.execute('INSERT INTO v3_catalog_entries VALUES(?,?,?,?) ON CONFLICT(source,external_id) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at', (source, external_id, serialized, stamp()))
                    stats['updated'] += int(bool(old))
                usable = int(raw['usable']) if isinstance(raw.get('usable'), bool) else None
                conn.execute('''INSERT INTO v3_catalog_availability(account_id,source,external_id,usable,reason,checked_at) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(account_id,source,external_id) DO UPDATE SET
                    usable=COALESCE(excluded.usable,v3_catalog_availability.usable),reason=CASE WHEN excluded.usable IS NULL THEN v3_catalog_availability.reason ELSE excluded.reason END,checked_at=excluded.checked_at,present=1''',
                    (account['id'], source, external_id, usable, str(raw.get('unusableReason') or ''), stamp()))
                if mode == 'usable' and usable != 1:
                    stats['skipped'] += 1
                    continue
                link = conn.execute('''SELECT d.id AS drama_id,l.issue FROM v3_catalog_links l
                    LEFT JOIN dramas d ON d.id=l.drama_id AND d.theater_id=l.theater_id
                    WHERE l.theater_id=? AND l.source=? AND l.external_id=?''', (account['theater_id'], source, external_id)).fetchone()
                drama_id = link['drama_id'] if link else None
                issue = ''
                if not drama_id:
                    matches = names.get(normalized_name(content['name']), set())
                    if len(matches) == 1:
                        drama_id = next(iter(matches)); stats['linked'] += 1
                    elif len(matches) > 1:
                        issue = '同剧场存在多个同名或历史名匹配，请确认关联'; stats['conflicts'] += 1
                    else:
                        # Keep existing global name constraints and existing records intact.
                        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', content['name']).strip().rstrip('. ')[:140] or '未命名剧集'
                        base = name
                        if conn.execute('SELECT 1 FROM dramas WHERE current_name=? UNION SELECT 1 FROM drama_aliases WHERE alias_name=?', (name, name)).fetchone():
                            name = f"{base}（{theater_name}）"
                        suffix = 1
                        while conn.execute('SELECT 1 FROM dramas WHERE current_name=? UNION SELECT 1 FROM drama_aliases WHERE alias_name=?', (name, name)).fetchone():
                            suffix += 1; name = f"{base}（{theater_name} {suffix}）"
                        drama_id = uuid.uuid4().hex
                        now = stamp()
                        conn.execute('INSERT INTO dramas(id,current_name,theater_id,created_at,updated_at) VALUES(?,?,?,?,?)', (drama_id, name, account['theater_id'], now, now))
                        names.setdefault(normalized_name(content['name']), set()).add(drama_id)
                        stats['created'] += 1
                conn.execute('INSERT INTO v3_catalog_links VALUES(?,?,?,?,?) ON CONFLICT(theater_id,source,external_id) DO UPDATE SET drama_id=excluded.drama_id,issue=excluded.issue', (account['theater_id'], source, external_id, drama_id, issue))
                if drama_id:
                    local_name = conn.execute('SELECT current_name FROM dramas WHERE id=?', (drama_id,)).fetchone()[0]
                    root = self.workspace / '剧集资料' / local_name
                    conn.execute('INSERT OR IGNORE INTO drama_profiles(id,drama_id,root_path,master_path,cover_path,updated_at) VALUES(?,?,?,?,?,?)',
                                 (uuid.uuid4().hex,drama_id,str(root),str(root / '原片'),'',stamp()))
                if drama_id and content.get('coverUrl'):
                    cover_candidates.append((drama_id, content['coverUrl']))
            conn.commit()
        return stats, list(dict.fromkeys(cover_candidates))

    def fill_cover(self, candidate):
        from server.cover_editor import CoverStore
        drama_id, url = candidate
        store = CoverStore(self.workspace, self.connection)
        with closing(self.connection()) as conn:
            project, _, _ = store._load(conn, drama_id)
            if project['drama']['original'] or project['drama']['versions']:
                return 'existing'
        data = self.downloader(url)
        path = store._write_image(drama_id, data)
        # The second check is inside the write lock: a concurrent manual replacement wins.
        with closing(self.connection()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            project, revision, name = store._load(conn, drama_id)
            if project['drama']['original'] or project['drama']['versions']:
                return 'existing'
            project['drama']['original'] = path
            if not project['sheep']['original'] and not project['sheep']['versions']:
                project['sheep']['original'] = path
            conn.execute('INSERT INTO v3_cover_projects VALUES(?,?,?) ON CONFLICT(drama_id) DO UPDATE SET content=excluded.content,revision=excluded.revision', (drama_id, json.dumps(project, ensure_ascii=False), revision + 1))
            root = self.workspace / '剧集资料' / name
            conn.execute('''INSERT INTO drama_profiles(id,drama_id,root_path,master_path,cover_path,updated_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(drama_id) DO UPDATE SET cover_path=excluded.cover_path,updated_at=excluded.updated_at''',
                (uuid.uuid4().hex, drama_id, str(root), str(root / '原片'), path, stamp()))
            conn.commit()
        return 'filled'

    def sync_avatar(self, account, remote):
        url = str(remote.get('avatar') or '')
        if not url:
            return False
        with closing(self.connection()) as conn:
            old = conn.execute('SELECT remote_url,path FROM v3_catalog_avatars WHERE account_id=?', (account['id'],)).fetchone()
        if old and old[0] == url and Path(old[1]).is_file():
            return False
        data = self.downloader(url)
        root = self.workspace / '账号头像'
        root.mkdir(parents=True, exist_ok=True)
        path = root / (hashlib.sha256(data).hexdigest() + '.png')
        # Identical avatar bytes share one file. Materialize it once even when
        # multiple account downloads finish together on Windows.
        with AVATAR_FILE_LOCK:
            if not path.exists():
                temporary = root / (uuid.uuid4().hex + '.tmp')
                temporary.write_bytes(data); temporary.replace(path)
        with closing(self.connection()) as conn:
            # Hold the write transaction across identity validation and attach.
            conn.execute('BEGIN IMMEDIATE')
            # Recheck identity after downloading, before attaching an image.
            current = conn.execute('SELECT channel_id FROM accounts WHERE id=?', (account['id'],)).fetchone()
            if not current or (account.get('channel_id') is not None and current['channel_id'] != account['channel_id']):
                raise ValueError('账号已删除或平台ID已变化，请重新获取')
            updated = stamp()
            conn.execute('INSERT INTO v3_catalog_avatars VALUES(?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET remote_url=excluded.remote_url,path=excluded.path,updated_at=excluded.updated_at', (account['id'], url, str(path), updated))
            conn.execute("INSERT INTO v2_change_events(change_type,account_id,updated_at) VALUES ('account_changed',?,?)", (account['id'], updated))
            conn.commit()
        return True

    def reconcile(self, account_id, source, seen):
        """Hide absent account/source entries only after a verified complete scan."""
        with closing(self.connection()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute('SELECT external_id FROM v3_catalog_availability WHERE account_id=? AND source=? AND present=1', (account_id, source)).fetchall()
            missing = [row[0] for row in rows if row[0] not in seen]
            conn.executemany("UPDATE v3_catalog_availability SET present=0,usable=0,reason='本次完整获取未返回该剧，当前账号已不可挂载',checked_at=? WHERE account_id=? AND source=? AND external_id=?",
                             [(stamp(), account_id, source, external_id) for external_id in missing])
            conn.commit()
        return len(missing)

    def items(self, account_id, source, query='', page=1, usable_only=False, page_size=24):
        account = self.accounts([account_id])[0]
        if source not in SOURCES:
            raise ValueError('挂载来源无效')
        if page_size not in (24, 48, 96):
            raise ValueError('每页剧集数请选择24、48或96部')
        where = 'a.account_id=? AND a.source=? AND a.present=1'
        args = [account_id, source]
        if usable_only: where += ' AND a.usable=1'
        if query:
            where += " AND (instr(lower(json_extract(e.content,'$.name')),lower(?))>0 OR instr(lower(d.current_name),lower(?))>0)"
            args += [query, query]
        tables = '''FROM v3_catalog_availability a JOIN v3_catalog_entries e USING(source,external_id)
            LEFT JOIN v3_catalog_links l ON l.source=a.source AND l.external_id=a.external_id AND l.theater_id=?
            LEFT JOIN dramas d ON d.id=l.drama_id AND d.theater_id=l.theater_id'''
        with closing(self.connection()) as conn:
            total = conn.execute('SELECT COUNT(*) ' + tables + ' WHERE ' + where, [account['theater_id'], *args]).fetchone()[0]
            page = min(max(1, page), max(1, (total + page_size - 1) // page_size))
            rows = conn.execute('SELECT a.*,e.content,d.id AS drama_id,l.issue,d.current_name ' + tables + ' WHERE ' + where + " ORDER BY a.usable DESC,json_extract(e.content,'$.name'),a.external_id LIMIT ? OFFSET ?", [account['theater_id'], *args, page_size, (page-1)*page_size]).fetchall()
        return {'items': [{**dict(r), **json.loads(r['content']), 'content': None} for r in rows], 'total': total, 'page': max(1, page), 'page_size': page_size}

    def eligibility(self, account_ids, source):
        if source not in SOURCES: return {'items': []}
        accounts = self.accounts(account_ids)
        result = []
        with closing(self.connection()) as conn:
            for account in accounts:
                for row in conn.execute('''SELECT l.drama_id,e.external_id,e.content,a.checked_at
                    FROM v3_catalog_links l JOIN v3_catalog_entries e USING(source,external_id)
                    JOIN dramas d ON d.id=l.drama_id AND d.theater_id=l.theater_id
                    JOIN v3_catalog_availability a USING(source,external_id)
                    WHERE l.theater_id=? AND l.drama_id IS NOT NULL AND a.account_id=? AND a.source=? AND a.usable=1 AND a.present=1''',
                    (account['theater_id'],account['id'],source)):
                    content = json.loads(row['content'])
                    result.append({'account_id':account['id'],'drama_id':row['drama_id'],
                                   'external_id':row['external_id'],'name':content['name'],
                                   'miniAppName':content.get('miniAppName',''),'checked_at':row['checked_at']})
        return {'items': result}

    def link(self, account_id, source, external_id, drama_id):
        account = self.accounts([account_id])[0]
        with closing(self.connection()) as conn:
            row = conn.execute('SELECT theater_id FROM dramas WHERE id=?', (drama_id,)).fetchone()
            if not row or row[0] != account['theater_id']:
                raise ValueError('只能关联当前账号所属剧场的剧集')
            if not conn.execute('SELECT 1 FROM v3_catalog_availability WHERE account_id=? AND source=? AND external_id=?', (account_id, source, external_id)).fetchone():
                raise ValueError('请先获取当前账号的剧集')
            conn.execute('INSERT INTO v3_catalog_links VALUES(?,?,?,?,?) ON CONFLICT(theater_id,source,external_id) DO UPDATE SET drama_id=excluded.drama_id,issue=excluded.issue', (account['theater_id'], source, external_id, drama_id, ''))
            conn.commit()
        return {'linked': True}

    def start(self, account_ids, sources, mode):
        accounts = self.accounts(account_ids)
        if mode not in ('usable', 'all') or not sources or any(s not in SOURCES for s in sources):
            raise ValueError('请选择获取来源及获取可挂载或获取全部')
        with JOB_LOCK:
            running = next((j for j in JOBS.values() if j['status'] in ('queued','running','stopping')), None)
            if running:
                raise ValueError('已有剧集获取任务正在运行，请等待完成或停止后重试')
            job = dict(id=uuid.uuid4().hex, status='queued', account_ids=account_ids, sources=list(dict.fromkeys(sources)), mode=mode,
                       fetched=0, created=0, linked=0, updated=0, skipped=0, conflicts=0, covers=0, cover_errors=0,
                       avatars=0, removed=0, page=0, total_reported=0, message='等待连接小V', errors=[], stop=False, updated_at=stamp())
            # Retain a small recent history rather than growing process memory forever.
            for key in list(JOBS)[:-19]: JOBS.pop(key, None)
            JOBS[job['id']] = job
        threading.Thread(target=self._run, args=(job, accounts), daemon=True, name='v3-catalog-sync').start()
        return snapshot(job['id'])

    def _run(self, job, accounts):
        def change(**values):
            with JOB_LOCK: job.update(**values, updated_at=stamp())
        try:
            change(status='running', message='正在读取账号和头像')
            with CAT_LOCK, self.client_factory(writable=False) as cat:
                remote_accounts = {a['uid']: a for a in cat.accounts() if a.get('platform') == 'Channels'}
                # Sync avatars for all locally matching accounts, including accounts outside this fetch selection.
                with closing(self.connection()) as conn:
                    local_accounts = [dict(r) for r in conn.execute('SELECT id,channel_id FROM accounts')]
                for account in local_accounts:
                    if job['stop']: break
                    remote = remote_accounts.get(account['channel_id'])
                    if remote:
                        try: job['avatars'] += int(self.sync_avatar(account, remote))
                        except (OSError, ValueError): pass  # Keep the existing avatar.
                for account in accounts:
                    remote = remote_accounts.get(account['channel_id'])
                    if not remote or remote.get('loginStatus') != '登录有效':
                        job['errors'].append(f"{account['nickname']}：账号未登录或登录失效，保留已有资料")
                        continue
                    for source in job['sources']:
                        if job['stop']: break
                        seen = set(); expected_total = None; complete = False
                        try:
                            for page in range(1,1001):
                                if job['stop']: break
                                change(account_name=account['nickname'], source=source, page=page,
                                       message=f"{account['nickname']} · {SOURCES[source]} · 第{page}页")
                                params = {'page': page, 'queryString': ''}
                                if source == 'channels_drama': params['sceneType'] = 3
                                response = cat.worker(account['channel_id'], 'getDramaComponent', params)
                                if not isinstance(response, dict) or 'list' not in response or not isinstance(response['list'], list):
                                    raise RuntimeError('接口返回内容不完整，已保存的资料保持不变')
                                if response.get('baseResp', {}).get('errcode') not in (None,0):
                                    raise RuntimeError('平台查询失败，已保存的资料保持不变')
                                rows = response['list']
                                raw_total = response.get('totalCount')
                                if raw_total is not None:
                                    if isinstance(raw_total, bool) or not str(raw_total).isdigit():
                                        raise RuntimeError('目录总数无效，未移除上次获取的剧集')
                                    total_reported = int(raw_total)
                                    if expected_total is not None and expected_total != total_reported:
                                        raise RuntimeError('获取期间目录总数发生变化，请重新获取；未移除上次获取的剧集')
                                    expected_total = total_reported
                                    change(total_reported=total_reported)
                                if any(not isinstance(row, dict) or not str(row.get('id') or '').strip() or not str(row.get('name') or '').strip() for row in rows):
                                    raise RuntimeError('目录包含不完整剧目，未移除上次获取的剧集')
                                if not rows:
                                    complete = expected_total is not None and len(seen) == expected_total
                                    break
                                unseen = [r for r in rows if isinstance(r,dict) and str(r.get('id') or '') not in seen]
                                if not unseen:
                                    raise RuntimeError('接口重复返回同一页，已停止该来源，稍后可重新获取')
                                seen.update(str(r.get('id') or '') for r in unseen)
                                stats, covers = self.ingest(account, source, unseen, job['mode'])
                                with JOB_LOCK:
                                    job['fetched'] += len(unseen)
                                    for key, value in stats.items(): job[key] += value
                                with ThreadPoolExecutor(max_workers=4) as pool:
                                    futures = [pool.submit(self.fill_cover, c) for c in covers if not job['stop']]
                                    for future in futures:
                                        try: job['covers'] += int(future.result() == 'filled')
                                        except (OSError, ValueError, sqlite3.Error): job['cover_errors'] += 1
                                if expected_total is not None and len(seen) >= expected_total:
                                    complete = len(seen) == expected_total
                                    break
                            else:
                                raise RuntimeError('达到1000页保护上限，已保留当前获取结果')
                            if not job['stop']:
                                if not complete:
                                    raise RuntimeError('未确认获取完整目录，未移除上次获取的剧集，请重新获取')
                                removed = self.reconcile(account['id'], source, seen)
                                change(removed=job['removed'] + removed)
                        except Exception as exc:
                            # Do not leak browser internals, tokens, or raw MCP errors into persistent data.
                            if isinstance(exc, sqlite3.Error):
                                LOGGER.exception('剧集目录保存失败 account_id=%s source=%s', account['id'], source)
                                message = '剧集目录保存失败，未移除已有资料，请重试；若持续失败请重新启动软件'
                            else:
                                message = str(exc) if isinstance(exc,(ValueError,RuntimeError)) else '读取中断，已获取资料已保留，可重新获取'
                            job['errors'].append(f"{account['nickname']} · {SOURCES[source]}：{message[:180]}")
            change(status='stopped' if job['stop'] else ('partial' if job['errors'] else 'completed'),
                   message='已停止，成功获取的资料已保留' if job['stop'] else ('获取未完成，成功批次已保存，原有目录未移除' if job['errors'] else '获取结束，剧集资料已保存'))
        except Exception:
            change(status='error', message='连接小V失败，请确认小V已打开且MCP可连接；已有资料保持不变')


def snapshot(job_id):
    with JOB_LOCK:
        if job_id not in JOBS:
            raise ValueError('获取任务不存在或服务已重启，请重新获取；已入库资料仍然保留')
        return copy.deepcopy({k:v for k,v in JOBS[job_id].items() if k != 'stop'})


def handle(handler, method, path, payload=None):
    prefix = '/api/v3/drama-catalog'
    if not path.startswith(prefix): return False
    from server.account_import import handle as handle_accounts
    if handle_accounts(handler, method, path, payload): return True
    from server import v2_file_service as files
    catalogue = Catalogue(files.WORKSPACE, files.connection)
    query = parse_qs(urlparse(handler.path).query)
    payload = payload or {}
    try:
        if path == prefix + '/items' and method == 'GET':
            result = catalogue.items(query.get('account_id',[''])[0], query.get('source',[''])[0], query.get('query',[''])[0], int(query.get('page',['1'])[0]), query.get('usable_only',['0'])[0] == '1', int(query.get('page_size',['24'])[0]))
        elif path == prefix + '/eligibility' and method == 'GET':
            result = catalogue.eligibility(query.get('account_ids',[''])[0].split(','), query.get('source',[''])[0])
        elif path == prefix + '/sync' and method == 'POST':
            result = catalogue.start(payload.get('account_ids') or [], payload.get('sources') or [], payload.get('mode'))
        elif path == prefix + '/latest' and method == 'GET':
            with JOB_LOCK: last = next(reversed(JOBS), None)
            result = snapshot(last) if last else None
        elif path == prefix + '/link' and method == 'POST':
            result = catalogue.link(payload.get('account_id'),payload.get('source'),payload.get('external_id'),payload.get('drama_id'))
        else:
            avatar = re.fullmatch(prefix + r'/accounts/([a-f0-9]+)/avatar', path)
            match = re.fullmatch(prefix + r'/jobs/([a-f0-9]+)(/stop)?', path)
            if avatar and method == 'GET':
                with closing(files.connection()) as conn:
                    row = conn.execute('SELECT path FROM v3_catalog_avatars WHERE account_id=?', (avatar[1],)).fetchone()
                if not row or not Path(row[0]).is_file(): raise ValueError('账号头像暂不可用')
                handler._binary(Path(row[0]), 'image/png', cache_control='private, max-age=3600'); return True
            if not match: raise ValueError('剧集获取入口不存在')
            if match[2] and method == 'POST':
                snapshot(match[1])
                with JOB_LOCK:
                    if JOBS[match[1]]['status'] in ('queued','running','stopping'):
                        JOBS[match[1]].update(stop=True,status='stopping',message='正在停止，保留已获取资料')
            elif method != 'GET' or match[2]: raise ValueError('请求方式无效')
            result = snapshot(match[1])
        handler._json(200, result)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        handler._json(400, {'error': str(exc)})
    return True
