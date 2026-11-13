"""All statuses retain history; live collection eligibility is separate."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from server import account_data, analytics_data, v2_file_service as service, v2_revenue_service as revenue
from server.account_visibility import hide_cancelled_rows
from server.operations_dashboard import dashboard_data
from tools.seed_recent_operations import seed


class AccountVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for key, value in [('WORKSPACE', root/'workspace'), ('DATA_ROOT', root/'data'), ('DATABASE_INITIALIZED_PATH', None)]:
            p = patch.object(service, key, value)
            p.start()
            self.addCleanup(p.stop)
        with closing(service.connection()) as conn:
            seed(conn, date(2026, 10, 31), days=4, account_count=4)
            self.account = dict(conn.execute("SELECT a.* FROM accounts a JOIN theaters t ON t.id=a.theater_id WHERE t.name='青柠剧场' LIMIT 1").fetchone())
            conn.commit()
        self.key = self.account['id']

    def connect(self):
        conn = sqlite3.connect(service.db_path())
        conn.row_factory = sqlite3.Row
        return conn

    def test_management_retains_archive_and_restore_recovers_all_history(self):
        before = dashboard_data(self.connect, allow_legacy_snapshots=True)
        service.update_account(self.key, {'status': '注销'})
        self.assertEqual('注销', service.get_account(self.key)['status'])
        self.assertIn(self.key, [r['id'] for r in service.list_accounts()['items']])
        after = dashboard_data(self.connect, allow_legacy_snapshots=True)
        self.assertIn(self.key, [r['id'] for r in after['accounts']])
        for field in ('video_accounts','video_account_daily','video_posts','video_post_punishments','revenue_account_periods'):
            self.assertEqual(before[field], after[field], field)
        for field in ('periods','queries'):
            self.assertEqual(before['revenue_rating'][field],after['revenue_rating'][field])
        service.update_account(self.key, {'status': '停用'})
        restored = dashboard_data(self.connect, allow_legacy_snapshots=True)
        self.assertEqual(len(before['video_posts']), len(restored['video_posts']))
        self.assertIn(self.key, [r['id'] for r in restored['accounts']])
        new = service.create_account({'nickname':'新注销档案','channel_id':'retired-new','theater_id':self.account['theater_id'],'status':'注销'})
        self.assertEqual('注销', service.get_account(new['id'])['status'])

    def test_foundation_retains_uid_only_cache_counts_and_coverage(self):
        with closing(self.connect()) as conn:
            # Some imported snapshots only have a platform UID, not the local account ID.
            conn.execute('UPDATE v3_video_account_daily SET account_id=\'\' WHERE account_id=?', (self.key,))
            conn.commit()
        before = analytics_data.data_base_overview(self.connect)
        by_source = {source: analytics_data.data_base_overview(self.connect, source_kind=source) for source in ('development_seed','simulation_ui')}
        service.update_account(self.key, {'status':'注销'})
        all_sources = analytics_data.data_base_overview(self.connect)
        self.assertEqual(all_sources['counts']['v3_video_account_daily'], before['counts']['v3_video_account_daily'])
        self.assertTrue(any(r['uid'] == self.account['channel_id'] for r in all_sources['video_account_daily']))
        for source in ('development_seed', 'simulation_ui'):
            data = analytics_data.data_base_overview(self.connect, source_kind=source)
            for field in ('video_accounts','video_account_daily','video_posts','video_post_daily','video_account_diagnostics','video_post_punishments','revenue_account_periods','revenue_details'):
                expected=by_source[source]
                self.assertEqual(expected[field],data[field],field)
            for field, table in [('revenue_period_coverage','v3_revenue_account_periods'),('revenue_detail_coverage','v3_revenue_details')]:
                self.assertEqual(data['counts'][table], sum(r['row_count'] for r in data[field]))

    def test_revenue_reads_retain_cancelled_but_collection_excludes_them(self):
        with closing(self.connect()) as conn:
            revenue.collectors.set_theater(conn,self.account['theater_id'],['qingning'])
            revenue.collectors.set_account(conn,self.key,self.account['theater_id'],'qingning')
            detail = revenue.QingningRow(1, 'retired-video', '测试剧', 100, 200, revenue.Decimal('12.34'))
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('12.34'), [detail])):
                revenue.collect_qingning(conn, '2026-10-31', '2026-10-31', account_ids=[self.key], save_details=True)
            saved = conn.execute('SELECT COUNT(*) FROM v2_daily_revenues').fetchone()[0]
        service.update_account(self.key, {'status':'注销'})
        with closing(self.connect()) as conn:
            data = revenue.revenue_source_data(conn)
            for key in ('rows', 'accounts'):
                self.assertTrue(any(r.get('account_id',r.get('id')) == self.key for r in data[key]))
            for data in (revenue.revenue_daily_account_summary(conn,'2026-10-31'), revenue.revenue_video_details(conn,'2026-10-31','2026-10-31')):
                self.assertTrue(any(r['account_id'] == self.key for r in data['items']))
            self.assertTrue(any(r['account_name'] == self.account['nickname'] for r in revenue.collection_logs(conn)['items']))
            self.assertIsInstance(revenue.revenue_video_candidates(conn,self.key,'retired-video'),dict)
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(None, [])) as fetch:
                revenue.collect_qingning(conn,'2026-10-30','2026-10-30',account_ids=[self.key])
                fetch.assert_not_called()
            self.assertEqual(saved, conn.execute('SELECT COUNT(*) FROM v2_daily_revenues').fetchone()[0])

    def test_snapshot_and_name_only_production_visibility_are_reversible(self):
        with closing(self.connect()) as conn:
            account_data.initialize(conn)
            conn.execute("INSERT INTO v3_account_data_runs(id,data_kind,collection_day,status,created_at) VALUES('run','account_stats','2026-10-31','completed','2026-11-01')")
            account_data._save_snapshot(conn,'run',{'id':'','uid':self.account['channel_id']},'2026-10-31','success',{'view':100})
            conn.commit()
        self.assertEqual(1, len(account_data.overview(self.connect,'2026-10-31')['snapshots']))

        service.update_account(self.key, {'status':'注销'})
        overview = account_data.overview(self.connect,'2026-10-31')
        self.assertEqual(1,len(overview['snapshots']))
        self.assertIn(self.key, [r['id'] for r in overview['accounts']])
        with closing(self.connect()) as conn:
            self.assertNotIn(self.key, [r['id'] for r in account_data._target_accounts(conn,[self.key],[])])
            self.assertEqual(2,len(hide_cancelled_rows(conn,[{'account_name':self.account['nickname']},{'account_name':'未知旧任务'}])))
        service.update_account(self.key, {'status':'正常'})
        self.assertEqual(1, len(account_data.overview(self.connect,'2026-10-31')['snapshots']))

    def test_production_and_task_center_keep_history_and_outputs_after_cancellation(self):
        from server.task_center_service import task_center_snapshot
        artifact = Path(self.temp.name)/'existing-output.mp4'
        artifact.write_bytes(b'preserve-existing-output')
        with closing(self.connect()) as conn:
            conn.execute('''INSERT INTO production_tasks(id,source_id,created_date,account_name,drama_name,
                root_path,material_path,template_path,final_path,created_at,updated_at)
                VALUES('production','source','2026-11-01',?,'测试剧',?,?,?,?,?,?)''',
                (self.account['nickname'],self.temp.name,self.temp.name,self.temp.name,self.temp.name,'2026-11-01','2026-11-01'))
            conn.execute("""INSERT INTO template_jobs(id,task_id,version_no,status,draft_name,seed,created_at,updated_at)
                VALUES('template','production',1,'draft_ready','现有草稿',1,'2026-11-01','2026-11-01')""")
            conn.commit()
        stub = SimpleNamespace(snapshot=lambda:{'jobs':[]})
        with patch('server.ffmpeg_finals.service.get_composer',return_value=stub), patch('server.ffmpeg_templates.service.get_maker',return_value=stub), patch('server.scenery.service.get_library',return_value=stub):
            self.assertIn('production',[r['id'] for r in service.list_tasks()['items']])
            self.assertEqual(1,len(task_center_snapshot()['tasks']))
            service.update_account(self.key,{'status':'注销'})
            self.assertIn('production',[r['id'] for r in service.list_tasks()['items']])
            snapshot = task_center_snapshot()
            self.assertEqual(1,len(snapshot['tasks']))
            self.assertEqual(1,len(snapshot['dramaPriorities']))
            service.update_account(self.key,{'status':'停用'})
            self.assertEqual(1,len(task_center_snapshot()['tasks']))
        with closing(self.connect()) as conn:
            self.assertEqual('draft_ready',conn.execute("SELECT status FROM template_jobs WHERE id='template'").fetchone()[0])
        self.assertEqual(b'preserve-existing-output',artifact.read_bytes())



if __name__ == '__main__':
    unittest.main()
