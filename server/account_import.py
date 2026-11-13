"""Preview Xiao V accounts and add only human-selected, theater-assigned records."""
from __future__ import annotations

import copy
import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from urllib.parse import urlparse

from server.drama_catalog import Catalogue, CAT_LOCK, account_metadata
from server.publishing.vcat import VcatClient

LOCK = threading.RLock()
PREVIEWS = {}
RUNS = {}
PREVIEW_TTL = 3600
CLIENT_FACTORY = VcatClient
FIELDS = ('uid', 'platform', 'platformName', 'nickname', 'avatar', 'groupName', 'tags', 'loginStatus', 'fansTotal')


class AccountImport:
    def __init__(self, workspace, connection, client_factory=None, avatar_catalogue=None):
        self.workspace = workspace
        self.connection = connection
        self.client_factory = client_factory or CLIENT_FACTORY
        self.avatars = avatar_catalogue or Catalogue(workspace, connection)

    def preview(self):
        # Only safe MCP fields enter the preview cache. Cookies/tokens never leave Xiao V.
        with CAT_LOCK, self.client_factory(writable=False) as client:
            accounts = client.accounts(resolve_groups=True)
        if not isinstance(accounts, list):
            raise ValueError('小V猫账号列表返回不完整，请重新获取')
        safe = []
        seen = set()
        for raw in accounts:
            if not isinstance(raw, dict) or raw.get('platform') != 'Channels': continue
            uid = str(raw.get('uid') or '').strip()
            if not uid or uid in seen: continue
            seen.add(uid)
            item = {key: raw.get(key) for key in FIELDS}
            item['uid'] = uid
            item['nickname'] = str(raw.get('nickname') or '').strip()
            item['tags'] = [str(t)[:80] for t in (raw.get('tags') or [])] if isinstance(raw.get('tags'), list) else []
            safe.append(item)
        with closing(self.connection()) as conn:
            local = [account_metadata(conn, dict(r)) for r in conn.execute('SELECT id,nickname,channel_id FROM accounts')]
        by_uid = {r['channel_id']:r for r in local}
        by_name = {r['nickname']:r for r in local}
        result = []
        for item in safe:
            exists = by_uid.get(item['uid'])
            conflict = by_name.get(item['nickname']) if not exists else None
            result.append({**item, 'match': 'existing' if exists else 'nickname_conflict' if conflict else 'new',
                           'local_nickname': exists['nickname'] if exists else None,
                           'localAvatar': exists.get('avatar_url') if exists else None})
        token = uuid.uuid4().hex
        now = time.monotonic()
        with LOCK:
            for key in list(PREVIEWS):
                if now - PREVIEWS[key]['created'] > PREVIEW_TTL: PREVIEWS.pop(key, None)
            if len(PREVIEWS) >= 20: PREVIEWS.pop(next(iter(PREVIEWS)))
            PREVIEWS[token] = {'created': now, 'accounts': {a['uid']:a for a in safe}, 'run_id': None}
        return {'token':token, 'items':result, 'total':len(result), 'local_nicknames':[r['nickname'] for r in local],
                'existing_count':sum(a['match']=='existing' for a in result),
                'new_count':sum(a['match']!='existing' for a in result),
                'conflict_count':sum(a['match']=='nickname_conflict' for a in result)}

    def start(self, token, items):
        if not isinstance(items, list) or not items or len(items) > 1000:
            raise ValueError('请勾选1至1000个待新增账号')
        if any(not isinstance(item,dict) for item in items):
            raise ValueError('账号选择内容无效')
        uids = [str(item.get('uid') or '') for item in items]
        if len(set(uids)) != len(uids): raise ValueError('选中的平台ID重复，请重新获取')
        with LOCK:
            preview = PREVIEWS.get(token)
            if not preview or time.monotonic()-preview['created'] > PREVIEW_TTL:
                raise ValueError('账号预览已过期或服务已重启，请重新获取；剧场选择可保留')
            if any(uid not in preview['accounts'] for uid in uids):
                raise ValueError('选中账号不在本次小V猫获取结果中，请重新获取')
            if preview['run_id']:
                return self.status(preview['run_id'])
            run_id = uuid.uuid4().hex
            run = {'id':run_id,'status':'queued','total':len(items),'completed':0,'created':0,'skipped':0,
                   'failed':0,'avatar_failed':0,'avatars':0,'results':[],
                   'message':'正在添加账号','finished_at':None}
            for key in list(RUNS)[:-19]:
                if RUNS[key]['status'] in ('completed','error'): RUNS.pop(key, None)
            RUNS[run_id] = run
            preview['run_id'] = run_id
            remote = {uid:copy.deepcopy(preview['accounts'][uid]) for uid in uids}
        threading.Thread(target=self._run,args=(run,copy.deepcopy(items),remote),daemon=True,name='v3-account-import').start()
        return self.status(run_id)

    def start_avatar_sync(self, token):
        # Explicit action: preview remains read-only and can never add accounts.
        with LOCK:
            preview = PREVIEWS.get(token)
            if not preview or time.monotonic() - preview['created'] > PREVIEW_TTL:
                raise ValueError('账号预览已过期，请重新获取后再同步头像')
            previous = RUNS.get(preview.get('avatar_run_id'))
            if previous:
                return copy.deepcopy(previous)
            with closing(self.connection()) as conn:
                local = [dict(r) for r in conn.execute('SELECT id,nickname,channel_id FROM accounts')]
            matches = [(a, copy.deepcopy(preview['accounts'][a['channel_id']])) for a in local
                       if a['channel_id'] in preview['accounts']]
            if not matches:
                raise ValueError('本次获取结果中没有已存在的本地账号可同步头像')
            run_id = uuid.uuid4().hex
            run = {'id':run_id, 'kind':'avatars', 'status':'queued', 'total':len(matches), 'completed':0,
                   'created':0, 'skipped':0, 'failed':0, 'avatar_failed':0, 'avatars':0, 'results':[],
                   'message':'正在同步已有账号头像', 'finished_at':None}
            for key in list(RUNS)[:-19]:
                if RUNS[key]['status'] in ('completed','error'): RUNS.pop(key, None)
            RUNS[run_id] = run
            preview['avatar_run_id'] = run_id
        threading.Thread(target=self._sync_avatars, args=(run,matches), daemon=True, name='v3-account-avatar-sync').start()
        return self.status(run_id)

    def _sync_avatars(self, run, matches):
        from server import v2_file_service as files
        with LOCK: run['status'] = 'running'
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [(account, pool.submit(self.avatars.sync_avatar, account, entry)) for account,entry in matches]
                for account, future in futures:
                    result = {'uid':account['channel_id'], 'nickname':account['nickname'], 'account_id':account['id']}
                    try:
                        updated = future.result()
                        result.update(status='updated' if updated else 'skipped', message='头像已更新' if updated else '头像无变化或小V猫未提供图片')
                        with LOCK:
                            run['avatars'] += int(updated)
                            run['skipped'] += int(not updated)
                    except Exception:
                        result.update(status='failed', message='头像同步失败，保留原头像；重新获取后可重试')
                        with LOCK:
                            run['avatar_failed'] += 1
                            run['failed'] += 1
                    with LOCK:
                        run['results'].append(result)
                        run['completed'] += 1
            with LOCK:
                run.update(status='completed', message='已有账号头像同步完成', finished_at=files.now_text())
        except Exception:
            with LOCK:
                run.update(status='error', message='头像同步已中断，已完成的头像保留，请重新获取后重试', finished_at=files.now_text())

    @staticmethod
    def status(run_id):
        with LOCK:
            if run_id not in RUNS: raise ValueError('导入进度不存在或服务已重启，请重新获取账号；已添加的账号会自动识别')
            return copy.deepcopy(RUNS[run_id])

    def _run(self, run, items, remote):
        from server import v2_file_service as files
        created = []
        committed = False
        try:
            with LOCK: run['status'] = 'running'
            with closing(self.connection()) as conn:
                conn.execute('BEGIN IMMEDIATE')
                for item in items:
                    uid = str(item['uid'])
                    entry = remote[uid]
                    result = {'uid':uid,'nickname':str(item.get('nickname') or entry['nickname'])}
                    conn.execute('SAVEPOINT import_account')
                    try:
                        existing = conn.execute('SELECT id,nickname FROM accounts WHERE channel_id=?',(uid,)).fetchone()
                        if existing:
                            result.update(status='skipped',nickname=existing['nickname'],message='已存在，未修改')
                        else:
                            name = files.safe_component(result['nickname'], '账号昵称')
                            theater_id = str(item.get('theater_id') or '')
                            theater = conn.execute('SELECT name,status FROM theaters WHERE id=?',(theater_id,)).fetchone()
                            if not theater or theater['status'] != '启用': raise ValueError('请选择已启用的所属剧场')
                            if conn.execute('SELECT 1 FROM accounts WHERE nickname=?',(name,)).fetchone():
                                raise ValueError('昵称已存在且平台ID不同，请修改本地昵称')
                            account_id = uuid.uuid4().hex
                            now = files.now_text()
                            conn.execute('''INSERT INTO accounts(id,nickname,channel_id,theater_id,sub_theater_name,status,
                                reporting_date,registration_date,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                                (account_id,name,uid,theater_id,'','正常','','','',now,now))
                            created.append(({'id':account_id,'channel_id':uid},entry))
                            result.update(status='created',nickname=name,account_id=account_id,theater_name=theater['name'],message='已新增')
                        conn.execute('RELEASE import_account')
                    except (ValueError, sqlite3.IntegrityError) as exc:
                        conn.execute('ROLLBACK TO import_account');conn.execute('RELEASE import_account')
                        result.update(status='failed',message=str(exc))
                    with LOCK:
                        run['results'].append(result)
                conn.commit()
                committed = True
            with LOCK:
                for result in run['results']:
                    run[{'created':'created','skipped':'skipped','failed':'failed'}[result['status']]] += 1
                run['completed'] = len(items)
                run['message'] = '账号已保存，正在缓存头像'
            # Avatar failure does not turn a successfully created business account into a failure.
            with ThreadPoolExecutor(max_workers=4) as pool:
                for future in [pool.submit(self.avatars.sync_avatar,account,entry) for account,entry in created]:
                    try:
                        updated = future.result()
                        with LOCK: run['avatars'] += int(updated)
                    except Exception:
                        with LOCK: run['avatar_failed'] += 1
            with LOCK: run.update(status='completed',message='账号获取与新增完成',finished_at=files.now_text())
        except Exception:
            # On connection/commit failure do not claim tentative rows were saved; refresh checks UID again.
            with LOCK:
                if not committed: run.update(results=[],created=0,skipped=0,failed=0,completed=0)
                run.update(status='error',message='添加过程已中断，请重新获取账号核对已存在项后重试',finished_at=files.now_text())


def handle(handler, method, path, payload=None):
    prefix = '/api/v3/drama-catalog/account-import'
    if not path.startswith(prefix): return False
    from server import v2_file_service as files
    service = AccountImport(files.WORKSPACE, files.connection)
    payload = payload or {}
    try:
        if path == prefix+'/preview' and method == 'POST': result = service.preview()
        elif path == prefix+'/sync-avatars' and method == 'POST': result = service.start_avatar_sync(str(payload.get('token') or ''))
        elif path == prefix+'/start' and method == 'POST': result = service.start(str(payload.get('token') or ''),payload.get('items'))
        elif path.startswith(prefix+'/runs/') and method == 'GET': result = service.status(path.removeprefix(prefix+'/runs/'))
        else: raise ValueError('账号获取入口不存在')
        handler._json(200,result)
    except (ValueError,RuntimeError,OSError,sqlite3.Error) as exc:
        handler._json(400,{'error':str(exc)})
    return True
