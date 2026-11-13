"""Real workbench collection and durable V3 publication attribution.

A successful upload is not proof of public publication. Platform-timed works
are bound by account + platform effectiveTime while still scheduled. Only a
subsequent published observation admits the work into the denominator.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

SH = timezone(timedelta(hours=8))
LOCK = threading.Lock()
SOURCE = 'xiao_v_live'


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def stamp():
    return datetime.now(SH).isoformat(timespec='seconds')


def number(value):
    try:
        n = float(value) if value is not None and not isinstance(value, bool) and value != '' else None
        return n if n is not None and math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def unix(value):
    if isinstance(value, (int, float)):
        return int(value) if math.isfinite(value) else None
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return int((d if d.tzinfo else d.replace(tzinfo=SH)).timestamp())
    except (ValueError, TypeError, OverflowError):
        return None


def local_time(value):
    return datetime.fromtimestamp(value, SH).strftime('%Y-%m-%d %H:%M:%S') if value else ''


def initialize(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS v3_operations_cache(
        uid TEXT NOT NULL,kind TEXT NOT NULL,payload_json TEXT NOT NULL,fetched_at TEXT NOT NULL,
        PRIMARY KEY(uid,kind));
      CREATE TABLE IF NOT EXISTS v3_publication_history(
        id TEXT PRIMARY KEY,execution_key TEXT NOT NULL,item_key TEXT NOT NULL,local_id TEXT NOT NULL,
        uid TEXT NOT NULL,account_id TEXT NOT NULL DEFAULT '',scheduled_unix INTEGER,
        schedule_type TEXT NOT NULL,task_state TEXT NOT NULL,post_id TEXT NOT NULL DEFAULT '',
        publish_unix INTEGER,publication_state TEXT NOT NULL DEFAULT 'unlinked',
        match_state TEXT NOT NULL DEFAULT 'unlinked',first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,UNIQUE(execution_key,item_key));
      CREATE UNIQUE INDEX IF NOT EXISTS idx_v3_publication_work
        ON v3_publication_history(uid,post_id) WHERE post_id<>'';
      CREATE TABLE IF NOT EXISTS v3_publication_optimizations(
        publication_id TEXT PRIMARY KEY,uid TEXT NOT NULL,post_id TEXT NOT NULL,export_id TEXT NOT NULL,
        analysis TEXT NOT NULL,tips_json TEXT NOT NULL,appeal_type INTEGER,platform_state TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS v3_operations_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,finished_at TEXT NOT NULL,summary_json TEXT NOT NULL);
    ''')

    from server.work_history import initialize as initialize_works
    initialize_works(conn)

def accounts_by_uid(conn, *, include_cancelled=False, include_paused=True):
    grouped = {}
    columns = {r[1] for r in conn.execute('PRAGMA table_info(accounts)')}
    active = "status<>'注销' AND " if 'status' in columns and not include_cancelled else ''
    if 'status' in columns and not include_paused:
        active += "status NOT IN ('停用','disabled') AND "
    for row in conn.execute(f"SELECT id,channel_id FROM accounts WHERE {active}channel_id<>''"):
        grouped.setdefault(row['channel_id'], []).append(row['id'])
    return {uid: ids[0] for uid, ids in grouped.items() if len(ids) == 1}


def executions(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_publish_documents'").fetchone():
        return []
    result = []
    for row in conn.execute("SELECT key,content FROM v3_publish_documents WHERE kind='publish_execution'"):
        for item in [*json.loads(row['content']).get('previous_items', []), *json.loads(row['content']).get('items', [])]:
            if item.get('uid') and item.get('key'):
                result.append((row['key'], item))
    return result


def record_executions(conn, docs=None, fetched_at=None):
    """Snapshot every attempt before its source task may be removed; no network."""
    at = fetched_at or stamp()
    ids = accounts_by_uid(conn, include_cancelled=True)
    saved = {r['id']: json.loads(r['payload_json']) for r in conn.execute('SELECT id,payload_json FROM v3_publication_history')}
    settings = {r['key']: json.loads(r['content']) for r in conn.execute("SELECT key,content FROM v3_publish_documents WHERE kind='settings'")} if conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_publish_documents'").fetchone() else {}
    for execution, row in docs if docs is not None else executions(conn):
        uid = row['uid']
        payload = row.get('accepted_payload') or row.get('payload') or {}
        mode = payload.get('scheduleType')
        if not mode:
            mode = 'timing' if unix(row.get('time')) else 'now'
        scheduled = unix(payload.get('scheduleTime') or row.get('time')) if mode == 'timing' else None
        identity = hashlib.sha256((execution+'\0'+row['key']).encode()).hexdigest()
        # Keep display metadata and previously captured work media, never session/task payloads.
        meta = {**saved.get(identity, {}), 'name': row.get('name') or saved.get(identity, {}).get('name', ''),
                'video_id': row.get('video_id') or ''}
        if settings.get(execution, {}).get('drama_id'): meta['drama_id']=settings[execution]['drama_id']
        conn.execute('''INSERT INTO v3_publication_history
          (id,execution_key,item_key,local_id,uid,account_id,scheduled_unix,schedule_type,task_state,
           first_seen_at,last_seen_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(execution_key,item_key) DO UPDATE SET local_id=excluded.local_id,
           account_id=excluded.account_id,scheduled_unix=excluded.scheduled_unix,
           schedule_type=excluded.schedule_type,task_state=excluded.task_state,last_seen_at=excluded.last_seen_at,
           payload_json=excluded.payload_json''',
          (identity,execution,row['key'],str(row.get('local_id') or ''),uid,ids.get(uid,''),scheduled,mode,
           row.get('status') or '',at,at,dump(meta)))


def reconcile(conn, posts_by_uid, tasks_by_uid, fetched_at=None):
    at = fetched_at or stamp()
    record_executions(conn, fetched_at=at)
    from server import work_history
    for uid, posts in posts_by_uid.items():
        work_history.ingest_posts(conn, uid, posts, at)
    rows = [dict(r) for r in conn.execute('SELECT * FROM v3_publication_history')]
    proposals = {}
    for row in rows:
        uid = row['uid']
        if uid not in posts_by_uid:
            continue  # Failed/missing collection must never erase attribution.
        posts = posts_by_uid[uid]
        if row['post_id']:
            hits = [p for p in posts if p['postId'] == row['post_id']]
            mode = 'matched'
        else:
            tasks = [t for t in tasks_by_uid.get(uid, []) if t.get('uid') == uid
                     and str(t.get('localId') or '') == row['local_id'] and row['local_id']]
            # Require a verified submission, not merely a planned slot.
            if len(tasks) != 1 or not (tasks[0].get('status') in ('发布成功','已发布','success','published') or str(tasks[0].get('statusCode')) == '2'):
                continue
            pid = (tasks[0].get('_source') or {}).get('postId')
            if pid:
                hits = [p for p in posts if p['postId'] == str(pid)]
            elif row['schedule_type'] == 'timing' and row['scheduled_unix']:
                # Match platform schedule, never the upload/create/task end time.
                hits = [p for p in posts if p.get('scheduleUnix') == row['scheduled_unix']
                        and p.get('publishStatus') in ('scheduled', 'published')]

            else:
                conn.execute("UPDATE v3_publication_history SET match_state='unsupported' WHERE id=?", (row['id'],))
                continue
            mode = 'matched' if len(hits) == 1 else 'ambiguous' if hits else 'unlinked'
        if len(hits) != 1:
            if not row['post_id']:
                conn.execute('UPDATE v3_publication_history SET match_state=? WHERE id=?', (mode,row['id']))
            continue
        post = hits[0]
        proposals.setdefault((uid, post['postId']), []).append((row, post))
    for (uid, pid), candidates in proposals.items():
        owners = [r['id'] for r in rows if r['uid'] == uid and r['post_id'] == pid]
        if len(candidates) != 1 or (owners and owners != [candidates[0][0]['id']]):
            for row, _ in candidates:
                if not row['post_id']:
                    conn.execute("UPDATE v3_publication_history SET match_state='ambiguous' WHERE id=?", (row['id'],))
            continue
        row, post = candidates[0]
        published = post.get('publishStatus') == 'published'
        state = 'published' if published or row['publication_state'] == 'published' else 'scheduled' if post.get('publishStatus') == 'scheduled' else 'unconfirmed'
        publish_at = post.get('postUnix') if published and post.get('postUnix') else row['publish_unix']
        if state == 'published' and not publish_at: state = 'unconfirmed'
        from server.work_media import local_cover_url, playback_url
        meta=json.loads(row['payload_json'])
        if local_cover_url(post.get('coverLocalId')): meta['cover_url']=local_cover_url(post['coverLocalId'])
        if 'videoUrl' in post and (post.get('metricSource')=='online_list' or not meta.get('video_url')):
            meta['video_url']=playback_url(post['videoUrl'])
        if 'videoDuration' in post: meta['video_duration']=number(post['videoDuration'])
        if post.get('publishStatus') in ('scheduled', 'published'):
            meta['official_status'] = post['publishStatus']
            meta.setdefault('delivery_confirmed_at', at)
        conn.execute('''UPDATE v3_publication_history SET post_id=?,publish_unix=?,publication_state=?,
            match_state='matched',last_seen_at=?,payload_json=? WHERE id=?''',(pid,publish_at,state,at,dump(meta),row['id']))
    from server.publishing.delivery import sync_public_release_times
    sync_public_release_times(conn)


def _publication_completion(conn, task_id, state):
    """Delivery is complete once every current item is accepted by the platform.

    A saved platform schedule counts; public release and its timestamp remain
    separate analytics observations. Never treat a local timer or upload start
    as completed delivery.
    """
    from server.publishing.delivery import delivery_confirmation, epoch
    items = [item for item in (state or {}).get('items', [])
             if isinstance(item, dict) and item.get('key')]
    if not items:
        return {'complete': False, 'reason': 'no_current_items', 'matched': 0, 'total': 0, 'confirmed_keys': []}
    confirmed = []
    times = []
    identities = set()
    observed = int(datetime.now(SH).timestamp())
    for item in items:
        payload = item.get('accepted_payload') or item.get('payload') or {}
        if item.get('status') != 'success' or payload.get('scheduleType') not in ('now', 'timing'):
            continue
        if not item.get('uid') or not item.get('local_id'):
            continue
        if item.get('checks') and not all(item['checks'].values()):
            continue
        proof = delivery_confirmation(item)
        if not proof:
            identity = hashlib.sha256((str(task_id) + '\0' + str(item['key'])).encode()).hexdigest()
            row = conn.execute("""SELECT post_id,uid,local_id,publication_state,match_state,payload_json
                FROM v3_publication_history WHERE id=?""", (identity,)).fetchone()
            if not row or row['match_state'] != 'matched' or not row['post_id']:
                continue
            if item.get('uid') != row['uid'] or str(item.get('local_id') or '') != str(row['local_id'] or ''):
                continue
            remote = item.get('remote') or {}
            if remote and (remote.get('uid') != item.get('uid') or str(remote.get('localId') or '') != str(item.get('local_id') or '')):
                continue
            remote_pid = str((remote.get('_source') or {}).get('postId') or '')
            if remote_pid and remote_pid != row['post_id']:
                continue
            proof = delivery_confirmation(item, row['post_id'])
            if not proof:
                # Historical observations can independently prove acceptance,
                # but explicit mismatched/failed remote evidence must not be bypassed.
                if remote:
                    continue
                meta = json.loads(row['payload_json'])
                if row['publication_state'] not in ('scheduled', 'published') and meta.get('official_status') not in ('scheduled', 'published'):
                    continue
                proof = {'post_id': row['post_id'], 'delivered_unix': epoch(meta.get('delivery_confirmed_at'))}
        identity = (item.get('uid'), proof['post_id'])
        if identity in identities:
            continue
        identities.add(identity)
        confirmed.append(item['key'])
        times.append(proof.get('delivered_unix') or epoch(item.get('delivery_confirmed_at')) or observed)
    complete = len(confirmed) == len(items)
    return {'complete': complete, 'reason': 'all_delivered' if complete else 'platform_delivery_unconfirmed',
            'matched': len(confirmed), 'total': len(items), 'confirmed_keys': confirmed,
            'latest_delivery_unix': max(times) if times else None}


def publication_completion(connection, task_id, state):
    with closing(connection()) as conn:
        return _publication_completion(conn, task_id, state)


def cache(conn, uid, kind, value, at, *, posts_scope=None):
    from server import work_history
    if kind == 'posts':
        work_history.ingest_posts(conn, uid, value, at)
    elif kind == 'diagnosis':
        work_history.ingest_diagnosis(conn, uid, value, at)
    if kind == 'posts':
        if posts_scope:
            raw = conn.execute("SELECT payload_json FROM v3_operations_cache WHERE uid=? AND kind='posts_collection'", (uid,)).fetchone()
            prior = conn.execute("SELECT fetched_at FROM v3_operations_cache WHERE uid=? AND kind='posts'", (uid,)).fetchone()
            meta = json.loads(raw[0]) if raw else {'fullFetchedAt': prior[0] if prior else None, 'ranges': []}
            ranges = [item for item in meta.get('ranges', []) if (item['startDate'], item['endDate']) != (posts_scope['start_date'], posts_scope['end_date'])]
            meta['ranges'] = [*ranges[-31:], {'startDate': posts_scope['start_date'], 'endDate': posts_scope['end_date'], 'fetchedAt': at}]
        else:
            meta = {'fullFetchedAt': at, 'ranges': []}
        cache(conn, uid, 'posts_collection', meta, at)
    if kind == 'stats' and isinstance(value, dict):
        previous = conn.execute("SELECT payload_json FROM v3_operations_cache WHERE uid=? AND kind='stats'",(uid,)).fetchone()
        if previous:
            old = json.loads(previous[0])
            days = {r['date']:r for r in old.get('daily',[]) if isinstance(r,dict) and r.get('date')}
            days.update({r['date']:r for r in value.get('daily',[]) if isinstance(r,dict) and r.get('date')})
            value = {**value,'daily':[days[d] for d in sorted(days)]}

    conn.execute('''INSERT INTO v3_operations_cache VALUES(?,?,?,?)
      ON CONFLICT(uid,kind) DO UPDATE SET payload_json=excluded.payload_json,fetched_at=excluded.fetched_at''',
      (uid,kind,dump(value),at))
    if kind in ('posts','diagnosis'): work_history.resolve(conn, uid)


def cache_login_statuses(conn, accounts, at=None):
    """Keep only explicit login observations for uniquely linked active accounts."""
    linked = accounts_by_uid(conn)
    at = at or stamp()
    for account in accounts:
        uid = account.get('uid')
        status = account.get('loginStatus')
        if uid in linked and isinstance(status, str) and status.strip():
            cache(conn, uid, 'login', {'status': status.strip()}, at)


def login_statuses(conn):
    """Read saved checks without a network call or any database mutation."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_operations_cache'").fetchone():
        return {}
    result = {}
    for row in conn.execute("SELECT uid,payload_json,fetched_at FROM v3_operations_cache WHERE kind='login'"):
        try:
            value = json.loads(row['payload_json'])
            status = value.get('status') if isinstance(value, dict) else None
        except (ValueError, TypeError):
            continue
        if isinstance(status, str) and status.strip():
            result[row['uid']] = {'login_status': status, 'login_checked_at': row['fetched_at']}
    return result


def cached(conn):
    return {(r['uid'],r['kind']): (json.loads(r['payload_json']),r['fetched_at'])
            for r in conn.execute('SELECT * FROM v3_operations_cache')}


def pages(client, tool, args):
    result=[];seen=set();expected=None
    for page in range(1,201):
        data=client.call(tool,{**args,'page':page,'pageSize':100})
        batch=data.get('list')
        if not isinstance(batch,list):raise RuntimeError('查询分页格式无效')
        total=data.get('total')
        if expected is not None and total != expected:raise RuntimeError('查询期间数量发生变化')
        expected=total
        for item in batch:
            key=item.get('localId') or item.get('uid')
            if not key or key in seen:raise RuntimeError('查询身份重复或缺失')
            seen.add(key);result.append(item)
        if total is not None and len(result)==total:return result
        if not batch:
            if total is not None:raise RuntimeError('查询分页不完整')
            return result
        if total is None and len(batch)<100:return result
    raise RuntimeError('查询分页超过限制')


def matched_feed(conn, feed):
    uid=feed.get('uid');time=number(feed.get('publishUnix'))
    if not time:return None
    rows=conn.execute('''SELECT * FROM v3_publication_history
      WHERE uid=? AND publish_unix=? AND publication_state='published' AND match_state='matched' ''',
      (uid,int(time))).fetchall()
    if len(rows)!=1:return None
    row=dict(rows[0])
    stored=conn.execute("SELECT payload_json FROM v3_operations_cache WHERE uid=? AND kind='posts'",(uid,)).fetchone()
    if stored:
        collisions=[p for p in json.loads(stored[0]) if number(p.get('postUnix'))==time and p.get('postId')!=row['post_id']]
        if collisions:return None
    stored=conn.execute("SELECT payload_json FROM v3_operations_cache WHERE uid=? AND kind='diagnosis'",(uid,)).fetchone()
    if stored:
        diag=json.loads(stored[0]) or {}
        identities={f.get('exportId') for f in diag.get('feeds',[]) if number(f.get('publishUnix'))==time}
        if len(identities)>1:return None
    return row


def store_optimization(conn, publication, feed, detail, at):
    analysis=detail.get('reason')
    if not isinstance(analysis,str) or not analysis.strip():raise ValueError('作品分析缺失')
    detail_time=unix(detail.get('feedCreateTime'))
    if detail_time and detail_time!=publication['publish_unix']:raise ValueError('分析详情的作品时间不一致')
    conn.execute('''INSERT INTO v3_publication_optimizations VALUES(?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(publication_id) DO UPDATE SET analysis=excluded.analysis,tips_json=excluded.tips_json,
      appeal_type=excluded.appeal_type,platform_state=excluded.platform_state,last_seen_at=excluded.last_seen_at''',
      (publication['id'],publication['uid'],publication['post_id'],feed['exportId'],analysis,
       dump(detail.get('tips') or []),detail.get('appealType'),detail.get('auditResult') or feed.get('punishState') or '',at,at))


def associate_publications(connection, client=None, uids=None, *, online=False, page_interval_seconds=None):
    from server.publishing.vcat import VcatClient
    if client is None:
        with VcatClient(account_data=True) as own:return associate_publications(connection,own,uids,online=online,page_interval_seconds=page_interval_seconds)
    with closing(connection()) as conn:
        docs=executions(conn)
        uids=sorted(set(uids) if uids is not None else {r['uid'] for _,r in docs})
    if online:
        from server.publishing.online_posts import configured_page_interval
        interval = configured_page_interval(connection) if page_interval_seconds is None else page_interval_seconds
        posts={uid:client.online_account_posts(uid,page_interval_seconds=interval) for uid in uids}
    else:
        posts={uid:client.account_posts(uid) for uid in uids}
    tasks={uid:pages(client,'vcat_list_publish_tasks',{'uid':uid,'platform':'视频号'}) for uid in uids}
    with closing(connection()) as conn:
        reconcile(conn,posts,tasks);conn.commit()


def track_publications_once(connection, client_factory=None):
    """Capture scheduled IDs before public release removes effectiveTime."""
    from server.publishing.vcat import VcatClient
    from server.publishing.delivery import confirm_saved_deliveries
    if not LOCK.acquire(blocking=False):return {'state':'busy'}
    try:
        confirm_saved_deliveries(connection)
        now=int(datetime.now(SH).timestamp())
        with closing(connection()) as conn:
            record_executions(conn)
            active_uids=set(accounts_by_uid(conn))
            rows=[dict(r) for r in conn.execute("""SELECT * FROM v3_publication_history
                WHERE publication_state<>'published' AND task_state NOT IN ('canceled','rejected','failed')
                AND local_id<>'' AND schedule_type='timing'
                AND (post_id<>'' OR scheduled_unix>?)""",(now,))]
            conn.commit()
        if not rows:return {'state':'idle','candidates':0}
        with (client_factory or (lambda:VcatClient(account_data=True)))() as client:
            available=pages(client,'vcat_list_accounts',{'platform':'视频号'})
            with closing(connection()) as conn:
                cache_login_statuses(conn, available)
                conn.commit()
            valid={a['uid'] for a in available if a.get('loginStatus')=='登录有效'} & active_uids
            uids={r['uid'] for r in rows if r['uid'] in valid}
            # Once a scheduled ID is captured, do not reread its account before it is due.
            online_uids={r['uid'] for r in rows if r['uid'] in uids and
                         (not r['post_id'] or not r['scheduled_unix'] or r['scheduled_unix'] <= now)}
            if online_uids:associate_publications(connection,client,online_uids,online=True)
            cached_uids=uids-online_uids
            if cached_uids:associate_publications(connection,client,cached_uids)
            return {'state':'online_completed' if online_uids else 'waiting_scheduled_time',
                    'candidates':len(rows),'accounts':len(uids)}
    finally:LOCK.release()


def start_publication_tracking(connection, *, interval=30, client_factory=None):
    """Desktop-owned daemon; no external scheduler, no publish/delete calls."""
    stop=threading.Event()
    def run():
        while not stop.is_set():
            try:result=track_publications_once(connection,client_factory)
            except Exception:result={'state':'unavailable','message':'发布归属跟踪未完成，请检查小V猫连接和账号登录'}
            try:
                with closing(connection()) as conn:
                    cache(conn,'__system__','publication_tracking',result,stamp());conn.commit()
            except Exception:pass
            stop.wait(interval)
    threading.Thread(target=run,name='v3-publication-attribution',daemon=True).start()
    return stop


def collect_operations(connection, client_factory=None, *, refresh=False, page_interval_seconds=None, media_cache=None):
    from server.publishing.vcat import VcatClient
    from server.publishing.online_posts import configured_page_interval, validate_page_interval
    interval = validate_page_interval(configured_page_interval(connection) if page_interval_seconds is None else page_interval_seconds)
    if not LOCK.acquire(blocking=False):raise ValueError('正在采集，请稍后查看结果')
    at=stamp();errors=[];counts={};stats={};posts={};tasks={};diagnoses={};source_refresh={};daily_collection={}
    try:
        with closing(connection()) as conn:
            uids_from_history={r['uid'] for _,r in executions(conn)}
            active_uids=set(accounts_by_uid(conn, include_paused=False))
            snapshots=cached(conn)
            previous_stats={uid:value for (uid,kind),(value,_) in snapshots.items() if kind=='stats'}
            previous_posts={uid:value for (uid,kind),(value,_) in snapshots.items() if kind=='posts'}
        if media_cache is None:
            from server.work_media import WorkMediaCache
            from server.v2_file_service import DATA_ROOT
            media_cache=WorkMediaCache(DATA_ROOT / 'cache' / 'work-covers')
        with (client_factory or (lambda: VcatClient(account_data=True)))() as client:
            accounts=pages(client,'vcat_list_accounts',{'platform':'视频号'})
            with closing(connection()) as conn:
                cache_login_statuses(conn, accounts)
                conn.commit()
            valid={a['uid'] for a in accounts if a.get('loginStatus')=='登录有效'} & active_uids
            source_refresh['works'] = {}
            scope=sorted((valid|uids_from_history)&active_uids)
            for uid in scope:
                for kind,fn in [('posts',lambda:client.online_account_posts(uid,page_interval_seconds=interval) if refresh and uid in valid else client.account_posts(uid)),
                                ('tasks',lambda:pages(client,'vcat_list_publish_tasks',{'uid':uid,'platform':'视频号'})),
                                ('diagnosis',lambda:client.account_diagnosis(uid))]:
                    try:
                        value=fn()
                        if kind=='posts':
                            value,cover_errors=media_cache.prepare(uid,value,previous_posts.get(uid,()),download=refresh and uid in valid)
                            errors.extend(cover_errors)
                            posts[uid]=value
                            source_refresh['works'][uid]='online_completed' if refresh and uid in valid else 'local_cache'
                        elif kind=='tasks':tasks[uid]=value
                        else:diagnoses[uid]=value
                    except Exception:
                        errors.append({'uid':uid,'stage':kind,'message':'读取失败，保留历史，请检查小V猫连接'})
                if uid in valid:
                    from server.account_daily_collection import collect_daily
                    end=(datetime.now(SH).date()-timedelta(days=1)).isoformat()
                    try:
                        stats[uid],daily_collection[uid]=collect_daily(client,uid,previous_stats.get(uid),end,at,refresh=refresh)
                        source_refresh[uid]=daily_collection[uid]['platformRefresh']
                        if daily_collection[uid]['state']=='partial':
                            errors.append({'uid':uid,'stage':'stats','message':'账号日数据尚未补齐，缺失日期或连续全0的起点依据仍未取得'})
                    except Exception:errors.append({'uid':uid,'stage':'stats','message':'账号统计读取失败，保留已保存的日期'})
            with closing(connection()) as conn:
                reconcile(conn,posts,tasks,at)
                for kind,values in [('posts',posts),('stats',stats),('diagnosis',diagnoses)]:
                    for uid,value in values.items():cache(conn,uid,kind,value,at)
                conn.commit()
            matched=0;unmatched=0;details=0
            for uid,diagnosis in diagnoses.items():
                from server import work_history
                with closing(connection()) as conn:
                    retained_feeds=work_history.collection_feeds(conn,uid,diagnosis)
                for feed in retained_feeds:
                    feed = {**feed, 'uid':uid}
                    with closing(connection()) as conn:
                        notice=conn.execute('SELECT * FROM v3_work_notices WHERE id=?',(work_history.notice_id(uid,feed),)).fetchone()
                    if notice and notice['match_state']=='matched': matched+=1
                    else: unmatched+=1
                    if notice and json.loads(notice['detail_json']).get('feedCreateTime'): continue
                    if uid not in valid:
                        errors.append({'uid':uid,'stage':'analysis','message':'通知已保存，账号登录失效，详情待补查'});continue
                    try:
                        detail=client.optimization_detail(uid,feed['exportId'])
                        with closing(connection()) as conn:
                            work_history.store_detail(conn,uid,feed,detail,at);conn.commit()
                        details+=1
                    except Exception:
                        errors.append({'uid':uid,'stage':'analysis','message':'作品分析读取失败，未以空内容替代'})
            with closing(connection()) as conn:
                counts=dict(conn.execute('SELECT publication_state,COUNT(*) FROM v3_publication_history GROUP BY publication_state'))
                summary={'finished_at':at,'accounts':len(valid),'post_rows':sum(map(len,posts.values())),
                    'publications':counts,'matched_optimizations':matched,'saved_analyses':details,
                    'pending_optimizations':unmatched,'errors':errors,
                    'mode':'platform_refresh_and_cached_diagnosis' if refresh else 'read_local_cache_and_official_analysis',
                    'source_refresh':source_refresh,'daily_collection':daily_collection,
                    'work_collection':{'mode':'online_list' if refresh else 'local_cache',
                        'page_interval_seconds':interval,'page_wait_min_seconds':interval/2}}
                conn.execute('INSERT INTO v3_operations_runs(finished_at,summary_json) VALUES(?,?)',(at,dump(summary)));conn.commit()
            return summary
    finally:
        LOCK.release()


def publication_dashboard(conn):
    values=cached(conn)
    events={r['publication_id']:dict(r) for r in conn.execute('SELECT * FROM v3_publication_optimizations')}
    result=[]
    for r in conn.execute('SELECT * FROM v3_publication_history'):
        row=dict(r);event=events.get(row['id']);diag=(values.get((row['uid'],'diagnosis')) or ({},''))[0] or {}
        checked=bool(diag.get('verified') and number(diag.get('lastVerifyUnix'))
                     and row['publish_unix'] and diag['lastVerifyUnix']>=row['publish_unix'])
        # An observed abnormal work without its analysis is never a confirmed negative.
        has_unread=any(number(f.get('publishUnix'))==row['publish_unix'] for f in diag.get('feeds',[]))
        row['optimization_state']='optimized' if event else 'not_detected' if checked and not has_unread else 'unknown'
        row['optimization']=event
        row['publish_time']=local_time(row['publish_unix'])
        result.append(row)
    latest=conn.execute('SELECT summary_json FROM v3_operations_runs ORDER BY id DESC LIMIT 1').fetchone()
    return result,json.loads(latest[0]) if latest else None


def real_dashboard_rows(conn):
    """Adapt safe JSON caches to the existing API without coercing missing to 0."""
    from server.account_data_mapping import build_account_core
    from server.work_media import local_cover_url, playback_url
    ids=accounts_by_uid(conn, include_cancelled=True);result={'video_accounts':[],'video_account_daily':[],'video_posts':[]}
    for (uid,kind),(value,at) in cached(conn).items():
        aid=ids.get(uid)
        if not aid:continue
        base={'uid':uid,'account_id':aid,'source_kind':SOURCE,'data_state':'cached_only',
              'freshness_state':'cached_only','fetched_at':at,'snapshot_date':at[:10],'payload_json':'{}'}
        if kind=='stats' and value:
            core=build_account_core(value)
            result['video_accounts'].append({**base,'id':uid,'fans_total':core['followerTotal'],'video_total':core['videoTotal']})
            boundary=(value.get('dailyCollection') or {}).get('boundary') or {}
            for d in core['daily']:
                if boundary.get('startDate') and d['date']<boundary['startDate']:continue
                item={**base,'id':uid+':'+d['date'],'stat_date':d['date'],'view':d['views'],
                      'fans_add':d['followsAdded'],'fans_net':d['followsNet'],'fans_reduce':d['followsReduced'],
                      'fans_total':d['followerTotal'],'like_count':d['hearts'],'favorite_count':d['thumbsUp'],
                       'comment_count':d['comments'],'forward_count':d['shares']}
                if any(item[k] is None for k in ('view','fans_net','like_count','comment_count')):item['data_state']='incomplete'
                result['video_account_daily'].append(item)
        elif kind=='posts':
            for p in value:
                # A scheduled upload is not a published traffic work.
                if p.get('publishStatus')!='published':continue
                item={**base,'fetched_at':p.get('observedAt') or '', 'snapshot_date':(p.get('observedAt') or '')[:10],'id':uid+':'+p['postId'],'post_id':p['postId'],'post_time':local_time(p.get('postUnix')),
                      'account_name':'','title':p.get('title') or '','description':p.get('desc') or '',
                      'cover_url':local_cover_url(p.get('coverLocalId')),'video_url':playback_url(p.get('videoUrl')),
                      'video_duration':number(p.get('videoDuration')),
                      'publish_status':p.get('publishStatus'),'timing':local_time(p.get('scheduleUnix')),
                      **{dest:number(p.get(src)) for dest,src in [('view','view'),('like_count','like'),('love_count','love'),
                          ('comment_count','comment'),('forward_count','forward'),('full_view','fullView')]}}
                if any(item[k] is None for k in ('view','like_count','love_count','comment_count','forward_count','full_view')):item['data_state']='incomplete'
                result['video_posts'].append(item)
    return result
