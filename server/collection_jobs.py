"""User-triggered account collection queue with durable, plain-language progress."""
from __future__ import annotations

import json
import threading
import uuid
from contextlib import closing
from datetime import datetime, timedelta

from server import operations_collection as ops
from server.account_daily_collection import collect_daily
from server.collection_progress import CollectionStopped, CollectionAccessLimited, access_limited, checkpoint
from server.publishing.online_posts import configured_page_interval, validate_page_interval, publication_window, PublicationRangeError

CATEGORIES = {'profile': '账号资料', 'daily': '账号日流量', 'works': '作品数据', 'optimization': '优化记录', 'revenue': '剧场收益'}
TERMINAL = {'success', 'skipped', 'partial', 'failed', 'stopped'}
ACTIVE = {'running', 'stopping'}
RECORDS_PER_CATEGORY = 3
EVENTS_PER_ITEM = 120
INVALID_LOGINS = {'登录失效', '未登录', '登录过期', '已过期', '登录无效'}

def invalid_login(account):
    return str(account.get('login_status') or '').strip() in INVALID_LOGINS

def detection_available(account):
    return account.get('platform_available', account['available']) and account.get('business_status') not in ('停用','注销','disabled') and not invalid_login(account)


def clone(value):
    return json.loads(ops.dump(value))



def prune_job_history(conn):
    """Keep the newest three real attempts per account/category, not three batches."""
    rows=conn.execute('SELECT id,payload_json FROM v3_collection_jobs ORDER BY rowid DESC').fetchall()
    counts, kept, saved = {}, set(), []
    for row in rows:
        job=json.loads(row['payload_json'])
        items=[]
        for item in job.get('items',[]):
            key=(item['account_id'],item['category'])
            if counts.get(key,0)>=RECORDS_PER_CATEGORY:
                continue
            counts[key]=counts.get(key,0)+1
            items.append(item)
            kept.add(json.dumps(item,sort_keys=True,ensure_ascii=False))
        if not items:
            conn.execute('DELETE FROM v3_collection_jobs WHERE id=?',(row['id'],))
            continue
        saved.append((row,job,items))
    for row,job,items in saved:
        before=ops.dump(job)
        if len(items)!=len(job.get('items',[])):
            job['items']=items
            ids={(i['account_id'],i['category']) for i in items}
            names={(i['account_name'],i['category']) for i in items}
            job['events']=[e for e in job.get('events',[]) if
                ((e.get('account_id'),e.get('category')) in ids if e.get('account_id') else
                 (e.get('account_name'),e.get('category')) in names)]
        job['retained_items']=[i for i in job.get('retained_items',[]) if
            json.dumps(i,sort_keys=True,ensure_ascii=False) in kept]
        if ops.dump(job)!=before:
            conn.execute('UPDATE v3_collection_jobs SET payload_json=? WHERE id=?',(ops.dump(job),row['id']))


def uid_snapshots(conn, uid):
    return {(r['uid'], r['kind']): (json.loads(r['payload_json']), r['fetched_at'])
            for r in conn.execute('SELECT * FROM v3_operations_cache WHERE uid=?', (uid,))}


def catalog(connection):
    with closing(connection()) as conn:
        columns = {r[1] for r in conn.execute('PRAGMA table_info(accounts)')}
        nickname = 'nickname' if 'nickname' in columns else 'id'
        rows = [dict(r) for r in conn.execute(f"SELECT id,{nickname} AS name,channel_id AS uid,status AS business_status FROM accounts ORDER BY {nickname},id")]
        unique = ops.accounts_by_uid(conn)
        # Poll only timestamps and daily metadata; never deserialize all works on each tick.
        has_cache = conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_operations_cache'").fetchone()
        cache_rows = list(conn.execute("SELECT uid,kind,fetched_at,CASE WHEN kind='stats' THEN json_extract(payload_json,'$.dailyCollection') END AS daily_meta,CASE WHEN kind='stats' THEN json_extract(payload_json,'$.total') END AS total_meta FROM v3_operations_cache")) if has_cache else []
        snapshots = {(r['uid'], r['kind']): (json.loads(r['daily_meta']) if r['daily_meta'] else {}, r['fetched_at']) for r in cache_rows}
        totals = {r['uid']: json.loads(r['total_meta']) for r in cache_rows if r['kind'] == 'stats' and r['total_meta']}
        from server.revenue_queue import account_states
        revenue_states = account_states(conn, (datetime.now(ops.SH).date()-timedelta(days=1)).isoformat())
        logins=ops.login_statuses(conn)
        result = []
        for row in rows:
            row.update(logins.get(row['uid'],{}))
            row['available'] = unique.get(row['uid']) == row['id']
            row['platform_available'] = row['available'] and row['business_status'] != '注销'
            row['revenue'] = revenue_states.get(row['id'], {'available':False,'mode':'unknown','state':'unconfigured','message':'未配置收益采集器','collector_name':''})
            row['available'] = row['business_status'] != '注销' and (row['platform_available'] or row['revenue']['available'])
            row['unavailable_reason'] = '账号已注销，停止采集；历史数据保留' if row['business_status'] == '注销' else '' if row['available'] else '请核对平台账号或收益采集器配置'
            row['last_success'] = {category: snapshots.get((row['uid'], kind), (None, ''))[1]
                                   for category, kind in [('profile', 'stats'), ('daily', 'stats'), ('works', 'posts'), ('optimization', 'diagnosis')]}
            daily = snapshots.get((row['uid'], 'stats'), ({}, ''))[0] or {}
            row['daily_through'] = daily.get('checkedThrough') if daily.get('state') == 'complete' else None
            row['daily_boundary'] = (daily.get('boundary') or {}).get('startDate')
            row['daily_missing'] = len(daily.get('missingDates') or [])
            row['daily_missing_dates'] = daily.get('missingDates') or []
            row['daily_state'] = daily.get('state') or 'unknown'
            row['profile_total'] = {key: ops.number((totals.get(row['uid']) or {}).get(key)) for key in ('postCount', 'fans')}
            row['profile_source_time'] = str((totals.get(row['uid']) or {}).get('updateTime') or '')
            row['last_success']['revenue'] = row['revenue'].get('last_success','')
            result.append(row)
        return result


class CollectionJobs:
    def __init__(self, connection, *, client_factory=None, media_cache=None):
        self.connection = connection
        self.client_factory = client_factory
        self.media_cache = media_cache
        self.mutex = threading.RLock()
        self.stop_event = threading.Event()
        self.job = None
        self.thread = None
        from server.optimization_detection import OptimizationDetection
        self.detection = OptimizationDetection(connection)
        with closing(connection()) as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_collection_jobs'").fetchone():
                prune_job_history(conn)
                conn.commit()
                row = conn.execute('SELECT payload_json FROM v3_collection_jobs ORDER BY rowid DESC LIMIT 1').fetchone()
                if row:
                    self.job = json.loads(row[0])
        if self.job and self.job['state'] in ACTIVE:
            self.job['state'] = 'stopped'
            self.job['finished_at'] = ops.stamp()
            for cell in self.job['items']:
                if cell['status'] not in TERMINAL:
                    cell.update(status='stopped', message='程序上次退出，后续采集未执行；已保存的数据保留，可继续未完成项')
            self._save()

    def _save(self):
        with closing(self.connection()) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS v3_collection_jobs(id TEXT PRIMARY KEY,payload_json TEXT NOT NULL)')
            conn.execute('INSERT INTO v3_collection_jobs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json',
                         (self.job['id'], ops.dump(self.job)))
            prune_job_history(conn)
            saved=conn.execute('SELECT payload_json FROM v3_collection_jobs WHERE id=?',(self.job['id'],)).fetchone()
            if saved:
                self.job['retained_items']=json.loads(saved[0]).get('retained_items',[])
            conn.commit()

    def refresh_logins(self):
        if not ops.LOCK.acquire(blocking=False):
            raise ValueError('正在采集或发布核对，请等待当前任务完成后刷新登录状态')
        try:
            from server.publishing.vcat import VcatClient
            with (self.client_factory or VcatClient)() as client:
                accounts=ops.pages(client,'vcat_list_accounts',{'platform':'视频号'})
            with closing(self.connection()) as conn:
                ops.cache_login_statuses(conn,accounts)
                conn.commit()
            return dict(state=self.state(),message='已读取小V猫本地登录信息；未进行在线检测，未返回明确状态的账号保留原记录')
        except ValueError:
            raise
        except Exception:
            raise ValueError('无法读取小V猫登录状态，请检查小V猫连接；原状态已保留') from None
        finally:
            ops.LOCK.release()

    def record_summaries(self):
        with closing(self.connection()) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_collection_jobs'").fetchone():
                return []
            rows = conn.execute("""WITH ranked AS (
                SELECT j.id AS job_id, json_extract(j.payload_json,'$.source') AS source,
                    json_extract(j.payload_json,'$.started_at') AS started_at, i.value AS item,
                    ROW_NUMBER() OVER (PARTITION BY json_extract(i.value,'$.account_id'),json_extract(i.value,'$.category') ORDER BY j.rowid DESC) AS rank
                FROM v3_collection_jobs j, json_each(j.payload_json,'$.items') i
                WHERE json_extract(i.value,'$.category') IN ('daily','works','optimization','revenue'))
                SELECT job_id,source,started_at,item FROM ranked WHERE rank=1""").fetchall()
        return [dict(job_id=r['job_id'],source=r['source'] or 'unknown',started_at=r['started_at'],item=json.loads(r['item'])) for r in rows]

    def records(self, account_id, category, offset=0):
        if category not in ('daily','works','optimization','revenue') or not isinstance(account_id,str) or not account_id or type(offset) is not int or offset<0:
            raise ValueError('请选择有效账号和采集类型')
        with self.mutex, closing(self.connection()) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_collection_jobs'").fetchone():
                return dict(records=[],has_more=False)
            rows=conn.execute("""SELECT j.id,j.payload_json FROM v3_collection_jobs j WHERE EXISTS (
                SELECT 1 FROM json_each(j.payload_json,'$.items') i
                WHERE json_extract(i.value,'$.account_id')=? AND json_extract(i.value,'$.category')=?)
                ORDER BY j.rowid DESC LIMIT 3""",(account_id,category)).fetchall()
            records=[]
            for row in rows[offset:]:
                job=json.loads(row['payload_json'])
                item=next(i for i in job['items'] if i['account_id']==account_id and i['category']==category)
                records.append(dict(job_id=job['id'],source=job.get('source','unknown'),parent_job_id=job.get('parent_job_id',''),
                    started_at=job['started_at'],finished_at=job.get('finished_at',''),options=job['options'],item=item,
                    events=[e for e in job.get('events',[]) if e.get('category')==category and
                        (e.get('account_id')==account_id if e.get('account_id') else e.get('account_name')==item['account_name'])]))
            return dict(records=records,has_more=False)

    def state(self):
        with self.mutex:
            accounts = catalog(self.connection)
            records = self.detection.records()
            for account in accounts:
                detection = records.get(account['uid'], {})
                account['last_success']['optimization'] = detection.get('last_success', '')
                account['optimization_due'] = detection_available(account) and self.detection.due(account['uid'])
            return {'job': clone(self.job), 'accounts': accounts, 'optimization_detection': self.detection.state(),
                    'record_summaries': self.record_summaries(), 'capabilities': {'version': 1, 'daily_reset_online': True, 'works_publication_range': True, 'optimization_detection': True, 'revenue': True},
                    'page_interval_seconds': configured_page_interval(self.connection), 'yesterday': (datetime.now(ops.SH).date()-timedelta(days=1)).isoformat()}

    def _emit(self, cell, message, status=None):
        with self.mutex:
            cell['message'] = message
            cell['updated_at'] = ops.stamp()
            if status == 'running' and not cell.get('started_at'):
                cell['started_at'] = cell['updated_at']
            if status in TERMINAL:
                cell['finished_at'] = cell['updated_at']
            if status:
                cell['status'] = status
            self.job['current_item'] = cell['id']
            self.job['events'].append({'time': ops.stamp(), 'account_id': cell['account_id'], 'account_name': cell['account_name'],
                                       'category': cell['category'], 'message': message})
            # Each account/category has its own process history. A busy account
            # must not erase every earlier account's events in the same batch.
            key = (cell['account_id'], cell['category'])
            matching = [i for i, event in enumerate(self.job['events'])
                        if (event.get('account_id'), event.get('category')) == key]
            dropped = set(matching[:-EVENTS_PER_ITEM])
            if dropped:
                self.job['events'] = [event for i, event in enumerate(self.job['events']) if i not in dropped]
                cell['events_truncated'] = True
            self._save()

    def start(self, payload, *, retry=False, source='manual'):
        with self.mutex:
            if self.job and self.job['state'] in ACTIVE:
                return {'job': clone(self.job), 'reused': True, 'message': '已有任务正在执行，已显示当前进度，未重复发起请求'}
            available = {str(a['id']): a for a in catalog(self.connection) if a['available']}
            retained_items = []
            if retry:
                source_job=self.job
                if payload.get('job_id'):
                    with closing(self.connection()) as conn:
                        row=conn.execute('SELECT payload_json FROM v3_collection_jobs WHERE id=?',(payload['job_id'],)).fetchone()
                    if not row: raise ValueError('记录已不存在，请刷新后重试')
                    source_job=json.loads(row[0])
                if not source_job:
                    raise ValueError('没有可继续的采集任务')
                retry_categories=payload.get('categories')
                if retry_categories is not None and (not isinstance(retry_categories,list) or not retry_categories or any(c not in CATEGORIES for c in retry_categories)):
                    raise ValueError('请选择需要重试的采集类型')
                subset = payload.get('account_ids')
                if subset is not None and (not isinstance(subset, list) or not subset or any(not isinstance(a, str) or a not in available for a in subset)):
                    raise ValueError('请选择需要重试的有效账号')
                previous = {c['id']: c for c in [*source_job.get('retained_items', []), *source_job['items']]}
                pairs = [(c['account_id'], c['category']) for c in previous.values() if c['status'] in ('failed', 'partial', 'stopped') and (subset is None or c['account_id'] in subset) and (retry_categories is None or c['category'] in retry_categories)]
                if payload.get('job_id'):
                    latest={(r['item']['account_id'],r['item']['category']):r['job_id'] for r in self.record_summaries()}
                    if any(latest.get(pair)!=source_job['id'] for pair in pairs):
                        raise ValueError('该类型已有更新的采集记录，请刷新后操作最新记录')
                selected_pairs = set(pairs)
                retained_items = [clone(c) for c in previous.values() if (c['account_id'], c['category']) not in selected_pairs]
                options = dict(source_job['options'])
                # A partial result was saved, but its missing portion must remain retryable.
                options['force_works'] = True
                options['force_optimization'] = False
                options['optimization_refresh_uids'] = [c['uid'] for c in previous.values() if (c['account_id'], c['category']) in selected_pairs and c['category'] == 'optimization' and not c.get('detection_completed')]
            else:
                ids, categories = payload.get('account_ids'), payload.get('categories')
                if not isinstance(ids, list) or not ids or any(not isinstance(a, str) or a not in available for a in ids):
                    raise ValueError('请选择已绑定且未注销的有效账号')
                if not isinstance(categories, list) or not categories or any(not isinstance(c, str) or c not in CATEGORIES for c in categories):
                    raise ValueError('请选择有效的采集内容')
                interval = validate_page_interval(payload.get('page_interval_seconds', configured_page_interval(self.connection)))
                cooldown = payload.get('works_cooldown_hours', 1)
                if isinstance(cooldown, bool) or not isinstance(cooldown, (int, float)) or not 0 <= cooldown <= 168:
                    raise ValueError('作品重复更新间隔需为0至168小时')
                if not isinstance(payload.get('force_works', False), bool):
                    raise ValueError('作品强制更新参数无效')
                if type(payload.get('force_optimization', False)) is not bool:
                    raise ValueError('立即检测参数无效')
                options = {'page_interval_seconds': interval, 'works_cooldown_hours': cooldown, 'force_works': payload.get('force_works', False), 'force_optimization': payload.get('force_optimization', False)}
                if 'scope_version' in payload or 'scope' in payload:
                    scope = payload.get('scope')
                    if type(payload.get('scope_version')) is not int or payload.get('scope_version') != 1 or not isinstance(scope, dict) or set(scope) - set(categories):
                        raise ValueError('采集范围参数无效')
                    for category, spec in scope.items():
                        allowed = {'daily': ('fill_missing', 'reset_online'), 'works': ('all', 'published_range'), 'revenue': ('routine',)}.get(category, ())
                        if not isinstance(spec, dict) or spec.get('mode') not in allowed:
                            raise ValueError('当前不支持该采集范围')
                        if category == 'works' and spec['mode'] == 'published_range':
                            if set(spec) != {'mode', 'start_date', 'end_date'}:
                                raise ValueError('作品发布时间范围参数无效')
                            publication_window(spec['start_date'], spec['end_date'])
                        elif set(spec) != {'mode'}:
                            raise ValueError('当前不支持该采集范围')
                    options.update(scope_version=1, scope=scope)

                platform_ids = payload.get('platform_account_ids')
                if platform_ids is not None:
                    if not isinstance(platform_ids, list) or any(not isinstance(a, str) or a not in ids for a in platform_ids):
                        raise ValueError('平台采集账号必须属于本次已选账号')
                    options['platform_account_ids'] = list(dict.fromkeys(platform_ids))
                pairs = [(aid, c) for aid in dict.fromkeys(ids) for c in CATEGORIES if c in categories]
            pairs = [(a, c) for a, c in pairs if a in available]
            if not pairs:
                raise ValueError('没有需要继续的有效采集项')
            if not ops.LOCK.acquire(blocking=False):
                raise ValueError('后台正在进行发布归属检查或其他采集，请稍后再试')
            def unavailable_item(a, category):
                account = available[a]
                if category == 'revenue':
                    revenue = account.get('revenue') or {}
                    return '' if revenue.get('available') else revenue.get('message') or '未配置收益采集器'
                if category != 'revenue' and 'platform_account_ids' in options and a not in options['platform_account_ids']:
                    return '停用账号本次仅采收益，平台数据未选入'
                if source == 'automatic' and account.get('business_status') in ('停用','注销','disabled'):
                    return '账号已停用或注销，不自动采集平台数据'
                if source == 'automatic' and invalid_login(account):
                    return '小V猫本地记录显示登录失效，请登录后读取本地登录状态'
                return '' if account.get('platform_available', True) else '未绑定可用的平台账号'

            self.stop_event.clear()
            self.job = {'id': uuid.uuid4().hex, 'state': 'running', 'started_at': ops.stamp(), 'finished_at': '',
                        'source': 'retry' if retry else source, 'parent_job_id': source_job['id'] if retry else '',
                        'options': options, 'current_item': '', 'events': [], 'retained_items': retained_items, 'items': [
                            {'id': a+':'+c, 'account_id': a, 'uid': available[a]['uid'], 'account_name': available[a]['name'],
                             'category': c, 'status': 'skipped' if unavailable_item(a, c) else 'waiting',
                             'message': '本项不适用，已跳过：'+unavailable_item(a, c) if unavailable_item(a, c) else '等待前面的账号完成，不会并发请求', 'updated_at': ops.stamp()}
                            for a, c in pairs]}
            try:
                self._save()
                self.thread = threading.Thread(target=self._run, name='v3-user-collection', daemon=True)
                self.thread.start()
            except BaseException:
                self.job['state'] = 'failed'
                ops.LOCK.release()
                raise
            return {'job': clone(self.job), 'reused': False}

    def save_detection(self, payload):
        with self.mutex:
            available = {str(a['id']): a for a in catalog(self.connection) if a['available']}
            return {'optimization_detection': self.detection.save(payload, {a:v for a,v in available.items() if detection_available(v)})}

    def detect_now(self, payload):
        with self.mutex:
            available = {str(a['id']): a for a in catalog(self.connection) if a['available']}
            ids = payload.get('account_ids')
            if not isinstance(ids, list) or not ids or any(not isinstance(a, str) or a not in available for a in ids):
                raise ValueError('请先选择需要立即检测的有效账号')
            active = {c['account_id'] for c in self.job['items'] if c['category'] == 'optimization' and c['status'] not in TERMINAL} if self.job and self.job['state'] in ACTIVE else set()
            eligible = {aid:a for aid,a in available.items() if detection_available(a)}
            pending = [aid for aid in dict.fromkeys(ids) if aid not in active and aid in eligible]
            if pending:
                self.detection.request(pending, eligible)
            try:
                self.tick_detection()
            except ValueError:
                pass  # Another V3 operation owns the shared lock; the request remains queued.
            return {'job': clone(self.job), 'optimization_detection': self.detection.state(),
                    'message': '可检测账号已加入队列；登录失效或未绑定平台的账号已跳过' if pending else '未新增检测请求；账号已在队列中，或登录失效/未绑定可用平台账号'}

    def tick_detection(self):
        with self.mutex:
            if self.job and self.job['state'] in ACTIVE:
                return
            available = {str(a['id']): a for a in catalog(self.connection) if a['available']}
            available = {aid:a for aid,a in available.items() if detection_available(a)}
            ids = self.detection.due_ids(available)
            if not ids:
                return
            result = self.start({'account_ids': ids, 'categories': ['optimization'], 'force_optimization': True}, source='automatic')
            if not result['reused']:
                for aid in ids:
                    self.detection.defer(aid, available[aid]['uid'], message='已进入检测队列')
            return result

    def stop(self, job_id):
        with self.mutex:
            if not self.job or self.job['id'] != job_id:
                raise ValueError('采集任务已变化，请重新读取状态')
            if self.job['state'] in ACTIVE:
                self.stop_event.set()
                self.job['state'] = 'stopping'
                self._save()
            return {'job': clone(self.job)}

    def _cache(self, uid, kind, value):
        with closing(self.connection()) as conn:
            ops.cache(conn, uid, kind, value, ops.stamp())
            conn.commit()

    def _resume_verified_revenue(self):
        from server.pingyue_collector import challenge_state
        from server.revenue_queue import collect_account
        while not self.stop_event.is_set():
            waiting = [c for c in self.job['items'] if c.get('revenue_result', {}).get('verification_id')]
            if not waiting:
                return
            pending = False
            for cell in waiting:
                checkpoint(self.stop_event.is_set)
                outcome = cell['revenue_result']
                state = challenge_state(outcome['verification_id'])
                if state == 'pending':
                    pending = True
                elif state == 'ready':
                    self._emit(cell, '人工验证已通过，继续未完成日期', 'running')
                    fresh = {}
                    status, message = collect_account(self.connection, cell['account_id'],
                        lambda message, c=cell: self._emit(c, message), self.stop_event.is_set, outcome=fresh)
                    cell['revenue_result'] = fresh
                    self._emit(cell, message, status)
                    pending = pending or bool(fresh.get('verification_id'))
                else:
                    outcome.pop('verification_id', None)
                    self._emit(cell, '验证暂未完成，已保存结果保留；下次继续采集', 'partial')
            if pending:
                self.stop_event.wait(.3)

    def _run(self):
        paused = False
        revenue_paused = False
        try:
            from server.revenue_queue import collect_account
            for cell in self.job['items']:
                if cell['category'] != 'revenue' or cell['status'] in TERMINAL:
                    continue
                checkpoint(self.stop_event.is_set)
                self._emit(cell, '正在核对收益配置及已保存日期', 'running')
                try:
                    outcome = {}
                    status, message = collect_account(self.connection, cell['account_id'],
                        lambda message, c=cell: self._emit(c, message), self.stop_event.is_set, outcome=outcome)
                    cell['revenue_result'] = outcome
                    self._emit(cell, message, status)
                except CollectionAccessLimited:
                    self._emit(cell, '收益来源出现访问限制，已暂停后续请求；请处理后重试', 'failed')
                    paused = revenue_paused = True
                    raise
                except CollectionStopped:
                    raise
                except Exception as exc:
                    self._emit(cell, '收益查询未完成，已保存结果保留；'+str(exc), 'failed')
            with closing(self.connection()) as conn:
                saved_logins = ops.login_statuses(conn)
            for cell in self.job['items']:
                if self.job.get('source') == 'automatic' and cell['category'] != 'revenue' and cell['status'] not in TERMINAL and invalid_login(saved_logins.get(cell['uid'], {})):
                    self._emit(cell, '小V猫本地记录显示登录失效，已跳过；未发起查询', 'skipped')
            video_cells = [c for c in self.job['items'] if c['category'] != 'revenue' and c['status'] not in TERMINAL]
            if not video_cells:
                return
            from server.publishing.vcat import VcatClient
            from server.work_media import WorkMediaCache
            media = self.media_cache
            if media is None and any(c['category']=='works' for c in self.job['items']):
                from server.v2_file_service import DATA_ROOT
                media = WorkMediaCache(DATA_ROOT / 'cache' / 'work-covers')
            first = video_cells[0]
            self._emit(first, '正在读取小V猫本地保存的账号登录信息')
            checkpoint(self.stop_event.is_set)
            with (self.client_factory or (lambda: VcatClient(account_data=True, optimization_actions=True)))() as client:
                client = CooperativeClient(client, self.stop_event.is_set)
                accounts = ops.pages(client, 'vcat_list_accounts', {'platform': '视频号'})
                with closing(self.connection()) as conn:
                    platform_accounts = ops.accounts_by_uid(conn)
                with closing(self.connection()) as conn:
                    ops.cache_login_statuses(conn, accounts)
                    conn.commit()
                valid = {a['uid'] for a in accounts if a.get('loginStatus') == '登录有效'}
                self._emit(first, '已读取小V猫本地登录信息，失效账号将跳过')
                current_full_posts = {}
                uids = list(dict.fromkeys(c['uid'] for c in video_cells))
                for uid in uids:
                    cells = [c for c in video_cells if c['uid']==uid]
                    with closing(self.connection()) as conn:
                        snapshots = uid_snapshots(conn, uid)
                    stats = snapshots.get((uid, 'stats'), ({}, ''))[0] or {}
                    # Run works first so a selected optimization step can use its fresh identity map.
                    for cell in sorted(cells, key=lambda c: ['works','daily','profile','optimization'].index(c['category'])):
                        checkpoint(self.stop_event.is_set)
                        category = cell['category']
                        with closing(self.connection()) as conn:
                            current_account = conn.execute('SELECT status FROM accounts WHERE id=?',(cell['account_id'],)).fetchone()
                        if current_account is None or current_account['status'] == '注销' or (self.job.get('source') == 'automatic' and current_account['status'] in ('停用','disabled')):
                            self._emit(cell,'账号已停用或注销，本项停止采集；已保存历史保留','skipped')
                            continue
                        if uid not in valid or platform_accounts.get(uid) != cell['account_id']:
                            if category == 'optimization':
                                self.detection.defer(cell['account_id'], uid, message='账号未登录或登录失效，未发起检测')
                            self._emit(cell, '小V猫本地未记录有效登录，已跳过；未向官方发起请求，请在小V猫登录后读取本地登录状态', 'skipped')
                            continue
                        self._emit(cell, '正在核对本地已保存的数据', 'running')
                        progress = lambda message, c=cell: self._emit(c, message)
                        opts = self.job['options']
                        try:
                            if category == 'works':
                                previous, fetched = snapshots.get((uid, 'posts'), ([], ''))
                                opts = self.job['options']
                                scope = opts.get('scope', {}).get('works', {'mode': 'all'})
                                ranged = scope['mode'] == 'published_range'
                                meta = snapshots.get((uid, 'posts_collection'), ({'fullFetchedAt': fetched, 'ranges': []}, ''))[0]
                                timestamps = [meta.get('fullFetchedAt')]
                                if ranged:
                                    timestamps += [item['fetchedAt'] for item in meta.get('ranges', []) if item['startDate'] <= scope['start_date'] and item['endDate'] >= scope['end_date']]
                                covered_at = max((ops.unix(t) or 0 for t in timestamps), default=0)
                                elapsed = datetime.now(ops.SH).timestamp() - covered_at if covered_at else float('inf')
                                label = f"{scope['start_date']} 至 {scope['end_date']} 发布的作品" if ranged else '全部作品'
                                if not opts['force_works'] and 0 <= elapsed < opts['works_cooldown_hours'] * 3600:
                                    self._emit(cell, f'{label}已在 {opts["works_cooldown_hours"]:g} 小时内完整读取，已跳过重复请求', 'skipped')
                                    continue
                                progress(f'正在更新{label}的当前累计流量')
                                range_args = {'published_start': scope['start_date'], 'published_end': scope['end_date']} if ranged else {}
                                rows = client.online_account_posts(uid, page_interval_seconds=opts['page_interval_seconds'], progress=progress, should_stop=self.stop_event.is_set, **range_args)
                                # A completely returned range can be saved even if cover processing is stopped.
                                media_progress = (lambda message: progress(message.replace('作品列表已完整返回', '本次范围的作品已返回'))) if ranged else progress
                                rows, errors = media.prepare(uid, rows, previous, progress=media_progress, should_stop=self.stop_event.is_set)
                                saved = rows
                                if ranged:
                                    merged = {str(item['postId']): item for item in previous}
                                    merged.update({str(item['postId']): item for item in rows})
                                    saved = list(merged.values())
                                progress('正在保存本次范围作品，保留其他作品和历史数据' if ranged else '正在保存完整作品列表、播放地址和本地封面引用')
                                with closing(self.connection()) as conn:
                                    ops.cache(conn, uid, 'posts', saved, ops.stamp(), posts_scope=scope if ranged else None)
                                    ops.reconcile(conn, {uid: rows}, {}, ops.stamp())
                                    conn.commit()
                                if not ranged: current_full_posts[uid] = rows
                                prefix = f'已保存范围内 {len(rows)} 条作品，范围外旧数据保留；' if ranged else f'已保存 {len(rows)} 条作品；'
                                self._emit(cell, prefix+('已按停止要求结束封面整理，其余封面可继续本项' if self.stop_event.is_set() else f'{len(errors)} 张封面获取失败，保留已有封面，可单独重试本项' if errors else '封面与播放地址已整理'), 'partial' if errors or self.stop_event.is_set() else 'success')
                            elif category == 'daily':
                                end = (datetime.now(ops.SH).date()-timedelta(days=1)).isoformat()
                                previous_metadata = stats.get('dailyCollection')
                                reset_online = self.job['options'].get('scope', {}).get('daily', {}).get('mode') == 'reset_online'
                                stats, info = collect_daily(client, uid, stats, end, ops.stamp(), refresh=True, progress=progress, should_stop=self.stop_event.is_set, save_partial=lambda value: self._cache(uid, 'stats', value), reset_online=reset_online)
                                if info['state'] != 'up_to_date' or stats.get('dailyCollection') != previous_metadata: self._cache(uid, 'stats', stats)
                                if info['state'] == 'partial':
                                    self._emit(cell, info.get('resetError') or f'已保存取得的日期；仍缺 {len(info["missingDates"])} 天，'+('历史起点尚未确认' if not info.get('boundaryConfirmed') else '需要补齐缺失字段或日期'), 'partial')
                                else:
                                    self._emit(cell, f'{info["startDate"]} 至 {end} 已完整'+('，本项无需请求' if info['state']=='up_to_date' else '，已补齐并保存'), 'skipped' if info['state']=='up_to_date' else 'success')
                            elif category == 'profile':
                                # Reuse totals obtained by the daily step; otherwise read Xiao V's cache once.
                                daily_cell = next((c for c in cells if c['category']=='daily'), None)
                                if not daily_cell or daily_cell['status'] != 'success':
                                    progress('读取小V猫已有账号资料：视频数、关注者数；本步骤不主动刷新官方数据')
                                    checkpoint(self.stop_event.is_set)
                                    result = client.call('vcat_get_account_stats', {'uid': uid, 'includeIncome': False})
                                    fresh = result.get('total') or {}
                                    stats = {**stats, 'total': {**(stats.get('total') or {}), **{k: v for k, v in fresh.items() if v is not None}}}
                                    self._cache(uid, 'stats', stats)
                                total = stats.get('total') or {}
                                measured = fresh if not daily_cell or daily_cell['status'] != 'success' else total
                                values = [ops.number(measured.get(k)) for k in ('postCount', 'fans')]
                                self._emit(cell, '已读取小V猫已有账号资料；来源更新时间：'+str(total.get('updateTime') or '未提供') if all(v is not None for v in values) else '本次视频数或关注者数仍不完整，缺失不补0，已有历史保留', 'success' if all(v is not None for v in values) else 'partial')
                            else:
                                with closing(self.connection()) as conn:
                                    saved_diagnosis = uid_snapshots(conn, uid).get((uid, 'diagnosis'), ({}, ''))[0] or {}
                                fresh = self.job['options'].get('force_optimization', False) or uid in self.job['options'].get('optimization_refresh_uids', []) or self.detection.due(uid) or not saved_diagnosis.get('verified')
                                if fresh:
                                    self.detection.defer(cell['account_id'], uid, attempted=True, message='正在检测；若程序中断，将按下一周期继续')
                                    progress('正在通过小V猫主动检测近期异常作品，等待本账号检测完成')
                                    diagnosis = client.refresh_account_diagnosis(uid)
                                    if not diagnosis or not diagnosis.get('verified'):
                                        raise RuntimeError('本次检测未返回完整名单，已有历史保留')
                                    diagnosis['detectedAt'] = ops.stamp()
                                    diagnosis['sourceTimestampUnix'] = diagnosis.get('lastVerifyUnix')
                                    diagnosis['lastVerifyUnix'] = int(ops.unix(diagnosis['detectedAt']))
                                    self._cache(uid, 'diagnosis', diagnosis)
                                    self.detection.defer(cell['account_id'], uid, success=True, attempted=True)
                                    cell['detection_completed'] = True
                                    progress('本次检测已完成，正在保存全部优化通知并自动核对作品')
                                else:
                                    diagnosis = saved_diagnosis
                                    if not diagnosis or not diagnosis.get('verified'):
                                        self._emit(cell, '尚无成功检测结果，已安排下一周期；也可点击立即检测重试', 'partial')
                                        continue
                                    cell['detection_completed'] = True
                                    progress('尚未到下次随机检测时间，复用上次成功名单，仅补充缺失的作品分析')
                                checkpoint(self.stop_event.is_set)
                                from server import work_history
                                # Save notices BEFORE any further network request can fail.
                                self._cache(uid, 'diagnosis', diagnosis)
                                with closing(self.connection()) as conn:
                                    feeds = work_history.collection_feeds(conn,uid,diagnosis)
                                current_notice_count = len(diagnosis.get('feeds', []))
                                online_posts = []
                                online_ok = False
                                failed = 0
                                if feeds:
                                    progress('补查账号完整作品列表，按发布时间核对；删除过的作品保留历史')
                                    try:
                                        if uid in current_full_posts:
                                            online_posts = current_full_posts[uid]
                                        else:
                                            online_posts = client.online_account_posts(uid, page_interval_seconds=opts['page_interval_seconds'], progress=progress, should_stop=self.stop_event.is_set)
                                            with closing(self.connection()) as conn:
                                                prior = uid_snapshots(conn,uid).get((uid,'posts'),([],''))[0]
                                            covers = {str(p['postId']):p.get('coverLocalId') for p in prior if p.get('coverLocalId')}
                                            online_posts = [{**p, **({'coverLocalId':covers[str(p['postId'])]} if str(p['postId']) in covers else {})} for p in online_posts]
                                            self._cache(uid, 'posts', online_posts)
                                            current_full_posts[uid] = online_posts
                                        online_ok = True
                                    except CollectionStopped: raise
                                    except Exception as exc:
                                        if self._limited(exc): raise
                                        failed += 1
                                try:
                                    tasks = ops.pages(client, 'vcat_list_publish_tasks', {'uid': uid, 'platform': '视频号'})
                                    with closing(self.connection()) as conn:
                                        latest = uid_snapshots(conn, uid)
                                        post_cache = latest.get((uid, 'posts'))
                                        ops.reconcile(conn, {uid: post_cache[0]} if post_cache else {}, {uid: tasks}, ops.stamp())
                                        work_history.resolve(conn, uid)
                                        conn.commit()
                                except CollectionStopped: raise
                                except Exception as exc:
                                    if self._limited(exc): raise
                                    failed += 1  # Software attribution failure must not exclude other notices.
                                saved = reused = 0
                                for n, feed in enumerate(feeds, 1):
                                    checkpoint(self.stop_event.is_set)
                                    progress(f'核对全部优化记录 {n} / {len(feeds)}；缺失详情自动补查')
                                    with closing(self.connection()) as conn:
                                        notice = conn.execute('SELECT * FROM v3_work_notices WHERE id=?', (work_history.notice_id(uid,feed),)).fetchone()
                                    if notice and json.loads(notice['detail_json']).get('feedCreateTime'): reused += 1; continue
                                    if not feed.get('exportId'): failed += 1; continue
                                    try:
                                        detail = client.optimization_detail(uid, feed['exportId'])
                                        with closing(self.connection()) as conn:
                                            work_history.store_detail(conn, uid, feed, detail, ops.stamp()); conn.commit()
                                        saved += 1
                                    except CollectionStopped: raise
                                    except Exception as exc:
                                        if self._limited(exc): raise
                                        failed += 1
                                with closing(self.connection()) as conn:
                                    work_history.resolve(conn, uid)
                                    pending = conn.execute("SELECT COUNT(*) FROM v3_work_notices WHERE uid=? AND match_state<>'matched'",(uid,)).fetchone()[0]
                                    conn.commit()
                                actions = work_history.process_actions(self.connection, client, uid, online_posts,
                                    fresh_detection=fresh and online_ok, should_stop=self.stop_event.is_set, page_interval_seconds=opts['page_interval_seconds'])
                                action_message = (f'；处理请求 {actions["submitted"]} 条（最终状态待核实），保护跳过 {actions["protected"]} 条，结果未确认 {actions["unknown"]} 条'
                                    if any(actions.values()) else '')
                                self._emit(cell, f'已收录本次全部 {current_notice_count} 条通知，并核对历史待查；新增分析 {saved} 条，复用 {reused} 条；历史待补查 {pending} 条'
                                    +(f'；{failed} 项查询未完成' if failed else '')+action_message
                                    +('；本次已主动检测' if fresh else '；复用上次检测名单')+'；最近成功检测：'+str(diagnosis.get('detectedAt') or '未提供'),
                                    'partial' if failed or pending or actions['unknown'] else 'success')
                        except PublicationRangeError as exc:
                            self._emit(cell, str(exc), 'failed')
                        except CollectionAccessLimited:
                            if category == 'optimization':
                                self.detection.defer(cell['account_id'], uid, message='检测遇到访问限制，自动检测已暂停')
                            self._emit(cell, '检测到登录或访问限制，已暂停后续请求，请处理后手动继续', 'failed')
                            paused = True
                            raise
                        except CollectionStopped:
                            raise
                        except Exception as exc:
                            if category == 'optimization':
                                self.detection.defer(cell['account_id'], uid, message='本次未完成，历史保留，可手动重试')
                            limited = self._limited(exc)
                            self._emit(cell, '检测到登录或访问限制，已暂停后续请求，请处理后手动继续' if limited else '本项未完成，已保存的历史保留；请检查小V猫连接后重试', 'failed')
                            if limited:
                                paused = True
                                raise CollectionStopped()
        except CollectionAccessLimited:
            paused = True
            current = next((c for c in self.job['items'] if c['id'] == self.job['current_item']), self.job['items'][0])
            if current['status'] not in TERMINAL:
                self._emit(current, '检测到登录或访问限制，已暂停后续请求，请处理后手动继续', 'failed')
        except CollectionStopped:
            pass
        except Exception:
            for cell in self.job['items']:
                if cell['status'] not in TERMINAL:
                    self._emit(cell, '连接小V猫或读取账号失败；已有数据保留，请检查连接后重试', 'failed')
        finally:
            if not paused and not self.stop_event.is_set():
                try:
                    self._resume_verified_revenue()
                except CollectionStopped:
                    pass
                except Exception as exc:
                    for cell in self.job['items']:
                        if cell.get('revenue_result', {}).pop('verification_id', None):
                            self._emit(cell, '验证后续采未完成，已有结果保留；'+str(exc), 'partial')
            with self.mutex:
                for cell in self.job['items']:
                    verification_id = cell.get('revenue_result', {}).get('verification_id')
                    if self.stop_event.is_set() and verification_id:
                        from server.pingyue_collector import defer_waiting
                        defer_waiting(verification_id)
                        cell['revenue_result'].pop('verification_id', None)
                        cell.update(status='stopped', message='已停止等待验证码；已保存收益保留，下次继续', updated_at=ops.stamp())
                    if cell['status'] not in TERMINAL:
                        message = '后续请求已停止；已完成项保留，本项可继续'
                        if cell['category'] == 'works':
                            message += '。未完整返回的作品分页不覆盖旧列表'
                        cell.update(status='stopped', message=message, updated_at=ops.stamp())
                states = {c['status'] for c in [*self.job.get('retained_items', []), *self.job['items']]}
                self.job['state'] = 'paused' if paused else 'stopped' if 'stopped' in states else 'partial' if states & {'failed','partial'} else 'completed'
                self.job['finished_at'] = ops.stamp()
                try:
                    if paused and not revenue_paused:
                        self.detection.pause()
                    for cell in self.job['items']:
                        if cell['category'] == 'optimization' and cell['status'] == 'stopped':
                            self.detection.defer(cell['account_id'], cell['uid'], message='检测已停止，未完成部分保留到下一周期')
                    self._save()
                finally:
                    ops.LOCK.release()

    _limited = staticmethod(access_limited)


class CooperativeClient:
    """Stop between remote calls, including helper pagination; surface rate limits."""
    def __init__(self, client, should_stop):
        self.client, self.should_stop = client, should_stop

    def __getattr__(self, name):
        value = getattr(self.client, name)
        if not callable(value): return value
        def invoke(*args, **kwargs):
            checkpoint(self.should_stop)
            try:
                return value(*args, **kwargs)
            except CollectionStopped:
                raise
            except Exception as exc:
                if access_limited(exc): raise CollectionAccessLimited() from None
                raise
        return invoke


_manager = None
_manager_lock = threading.Lock()


def manager(connection):
    global _manager
    with _manager_lock:
        if _manager is None: _manager = CollectionJobs(connection)
        return _manager


_scheduler_stop = threading.Event()
_scheduler_thread = None
_scheduler_lock = threading.Lock()


def start_optimization_detection_scheduler(connection):
    """Service lifetime only; defaults to disabled until the user saves a scope."""
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            return
        jobs = manager(connection)
        _scheduler_stop.clear()
        def run():
            import logging
            while not _scheduler_stop.wait(5):
                try:
                    jobs.tick_detection()
                except ValueError:
                    pass  # Another V3 collection owns the shared lock; wait for the next tick.
                except Exception:
                    logging.getLogger(__name__).warning('优化检测调度暂未完成，下次检查重试', exc_info=False)
        _scheduler_thread = threading.Thread(target=run, name='v3-optimization-detection', daemon=True)
        _scheduler_thread.start()
