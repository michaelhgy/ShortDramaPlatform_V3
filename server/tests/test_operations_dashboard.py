import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service
from server.operations_dashboard import dashboard_data
from tools.seed_recent_operations import seed


class OperationsDashboardTests(unittest.TestCase):
    def setUp(self):
        self.connections = []
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(service, 'WORKSPACE', root / 'workspace'),
                        patch.object(service, 'DATA_ROOT', root / 'system-data'),
                        patch.object(service, 'DATABASE_INITIALIZED_PATH', None)]
        for p in self.patches:
            p.start()
        conn = service.connection()
        try:
            self.result = seed(conn, date(2026, 10, 31), days=10, account_count=8)
            conn.commit()
        finally:
            conn.close()
        self.path = service.db_path()

    def test_dashboard_returns_saved_analysis_mapping_without_altering_notices(self):
        from server import optimization_analysis as analysis
        from server import operations_collection as ops
        with self.connect() as c:
            c.execute("INSERT INTO v3_publish_documents(kind,key,content,updated_at) VALUES('settings',?,?,?)",(analysis.KEY,ops.dump({'version':3,'mappings':[{'analysis':'采集原文','tag':'自由标签'}]}),ops.stamp()))
            c.commit()
        data=dashboard_data(self.connect)
        self.assertEqual(data['optimization_analysis_configuration']['version'],3)
        self.assertEqual(data['optimization_analysis_configuration']['mappings'][0]['tag'],'自由标签')

    def test_runtime_never_falls_back_to_seeded_data_before_first_collection(self):
        data=dashboard_data(self.connect)
        self.assertEqual(data['video_posts'],[])
        self.assertEqual(data['video_account_daily'],[])
        self.assertEqual(data['revenue_account_periods'],[])
        self.assertEqual(data['video_post_punishments'],[])
        self.assertIsNone(data['collection'])

    def test_dashboard_exposes_saved_login_checks_without_a_new_collection(self):
        from server import operations_collection as ops
        with self.connect() as c:
            uid = c.execute("SELECT channel_id FROM accounts WHERE status<>'注销' AND channel_id<>'' LIMIT 1").fetchone()[0]
            ops.cache_login_statuses(c, [{'uid':uid,'loginStatus':'登录失效'}], '2026-11-03T10:00:00+08:00')
            c.commit()
        data = dashboard_data(self.connect)
        account = next(a for a in data['accounts'] if a['channel_id'] == uid)
        self.assertEqual(account['login_status'], '登录失效')
        self.assertEqual(account['login_checked_at'], '2026-11-03T10:00:00+08:00')
        self.assertTrue(all('login_status' not in a for a in data['accounts'] if a['channel_id'] != uid))

    def tearDown(self):
        for conn in self.connections:
            conn.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        self.connections.append(conn)
        return conn

    def test_seed_builds_linked_catalog_and_metrics_without_orphans(self):
        with self.connect() as c:
            self.assertEqual(8, c.execute('SELECT count(*) FROM accounts').fetchone()[0])
            self.assertEqual([], c.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(0, c.execute('SELECT count(*) FROM v3_video_posts p LEFT JOIN accounts a ON a.id=p.account_id WHERE a.id IS NULL').fetchone()[0])
            self.assertEqual(0, c.execute('SELECT count(*) FROM v3_video_post_daily d JOIN v3_video_posts p ON p.post_id=d.post_id WHERE d.stat_date<substr(p.post_time,1,10)').fetchone()[0])
            self.assertEqual(0, c.execute('SELECT count(*) FROM v3_video_posts p WHERE abs(p.view-(SELECT sum(d.view) FROM v3_video_post_daily d WHERE d.post_id=p.post_id))>0.01').fetchone()[0])
            self.assertGreater(c.execute("SELECT count(*) FROM v3_revenue_account_periods WHERE period_type='month_cumulative'").fetchone()[0], 0)

    def test_repeat_seed_does_not_multiply_business_keys(self):
        tables = ['accounts', 'dramas', 'v3_video_account_daily', 'v3_video_posts', 'v3_video_post_daily', 'v3_revenue_account_periods', 'v3_video_post_punishments']
        with self.connect() as c:
            before = {t: c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in tables}
            seed(c, date(2026, 10, 31), days=10, account_count=8)
            after = {t: c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in tables}
        self.assertEqual(before, after)

    def test_reader_combines_sources_and_chooses_latest_daily_fact(self):
        with self.connect() as c:
            row = dict(c.execute('SELECT * FROM v3_video_account_daily LIMIT 1').fetchone())
            row.update(id='later', source_kind='another_source', view=1234567, fetched_at='2099-01-01T00:00:00+08:00')
            columns = list(row)
            c.execute(f"INSERT INTO v3_video_account_daily({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", list(row.values()))
            c.commit()
        data = dashboard_data(self.connect, allow_legacy_snapshots=True)
        matches = [r for r in data['video_account_daily'] if r['account_id']==row['account_id'] and r['stat_date']==row['stat_date']]
        self.assertEqual(1, len(matches))
        self.assertEqual(1234567, matches[0]['view'])
        self.assertEqual('2026-10-31', data['latest_date'])

    def test_dashboard_read_is_query_only_and_does_not_trigger_collection(self):
        def readonly():
            c = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA query_only=ON')
            return c
        data = dashboard_data(readonly, allow_legacy_snapshots=True)
        self.assertEqual(8, len(data['accounts']))
        self.assertGreater(len(data['video_posts']), 50)
        self.assertEqual(80, len(data['video_account_daily']))
        self.assertEqual([], [r for r in data['revenue_account_periods'] if r['period_type']=='month_cumulative' and r['date_precision']=='day'])

    def test_matrix_daily_retains_valid_history_without_changing_latest_failed_report(self):
        with self.connect() as c:
            saved = dict(c.execute("SELECT * FROM v3_video_account_daily WHERE data_state='record' ORDER BY stat_date DESC LIMIT 1").fetchone())
            failed = dict(saved, id='newest-failure', source_kind='failed_source', data_state='failed', view=0, fetched_at='2099-01-01T00:00:00+08:00')
            columns=list(failed)
            c.execute(f"INSERT INTO v3_video_account_daily({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",list(failed.values()))
            c.commit()
        data=dashboard_data(self.connect, allow_legacy_snapshots=True)
        self.assertEqual('failed',next(r for r in data['video_account_daily'] if r['account_id']==saved['account_id'] and r['stat_date']==saved['stat_date'])['data_state'])
        latest=next(r for r in data['account_daily_latest'] if r['account_id']==saved['account_id'])
        self.assertEqual(saved['id'],latest['id']);self.assertEqual(saved['view'],latest['view'])
        with self.connect() as c:
            c.execute("UPDATE accounts SET status='注销' WHERE id=?",(saved['account_id'],));c.commit()
        self.assertTrue(any(r['account_id']==saved['account_id'] for r in dashboard_data(self.connect, allow_legacy_snapshots=True)['account_daily_latest']))

    def test_rating_retains_saved_successful_income_when_latest_attempt_fails(self):
        with self.connect() as c:
            saved=dict(c.execute('''SELECT d.*,a.adapter_key FROM v2_daily_revenues d
                JOIN v2_revenue_collection_attempts a ON a.id=d.source_attempt_id LIMIT 1''').fetchone())
            c.execute('''UPDATE v3_revenue_account_periods SET amount=NULL,data_state='failed',collected_at='2099-01-01T00:00:00+08:00'
                WHERE account_id=? AND period_type='day' AND period_end=?''',(saved['account_id'],saved['revenue_date']))
            attempt=dict(c.execute('SELECT * FROM v2_revenue_collection_attempts WHERE id=?',(saved['source_attempt_id'],)).fetchone())
            attempt.update(id='new-failure',collection_status='failed',amount=None,error_message='fixture failure',collected_at='2099-01-01T00:00:00+08:00')
            columns=list(attempt)
            c.execute(f"INSERT INTO v2_revenue_collection_attempts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",list(attempt.values()))
            c.commit()
        data=dashboard_data(self.connect, allow_legacy_snapshots=True)
        rating=data['revenue_rating']
        recovered=[r for r in rating['periods'] if r['id']=='saved-success:'+saved['id']]
        self.assertEqual(1,len(recovered));self.assertEqual(saved['amount'],recovered[0]['amount'])
        self.assertEqual('failed',next(r for r in rating['queries'] if r['id']=='new-failure')['collection_status'])
        self.assertEqual('failed',next(r for r in data['revenue_account_periods'] if r['account_id']==saved['account_id'] and r['period_end']==saved['revenue_date'])['data_state'])

    def test_rating_recovery_does_not_promote_unverified_legacy_only_days(self):
        with self.connect() as c:
            saved=dict(c.execute('SELECT * FROM v2_daily_revenues LIMIT 1').fetchone())
            attempt=dict(c.execute('SELECT * FROM v2_revenue_collection_attempts WHERE id=?',(saved['source_attempt_id'],)).fetchone())
            attempt.update(id='legacy-attempt',adapter_key='qingning',revenue_date='2020-01-01',amount='99999.00')
            columns=list(attempt)
            c.execute(f"INSERT INTO v2_revenue_collection_attempts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",list(attempt.values()))
            saved.update(id='legacy-daily',revenue_date='2020-01-01',amount='99999.00',source_attempt_id='legacy-attempt')
            columns=list(saved)
            c.execute(f"INSERT INTO v2_daily_revenues({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",list(saved.values()))
            c.commit()
        data=dashboard_data(self.connect, allow_legacy_snapshots=True)
        self.assertFalse(any(r['id']=='saved-success:legacy-daily' for r in data['revenue_rating']['periods']))

    def test_rating_keeps_prior_success_when_new_source_is_pending(self):
        with self.connect() as c:
            prior=dict(c.execute("SELECT * FROM v3_revenue_account_periods WHERE period_type='day' AND CAST(amount AS REAL)>0 LIMIT 1").fetchone())
            pending={**prior,'id':'pending-source','source_kind':'pending-source','amount':'1.00',
                     'collected_at':'2099-01-01T00:00:00+08:00','raw_result_json':'{"income_updated":false}'}
            columns=list(pending)
            c.execute(f"INSERT INTO v3_revenue_account_periods({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",list(pending.values()))
            c.commit()
        data=dashboard_data(self.connect, allow_legacy_snapshots=True)
        facts={r['id']:r for r in data['revenue_rating']['periods']}
        self.assertEqual(prior['amount'],facts[prior['id']]['amount'])
        self.assertEqual('1.00',facts['pending-source']['amount'])

    def test_rating_recovers_saved_success_when_current_zero_is_unconfirmed(self):
        with self.connect() as c:
            saved=dict(c.execute('SELECT * FROM v2_daily_revenues WHERE CAST(amount AS REAL)>0 LIMIT 1').fetchone())
            c.execute('''UPDATE v3_revenue_account_periods SET amount='0.00',raw_result_json='{}',collected_at='2099-01-01T00:00:00+08:00'
                WHERE account_id=? AND period_type='day' AND period_end=?''',(saved['account_id'],saved['revenue_date']))
            c.commit()
        data=dashboard_data(self.connect, allow_legacy_snapshots=True)
        recovered=next(r for r in data['revenue_rating']['periods'] if r['id']=='saved-success:'+saved['id'])
        self.assertEqual(saved['amount'],recovered['amount'])

    def test_latest_rating_query_normalizes_naive_beijing_and_utc_timestamps(self):
        with self.connect() as c:
            row=dict(c.execute('SELECT * FROM v2_revenue_collection_attempts LIMIT 1').fetchone())
            for identity,stamp in [('naive-older','2099-01-01T08:00:00'),('utc-newer','2099-01-01T00:30:00Z')]:
                row.update(id=identity,collected_at=stamp)
                columns=list(row)
                c.execute(f"INSERT INTO v2_revenue_collection_attempts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",list(row.values()))
            c.commit()
        data=dashboard_data(self.connect, allow_legacy_snapshots=True)
        target=next(r for r in data['revenue_rating']['queries'] if r['account_id']==row['account_id'] and r['revenue_date']==row['revenue_date'])
        self.assertEqual('utc-newer',target['id'])

    def test_failed_latest_work_snapshot_preserves_previous_usable_play_count(self):
        with self.connect() as c:
            prior=dict(c.execute("SELECT * FROM v3_video_posts WHERE data_state='record' LIMIT 1").fetchone())
            failed={**prior,'id':'failed-post-snapshot','snapshot_date':'2099-01-01','fetched_at':'2099-01-01T00:00:00+08:00','data_state':'failed','view':0}
            columns=list(failed)
            c.execute(f"INSERT INTO v3_video_posts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",list(failed.values()))
            c.commit()
        result=next(r for r in dashboard_data(self.connect, allow_legacy_snapshots=True)['video_posts'] if r['post_id']==prior['post_id'])
        self.assertEqual(prior['id'],result['id'])
        self.assertEqual(prior['view'],result['view'])
        self.assertEqual(prior['fetched_at'],result['fetched_at'])
