import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from datetime import date, timedelta
from server import operations_collection as ops
from server.collection_jobs import CollectionJobs
from server.account_daily_collection import DAILY_FIELDS


class CollectionJobsTests(unittest.TestCase):
    def setUp(self):
        self.connections=[]
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name) / 'test.sqlite'
        with self.connect() as c:
            c.executescript("CREATE TABLE accounts(id TEXT,nickname TEXT,channel_id TEXT,status TEXT); INSERT INTO accounts VALUES('a','甲','u','正常'),('b','乙','v','正常'),('closed','注销','z','注销'); CREATE TABLE v3_publish_documents(kind TEXT,key TEXT,content TEXT);")
            ops.initialize(c)
        self.calls = []; self.block = None; self.entered = threading.Event(); self.fail = None
        owner = self
        class Client:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def call(self, name, args):
                owner.calls.append((name, dict(args)))
                if name == 'vcat_list_accounts':
                    if owner.block:
                        owner.entered.set(); owner.block.wait(5)
                    return {'list':[{'uid':'u','loginStatus':'登录有效'},{'uid':'v','loginStatus':'登录有效'}], 'total':2}
                if owner.fail: raise RuntimeError(owner.fail)
                if name == 'vcat_get_account_stats': return {'total': {'postCount':3,'fans':8,'updateTime':'2026-11-01'},'daily':[]}
                if name == 'vcat_list_publish_tasks': return {'list':[],'total':0}
                if name == 'vcat_refresh_account_stats': return {'results':[{'uid': args['uids'][0],'success': True}]}
                raise AssertionError(name)
            def online_account_posts(self, uid, **kwargs):
                owner.calls.append(('works', {'uid':uid}))
                if owner.fail: raise RuntimeError(owner.fail)
                kwargs['progress']('第 1 页已返回，累计读取 1 / 1 条作品')
                return [{'uid': uid, 'postId':'p', 'publishStatus':'published', 'postUnix':1,'view':7}]
            def account_diagnosis(self, uid): return {'uid': uid, 'verified':True,'feeds':[]}
        class Media:
            def prepare(self, uid, rows, previous=(), **kwargs): return rows, []
        self.jobs = CollectionJobs(self.connect, client_factory=Client, media_cache=Media())
    def connect(self):
        c=sqlite3.connect(self.path, check_same_thread=False); c.row_factory=sqlite3.Row; self.connections.append(c); return c
    def tearDown(self):
        if self.block: self.block.set()
        if self.jobs.thread: self.jobs.thread.join(5)
        for connection in self.connections: connection.close()
        self.tmp.cleanup()
    def start(self, cats=('profile',), ids=('a',), **options):
        result=self.jobs.start({'account_ids':list(ids),'categories':list(cats),**options})
        self.jobs.thread.join(5); self.assertFalse(self.jobs.thread.is_alive()); return self.jobs.state()['job']
    def test_paused_mixed_job_collects_revenue_without_platform_requests_unless_explicit(self):
        from unittest.mock import patch
        with self.connect() as conn:
            conn.execute("UPDATE accounts SET status='停用' WHERE id='a'")
        meta = [dict(id='a',uid='u',name='甲',business_status='停用',available=True,platform_available=True,last_success={},revenue=dict(available=True))]
        with patch('server.collection_jobs.catalog',return_value=meta), patch('server.revenue_queue.collect_account',return_value=('success','收益已保存')) as collect:
            job=self.start(('profile','revenue'),platform_account_ids=[])
            self.assertEqual(collect.call_count,1)
        self.assertEqual(self.calls,[])
        self.assertEqual({i['category']:i['status'] for i in job['items']},{'profile':'skipped','revenue':'success'})
        job=self.start(('profile',),platform_account_ids=['a'])
        self.assertEqual(job['items'][0]['status'],'success')
        self.assertTrue(any(name=='vcat_get_account_stats' for name,_ in self.calls))

    def test_automatic_detection_omits_paused_and_cancelled_but_manual_platform_selection_is_available(self):
        from server.collection_jobs import detection_available, catalog
        with self.connect() as conn:
            conn.execute("UPDATE accounts SET status='停用' WHERE id='a'")
        rows={a['id']:a for a in catalog(self.connect)}
        self.assertTrue(rows['a']['platform_available'])
        self.assertFalse(detection_available(rows['a']))
        self.assertFalse(rows['closed']['available'])
        self.assertEqual(self.calls,[])
        with self.assertRaises(ValueError):
            self.jobs.start({'account_ids':['a'],'platform_account_ids':['closed'],'categories':['profile']})
        self.assertEqual(self.calls,[])

    def test_mixed_selection_skips_inapplicable_categories_before_source_requests(self):
        from unittest.mock import patch
        catalog = [dict(id='a', uid='u', name='甲', available=True, last_success={}, platform_available=True,
                        revenue=dict(available=False, message='未配置收益采集器')),
                   dict(id='b', uid='v', name='乙', available=True, last_success={}, platform_available=False,
                        revenue=dict(available=True))]
        with patch('server.collection_jobs.catalog', return_value=catalog):
            with patch('server.revenue_queue.collect_account', return_value=('success', '收益已保存')) as collect:
                job = self.start(('profile', 'revenue'), ('a', 'b'))
        states = {(i['account_id'], i['category']): i for i in job['items']}
        self.assertEqual(states['a','revenue']['status'], 'skipped')
        self.assertIn('未配置收益采集器', states['a','revenue']['message'])
        self.assertEqual(states['b','profile']['status'], 'skipped')
        self.assertEqual(states['a','profile']['status'], 'success')
        self.assertEqual(states['b','revenue']['status'], 'success')
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(collect.call_args.args[1], 'b')
        self.assertEqual([a['uid'] for n,a in self.calls if n=='vcat_get_account_stats'], ['u'])

    def test_inapplicable_only_job_makes_no_source_requests(self):
        from unittest.mock import patch
        catalog = [dict(id='a', uid='u', name='甲', available=True, last_success={}, platform_available=True,
                        revenue=dict(available=False, message='未配置收益采集器'))]
        with patch('server.collection_jobs.catalog', return_value=catalog):
            with patch('server.revenue_queue.collect_account') as collect:
                job = self.start(('revenue',))
        self.assertEqual(job['items'][0]['status'], 'skipped')
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(self.calls, [])
        collect.assert_not_called()

    def test_process_events_are_retained_per_account_and_category_with_actual_item_times(self):
        from unittest.mock import patch
        self.jobs.job={'id':'event-isolation','source':'manual','state':'running',
            'started_at':'2026-11-05T08:00:00+08:00','finished_at':'',
            'options':{},'events':[],'items':[
                dict(id=a+':works',account_id=a,uid=a,account_name=a,category='works',status='waiting',message='',updated_at='')
                for a in ['a','b']]}
        a,b=self.jobs.job['items']
        with patch('server.collection_jobs.ops.stamp',return_value='2026-11-05T08:30:00+08:00'):
            self.jobs._emit(a,'甲开始','running')
            self.jobs._emit(a,'甲已保存','success')
        self.jobs._emit(b,'乙开始','running')
        for n in range(125):self.jobs._emit(b,f'乙步骤{n}')
        self.jobs._emit(b,'乙已保存','success')
        first=self.jobs.records('a','works')['records'][0]
        second=self.jobs.records('b','works')['records'][0]
        self.assertEqual(['甲开始','甲已保存'],[e['message'] for e in first['events']])
        self.assertEqual('2026-11-05T08:30:00+08:00',first['item']['started_at'])
        self.assertEqual('2026-11-05T08:30:00+08:00',first['item']['finished_at'])
        self.assertEqual(120,len(second['events']))
        self.assertTrue(second['item']['events_truncated'])

    def test_records_keep_history_and_read_latest_per_account_category(self):
        first=self.start(('works',),force_works=True)
        second=self.start(('profile',),ids=('b',))
        records=self.jobs.records('a','works')['records']
        self.assertEqual([r['job_id'] for r in records],[first['id']])
        self.assertEqual(records[0]['source'],'manual')
        self.assertTrue(all(e['account_id']=='a' for e in records[0]['events']))
        latest=self.jobs.state()['record_summaries']
        self.assertEqual(next(r for r in latest if r['item']['category']=='works')['job_id'],first['id'])
        before=len(self.calls)
        self.assertEqual(self.jobs.records('b','daily')['records'],[])
        self.assertEqual(len(self.calls),before)
        with self.assertRaises(ValueError):self.jobs.records('a','invalid')

    def test_retry_record_uses_original_scope_and_only_one_category(self):
        self.fail='offline'
        first=self.start(('works','profile'),force_works=True)
        self.fail=None
        self.start(('profile',),ids=('b',))
        self.jobs.start({'account_ids':['a'],'job_id':first['id'],'categories':['works']},retry=True)
        self.jobs.thread.join(5)
        latest=self.jobs.state()['job']
        self.assertEqual([(i['account_id'],i['category']) for i in latest['items']],[('a','works')])
        self.assertEqual(latest['source'],'retry')
        self.assertEqual(latest['parent_job_id'],first['id'])
        records=self.jobs.records('a','works')['records']
        self.assertEqual([r['item']['status'] for r in records],['success','failed'])
        self.assertEqual(self.jobs.records('a','daily')['records'],[])
        with self.assertRaisesRegex(ValueError,'更新的采集记录'):
            self.jobs.start({'account_ids':['a'],'job_id':first['id'],'categories':['works']},retry=True)

    def test_startup_deletes_excess_records_and_has_no_older_pages(self):
        first=self.start(('works',),force_works=True)
        with self.connect() as c:
            for n in range(23):
                job=json.loads(json.dumps(first));job['id']='history-'+str(n)
                c.execute('INSERT INTO v3_collection_jobs VALUES(?,?)',(job['id'],json.dumps(job)))
            c.commit()
        restored=CollectionJobs(self.connect,client_factory=self.jobs.client_factory)
        page=restored.records('a','works')
        self.assertEqual([r['job_id'] for r in page['records']],['history-22','history-21','history-20'])
        self.assertFalse(page['has_more'])
        self.assertEqual(restored.records('a','works',3)['records'],[])
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_collection_jobs').fetchone()[0],3)

    def test_each_account_category_retains_three_without_deleting_other_batch_items(self):
        first=self.start(('works','profile'),ids=('a','b'),force_works=True)
        with self.connect() as c:
            ops.cache(c,'u','sentinel',{'saved_business_data':17},ops.stamp());c.commit()
        for _ in range(3):self.start(('works',),force_works=True)
        self.assertEqual(len(self.jobs.records('a','works')['records']),3)
        self.assertEqual([r['job_id'] for r in self.jobs.records('b','works')['records']],[first['id']])
        with self.connect() as c:
            old=json.loads(c.execute('SELECT payload_json FROM v3_collection_jobs WHERE id=?',(first['id'],)).fetchone()[0])
            self.assertNotIn(('a','works'),[(i['account_id'],i['category']) for i in old['items']])
            self.assertIn(('a','profile'),[(i['account_id'],i['category']) for i in old['items']])
            self.assertFalse(any(e.get('account_id')=='a' and e.get('category')=='works' for e in old['events']))
            self.assertEqual(json.loads(c.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='sentinel'").fetchone()[0]),{'saved_business_data':17})

    def test_deleted_attempt_is_not_preserved_in_retry_retained_items(self):
        self.fail='offline'
        first=self.start(('works',),ids=('a','b'),force_works=True)
        self.fail=None
        self.jobs.start({'account_ids':['b']},retry=True);self.jobs.thread.join(5)
        retry_id=self.jobs.job['id']
        self.assertTrue(self.jobs.job['retained_items'])
        for _ in range(3):self.start(('works',),force_works=True)
        with self.connect() as c:
            retry=json.loads(c.execute('SELECT payload_json FROM v3_collection_jobs WHERE id=?',(retry_id,)).fetchone()[0])
            self.assertEqual(retry['retained_items'],[])
            first_saved=json.loads(c.execute('SELECT payload_json FROM v3_collection_jobs WHERE id=?',(first['id'],)).fetchone()[0])
            self.assertEqual([i['account_id'] for i in first_saved['items']],['b'])

    def test_refresh_login_only_reads_account_list_and_persists_observations(self):
        result=self.jobs.refresh_logins()
        self.assertEqual([n for n,_ in self.calls],['vcat_list_accounts'])
        self.assertIsNone(result['state']['job'])
        account=next(a for a in result['state']['accounts'] if a['id']=='a')
        self.assertEqual(account['login_status'],'登录有效')
        self.assertTrue(account['login_checked_at'])

    def test_refresh_login_failure_keeps_saved_status_and_releases_lock(self):
        with self.connect() as c:
            ops.cache_login_statuses(c,[dict(uid='u',loginStatus='登录失效')]);c.commit()
        from unittest.mock import patch
        with patch.object(self.jobs,'client_factory',side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(ValueError,'原状态已保留'):self.jobs.refresh_logins()
        self.assertEqual(next(a for a in self.jobs.state()['accounts'] if a['id']=='a')['login_status'],'登录失效')
        self.assertTrue(ops.LOCK.acquire(blocking=False));ops.LOCK.release()

    def test_refresh_login_during_collection_does_not_call_source(self):
        self.assertTrue(ops.LOCK.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(ValueError,'等待当前任务'):self.jobs.refresh_logins()
        finally:ops.LOCK.release()
        self.assertEqual(self.calls,[])

    def test_reads_only_selected_accounts_and_category(self):
        job=self.start()
        self.assertEqual(job['state'],'completed'); self.assertEqual(len(job['items']),1)
        self.assertEqual([n for n,_ in self.calls],['vcat_list_accounts','vcat_get_account_stats'])
        self.assertEqual(self.calls[-1][1]['uid'],'u')
        self.assertTrue(any('关注者' in e['message'] for e in job['events']))
    def test_existing_account_check_saves_login_without_extra_remote_calls(self):
        self.start()
        with self.connect() as c:
            self.assertEqual(ops.login_statuses(c)['u']['login_status'], '登录有效')
        self.assertEqual([name for name,_ in self.calls], ['vcat_list_accounts','vcat_get_account_stats'])

    def test_cooldown_skips_works_without_online_request(self):
        with self.connect() as c: ops.cache(c,'u','posts',[],ops.stamp()); c.commit()
        job=self.start(('works',))
        self.assertEqual(job['items'][0]['status'],'skipped'); self.assertNotIn('works',[n for n,_ in self.calls])
    def test_explicit_works_override_and_progress(self):
        with self.connect() as c: ops.cache(c,'u','posts',[],ops.stamp()); c.commit()
        job=self.start(('works',),force_works=True)
        self.assertEqual(job['state'],'completed'); self.assertTrue(any('1 / 1' in e['message'] for e in job['events']))
        with self.connect() as c: self.assertEqual(len(json.loads(c.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts'").fetchone()[0])),1)
    def test_duplicate_reuses_active_job_and_stop_is_cooperative(self):
        self.block=threading.Event()
        first=self.jobs.start({'account_ids':['a','b'],'categories':['profile']})
        self.assertTrue(self.entered.wait(3))
        second=self.jobs.start({'account_ids':['b'],'categories':['works']})
        self.assertTrue(second['reused']); self.assertEqual(first['job']['id'],second['job']['id'])
        self.jobs.stop(first['job']['id']); self.block.set();self.jobs.thread.join(5)
        job=self.jobs.state()['job']; self.assertEqual(job['state'],'stopped')
        self.assertEqual([n for n,_ in self.calls],['vcat_list_accounts'])
        self.assertTrue(all(c['status']=='stopped' for c in job['items']))
    def test_retries_only_failed_pairs(self):
        self.fail='offline'; job=self.start(('works','profile'))
        self.assertEqual(job['state'],'partial')
        # Preserve successful profile and retry only failed works.
        self.jobs.job['items'][0]['status']='success'; self.fail=None; self.calls.clear()
        self.jobs.start({},retry=True); self.jobs.thread.join(5)
        retry=self.jobs.state()['job']; self.assertEqual(len(retry['items']),1)
        self.assertEqual(retry['items'][0]['category'],'works');self.assertEqual(retry['state'],'completed')
    def test_failure_retains_old_post_snapshot(self):
        with self.connect() as c: ops.cache(c,'u','posts',[{'uid':'u','postId':'old'}],ops.stamp());c.commit()
        self.fail='offline';job=self.start(('works',),force_works=True)
        self.assertEqual(job['items'][0]['status'],'failed')
        with self.connect() as c:self.assertEqual(json.loads(c.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts'").fetchone()[0])[0]['postId'],'old')
    def test_access_limit_pauses_daily_and_all_later_accounts(self):
        self.fail='HTTP 429';job=self.start(('daily','works'),('a','b'),force_works=True)
        self.assertEqual(job['state'],'paused'); self.assertFalse(any(args.get('uid')=='v' for _,args in self.calls))
        self.assertEqual(sum(c['status']=='failed' for c in job['items']),1)
    def test_daily_429_does_not_get_swallowed_as_missing(self):
        self.fail='HTTP 403';job=self.start(('daily',),('a','b'))
        self.assertEqual(job['state'],'paused');self.assertEqual([n for n,_ in self.calls],['vcat_list_accounts','vcat_get_account_stats'])
    def test_complete_daily_requires_no_stats_or_refresh_call(self):
        end=date.today()-timedelta(days=1);start=end-timedelta(days=1)
        stats={'dailyCollection':{'boundary':{'rule':'consecutive_zero_days','startDate':str(start)}},'daily':[{'date':str(d),**{k:1 for k in DAILY_FIELDS}} for d in (start,end)]}
        with self.connect() as c: ops.cache(c,'u','stats',stats,ops.stamp());c.commit()
        job=self.start(('daily',));self.assertEqual(job['items'][0]['status'],'skipped');self.assertEqual([n for n,_ in self.calls],['vcat_list_accounts'])
    def test_90_day_fallback_completes_daily_job_and_persists_start_for_repeat(self):
        from datetime import datetime
        end=datetime.now(ops.SH).date()-timedelta(days=1)
        start=end-timedelta(days=62)
        rows=[{'date':str(start+timedelta(days=i)),**{key:1 for key in DAILY_FIELDS}} for i in range(63)]
        with self.connect() as conn:
            ops.cache(conn,'u','stats',{'daily':rows,'dailyCollection':{'state':'partial','boundary':None}},ops.stamp());conn.commit()
        job=self.start(('daily',))
        self.assertEqual(job['state'],'completed');self.assertEqual(job['items'][0]['status'],'success')
        self.assertIn(str(start),job['items'][0]['message'])
        with self.connect() as conn:
            stats=json.loads(conn.execute("SELECT payload_json FROM v3_operations_cache WHERE uid='u' AND kind='stats'").fetchone()[0])
        self.assertEqual(stats['dailyCollection']['boundary']['startDate'],str(start))
        self.assertEqual(stats['dailyCollection']['boundary']['rule'],'lookback_limit')
        self.assertEqual(stats['dailyCollection']['missingDates'],[])
        self.assertTrue(all(args['startDate']>=str(end-timedelta(days=89)) for name,args in self.calls if name=='vcat_get_account_stats'))
        self.calls.clear();repeat=self.start(('daily',))
        self.assertEqual(repeat['items'][0]['status'],'skipped')
        self.assertEqual([name for name,_ in self.calls],['vcat_list_accounts'])

    def test_job_survives_manager_recreation(self):
        first=self.start(); restored=CollectionJobs(self.connect).state()['job']
        self.assertEqual(first['id'],restored['id']);self.assertEqual(restored['state'],'completed')
    def test_interrupted_running_job_can_be_continued(self):
        self.start();self.jobs.job['state']='running'; self.jobs.job['items'][0]['status']='running';self.jobs._save()
        restored=CollectionJobs(self.connect).state()['job'];self.assertEqual(restored['state'],'stopped');self.assertEqual(restored['items'][0]['status'],'stopped')
    def test_invalid_scope_and_settings(self):
        for payload in ({'account_ids':['closed'],'categories':['works']},{'account_ids':['a'],'categories':['not-a-category']},{'account_ids':['a'],'categories':['works'],'page_interval_seconds':0},{'account_ids':['a'],'categories':['works'],'works_cooldown_hours':float('nan')}):
            with self.assertRaises(ValueError):self.jobs.start(payload)
        self.assertEqual(self.calls,[])
    def test_actual_http_routes_use_the_queue_and_validate_scope(self):
        import io
        from unittest.mock import Mock, patch
        from server import v2_file_service as service
        handler=service.Handler.__new__(service.Handler)
        handler.path='/api/v3/operations-dashboard/collection';handler._json=Mock()
        with patch('server.collection_jobs.manager',return_value=self.jobs): handler.do_GET()
        self.assertEqual(handler._json.call_args.args[0],200)
        self.assertEqual(self.calls,[])
        body=json.dumps({'account_ids':['closed'],'categories':['works']}).encode()
        handler.path+='/start';handler.headers={'Content-Length':str(len(body))};handler.rfile=io.BytesIO(body)
        with patch('server.collection_jobs.manager',return_value=self.jobs): handler.do_POST()
        self.assertEqual(handler._json.call_args.args[0],409)
        self.assertEqual(self.calls,[])

    def test_daily_stop_keeps_returned_dates(self):
        owner=self
        class Cat:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def call(self,name,args):
                if name=='vcat_list_accounts':return {'list':[{'uid':'u','loginStatus':'登录有效'}],'total':1}
                if name=='vcat_get_account_stats':
                    owner.jobs.stop(owner.jobs.job['id'])
                    return {'daily':[{'date':args['endDate'],**{k:1 for k in DAILY_FIELDS}}]}
                raise AssertionError('Stop must prevent further calls')
        self.jobs.client_factory=Cat
        job=self.start(('daily',))
        self.assertEqual(job['state'],'stopped')
        with self.connect() as c:
            saved=json.loads(c.execute("SELECT payload_json FROM v3_operations_cache WHERE uid='u' AND kind='stats'").fetchone()[0])
            self.assertEqual(len(saved['daily']),1)
            self.assertEqual(saved['daily'][0]['view'],1)

    def test_complete_day_repairs_partial_metadata_without_network(self):
        end=(__import__('datetime').datetime.now(ops.SH).date()-timedelta(days=1)).isoformat()
        with self.connect() as c:
            ops.cache(c,'u','stats',{'dailyCollection':{'state':'partial','boundary':{'rule':'consecutive_zero_days','startDate':end}},'daily':[{'date':end,**{k:0 for k in DAILY_FIELDS}}]},ops.stamp());c.commit()
        self.start(('daily',))
        self.assertEqual(next(a for a in self.jobs.state()['accounts'] if a['id']=='a')['daily_through'],end)
        self.assertEqual([n for n,_ in self.calls],['vcat_list_accounts'])

    def test_online_page_progress_and_cancellation_before_next_request(self):
        from server.publishing.online_posts import read_online_posts,PagePacer
        from server.collection_progress import CollectionStopped
        from server.tests.test_online_posts import Client,page,Clock
        clock=Clock();cat=Client([page(['p'],total=2,more=True,cursor={'page':2}),page(['q'],total=2)])
        messages=[];stop=[False]
        def progress(message):
            messages.append(message)
            if '1 / 2' in message:stop[0]=True
        with self.assertRaises(CollectionStopped):
            read_online_posts(cat,'u',pacer=PagePacer(sleeper=clock.sleep,clock=clock.clock),progress=progress,should_stop=lambda:stop[0])
        self.assertEqual(len(cat.requests),1);self.assertTrue(any('第 1 页' in m for m in messages))

    def test_page_wait_stop_is_responsive_and_prevents_request(self):
        from server.publishing.online_posts import PagePacer
        from server.collection_progress import CollectionStopped
        waits=[];stop=[False];requested=[]
        def sleep(value): waits.append(value);stop[0]=True
        gate=PagePacer(sleeper=sleep,clock=lambda:0,uniform=lambda a,b:b)
        gate.last_finished=0
        with self.assertRaises(CollectionStopped):gate.run(lambda:requested.append(True),60,should_stop=lambda:stop[0])
        self.assertEqual(requested,[]);self.assertEqual(waits,[.2])

    def test_status_read_never_connects_to_xiaovcat(self):
        state=self.jobs.state();self.assertEqual(len(state['accounts']),3);self.assertEqual(self.calls,[]);self.assertFalse(next(a for a in state['accounts'] if a['id']=='closed')['available'])

    def test_retry_scope_only_retries_selected_failed_account(self):
        self.fail = 'offline'
        self.start(('works',), ('a', 'b'))
        self.fail = None
        self.calls.clear()
        self.jobs.start({'account_ids': ['b']}, retry=True)
        self.jobs.thread.join(5)
        job = self.jobs.state()['job']
        self.assertEqual({item['account_id'] for item in job['items']}, {'b'})
        self.assertEqual([args['uid'] for name, args in self.calls if name == 'works'], ['v'])
        self.assertEqual(job['state'], 'partial')
        self.assertEqual([(item['account_id'], item['status']) for item in job['retained_items']], [('a', 'failed')])

    def test_separate_retries_keep_pending_accounts_across_reload(self):
        self.fail = 'offline'
        self.start(('works',), ('a', 'b'))
        self.fail = None
        self.jobs.start({'account_ids': ['b']}, retry=True)
        self.jobs.thread.join(5)
        self.calls.clear()
        reloaded = CollectionJobs(self.connect, client_factory=self.jobs.client_factory, media_cache=self.jobs.media_cache)
        reloaded.start({'account_ids': ['a']}, retry=True)
        reloaded.thread.join(5)
        job = reloaded.state()['job']
        self.assertEqual(job['state'], 'completed')
        self.assertEqual([args['uid'] for name, args in self.calls if name == 'works'], ['u'])
        self.assertEqual([(item['account_id'], item['status']) for item in job['retained_items']], [('b', 'success')])

    def test_retry_scope_rejects_invalid_or_completed_selection(self):
        self.fail = 'offline'
        self.start(('works',))
        for selection in ([], ['unknown'], 'a'):
            with self.assertRaises(ValueError):
                self.jobs.start({'account_ids': selection}, retry=True)
        with self.assertRaises(ValueError):
            self.jobs.start({'account_ids': ['b']}, retry=True)

    def test_catalog_exposes_real_totals_and_daily_gaps_without_external_reads(self):
        with self.connect() as conn:
            ops.cache(conn, 'u', 'stats', {'total': {'postCount': 0, 'fans': 9, 'updateTime': '2026-11-02 20:00:00'}, 'dailyCollection': {'state': 'partial', 'missingDates': ['2026-11-02']}}, ops.stamp())
            conn.commit()
        row = next(a for a in self.jobs.state()['accounts'] if a['id'] == 'a')
        self.assertEqual(row['profile_total'], {'postCount': 0, 'fans': 9})
        self.assertEqual(row['profile_source_time'], '2026-11-02 20:00:00')
        self.assertEqual(row['daily_missing_dates'], ['2026-11-02'])
        self.assertEqual(row['daily_state'], 'partial')
        self.assertEqual(self.calls, [])

    def test_daily_reset_scope_refreshes_complete_account_without_touching_other_categories(self):
        end = (__import__('datetime').datetime.now(ops.SH).date()-timedelta(days=1)).isoformat()
        with self.connect() as conn:
            ops.cache(conn, 'u', 'stats', {'daily': [{'date':end, **{key:1 for key in DAILY_FIELDS}}], 'dailyCollection': {'state':'complete', 'boundary':{'rule':'consecutive_zero_days','startDate':end}}}, ops.stamp())
            conn.commit()
        job = self.start(('daily',), scope_version=1, scope={'daily': {'mode':'reset_online'}})
        self.assertEqual(job['options']['scope']['daily']['mode'], 'reset_online')
        self.assertEqual([name for name, _ in self.calls][:2], ['vcat_list_accounts', 'vcat_refresh_account_stats'])
        self.assertFalse(any(name == 'works' for name, _ in self.calls))
        self.assertTrue(all(args.get('uid', 'u') == 'u' for name, args in self.calls))
        self.calls.clear()
        self.jobs.start({}, retry=True)
        self.jobs.thread.join(5)
        self.assertEqual(self.jobs.job['options']['scope']['daily']['mode'], 'reset_online')
        self.assertEqual(sum(name == 'vcat_refresh_account_stats' for name, _ in self.calls), 1)

    def test_rejects_unsupported_scope_before_any_requests(self):
        for extra in [
            {'scope_version':1, 'scope':{'daily':{'mode':'force_range','start_date':'2026-01-01'}}},
            {'scope_version':1, 'scope':{'works':{'mode':'all'}}},
            {'scope_version':True, 'scope':{'daily':{'mode':'reset_online'}}},
            {'scope':{'daily':{'mode':'reset_online'}}},
        ]:
            with self.assertRaises(ValueError):
                self.jobs.start({'account_ids':['a'],'categories':['daily'], **extra})
        self.assertEqual(self.calls, [])
        self.assertTrue(self.jobs.state()['capabilities']['daily_reset_online'])

    def install_range_source(self):
        from server.tests.test_online_posts import dated, dated_page
        from server.publishing.online_posts import read_online_posts, PagePacer
        owner=self
        self.range_pages=[dated_page([dated('new','2026-11-02',view=99),dated('week','2026-10-28',view=50),dated('older','2026-10-25',view=10)],total=10,more=True,cursor={'page':2}),dated_page([dated('two_weeks','2026-10-21',view=5),dated('old','2026-10-19',view=1)],total=10,more=True,cursor={'page':3})]
        class RangeClient(self.jobs.client_factory):
            account_data=True
            def online_account_posts(self,uid,**kwargs):
                owner.calls.append(('range', {'uid':uid, **{k:v for k,v in kwargs.items() if k.startswith('published_')}}))
                return read_online_posts(self,uid,pacer=PagePacer(sleeper=lambda t:None,uniform=lambda a,b:0),**kwargs)
            def _online_posts_page(self,uid,params):
                index=params.get('page',1)-1
                owner.calls.append(('range_page', {'uid':uid,'page':index+1}))
                response=owner.range_pages[index]
                if isinstance(response,Exception):raise response
                return response
        self.jobs.client_factory=RangeClient

    def range_options(self,start='2026-10-28',end='2026-11-03'):
        return {'scope_version':1,'scope':{'works':{'mode':'published_range','start_date':start,'end_date':end}}}

    def test_range_only_updates_included_works_preserves_old_rows_and_per_work_observation(self):
        from server.tests.test_online_posts import dated
        old=dated('old','2026-01-01',view=777,observedAt='2026-10-01T00:00:00Z',coverLocalId='old-cover',videoUrl='old-link')
        with self.connect() as conn:
            ops.cache(conn,'u','posts',[old,dated('new','2026-11-02',view=1)],'2020-01-01T00:00:00+08:00')
            conn.execute("DELETE FROM v3_operations_cache WHERE kind='posts_collection'")  # Legacy cache before scoped collection existed.
            conn.commit()
        self.install_range_source()
        job=self.start(('works',),**self.range_options())
        self.assertEqual(job['state'],'completed')
        self.assertEqual([args['page'] for name,args in self.calls if name=='range_page'],[1])
        with self.connect() as conn:
            rows={row['postId']:row for row in json.loads(conn.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts'").fetchone()[0])}
            meta=json.loads(conn.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts_collection'").fetchone()[0])
        self.assertEqual(set(rows),{'old','new','week'})
        self.assertEqual(rows['new']['view'],99)
        self.assertEqual(rows['old'],old)
        self.assertEqual(meta['fullFetchedAt'],'2020-01-01T00:00:00+08:00')
        self.assertEqual(meta['ranges'][0]['startDate'],'2026-10-28')
        self.assertIn('范围外旧数据保留',job['items'][0]['message'])

    def test_range_cooldown_does_not_skip_larger_range_or_full_collection(self):
        self.install_range_source();self.start(('works',),**self.range_options())
        self.calls.clear();same=self.start(('works',),**self.range_options())
        self.assertEqual(same['items'][0]['status'],'skipped')
        self.assertFalse(any(name=='range_page' for name,_ in self.calls))
        self.calls.clear();wider=self.start(('works',),**self.range_options('2026-10-21'))
        self.assertEqual(wider['state'],'completed')
        self.assertEqual([args['page'] for name,args in self.calls if name=='range_page'],[1,2])
        # A full task cannot be skipped using the timestamp of a recent partial range.
        self.jobs.client_factory=self.jobs.client_factory.__bases__[0]
        self.calls.clear();full=self.start(('works',))
        self.assertEqual(full['state'],'completed')
        self.assertTrue(any(name=='works' for name,_ in self.calls))

    def test_forced_range_bypasses_recent_coverage_without_changing_scope_or_interval(self):
        self.install_range_source()
        self.start(('works',), **self.range_options())
        self.calls.clear()
        skipped = self.start(('works',), **self.range_options())
        self.assertEqual(skipped['items'][0]['status'], 'skipped')
        self.assertFalse(any(name == 'range' for name, _ in self.calls))
        self.calls.clear()
        forced = self.start(('works',), force_works=True, page_interval_seconds=4, **self.range_options())
        self.assertEqual(forced['items'][0]['status'], 'success')
        self.assertEqual(forced['options']['scope'], skipped['options']['scope'])
        self.assertEqual(forced['options']['page_interval_seconds'], 4)
        self.assertEqual(forced['options']['works_cooldown_hours'], 1)
        self.assertTrue(any(name == 'range' for name, _ in self.calls))
        self.assertEqual([args['page'] for name, args in self.calls if name == 'range_page'], [1])

    def test_full_snapshot_covers_recent_range_but_first_range_is_not_full_snapshot(self):
        self.start(('works',))
        self.install_range_source();self.calls.clear()
        skipped=self.start(('works',),**self.range_options())
        self.assertEqual(skipped['items'][0]['status'],'skipped')
        self.assertFalse(any(name=='range_page' for name,_ in self.calls))

    def test_range_failure_saves_neither_subset_nor_false_coverage_and_retry_keeps_scope(self):
        from server.tests.test_online_posts import dated
        old=dated('old','2020-01-01',view=44)
        with self.connect() as conn:ops.cache(conn,'u','posts',[old],'2020-01-01T00:00:00+08:00');conn.commit()
        self.install_range_source();second=self.range_pages[1];self.range_pages[1]=RuntimeError('offline')
        failed=self.start(('works',),**self.range_options('2026-10-21'))
        self.assertEqual(failed['state'],'partial')
        with self.connect() as conn:
            self.assertEqual(json.loads(conn.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts'").fetchone()[0]),[old])
            self.assertEqual(json.loads(conn.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts_collection'").fetchone()[0])['ranges'],[])
        self.range_pages[1]=second;self.calls.clear()
        self.jobs.start({'account_ids':['a']},retry=True);self.jobs.thread.join(5)
        self.assertEqual(self.jobs.job['options']['scope'],failed['options']['scope'])
        self.assertEqual(self.jobs.job['state'],'completed')
        self.assertTrue(all(args['published_start']=='2026-10-21' for name,args in self.calls if name=='range'))

    def test_range_validation_rejects_invalid_dates_or_extra_fields_before_network(self):
        for scope in [
            {'mode':'published_range','start_date':'2026-02-30','end_date':'2026-03-01'},
            {'mode':'published_range','start_date':'2026-11-03','end_date':'2026-11-02'},
            {'mode':'published_range','start_date':'2026-11-01','end_date':'2999-01-01'},
            {'mode':'published_range','start_date':'2026-11-01'},
            {'mode':'all','start_date':'2026-11-01'},
        ]:
            with self.assertRaises(ValueError):self.jobs.start({'account_ids':['a'],'categories':['works'],'scope_version':1,'scope':{'works':scope}})
        self.assertEqual(self.calls,[])
        self.assertTrue(self.jobs.state()['capabilities']['works_publication_range'])

    def test_stopping_range_before_boundary_does_not_save_incomplete_subset(self):
        from server.tests.test_online_posts import dated
        old=dated('old','2020-01-01',view=44)
        with self.connect() as conn:ops.cache(conn,'u','posts',[old],'2020-01-01T00:00:00+08:00');conn.commit()
        self.install_range_source();owner=self
        class StopClient(self.jobs.client_factory):
            def _online_posts_page(self,uid,params):
                response=super()._online_posts_page(uid,params)
                owner.jobs.stop(owner.jobs.job['id'])
                return response
        self.jobs.client_factory=StopClient
        job=self.start(('works',),**self.range_options('2026-10-21'))
        self.assertEqual(job['state'],'stopped')
        self.assertEqual([args['page'] for name,args in self.calls if name=='range_page'],[1])
        with self.connect() as conn:
            self.assertEqual(json.loads(conn.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts'").fetchone()[0]),[old])
            self.assertEqual(json.loads(conn.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts_collection'").fetchone()[0])['ranges'],[])



    def test_automatic_saved_invalid_login_skips_platform_categories_without_connecting(self):
        for status in ('登录失效','未登录','登录过期','已过期','登录无效'):
            with self.connect() as c:
                ops.cache_login_statuses(c,[dict(uid='u',loginStatus=status)]);c.commit()
            self.calls.clear()
            self.jobs.start({'account_ids':['a'],'categories':['profile','daily','works','optimization'],'force_daily':True,'force_optimization':True},source='automatic')
            self.jobs.thread.join(5);self.assertFalse(self.jobs.thread.is_alive());job=self.jobs.state()['job']
            self.assertEqual({i['status'] for i in job['items']},{'skipped'})
            self.assertTrue(all('登录失效' in i['message'] for i in job['items']))
            self.assertEqual(self.calls,[])

    def test_login_skip_is_per_account_and_revenue_uses_independent_credentials(self):
        from unittest.mock import patch
        with self.connect() as c:
            ops.cache_login_statuses(c,[dict(uid='u',loginStatus='登录失效')]);c.commit()
        base=self.jobs.client_factory
        class StillInvalid(base):
            def call(self,name,args):
                result=super().call(name,args)
                if name=='vcat_list_accounts':
                    for item in result['list']:
                        if item['uid']=='u':item['loginStatus']='登录失效'
                return result
        self.jobs.client_factory=StillInvalid
        from server.collection_jobs import catalog
        accounts=catalog(self.connect)
        next(a for a in accounts if a['id']=='a')['revenue']=dict(available=True)
        with patch('server.collection_jobs.catalog',return_value=accounts),patch('server.revenue_queue.collect_account',return_value=('success','收益已保存')) as revenue:
            job=self.start(('profile','revenue'),('a','b'))
        states={(i['account_id'],i['category']):i['status'] for i in job['items']}
        self.assertEqual(states['a','profile'],'skipped')
        self.assertEqual(states['a','revenue'],'success')
        self.assertEqual(states['b','profile'],'success')
        self.assertEqual(revenue.call_count,1)
        self.assertEqual([args['uid'] for name,args in self.calls if name=='vcat_get_account_stats'],['v'])

    def test_manual_selection_rechecks_stale_invalid_login_and_can_collect(self):
        with self.connect() as c:
            ops.cache_login_statuses(c,[dict(uid='u',loginStatus='登录失效')]);c.commit()
        self.assertEqual(self.start()['items'][0]['status'],'success')
        self.assertEqual([name for name,args in self.calls].count('vcat_list_accounts'),1)
        self.assertEqual([args['uid'] for name,args in self.calls if name=='vcat_get_account_stats'],['u'])
        with self.connect() as c:self.assertEqual(ops.login_statuses(c)['u']['login_status'],'登录有效')

    def test_revenue_only_ignores_all_login_states_and_never_connects_xiao_v(self):
        from unittest.mock import patch
        from server.collection_jobs import catalog
        for status in ('登录失效','未登录','登录有效','登录过期'):
            with self.subTest(status=status):
                with self.connect() as c:
                    ops.cache_login_statuses(c,[dict(uid='u',loginStatus=status)]);c.commit()
                accounts=catalog(self.connect)
                next(a for a in accounts if a['id']=='a')['revenue']=dict(available=True)
                self.calls.clear()
                with patch('server.collection_jobs.catalog',return_value=accounts),patch('server.revenue_queue.collect_account',return_value=('success','收益已保存')) as revenue:
                    job=self.start(('revenue',))
                self.assertEqual(job['items'][0]['status'],'success')
                self.assertEqual(revenue.call_count,1)
                self.assertEqual(self.calls,[])


if __name__=='__main__': unittest.main()
