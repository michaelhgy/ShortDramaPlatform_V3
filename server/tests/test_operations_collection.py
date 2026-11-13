import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from server import operations_collection as ops


class OperationsCollectionTests(unittest.TestCase):
    def setUp(self):
        self.connections=[]; self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'db.sqlite'
        with self.connect() as c:
            c.executescript("CREATE TABLE accounts(id TEXT,channel_id TEXT,status TEXT); INSERT INTO accounts VALUES('a','u','正常'),('b','v','正常'); CREATE TABLE v3_publish_documents(kind TEXT,key TEXT,content TEXT);")
            ops.initialize(c)
    def test_cancelled_accounts_keep_live_cache_history_without_reentering_collection(self):
        from server import work_history
        with self.connect() as c:
            ops.cache(c,'u','stats',{'total':{'postCount':1,'fans':9},'daily':[{'date':'2026-11-05','view':123,'fansNet':2,'like':3,'comment':1}]},'2026-11-06T10:00:00+08:00')
            ops.cache(c,'u','posts',[{'uid':'u','postId':'p','postUnix':1800000000,'publishStatus':'published','view':123}],'2026-11-06T10:00:00+08:00')
            work_history.ingest_posts(c,'u',[{'uid':'u','postId':'p','postUnix':1800000000,'publishStatus':'published'}],'2026-11-06T10:00:00+08:00')
            before=ops.real_dashboard_rows(c)
            before_works=work_history.dashboard(c)[0]
            c.execute("UPDATE accounts SET status='注销' WHERE id='a'")
            self.assertNotIn('u',ops.accounts_by_uid(c))
            self.assertEqual('a',ops.accounts_by_uid(c,include_cancelled=True)['u'])
            self.assertEqual(before,ops.real_dashboard_rows(c))
            self.assertEqual(before_works,work_history.dashboard(c)[0])
            self.assertEqual(1,len(before['video_posts']))
            self.assertEqual(1,len(before_works))

    def tearDown(self):
        for c in self.connections:c.close()
        self.tmp.cleanup()
    def connect(self):
        c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; self.connections.append(c); return c
    def seed(self,c,key='k',uid='u',when=1800000000,mode='timing'):
        row={'key':key,'uid':uid,'local_id':key,'status':'success','payload':{'scheduleType':mode,'scheduleTime':ops.local_time(when)}}
        c.execute('INSERT INTO v3_publish_documents VALUES(?,?,?)',('publish_execution',key,json.dumps({'items':[row]})))
        return row
    def post(self,status='scheduled',uid='u',pid='p',when=1800000000):
        return {'uid':uid,'postId':pid,'publishStatus':status,'scheduleUnix':when,'postUnix':when if status=='published' else when-3600}
    def task(self,key='k',uid='u'):return {'localId':key,'uid':uid,'status':'发布成功'}
    def test_login_checks_only_save_explicit_results_for_linked_accounts(self):
        with self.connect() as c:
            ops.cache_login_statuses(c, [{'uid':'u','loginStatus':'登录有效'}, {'uid':'v','loginStatus':'登录失效'},
                {'uid':'outside','loginStatus':'登录有效'}], '2026-11-03T10:00:00+08:00')
            saved = ops.login_statuses(c)
            self.assertEqual(set(saved), {'u','v'})
            self.assertEqual(saved['u'], {'login_status':'登录有效','login_checked_at':'2026-11-03T10:00:00+08:00'})
            self.assertEqual(saved['v']['login_status'], '登录失效')
            ops.cache_login_statuses(c, [{'uid':'u'}, {'uid':'v','loginStatus':None}], 'later')
            self.assertEqual(ops.login_statuses(c), saved)
            ops.cache_login_statuses(c, [{'uid':'u','loginStatus':'登录失效'}], '2026-11-03T11:00:00+08:00')
            self.assertEqual(ops.login_statuses(c)['u']['login_status'], '登录失效')
            self.assertEqual(ops.login_statuses(c)['u']['login_checked_at'], '2026-11-03T11:00:00+08:00')

    def test_login_reader_tolerates_old_database_and_damaged_observation_without_writing(self):
        with sqlite3.connect(':memory:') as c:
            c.row_factory = sqlite3.Row
            self.assertEqual(ops.login_statuses(c), {})
            self.assertEqual(c.total_changes, 0)
        with self.connect() as c:
            c.execute("INSERT INTO v3_operations_cache VALUES('u','login','broken','now')")
            before = c.total_changes
            self.assertEqual(ops.login_statuses(c), {})
            self.assertEqual(c.total_changes, before)

    def test_scheduled_upload_not_published_and_effective_time_wins(self):
        with self.connect() as c:
            self.seed(c);ops.reconcile(c,{'u':[self.post()]},{'u':[self.task()]})
            r=dict(c.execute('SELECT * FROM v3_publication_history').fetchone())
            self.assertEqual(r['publication_state'],'scheduled');self.assertIsNone(r['publish_unix']);self.assertEqual(r['post_id'],'p')
            ops.reconcile(c,{'u':[self.post('published')]},{'u':[]})
            self.assertEqual(c.execute('SELECT publication_state FROM v3_publication_history').fetchone()[0],'published')
    def test_cleanup_gate_accepts_official_schedule_before_public_release(self):
        with self.connect() as c:
            row = self.seed(c)
            state = {'items': [row]}
            ops.reconcile(c, {'u': [self.post('scheduled')]}, {'u': [self.task()]})
            c.commit()
            self.assertTrue(ops.publication_completion(self.connect, 'k', state)['complete'])
            self.assertIsNone(c.execute('SELECT publish_unix FROM v3_publication_history').fetchone()[0])
            ops.reconcile(c, {'u': [self.post('published')]}, {'u': []})
            c.commit()
            gate = ops.publication_completion(self.connect, 'k', state)
            self.assertTrue(gate['complete'])
            self.assertEqual(1, gate['matched'])
            failed = {'items': [{**row, 'status': 'failed'}]}
            self.assertFalse(ops.publication_completion(self.connect, 'k', failed)['complete'])

    def test_upload_time_and_nearby_minute_are_not_attribution(self):
        with self.connect() as c:
            self.seed(c);p=self.post('published');p['scheduleUnix']=None;p['postUnix']=1800000001
            ops.reconcile(c,{'u':[p]},{'u':[self.task()]})
            self.assertEqual(c.execute('SELECT post_id FROM v3_publication_history').fetchone()[0],'')
    def test_ambiguous_work_or_competing_attempts_excluded(self):
        with self.connect() as c:
            self.seed(c);self.seed(c,'k2')
            ops.reconcile(c,{'u':[self.post()]},{'u':[self.task(),self.task('k2')]})
            self.assertEqual(c.execute("SELECT COUNT(*) FROM v3_publication_history WHERE match_state='ambiguous'").fetchone()[0],2)
    def test_same_post_id_across_accounts_isolated(self):
        with self.connect() as c:
            self.seed(c);self.seed(c,'other','v')
            ops.reconcile(c,{'u':[self.post('published')],'v':[self.post('published','v')]},{'u':[self.task()],'v':[self.task('other','v')]})
            self.assertEqual(c.execute("SELECT COUNT(*) FROM v3_publication_history WHERE publication_state='published'").fetchone()[0],2)
            self.assertEqual(ops.matched_feed(c,{'uid':'v','publishUnix':1800000000})['account_id'],'b')
    def test_deletion_retains_denominator_and_full_analysis_idempotently(self):
        with self.connect() as c:
            self.seed(c);ops.reconcile(c,{'u':[self.post('published')]},{'u':[self.task()]})
            feed={'uid':'u','publishUnix':1800000000,'exportId':'e'};r=ops.matched_feed(c,feed)
            for _ in range(2):ops.store_optimization(c,r,feed,{'reason':'完整分析原文','feedCreateTime':1800000000,'appealType':6},ops.stamp())
            ops.reconcile(c,{'u':[]},{'u':[]})
            history,_=ops.publication_dashboard(c)
            self.assertEqual(len(history),1);self.assertEqual(history[0]['publication_state'],'published')
            self.assertEqual(history[0]['optimization']['analysis'],'完整分析原文');self.assertEqual(history[0]['optimization_state'],'optimized')
    def test_external_feed_or_wrong_seconds_never_matches(self):
        with self.connect() as c:
            self.seed(c);ops.reconcile(c,{'u':[self.post('published')]},{'u':[self.task()]})
            self.assertIsNone(ops.matched_feed(c,{'uid':'v','publishUnix':1800000000}))
            self.assertIsNone(ops.matched_feed(c,{'uid':'u','publishUnix':1800000001}))
            with self.assertRaises(ValueError):ops.store_optimization(c,ops.matched_feed(c,{'uid':'u','publishUnix':1800000000}),{'exportId':'e'},{'reason':'x','feedCreateTime':1800000001},ops.stamp())
    def test_external_work_at_same_second_is_ambiguous(self):
        with self.connect() as c:
            self.seed(c);ops.reconcile(c,{'u':[self.post('published')]},{'u':[self.task()]})
            ops.cache(c,'u','posts',[self.post('published'),self.post('published',pid='outside')],ops.stamp())
            self.assertIsNone(ops.matched_feed(c,{'uid':'u','publishUnix':1800000000}))

    def test_missing_diagnosis_is_unknown_not_zero(self):
        with self.connect() as c:
            self.seed(c);ops.reconcile(c,{'u':[self.post('published')]},{'u':[self.task()]})
            self.assertEqual(ops.publication_dashboard(c)[0][0]['optimization_state'],'unknown')
            ops.cache(c,'u','diagnosis',{'verified':True,'lastVerifyUnix':1800000001,'feeds':[]},ops.stamp())
            self.assertEqual(ops.publication_dashboard(c)[0][0]['optimization_state'],'not_detected')
    def test_missing_analysis_preserves_unknown(self):
        with self.connect() as c:
            self.seed(c);ops.reconcile(c,{'u':[self.post('published')]},{'u':[self.task()]})
            ops.cache(c,'u','diagnosis',{'verified':True,'lastVerifyUnix':1800000001,'feeds':[{'publishUnix':1800000000}]},ops.stamp())
            self.assertEqual(ops.publication_dashboard(c)[0][0]['optimization_state'],'unknown')
    def test_unknown_platform_status_never_becomes_published(self):
        with self.connect() as c:
            self.seed(c);ops.reconcile(c,{'u':[self.post()]},{'u':[self.task()]})
            ops.reconcile(c,{'u':[self.post('unknown')]},{'u':[]})
            self.assertEqual(c.execute('SELECT publication_state FROM v3_publication_history').fetchone()[0],'unconfirmed')
    def test_archived_attempts_restored_and_missing_metrics_not_zero(self):
        with self.connect() as c:
            row=self.seed(c);c.execute('UPDATE v3_publish_documents SET content=?',(json.dumps({'items':[],'previous_items':[row]}),))
            ops.record_executions(c);self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_publication_history').fetchone()[0],1)
            ops.cache(c,'u','stats',{'total':{'postCount':7},'daily':[{'date':'2026-11-01','view':0}]},ops.stamp())
            data=ops.real_dashboard_rows(c)
            self.assertIsNone(data['video_accounts'][0]['fans_total']);self.assertEqual(data['video_accounts'][0]['video_total'],7)
            self.assertEqual(data['video_account_daily'][0]['view'],0);self.assertIsNone(data['video_account_daily'][0]['fans_net'])
    def test_daily_history_accumulates_and_work_observation_uses_source_clock(self):
        with self.connect() as c:
            for date in ['2026-10-25','2026-11-01']:
                ops.cache(c,'u','stats',{'daily':[{'date':date,'view':1}]},ops.stamp())
            ops.cache(c,'u','posts',[{**self.post('published'),'view':1,'observedAt':'2026-11-01T10:00:00Z'}],ops.stamp())
            data=ops.real_dashboard_rows(c)
            self.assertEqual(len(data['video_account_daily']),2)
            self.assertEqual(data['video_posts'][0]['fetched_at'],'2026-11-01T10:00:00Z')

    def test_online_collector_preserves_previous_snapshot_when_any_page_fails(self):
        owner=self
        class Cat:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def online_account_posts(self,uid,**kwargs):raise RuntimeError('second page failed')
            def account_posts(self,uid):raise AssertionError('No local fallback for failed online reads')
            def account_diagnosis(self,uid):return {}
            def call(self,name,args):
                if name=='vcat_list_accounts':return {'list':[{'uid':'u','loginStatus':'登录有效'}],'total':1}
                if name=='vcat_list_publish_tasks':return {'list':[],'total':0}
                if name=='vcat_get_account_stats':return {'daily':[]}
                if name=='vcat_refresh_account_stats':return {'results':[{'uid':'u','success':True}]}
                raise AssertionError('Unexpected tool '+name)
        with self.connect() as c:ops.cache(c,'u','posts',[self.post('published')],'old')
        result=ops.collect_operations(self.connect,Cat,refresh=True,page_interval_seconds=2)
        self.assertTrue(any(e['stage']=='posts' for e in result['errors']))
        with self.connect() as c:
            self.assertEqual(json.loads(c.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='posts'").fetchone()[0])[0]['postId'],'p')

    def test_tracker_binds_before_publication_then_confirms_by_id(self):
        owner=self
        class Cat:
            published=False
            online_calls=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def account_posts(self,uid):
                p=owner.post('published' if self.published else 'scheduled')
                if self.published:p['scheduleUnix']=None
                return [p]
            def online_account_posts(self,uid,**kwargs):
                Cat.online_calls+=1
                return self.account_posts(uid)
            def call(self,name,args):
                if name in ('vcat_get_post_sync','vcat_start_post_sync'):raise AssertionError('Slow sync is forbidden')
                if name=='vcat_list_accounts':return {'list':[{'uid':'u','loginStatus':'登录有效'}],'total':1}
                return {'list':[owner.task()],'total':1}
        with self.connect() as c:self.seed(c)
        self.assertEqual(ops.track_publications_once(self.connect,Cat)['accounts'],1)
        with self.connect() as c:self.assertEqual(c.execute('SELECT publication_state FROM v3_publication_history').fetchone()[0],'scheduled')
        self.assertEqual(ops.track_publications_once(self.connect,Cat)["state"],"waiting_scheduled_time")
        self.assertEqual(Cat.online_calls,1)
        Cat.published=True
        from unittest.mock import patch
        with patch('server.operations_collection.time.time',return_value=1800000001):ops.track_publications_once(self.connect,Cat)
        with self.connect() as c:self.assertEqual(c.execute('SELECT publication_state FROM v3_publication_history').fetchone()[0],'published')

    def test_work_media_survives_publication_record_refresh_and_platform_deletion(self):
        from server.work_media import local_cover_url
        with self.connect() as c:
            self.seed(c)
            post={**self.post('published'),'metricSource':'online_list','coverLocalId':'a'*64,
                  'videoUrl':'https://finder.video.qq.com/v?sign=one','videoDuration':8}
            ops.reconcile(c,{'u':[post]},{'u':[self.task()]})
            ops.cache(c,'u','posts',[post],ops.stamp())
            work=ops.real_dashboard_rows(c)['video_posts'][0]
            self.assertEqual(local_cover_url('a'*64),work['cover_url'])
            self.assertEqual(post['videoUrl'],work['video_url'])
            self.assertEqual(8,work['video_duration'])
            post['videoUrl']='https://finder.video.qq.com/v?sign=two'
            ops.reconcile(c,{'u':[post]},{'u':[]})
            ops.reconcile(c,{'u':[]},{'u':[]})
            meta=json.loads(c.execute('SELECT payload_json FROM v3_publication_history').fetchone()[0])
            self.assertEqual(local_cover_url('a'*64),meta['cover_url'])
            self.assertEqual(post['videoUrl'],meta['video_url'])

    def test_live_collector_uses_injected_client_and_is_idempotent(self):
        owner=self
        when=int(ops.time.time())-86400
        class Cat:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def account_posts(self,uid):return [owner.post('published',when=when)]
            def online_account_posts(self,uid,**kwargs):return [owner.post('published',when=when)]
            def account_diagnosis(self,uid):return {'uid':uid,'verified':True,'lastVerifyUnix':when+1,'feeds':[{'uid':uid,'publishUnix':when,'exportId':'e'}]}
            def call(self,name,args):
                if name=='vcat_list_accounts':return {'list':[{'uid':'u','loginStatus':'登录有效'}],'total':1}
                if name=='vcat_list_publish_tasks':return {'list':[owner.task()],'total':1}
                from server.account_daily_collection import DAILY_FIELDS
                end=ops.datetime.now(ops.SH).date()-ops.timedelta(days=1)
                daily=[{'date':str(end-ops.timedelta(days=i)),**{key:0 for key in DAILY_FIELDS},'view':1 if i==0 else 0} for i in range(8)]
                return {'total':{'postCount':1,'fans':2},'daily':daily}
            def optimization_detail(self,uid,export_id):return {'reason':'完整分析','feedCreateTime':when}
        with self.connect() as c:self.seed(c,when=when)
        for _ in range(2):result=ops.collect_operations(self.connect,Cat,refresh=True)
        self.assertEqual(result['matched_optimizations'],1);self.assertEqual(result['errors'],[])
        with self.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_publication_optimizations').fetchone()[0],1)

if __name__=='__main__':unittest.main()
