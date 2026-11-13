"""Durable official work ledger, automatic identity checks and guarded actions.

All mutations belong to collection/migration, never dashboard reads. Platform
absence is not evidence of deletion. No timestamp or export ID fuzzy matching.
"""
import hashlib
import json
import math
from contextlib import closing


def _ops():
    from server import operations_collection
    return operations_collection


def initialize(conn):
    first = not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_work_history'").fetchone()
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS v3_work_history(
        uid TEXT NOT NULL,post_id TEXT NOT NULL,publish_unix INTEGER NOT NULL,
        identity_state TEXT NOT NULL DEFAULT 'valid',first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(uid,post_id));
      CREATE TABLE IF NOT EXISTS v3_work_notices(
        id TEXT PRIMARY KEY,uid TEXT NOT NULL,export_id TEXT NOT NULL,publish_unix INTEGER,
        post_id TEXT NOT NULL DEFAULT '',match_state TEXT NOT NULL DEFAULT 'pending',
        detail_json TEXT NOT NULL DEFAULT '{}',feed_json TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,last_seen_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS v3_optimization_action_settings(
        id INTEGER PRIMARY KEY CHECK(id=1),payload_json TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS v3_optimization_action_log(
        uid TEXT NOT NULL,post_id TEXT NOT NULL,notice_id TEXT NOT NULL,action TEXT NOT NULL,
        state TEXT NOT NULL,message TEXT NOT NULL,at TEXT NOT NULL,views REAL,
        PRIMARY KEY(uid,post_id));
    ''')
    if first:
        # Migrate only existing evidence, with its original observation times.
        for row in conn.execute("SELECT * FROM v3_operations_cache WHERE kind IN ('posts','diagnosis')").fetchall():
            value = json.loads(row['payload_json'])
            if row['kind'] == 'posts': ingest_posts(conn, row['uid'], value, row['fetched_at'])
            else: ingest_diagnosis(conn, row['uid'], value, row['fetched_at'])
        for row in conn.execute('SELECT * FROM v3_publication_optimizations').fetchall():
            pub = conn.execute('SELECT * FROM v3_publication_history WHERE id=?', (row['publication_id'],)).fetchone()
            if pub:
                feed = {'uid':row['uid'], 'exportId':row['export_id'], 'publishUnix':pub['publish_unix']}
                ingest_diagnosis(conn, row['uid'], {'feeds':[feed]}, row['last_seen_at'])
                store_detail(conn, row['uid'], feed, {'reason':row['analysis'], 'tips':json.loads(row['tips_json']),
                    'auditResult':row['platform_state']}, row['last_seen_at'])


def _epoch(value):
    if isinstance(value,bool): return None
    n = _ops().number(value)
    if n is not None: return int(n) if n>0 and n==int(n) else None
    return _ops().unix(value)


def notice_id(uid, feed):
    key = feed.get('exportId') or ['missing', feed.get('uniqueId'), feed.get('publishUnix')]
    return hashlib.sha256(json.dumps([uid,key],ensure_ascii=False).encode()).hexdigest()


def ingest_posts(conn, uid, posts, at):
    for post in posts or []:
        when = _epoch(post.get('postUnix'))
        pid = str(post.get('postId') or '')
        if post.get('publishStatus') != 'published' or not pid or not when: continue
        if post.get('uid') and post['uid'] != uid: continue
        # Only save safe metadata and metrics, never signed media URLs or sessions.
        safe = {k:post[k] for k in ('postId','postUnix','title','desc','coverLocalId','videoDuration',
            'view','like','love','comment','forward','fullView','observedAt','isSticky') if k in post}
        conn.execute('''INSERT INTO v3_work_history(uid,post_id,publish_unix,first_seen_at,last_seen_at,payload_json)
          VALUES(?,?,?,?,?,?) ON CONFLICT(uid,post_id) DO UPDATE SET
          identity_state=CASE WHEN publish_unix<>excluded.publish_unix THEN 'conflict' ELSE identity_state END,
          last_seen_at=excluded.last_seen_at,payload_json=excluded.payload_json''',
          (uid,pid,when,at,at,_ops().dump(safe)))
    resolve(conn, uid)


def ingest_diagnosis(conn, uid, diagnosis, at):
    for feed in (diagnosis or {}).get('feeds', []):
        if feed.get('uid') and feed['uid'] != uid: continue
        safe = {k:feed.get(k) for k in ('uid','exportId','uniqueId','publishUnix','punishState')}
        conn.execute('''INSERT INTO v3_work_notices(id,uid,export_id,publish_unix,feed_json,first_seen_at,last_seen_at)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET feed_json=excluded.feed_json,
          match_state=CASE WHEN publish_unix IS NOT excluded.publish_unix THEN 'conflict' ELSE match_state END,
          last_seen_at=excluded.last_seen_at''',
          (notice_id(uid,feed),uid,str(feed.get('exportId') or ''),_epoch(feed.get('publishUnix')),_ops().dump(safe),at,at))
    resolve(conn, uid)


def collection_feeds(conn, uid, diagnosis):
    """Retry retained unread notices even after they leave the platform's recent list."""
    feeds = {notice_id(uid,f):{**f,'uid':uid} for f in (diagnosis or {}).get('feeds',[])}
    for r in conn.execute("SELECT * FROM v3_work_notices WHERE uid=? AND match_state<>'matched'",(uid,)):
        feeds.setdefault(r['id'], {**json.loads(r['feed_json']),'uid':uid})
    return list(feeds.values())


def candidates(conn, uid, when):
    works = {r['post_id']:r['identity_state'] for r in conn.execute(
        'SELECT post_id,identity_state FROM v3_work_history WHERE uid=? AND publish_unix=?', (uid,when))}
    for r in conn.execute("SELECT post_id FROM v3_publication_history WHERE uid=? AND publish_unix=? AND publication_state='published' AND match_state='matched'",(uid,when)):
        works.setdefault(r['post_id'], 'valid')
    return works


def resolve(conn, uid):
    meta = conn.execute("SELECT payload_json FROM v3_operations_cache WHERE uid=? AND kind='posts_collection'",(uid,)).fetchone()
    full_at = _epoch(json.loads(meta[0]).get('fullFetchedAt')) if meta else None
    for r in conn.execute('SELECT * FROM v3_work_notices WHERE uid=?',(uid,)).fetchall():
        if r['match_state'] == 'conflict': continue
        detail = json.loads(r['detail_json'])
        when = r['publish_unix']
        works = candidates(conn, uid, when) if when else {}
        peers = conn.execute('SELECT COUNT(*) FROM v3_work_notices WHERE uid=? AND publish_unix=?',(uid,when)).fetchone()[0]
        state = 'pending'
        pid = r['post_id']
        if detail and (detail.get('uid',uid) != uid or detail.get('exportId',r['export_id']) != r['export_id'] or (_epoch(detail.get('feedCreateTime')) and _epoch(detail.get('feedCreateTime')) != when)):
            state = 'conflict'
        elif len(works)>1 or peers>1: state = 'ambiguous'
        elif works and next(iter(works.values())) != 'valid': state = 'conflict'
        elif len(works)==1 and detail.get('reason') and when and r['export_id'] and _epoch(detail.get('feedCreateTime'))==when and full_at and full_at>=when:
            found = next(iter(works))
            if pid and pid != found: state = 'conflict'
            else: pid, state = found, 'matched'
        conn.execute('UPDATE v3_work_notices SET post_id=?,match_state=? WHERE id=?',(pid,state,r['id']))


def store_detail(conn, uid, feed, detail, at):
    safe = {k:detail[k] for k in ('uid','exportId','reason','tips','appealType','uniqueId','feedCreateTime','auditResult') if k in detail}
    if not isinstance(safe.get('reason'),str) or not safe['reason'].strip(): raise ValueError('作品分析缺失')
    conn.execute('UPDATE v3_work_notices SET detail_json=?,last_seen_at=? WHERE id=?',(_ops().dump(safe),at,notice_id(uid,feed)))
    resolve(conn, uid)
    # Preserve the existing software-publication API for older callers.
    row = conn.execute('SELECT * FROM v3_work_notices WHERE id=?',(notice_id(uid,feed),)).fetchone()
    if row and row['match_state']=='matched':
        pub = conn.execute("SELECT * FROM v3_publication_history WHERE uid=? AND post_id=? AND match_state='matched' AND publication_state='published'",(uid,row['post_id'])).fetchone()
        if pub: _ops().store_optimization(conn,dict(pub),{**feed,'exportId':row['export_id']},detail,at)


def dashboard(conn):
    """Read-only: return the union of official and previously confirmed software works."""
    ops = _ops()
    ids = ops.accounts_by_uid(conn, include_cancelled=True)
    software, _ = ops.publication_dashboard(conn)
    by_work = {(r['uid'],r['post_id']):{**r,'software':True} for r in software
        if r['publication_state']=='published' and r['match_state']=='matched' and r['post_id']}
    notices = [dict(r) for r in conn.execute('SELECT * FROM v3_work_notices') if r['uid'] in ids]
    values = ops.cached(conn)
    for r in conn.execute('SELECT * FROM v3_work_history'):
        if r['uid'] not in ids: continue
        key=(r['uid'],r['post_id'])
        saved=by_work.get(key,{})
        by_work[key] = {**dict(r),**saved,'id':saved.get('id') or r['uid']+':'+r['post_id'],
            'account_id':ids[r['uid']],'publication_state':'published','match_state':'matched',
            'publish_time':ops.local_time(r['publish_unix']),'software':bool(saved)}
    for row in by_work.values():
        diag = (values.get((row['uid'],'diagnosis')) or ({},''))[0] or {}
        related = [n for n in notices if n['uid']==row['uid'] and n['publish_unix']==row['publish_unix']]
        events = [n for n in related if n['post_id']==row['post_id'] and n['match_state']=='matched']
        event = events[0] if len(events)==1 else None
        unresolved = any(n['uid']==row['uid'] and n['match_state']!='matched' and
                         (not n['publish_unix'] or n['publish_unix']==row['publish_unix']) for n in notices)
        checked = row.get('identity_state','valid')=='valid' and bool(diag.get('verified') and (_epoch(diag.get('lastVerifyUnix')) or 0)>=row['publish_unix'])
        # A migrated software event is also durable evidence.
        old = None  # Legacy associations alone are not independent official-detail proof.
        row['optimization'] = ({'analysis':json.loads(event['detail_json'])['reason'],
            'platform_state':json.loads(event['detail_json']).get('auditResult') or '',
            'first_seen_at':event['first_seen_at']} if event else old if not unresolved else None)
        row['optimization_state'] = 'optimized' if row['optimization'] else 'not_detected' if checked and not unresolved and not related else 'unknown'
    pending = [{**n,'account_id':ids[n['uid']],'publish_time':ops.local_time(n['publish_unix']),
                'analysis':json.loads(n['detail_json']).get('reason','')} for n in notices if n['match_state']!='matched']
    logs = [dict(r) for r in conn.execute('SELECT * FROM v3_optimization_action_log ORDER BY at DESC LIMIT 100')]
    return list(by_work.values()), pending, logs


def action_records(conn, page=1, page_size=10, snapshot=None):
    """Read one stable page; newly inserted requests appear on explicit refresh."""
    for n, low, high in ((page,1,None),(page_size,1,50)):
        if type(n) is not int or n<low or (high is not None and n>high): raise ValueError('处理记录分页参数无效')
    if snapshot is not None and (type(snapshot) is not int or snapshot<0): raise ValueError('处理记录分页参数无效')
    newest=conn.execute('SELECT COALESCE(MAX(rowid),0) FROM v3_optimization_action_log').fetchone()[0]
    snapshot=newest if snapshot is None else min(snapshot,newest)
    total=conn.execute('SELECT COUNT(*) FROM v3_optimization_action_log WHERE rowid<=?',(snapshot,)).fetchone()[0]
    page_count=max(1,(total+page_size-1)//page_size)
    page=min(page,page_count)
    rows=conn.execute('SELECT * FROM v3_optimization_action_log WHERE rowid<=? ORDER BY rowid DESC LIMIT ? OFFSET ?',
        (snapshot,page_size,(page-1)*page_size)).fetchall()
    columns={r[1] for r in conn.execute('PRAGMA table_info(accounts)')}
    names={}
    if 'nickname' in columns:
        for r in conn.execute('SELECT channel_id,nickname FROM accounts'):
            names.setdefault(r['channel_id'],[]).append(r['nickname'])
    records=[]
    for r in rows:
        work=conn.execute('SELECT * FROM v3_work_history WHERE uid=? AND post_id=?',(r['uid'],r['post_id'])).fetchone()
        pub=conn.execute("SELECT * FROM v3_publication_history WHERE uid=? AND post_id=? AND publication_state='published' AND match_state='matched'",(r['uid'],r['post_id'])).fetchone()
        notice=conn.execute('SELECT detail_json FROM v3_work_notices WHERE id=?',(r['notice_id'],)).fetchone()
        meta=json.loads(work['payload_json']) if work else {}
        release=json.loads(pub['payload_json']) if pub else {}
        account_names=names.get(r['uid'],[])
        records.append({**dict(r),'account_name':account_names[0] if len(account_names)==1 else r['uid'],
            'title':release.get('name') or meta.get('title') or '作品 '+r['post_id'],
            'publish_time':_ops().local_time(work['publish_unix'] if work else pub['publish_unix'] if pub else None),
            'analysis':json.loads(notice['detail_json']).get('reason','') if notice else ''})
    return {'records':records,'total':total,'page':page,'page_size':page_size,'page_count':page_count,'snapshot':snapshot}


DEFAULT_SETTINGS = {'enabled':False,'action':'hide','scope':'software','min_play_count':None,'exclude_sticky':True,'post_publish_hours':10}


def settings(conn):
    row=conn.execute('SELECT payload_json FROM v3_optimization_action_settings WHERE id=1').fetchone()
    return {**DEFAULT_SETTINGS,**(json.loads(row[0]) if row else {})}


def save_settings(conn, payload):
    if not isinstance(payload,dict): raise ValueError('优化设置格式无效')
    value={**settings(conn),**{k:payload[k] for k in DEFAULT_SETTINGS if k in payload}}
    if type(value['enabled']) is not bool or type(value['exclude_sticky']) is not bool: raise ValueError('开关格式无效')
    if value['action'] not in ('hide','delete') or value['scope'] not in ('all','software'): raise ValueError('处理方式或范围无效')
    hours=value['post_publish_hours']
    if isinstance(hours,bool) or not isinstance(hours,(int,float)) or not math.isfinite(hours) or hours<=0:
        raise ValueError('发布后处理时限必须是大于0的小时数')
    n=value['min_play_count']
    if n is not None and (isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or n<=0 or n!=int(n)):
        raise ValueError('播放保护门槛必须是正整数')
    if value['enabled'] and n is None: raise ValueError('启用前请设置播放保护门槛')
    conn.execute('INSERT INTO v3_optimization_action_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json',(_ops().dump(value),))
    return value


def process_actions(connection, client, uid, posts, *, fresh_detection=False, should_stop=None, page_interval_seconds=2):
    """Only called after a fresh successful detection and an online work read.

    Persist intent before sending; interruption is an unknown outcome and must
    never be retried automatically. MCP acknowledgements are not deletion proof.
    """
    from server.collection_progress import checkpoint, CollectionStopped
    ops=_ops()
    counts={'submitted':0,'protected':0,'unknown':0}
    with closing(connection()) as conn:
        policy=settings(conn)
        if not policy['enabled'] or not fresh_detection: return counts
        diag_row=conn.execute("SELECT payload_json FROM v3_operations_cache WHERE uid=? AND kind='diagnosis'",(uid,)).fetchone()
        diagnosis=json.loads(diag_row[0]) if diag_row else {}
        verified=_epoch(diagnosis.get('lastVerifyUnix'))
        if not diagnosis.get('verified') or not verified or not 0<=ops.time.time()-verified<=300: return counts
        current={notice_id(uid,f) for f in diagnosis.get('feeds',[])}
        rows=[dict(r) for r in conn.execute("SELECT * FROM v3_work_notices WHERE uid=? AND match_state='matched'",(uid,)) if r['id'] in current]
    def within_window(published):
        return published is not None and 0 <= ops.time.time()-published <= policy['post_publish_hours']*3600

    for r in rows:
        checkpoint(should_stop)
        if not within_window(r['publish_unix']): counts['protected']+=1;continue
        with closing(connection()) as conn:
            if settings(conn)!=policy: break
            owned=conn.execute("SELECT 1 FROM v3_publication_history WHERE uid=? AND post_id=? AND publication_state='published' AND match_state='matched'",(uid,r['post_id'])).fetchone()
            if policy['scope']=='software' and not owned: counts['protected']+=1;continue
        # Single-action APIs do not accept a play threshold. Re-read this work's
        # publication day immediately before EACH request; never act on the
        # earlier full-list snapshot after slow detail/pagination requests.
        day=ops.local_time(r['publish_unix'])[:10]
        try:
            latest=client.online_account_posts(uid,published_start=day,published_end=day,
                page_interval_seconds=page_interval_seconds,should_stop=should_stop)
        except CollectionStopped: raise
        except Exception:
            counts['protected']+=1;continue
        with closing(connection()) as conn:
            ingest_posts(conn,uid,latest,ops.stamp());conn.commit()
        hits=[p for p in latest if str(p.get('postId'))==r['post_id']]
        same_second=[p for p in latest if _epoch(p.get('postUnix'))==r['publish_unix'] and p.get('publishStatus')=='published']
        if len(hits)!=1 or len(same_second)!=1: counts['protected']+=1;continue
        p=hits[0]; view=ops.number(p.get('view')); observed=_epoch(p.get('observedAt'))
        if (p.get('uid',uid)!=uid or p.get('publishStatus')!='published' or _epoch(p.get('postUnix'))!=r['publish_unix']
            or view is None or view<0 or not observed or not 0<=ops.time.time()-observed<=300
            or view>=policy['min_play_count'] or (policy['exclude_sticky'] and p.get('isSticky') is not False)):
            counts['protected']+=1;continue
        with closing(connection()) as conn:
            # Recheck saved settings and identity immediately before each action.
            if settings(conn)!=policy: break
            if not within_window(r['publish_unix']): counts['protected']+=1;continue
            valid=conn.execute("SELECT 1 FROM v3_work_notices WHERE id=? AND match_state='matched' AND post_id=?",(r['id'],r['post_id'])).fetchone()
            software=conn.execute("SELECT 1 FROM v3_publication_history WHERE uid=? AND post_id=? AND publication_state='published' AND match_state='matched'",(uid,r['post_id'])).fetchone()
            if not valid or (policy['scope']=='software' and not software): counts['protected']+=1;continue
            if conn.execute('SELECT 1 FROM v3_optimization_action_log WHERE uid=? AND post_id=?',(uid,r['post_id'])).fetchone(): continue
            conn.execute('INSERT INTO v3_optimization_action_log VALUES(?,?,?,?,?,?,?,?)',
                (uid,r['post_id'],r['id'],policy['action'],'unknown','请求准备发送；中断后不自动重试',ops.stamp(),view))
            conn.commit()
        try:
            client.act_on_optimization(uid,r['export_id'],policy['action'])
            state,message='submitted','接口已返回；平台最终状态待核实，不自动重复处理'
            counts['submitted']+=1
        except CollectionStopped: raise
        except Exception:
            state,message='unknown','请求未确认；可能未执行，也可能已执行，不自动重试'
            counts['unknown']+=1
        with closing(connection()) as conn:
            conn.execute('UPDATE v3_optimization_action_log SET state=?,message=? WHERE uid=? AND post_id=?',(state,message,uid,r['post_id']))
            conn.commit()
    return counts
