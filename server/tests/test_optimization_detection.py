import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

from server import operations_collection as ops
from server.collection_jobs import CollectionJobs
from server.optimization_detection import OptimizationDetection
from server.publishing.vcat import VcatClient


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite'
        with closing(self.connect()) as c:
            c.executescript("CREATE TABLE accounts(id TEXT,nickname TEXT,channel_id TEXT,status TEXT); INSERT INTO accounts VALUES('a','甲','u','正常'),('b','乙','v','正常'); CREATE TABLE v3_publish_documents(kind TEXT,key TEXT,content TEXT);")
            ops.initialize(c)
            c.commit()
        self.now = 1800000000
        self.samples = []
        self.calls = []
        self.invalid = set()
        self.fail_refresh = False
        self.fail_detail = False
        self.block = None
        self.entered = threading.Event()
        self.feeds = []
        self.posts = []
        self.publication_when = int(ops.time.time())-86400
        owner = self
        class Client:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def call(self, name, args):
                owner.calls.append((name, dict(args)))
                if name == 'vcat_list_accounts':
                    if owner.block:
                        owner.entered.set()
                        owner.block.wait(5)
                    return {'list': [{'uid': u, 'loginStatus': '登录失效' if u in owner.invalid else '登录有效'} for u in ('u','v')], 'total': 2}
                if name == 'vcat_list_publish_tasks': return {'list': [], 'total': 0}
                if name == 'vcat_get_account_stats': return {'total': {'postCount': 1, 'fans': 5}, 'daily': []}
                raise AssertionError(name)
            def refresh_account_diagnosis(self, uid):
                owner.calls.append(('detect', {'uid': uid}))
                if owner.fail_refresh: raise RuntimeError('source unavailable')
                return {'uid': uid, 'verified': True, 'lastVerifyUnix': 1, 'feeds': [dict(f, uid=uid) for f in owner.feeds]}
            def online_account_posts(self, uid, **kwargs):
                owner.calls.append(('works', {'uid':uid}))
                return owner.posts
            def optimization_detail(self, uid, export_id):
                owner.calls.append(('detail', {'uid': uid, 'export_id': export_id}))
                if owner.fail_detail: raise RuntimeError('detail unavailable')
                return {'reason': '官方分析原文', 'tips': ['建议'], 'feedCreateTime': owner.publication_when}
        self.jobs = CollectionJobs(self.connect, client_factory=Client)
        self.jobs.detection = OptimizationDetection(self.connect, clock=lambda: self.now, uniform=self.uniform)

    def uniform(self, low, high):
        self.samples.append((low, high))
        return (low + high) / 2

    def connect(self):
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def tearDown(self):
        if self.block: self.block.set()
        if self.jobs.thread: self.jobs.thread.join(5)
        self.temp.cleanup()

    def finish(self):
        self.jobs.thread.join(5)
        self.assertFalse(self.jobs.thread.is_alive())
        return self.jobs.state()['job']

    def configure(self, enabled=True):
        return self.jobs.save_detection({'enabled': enabled, 'min_minutes': 50, 'max_minutes': 70})

    def collect(self, **options):
        self.jobs.start({'account_ids': ['a'], 'categories': ['optimization'], **options})
        return self.finish()

    def test_default_off_and_global_enable_schedules_all_available_accounts(self):
        self.assertFalse(self.jobs.state()['optimization_detection']['enabled'])
        self.jobs.tick_detection()
        self.assertEqual(self.calls, [])
        self.configure()
        self.jobs.tick_detection()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.jobs.detection.records()['u']['next_due'], self.now + 3600)
        self.now += 3601
        self.jobs.tick_detection()
        job = self.finish()
        self.assertEqual({i['account_id'] for i in job['items']}, {'a', 'b'})
        self.assertEqual({x[1]['uid'] for x in self.calls if x[0] == 'detect'}, {'u', 'v'})
        self.assertEqual(self.samples[-1], (50, 70))
        self.assertFalse(next(a for a in self.jobs.state()['accounts'] if a['id'] == 'a')['optimization_due'])

    def test_successful_live_detection_records_completion_time_not_account_cache_time(self):
        self.collect(force_optimization=True)
        with closing(self.connect()) as c:
            diag = json.loads(c.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='diagnosis'").fetchone()[0])
        self.assertEqual(diag['sourceTimestampUnix'], 1)
        self.assertGreater(diag['lastVerifyUnix'], 1)
        self.assertEqual(diag['lastVerifyUnix'], int(ops.unix(diag['detectedAt'])))

    def test_manual_bypasses_interval_and_resets_next_automatic_time(self):
        self.configure()
        self.jobs.detect_now({'account_ids': ['a']})
        self.finish()
        previous = self.jobs.detection.records()['u']['next_due']
        self.now += 600
        self.jobs.detect_now({'account_ids': ['a']})
        self.finish()
        row = self.jobs.detection.records()['u']
        self.assertEqual(row['next_due'], previous + 600)
        self.assertTrue(row['last_success'])
        self.assertEqual(len([x for x in self.calls if x[0] == 'detect']), 2)

    def test_duplicate_manual_requests_reuse_inflight_and_skip_invalid_login(self):
        self.invalid.add('v')
        self.block = threading.Event()
        first = self.jobs.detect_now({'account_ids': ['a', 'b']})
        self.assertTrue(self.entered.wait(2))
        second = self.jobs.detect_now({'account_ids': ['a', 'b']})
        self.assertEqual(first['job']['id'], second['job']['id'])
        self.assertFalse(any(r['requested_at'] for r in self.jobs.detection.records().values()))
        self.block.set()
        job = self.finish()
        self.assertEqual([x for x in self.calls if x[0] == 'detect'], [('detect', {'uid': 'u'})])
        self.assertEqual(next(i for i in job['items'] if i['account_id'] == 'b')['status'], 'skipped')
        self.assertFalse(self.jobs.detection.records()['v']['last_success'])
        self.assertIn('登录失效', self.jobs.detection.records()['v']['last_error'])

    def test_manual_waits_behind_another_category_and_duplicates_merge(self):
        self.block = threading.Event()
        first = self.jobs.start({'account_ids': ['a'], 'categories': ['profile']})
        self.assertTrue(self.entered.wait(2))
        self.jobs.detect_now({'account_ids': ['b']})
        self.jobs.detect_now({'account_ids': ['b']})
        self.assertEqual(self.jobs.job['id'], first['job']['id'])
        self.assertEqual(self.jobs.detection.due_ids({'b': {'uid': 'v'}}), ['b'])
        self.block.set()
        self.finish()
        self.jobs.tick_detection()
        job = self.finish()
        self.assertEqual([i['account_id'] for i in job['items']], ['b'])
        self.assertEqual(len([x for x in self.calls if x[0] == 'detect']), 1)

    def test_detection_failure_preserves_previous_snapshot_and_defers_retry(self):
        self.collect()
        with closing(self.connect()) as c:
            before = c.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='diagnosis'").fetchone()[0]
        success = self.jobs.detection.records()['u']['last_success']
        self.now += 3601
        self.fail_refresh = True
        job = self.collect()
        self.assertEqual(job['items'][0]['status'], 'failed')
        self.assertEqual(self.jobs.detection.records()['u']['last_success'], success)
        with closing(self.connect()) as c:
            self.assertEqual(c.execute("SELECT payload_json FROM v3_operations_cache WHERE kind='diagnosis'").fetchone()[0], before)
        count = len(self.calls)
        self.jobs.tick_detection()
        self.assertEqual(len(self.calls), count)

    def test_detail_retry_uses_successful_list_and_survives_later_deletion(self):
        with closing(self.connect()) as c:
            row = {'key': 'k', 'uid': 'u', 'local_id': 'k', 'status': 'success', 'payload': {'scheduleType': 'timing', 'scheduleTime': ops.local_time(self.publication_when)}}
            c.execute('INSERT INTO v3_publish_documents VALUES(?,?,?)', ('publish_execution', 'k', json.dumps({'items': [row]})))
            post = {'uid': 'u', 'postId': 'p', 'publishStatus': 'published', 'scheduleUnix': self.publication_when, 'postUnix': self.publication_when}
            self.posts = [post]
            ops.reconcile(c, {'u': [post]}, {'u': [{'uid': 'u', 'localId': 'k', 'status': '发布成功'}]})
            ops.cache(c, 'u', 'posts', [post], ops.stamp())
            c.commit()
        self.feeds = [{'exportId': 'e', 'publishUnix': self.publication_when, 'punishState': '推荐曝光减少'}]
        self.fail_detail = True
        self.assertEqual(self.collect(force_optimization=True)['state'], 'partial')
        self.fail_detail = False
        self.jobs.start({}, retry=True)
        self.assertEqual(self.finish()['state'], 'completed')
        self.assertEqual(len([x for x in self.calls if x[0] == 'detect']), 1)
        self.assertEqual(len([x for x in self.calls if x[0] == 'detail']), 2)
        self.collect(force_optimization=True)
        self.assertEqual(len([x for x in self.calls if x[0] == 'detail']), 2)
        self.feeds = []
        self.collect(force_optimization=True)
        with closing(self.connect()) as c:
            self.assertEqual(c.execute('SELECT analysis FROM v3_publication_optimizations').fetchone()[0], '官方分析原文')

    def test_invalid_manual_detection_skips_until_local_login_record_restored(self):
        self.collect(force_optimization=True)
        self.invalid.add('u')
        self.assertEqual(self.collect(force_optimization=True)['items'][0]['status'], 'skipped')
        self.invalid.clear()
        self.jobs.refresh_logins()
        self.assertEqual(self.collect(force_optimization=True)['state'], 'completed')
        self.assertEqual(len([c for c in self.calls if c[0] == 'detect']), 2)

    def test_restart_retains_schedule_and_does_not_repeat_successful_detection(self):
        self.configure()
        self.jobs.detect_now({'account_ids': ['a']})
        self.finish()
        restarted = CollectionJobs(self.connect, client_factory=lambda: self.fail('unexpected client'))
        restarted.detection = OptimizationDetection(self.connect, clock=lambda: self.now, uniform=self.uniform)
        self.assertTrue(restarted.state()['optimization_detection']['enabled'])
        self.assertEqual(restarted.detection.records()['u'], self.jobs.detection.records()['u'])
        restarted.tick_detection()
        self.assertIsNone(restarted.thread)

    def test_disabling_prevents_auto_but_preserves_manual_operation(self):
        self.configure()
        self.configure(False)
        self.now += 7200
        self.jobs.tick_detection()
        self.assertEqual(self.calls, [])
        self.jobs.detect_now({'account_ids': ['a']})
        self.assertEqual(self.finish()['state'], 'completed')

    def test_access_limit_pauses_auto_and_discards_queued_requests(self):
        self.configure()
        self.jobs.detection.request(['a'], {'a': {'uid': 'u'}})
        self.jobs.detection.pause()
        self.now += 7200
        self.jobs.tick_detection()
        self.assertEqual(self.calls, [])
        self.assertTrue(self.jobs.state()['optimization_detection']['paused_reason'])
        self.configure()
        self.assertFalse(self.jobs.state()['optimization_detection']['paused_reason'])

    def test_global_schedule_includes_newly_added_accounts_without_reconfiguration(self):
        self.configure()
        with closing(self.connect()) as c:
            c.execute("INSERT INTO accounts VALUES('c','新账号','w','正常')")
            c.commit()
        self.jobs.tick_detection()
        self.assertIn('w', self.jobs.detection.records())
        self.assertEqual(self.jobs.detection.records()['w']['next_due'], self.now + 3600)
        self.assertNotIn('account_ids', self.jobs.state()['optimization_detection'])

    def test_global_settings_can_be_saved_with_no_accounts(self):
        with closing(self.connect()) as c:
            c.execute('DELETE FROM accounts')
            c.commit()
        self.assertTrue(self.configure()['optimization_detection']['enabled'])
        self.jobs.tick_detection()
        self.assertEqual(self.calls, [])

    def test_invalid_settings_do_not_overwrite_saved_configuration(self):
        before = self.configure()
        for data in [{'enabled': True, 'min_minutes': 0, 'max_minutes': 70},
                     {'enabled': True, 'min_minutes': 70, 'max_minutes': 50},
                     {'enabled': True, 'min_minutes': True, 'max_minutes': 70},
                     {'enabled': 'yes', 'min_minutes': 50, 'max_minutes': 70}]:
            with self.assertRaises(ValueError): self.jobs.save_detection(data)
            self.assertEqual(self.jobs.state()['optimization_detection'], before['optimization_detection'])


    def test_automatic_and_queued_detection_ignore_saved_invalid_login_until_local_refresh(self):
        self.configure()
        self.invalid.add('v')
        # A request already queued before the login expired must also be excluded.
        self.jobs.detection.request(['b'],{'b':{'uid':'v'}})
        with closing(self.connect()) as c:
            ops.cache_login_statuses(c,[dict(uid='v',loginStatus='登录失效')]);c.commit()
        self.now+=3601
        self.jobs.tick_detection()
        job=self.finish()
        self.assertEqual([i['account_id'] for i in job['items']],['a'])
        self.assertEqual([args['uid'] for name,args in self.calls if name=='detect'],['u'])
        self.assertFalse(next(a for a in self.jobs.state()['accounts'] if a['id']=='b')['optimization_due'])
        self.calls.clear()
        self.jobs.tick_detection()
        self.jobs.detect_now({'account_ids':['b']})
        self.assertEqual(self.calls,[])
        self.invalid.clear()
        self.jobs.refresh_logins()  # Reads local list only, no online login check.
        self.jobs.tick_detection()
        job=self.finish()
        self.assertEqual([i['account_id'] for i in job['items']],['b'])
        self.assertEqual([args['uid'] for name,args in self.calls if name=='detect'],['v'])


    def test_all_invalid_automatic_accounts_create_no_job_or_source_request(self):
        self.configure()
        with closing(self.connect()) as c:
            ops.cache_login_statuses(c,[dict(uid=u,loginStatus='登录失效') for u in ('u','v')]);c.commit()
        self.now+=3601
        self.jobs.tick_detection()
        self.assertIsNone(self.jobs.job)
        self.assertEqual(self.calls,[])
        with closing(self.connect()) as c:
            exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='v3_collection_jobs'").fetchone()
            if exists:self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_collection_jobs').fetchone()[0],0)


    def test_external_work_is_collected_and_unread_notice_retries_after_recent_list_removal(self):
        self.posts=[{'uid':'u','postId':'external','publishStatus':'published','postUnix':self.publication_when}]
        self.feeds=[{'exportId':'external-notice','publishUnix':self.publication_when}]
        self.fail_detail=True
        self.assertEqual(self.collect(force_optimization=True)['state'],'partial')
        self.fail_detail=False
        self.feeds=[]
        self.assertEqual(self.collect(force_optimization=True)['state'],'completed')
        from server.work_history import dashboard
        with closing(self.connect()) as c:
            history,pending,_=dashboard(c)
            self.assertEqual(len(history),1)
            self.assertFalse(history[0]['software'])
            self.assertEqual(history[0]['optimization_state'],'optimized')
            self.assertEqual(pending,[])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_publication_optimizations').fetchone()[0],0)


class DetectionAdapterTests(unittest.TestCase):
    def test_refresh_requires_account_data_permission_and_uses_only_feed_refresh(self):
        client = VcatClient.__new__(VcatClient)
        client.account_data = False
        client.call = Mock(return_value={'success': True})
        client.account_diagnosis = Mock(return_value={'verified': True, 'feeds': []})
        with self.assertRaises(ValueError): client.refresh_account_diagnosis('u')
        client.call.assert_not_called()
        client.account_data = True
        self.assertEqual(client.refresh_account_diagnosis('u')['feeds'], [])
        client.call.assert_called_once_with('vcat_refresh_account_feeds', {'uid': 'u'})

    def test_refresh_failure_never_relabels_old_diagnosis_as_fresh(self):
        client = VcatClient.__new__(VcatClient)
        client.account_data = True
        client.call = Mock(return_value={'success': False})
        client.account_diagnosis = Mock(return_value={'verified': True, 'feeds': []})
        with self.assertRaises(RuntimeError): client.refresh_account_diagnosis('u')
        client.account_diagnosis.assert_not_called()


