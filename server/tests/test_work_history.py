import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock
from server import operations_collection as ops, work_history as works


class WorkHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'test.sqlite'
        self.at=ops.stamp();self.when=int(time.time())-3600
        self.feed={'uid':'u','exportId':'notice-export','publishUnix':self.when}
        self.post={'uid':'u','postId':'official-id','exportId':'DIFFERENT-work-export','postUnix':self.when,
                   'publishStatus':'published','view':12,'observedAt':self.at,'isSticky':False}
        self.detail={'uid':'u','exportId':'notice-export','feedCreateTime':self.when,'reason':'原创度低','tips':[]}
        with closing(self.connect()) as c:
            c.executescript("CREATE TABLE accounts(id TEXT,channel_id TEXT,status TEXT); INSERT INTO accounts VALUES('a','u','正常'); CREATE TABLE v3_publish_documents(kind TEXT,key TEXT,content TEXT);")
            ops.initialize(c);c.commit()
    def tearDown(self):self.tmp.cleanup()
    def connect(self):
        c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row;return c
    def save(self, posts=None, feed=None, detail=None):
        with closing(self.connect()) as c:
            ops.cache(c,'u','posts',posts if posts is not None else [self.post],self.at)
            ops.cache(c,'u','diagnosis',{'verified':True,'lastVerifyUnix':int(time.time()),'feeds':[feed or self.feed]},self.at)
            works.store_detail(c,'u',feed or self.feed,detail or self.detail,self.at);c.commit()
    def get(self):
        with closing(self.connect()) as c:return works.dashboard(c)
    def test_nonsoftware_notice_matches_without_export_id_equivalence_and_reads_are_pure(self):
        self.save()
        with closing(self.connect()) as c:
            before=c.total_changes
            history,pending,_=works.dashboard(c)
            self.assertEqual(c.total_changes,before)
        self.assertEqual(len(history),1);self.assertEqual(pending,[])
        self.assertFalse(history[0]['software']);self.assertEqual(history[0]['optimization_state'],'optimized')
    def test_deletion_or_hidden_absence_preserves_publication_and_optimization(self):
        self.save();self.save(posts=[])
        history,pending,_=self.get()
        self.assertEqual(len(history),1);self.assertEqual(history[0]['post_id'],'official-id')
        self.assertEqual(history[0]['optimization_state'],'optimized');self.assertEqual(pending,[])
        with closing(self.connect()) as c:
            ops.cache(c,'u','diagnosis',{'verified':True,'lastVerifyUnix':int(time.time()),'feeds':[]},self.at);c.commit()
        self.assertEqual(self.get()[0][0]['optimization_state'],'optimized')
    def test_same_second_multiple_posts_never_guess(self):
        self.save(posts=[self.post,{**self.post,'postId':'another-id'}])
        history,pending,_=self.get()
        self.assertEqual(len(history),2);self.assertEqual(pending[0]['match_state'],'ambiguous')
        self.assertTrue(all(r['optimization_state']=='unknown' for r in history))
    def test_detail_conflicts_and_missing_second_stay_unmatched(self):
        for value in (self.when+1,None):
            with self.subTest(value=value):
                with closing(self.connect()) as c:
                    c.execute('DELETE FROM v3_work_notices');c.commit()
                self.save(detail={**self.detail,'feedCreateTime':value})
                self.assertEqual(len(self.get()[1]),1)
    def test_partial_list_does_not_prove_unique_match(self):
        with closing(self.connect()) as c:
            ops.cache(c,'u','posts',[self.post],self.at,posts_scope={'start_date':'2026-11-01','end_date':'2026-11-05'})
            ops.cache(c,'u','diagnosis',{'feeds':[self.feed]},self.at)
            works.store_detail(c,'u',self.feed,self.detail,self.at);c.commit()
        self.assertEqual(self.get()[1][0]['match_state'],'pending')
    def test_all_notifications_retained_without_works_or_details(self):
        with closing(self.connect()) as c:
            ops.cache(c,'u','diagnosis',{'feeds':[self.feed,{'uid':'u','uniqueId':'missing-export'}]},self.at);c.commit()
        self.assertEqual(len(self.get()[1]),2)
    def test_duplicate_collection_is_idempotent_and_late_collision_revokes_match(self):
        self.save();self.save()
        self.assertEqual(len(self.get()[0]),1)
        self.save(posts=[self.post,{**self.post,'postId':'collision'}])
        self.assertEqual(self.get()[1][0]['match_state'],'ambiguous')
    def enable(self, **changes):
        with closing(self.connect()) as c:
            works.save_settings(c,{'enabled':True,'min_play_count':100,'scope':'all',**changes});c.commit()
    def run_actions(self, posts=None, fresh=True, client=None):
        client=client or Mock()
        client.online_account_posts.return_value=posts if posts is not None else [self.post]
        result=works.process_actions(self.connect,client,'u',posts if posts is not None else [self.post],fresh_detection=fresh)
        return client,result
    def test_default_disabled_and_enabled_requires_positive_threshold(self):
        self.save();client,_=self.run_actions();client.act_on_optimization.assert_not_called()
        with closing(self.connect()) as c:
            for threshold in (None,0,-1,True,1.5,float('nan'),'100'):
                with self.assertRaises(ValueError):works.save_settings(c,{'enabled':True,'min_play_count':threshold})
    def test_threshold_equal_above_missing_stale_or_sticky_are_protected(self):
        self.save();self.enable()
        for patch in ({'view':100},{'view':101},{'view':None},{'view':-1},{'observedAt':'2020-01-01'},
                      {'isSticky':True},{'isSticky':None},{'postUnix':self.when+1},{'uid':'other'}):
            with closing(self.connect()) as c:
                c.execute('DELETE FROM v3_work_history');c.execute('DELETE FROM v3_work_notices');c.commit()
            self.save()
            client,result=self.run_actions(posts=[{**self.post,**patch}]);client.act_on_optimization.assert_not_called()
            self.assertEqual(result['protected'],1)
    def test_software_scope_excludes_external_and_no_replay_of_old_notifications(self):
        self.save();self.enable(scope='software')
        client,_=self.run_actions();client.act_on_optimization.assert_not_called()
        self.enable(scope='all')
        with closing(self.connect()) as c:
            ops.cache(c,'u','diagnosis',{'verified':True,'lastVerifyUnix':int(time.time()),'feeds':[]},self.at);c.commit()
        client,_=self.run_actions();client.act_on_optimization.assert_not_called()
    def test_action_uses_notice_export_id_and_never_retries_unknown_result(self):
        self.save();self.enable()
        client=Mock();client.act_on_optimization.side_effect=RuntimeError('connection lost')
        _,result=self.run_actions(client=client)
        self.assertEqual(result['unknown'],1)
        client.act_on_optimization.assert_called_once_with('u','notice-export','hide')
        self.run_actions(client=client);client.act_on_optimization.assert_called_once()
        self.assertEqual(self.get()[2][0]['state'],'unknown')
    def test_returned_action_remains_submitted_until_platform_verification(self):
        self.save();self.enable(action='delete')
        client,result=self.run_actions()
        self.assertEqual(result['submitted'],1);self.assertEqual(self.get()[2][0]['state'],'submitted')
        self.assertEqual(len(self.get()[0]),1)
    def test_not_fresh_detection_does_not_act(self):
        self.save();self.enable();client,_=self.run_actions(fresh=False);client.act_on_optimization.assert_not_called()
    def test_schema_migration_preserves_cached_history_and_does_not_enable_actions(self):
        self.save()
        with closing(self.connect()) as c:
            c.executescript('DROP TABLE v3_work_history;DROP TABLE v3_work_notices;')
            works.initialize(c);c.commit()
            self.assertFalse(works.settings(c)['enabled'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_work_history').fetchone()[0],1)

    def test_unread_retained_notice_is_retried_after_it_leaves_recent_list(self):
        with closing(self.connect()) as c:
            ops.cache(c,'u','diagnosis',{'feeds':[self.feed]},self.at)
            ops.cache(c,'u','diagnosis',{'feeds':[]},self.at)
            backlog=works.collection_feeds(c,'u',{'feeds':[]})
            self.assertEqual(len(backlog),1)
            self.assertEqual(backlog[0]['exportId'],'notice-export')
            c.commit()

    def test_an_additional_notification_same_second_revokes_automatic_identity(self):
        self.save()
        with closing(self.connect()) as c:
            ops.cache(c,'u','diagnosis',{'feeds':[self.feed,{**self.feed,'exportId':'second-notice'}]},self.at);c.commit()
        self.assertEqual(len(self.get()[1]),2)
        self.assertTrue(all(n['match_state']=='ambiguous' for n in self.get()[1]))

    def test_action_capability_is_narrow_and_off_on_normal_read_connections(self):
        from server.publishing.vcat import VcatClient
        client=VcatClient.__new__(VcatClient)
        client.account_data=True;client.optimization_actions=False;client.writable=False
        client.request=Mock()
        with self.assertRaises(ValueError):client.act_on_optimization('u','e','delete')
        with self.assertRaises(ValueError):client.call('vcat_hide_punish_post',{'uid':'u','exportId':'e'})
        client.request.assert_not_called()
        client.optimization_actions=True
        client.call=Mock(return_value={'success':False})
        with self.assertRaises(RuntimeError):client.act_on_optimization('u','e','hide')
        client.call.assert_called_once_with('vcat_hide_punish_post',{'uid':'u','exportId':'e'})


    def test_play_count_rechecked_per_action_even_if_prior_full_list_was_below_threshold(self):
        self.save();self.enable()
        client=Mock();client.online_account_posts.return_value=[{**self.post,'view':100}]
        result=works.process_actions(self.connect,client,'u',[self.post],fresh_detection=True)
        client.act_on_optimization.assert_not_called()
        self.assertEqual(result['protected'],1)
        self.assertEqual(client.online_account_posts.call_args.kwargs['published_start'],ops.local_time(self.when)[:10])


    def test_real_initializer_upgrades_version12_additively_with_cached_work_preserved(self):
        from server import v2_file_service as service
        from unittest.mock import patch
        root=Path(self.tmp.name)/'migration'
        with patch.object(service,'WORKSPACE',root/'workspace'), patch.object(service,'DATA_ROOT',root/'data'), patch.object(service,'DATABASE_INITIALIZED_PATH',None):
            with closing(service.connection()) as c:
                ops.cache(c,'migration-account','posts',[{**self.post,'uid':'migration-account'}],self.at)
                c.executescript('DROP TABLE v3_work_history; DROP TABLE v3_work_notices; PRAGMA user_version=12;')
                c.commit()
            service.DATABASE_INITIALIZED_PATH=None
            with closing(service.connection()) as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],13)
                self.assertEqual(c.execute("SELECT post_id FROM v3_work_history WHERE uid='migration-account'").fetchone()[0],self.post['postId'])
                self.assertEqual(c.execute("SELECT COUNT(*) FROM v3_operations_cache WHERE uid='migration-account' AND kind='posts'").fetchone()[0],1)
                self.assertFalse(works.settings(c)['enabled'])


    def test_publication_window_defaults_and_custom_values_preserve_existing_settings(self):
        with closing(self.connect()) as c:
            c.execute('INSERT INTO v3_optimization_action_settings VALUES(1,?)',(json.dumps({'enabled':False,'action':'delete','scope':'all','min_play_count':100,'exclude_sticky':False}),))
            self.assertEqual(works.settings(c)['post_publish_hours'],10)
            for invalid in (None,False,0,-1,float('nan'),float('inf'),'10'):
                with self.assertRaises(ValueError):works.save_settings(c,{'post_publish_hours':invalid})
            saved=works.save_settings(c,{'post_publish_hours':1.5})
            self.assertEqual(saved['post_publish_hours'],1.5)
            self.assertEqual(saved['action'],'delete');self.assertFalse(saved['enabled'])
            c.commit()
        with closing(self.connect()) as c:self.assertEqual(works.settings(c)['post_publish_hours'],1.5)

    def set_age(self, seconds, now):
        self.when=now-seconds
        self.post['postUnix']=self.when;self.feed['publishUnix']=self.when;self.detail['feedCreateTime']=self.when

    def test_publication_window_boundary_and_custom_duration(self):
        from unittest.mock import patch
        now=int(time.time())
        for hours,age,expected in ((10,35999,1),(10,36000,1),(10,36001,0),(1.5,5400,1),(1.5,5401,0)):
            with self.subTest(hours=hours,age=age):
                with closing(self.connect()) as c:
                    c.execute('DELETE FROM v3_work_history');c.execute('DELETE FROM v3_work_notices');c.execute('DELETE FROM v3_optimization_action_log');c.commit()
                # Keep the cached verification and action checks on the same clock.
                with patch('server.operations_collection.time.time',return_value=now):
                    self.set_age(age,now);self.save();self.enable(post_publish_hours=hours)
                    client,result=self.run_actions()
                self.assertEqual(client.act_on_optimization.call_count,expected)
                self.assertEqual(result['protected'],1-expected)
                self.assertEqual(len(self.get()[0]),1)

    def test_publication_window_rechecked_after_slow_online_request(self):
        from unittest.mock import patch
        now=int(time.time());clock=[now]
        self.set_age(35999,now);self.save();self.enable(post_publish_hours=10)
        client=Mock()
        def online(*args,**kwargs):clock[0]=now+2;return [self.post]
        client.online_account_posts.side_effect=online
        with patch('server.operations_collection.time.time',side_effect=lambda:clock[0]):
            result=works.process_actions(self.connect,client,'u',[self.post],fresh_detection=True)
        client.act_on_optimization.assert_not_called();self.assertEqual(result['protected'],1)
        self.assertEqual(self.get()[2],[])

    def test_missing_or_future_publication_time_never_sends_action(self):
        from unittest.mock import patch
        now=int(time.time());self.save();self.enable()
        for value in (None,now+1):
            with closing(self.connect()) as c:
                c.execute("UPDATE v3_work_notices SET publish_unix=?,match_state='matched'",(value,));c.commit()
            with patch('server.operations_collection.time.time',return_value=now):client,result=self.run_actions()
            client.act_on_optimization.assert_not_called();client.online_account_posts.assert_not_called()
            self.assertEqual(result['protected'],1)

    def seed_action_records(self, count):
        with closing(self.connect()) as c:
            for i in range(count):
                c.execute('INSERT INTO v3_optimization_action_log VALUES(?,?,?,?,?,?,?,?)',
                    ('u',f'p{i:04d}','notice','hide','submitted','平台状态待核实',self.at,i))
            c.commit()

    def test_records_page_past100_with_stable_snapshot_and_no_mutation(self):
        self.seed_action_records(123)
        with closing(self.connect()) as c:
            before=c.total_changes
            first=works.action_records(c)
            self.assertEqual(c.total_changes,before)
            self.assertEqual((first['total'],first['page_count'],len(first['records'])),(123,13,10))
            self.assertEqual(first['records'][0]['post_id'],'p0122')
            all_ids=[]
            for page in range(1,14):
                data=works.action_records(c,page,snapshot=first['snapshot'])
                all_ids.extend(r['post_id'] for r in data['records'])
            self.assertEqual(len(all_ids),123);self.assertEqual(len(set(all_ids)),123)
            self.assertEqual(all_ids[-1],'p0000')
            c.execute('INSERT INTO v3_optimization_action_log VALUES(?,?,?,?,?,?,?,?)',('u','new','notice','hide','unknown','未确认',self.at,1))
            second=works.action_records(c,2,snapshot=first['snapshot'])
            self.assertEqual(second['total'],123);self.assertEqual(second['records'][0]['post_id'],'p0112')
            refreshed=works.action_records(c)
            self.assertEqual(refreshed['total'],124);self.assertEqual(refreshed['records'][0]['post_id'],'new')
            self.assertEqual(works.action_records(c,999)['page'],13)

    def test_empty_record_page_invalid_parameters_and_long_fields(self):
        with closing(self.connect()) as c:
            data=works.action_records(c)
            self.assertEqual((data['total'],data['page'],data['page_count'],data['records']),(0,1,1,[]))
            for page,size,snapshot in ((0,10,None),(1,0,None),(1,51,None),(True,10,None),(None,10,None),(1,10,-1),(1,10,'10')):
                with self.assertRaises(ValueError):works.action_records(c,page,size,snapshot)
        self.save();self.enable();self.run_actions()
        with closing(self.connect()) as c:
            c.execute('ALTER TABLE accounts ADD COLUMN nickname TEXT')
            c.execute("UPDATE accounts SET nickname='记录核验账号'")
            detail={**self.detail,'reason':'很长的分析原文'*300}
            c.execute('UPDATE v3_work_notices SET detail_json=?',(json.dumps(detail,ensure_ascii=False),))
            record=works.action_records(c)['records'][0]
            self.assertEqual(record['account_name'],'记录核验账号')
            self.assertEqual(record['analysis'],detail['reason']);self.assertEqual(record['publish_time'],ops.local_time(self.when))
            self.assertEqual(record['state'],'submitted')


    def test_action_records_http_route_validates_and_returns_page_without_remote_calls(self):
        from server import v2_file_service as service
        from unittest.mock import patch
        self.seed_action_records(23)
        handler=service.Handler.__new__(service.Handler)
        handler._json=Mock()
        handler.path='/api/v3/operations-dashboard/optimization/actions/records?page=3&page_size=10'
        with patch.object(service,'connection',self.connect):service.Handler.do_GET(handler)
        status,result=handler._json.call_args.args
        self.assertEqual(status,200);self.assertEqual(result['total'],23);self.assertEqual(len(result['records']),3)
        handler._json.reset_mock()
        handler.path='/api/v3/operations-dashboard/optimization/actions/records?page=oops'
        with patch.object(service,'connection',self.connect):service.Handler.do_GET(handler)
        self.assertEqual(handler._json.call_args.args[0],400)


if __name__=='__main__':unittest.main()
