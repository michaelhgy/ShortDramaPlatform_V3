"""Financial collection rules checked against isolated V3 databases."""
import json
from contextlib import closing
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service
from server import v2_revenue_service as revenue
from server import revenue_collection_state as state
from server.operations_dashboard import dashboard_data

D = revenue.Decimal


class RevenueCollectionRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in [('WORKSPACE',root/'workspace'),('DATA_ROOT',root/'system-data'),('DATABASE_INITIALIZED_PATH',None)]:
            obj = patch.object(service,name,value)
            obj.start()
            self.addCleanup(obj.stop)
        self.conn = service.connection()
        self.addCleanup(self.conn.close)
        for key,name in [('q','青柠剧场'),('t','触摸剧场')]:
            self.conn.execute("INSERT INTO theaters(id,name,created_at,updated_at) VALUES(?,?,?,?)",(key,name,'2026-08-01','2026-08-01'))
            self.conn.execute("INSERT INTO accounts(id,nickname,channel_id,theater_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",(key,name,key,key,'2026-08-01','2026-08-01'))
            collector = 'qingning' if key == 'q' else 'touch'
            revenue.collectors.set_theater(self.conn, key, [collector])
            revenue.collectors.set_account(self.conn, key, key, collector)
        self.conn.commit()
        self.conn.execute('PRAGMA foreign_keys=ON')

    def touch(self, amount, day=29, month=8, skip=True):
        with patch.object(revenue,'fetch_touch_latest',return_value=('success',D(amount),'')) as fetch:
            result = revenue.collect_supported_theaters(self.conn,'2026-08-28','2026-08-28',['触摸剧场'],
                skip_completed=skip,collected_at=datetime(2026,month,day,10))
        return result,fetch.call_count

    def qingning(self, fetch, **options):
        with patch.object(revenue,'fetch_qingning_day_details',side_effect=fetch):
            return revenue.collect_qingning(self.conn,'2026-08-28','2026-08-28',
                skip_completed=True,initial_backfill=True,**options)

    def test_interrupted_first_collection_resumes_without_requerying_saved_day(self):
        def interrupt(item):
            if item['status'] == 'success':
                raise RuntimeError('模拟进程中断')
        with self.assertRaisesRegex(RuntimeError,'中断'):
            self.qingning(lambda *_:(D('12'),[]),progress_callback=interrupt)
        self.conn.close()
        self.conn = service.connection()  # durable state, not a process-local cursor
        self.addCleanup(self.conn.close)
        calls = []
        def fetch(_,day):
            calls.append(day)
            return None,[]
        result = self.qingning(fetch)
        self.assertEqual(7,len(calls))
        self.assertNotIn('2026-08-28',calls)
        self.assertTrue(result['backfills'][0]['complete'])

    def test_failure_breaks_empty_streak_and_keeps_history_retryable(self):
        calls = []
        def fetch(_,day):
            calls.append(day)
            if len(calls)==3:
                raise RuntimeError('网络失败')
            return D('0'),[]
        first = self.qingning(fetch)
        self.assertEqual(10,len(calls))
        self.assertFalse(first['backfills'][0]['complete'])
        calls.clear()
        second = self.qingning(lambda _,day:(calls.append(day) or D('0'),[]))
        self.assertEqual(['2026-08-26'],calls)
        self.assertTrue(second['backfills'][0]['complete'])

    def test_read_budget_pauses_instead_of_marking_first_history_complete(self):
        fetch = lambda *_:(None,[])
        self.assertFalse(self.qingning(fetch,max_initial_days=3)['backfills'][0]['complete'])
        self.assertFalse(self.qingning(fetch,max_initial_days=3)['backfills'][0]['complete'])
        third = self.qingning(fetch,max_initial_days=3)
        self.assertTrue(third['backfills'][0]['complete'])
        self.assertEqual(1,len(third['items']))
        self.assertEqual(0,self.conn.execute('SELECT count(*) FROM v2_daily_revenues').fetchone()[0])

    def test_simulated_attempt_does_not_block_real_collection(self):
        self.conn.execute("""INSERT INTO v2_revenue_collection_attempts
            (id,request_id,account_id,theater_id,adapter_key,revenue_date,collection_status,amount,collected_at)
            VALUES('fake','fake','q','q','development_seed','2026-08-28','success','999','2026-08-29')""")
        self.conn.commit()
        with patch.object(revenue,'fetch_qingning_day_details',return_value=(D('3'),[])) as fetch:
            revenue.collect_qingning(self.conn,'2026-08-28','2026-08-28',skip_completed=True)
        self.assertEqual(1,fetch.call_count)
        self.assertEqual('3.00',self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])

    def test_cumulative_first_delta_gap_and_dashboard_share_dates(self):
        self.touch('100')
        result,_ = self.touch('130',day=31)
        self.assertEqual('2026-08-31',result['items'][0]['date'])
        self.assertEqual('30.00',result['items'][0]['amount'])
        rows = list(self.conn.execute("SELECT revenue_date,amount FROM v2_daily_revenues ORDER BY revenue_date"))
        self.assertEqual([('2026-08-29','100.00'),('2026-08-31','30.00')],[tuple(r) for r in rows])
        data = dashboard_data(service.connection)
        self.assertEqual({'2026-08-29':'100.00','2026-08-31':'30.00'},
                         {r['period_end']:r['amount'] for r in data['revenue_account_periods']})
        self.assertTrue(all(r['include_in_analysis']==1 for r in data['revenue_account_periods']))
        meta = json.loads(data['revenue_account_periods'][-1]['raw_result_json'])
        self.assertEqual('cumulative_delta',meta['method'])
        self.assertEqual('unknown',meta['source_period'])

    def test_same_day_skip_and_explicit_refresh_never_double_credit(self):
        self.touch('100')
        _,calls = self.touch('130')
        self.assertEqual(0,calls)
        self.touch('130',skip=False)
        self.touch('130',skip=False)
        self.assertEqual('130.00',self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])
        self.assertEqual(1,self.conn.execute('SELECT count(*) FROM v3_revenue_cumulative_snapshots').fetchone()[0])
        result,_ = self.touch('150',day=30)
        self.assertEqual('20.00',result['items'][0]['amount'])

    def test_unknown_cycle_decrease_preserves_last_valid_baseline(self):
        self.touch('100',day=31)
        result,_ = self.touch('5',day=1,month=9)
        self.assertEqual('failed',result['items'][0]['status'])
        self.assertIn('周期',result['items'][0]['message'])
        self.assertEqual(1,self.conn.execute('SELECT count(*) FROM v3_revenue_cumulative_snapshots').fetchone()[0])
        self.assertEqual('100.00',self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])

    def test_verified_monthly_cycle_starts_new_baseline(self):
        spec = dict(revenue.REVENUE_ADAPTERS['触摸剧场'],cumulative_period='month')
        with patch.dict(revenue.REVENUE_ADAPTERS,{'触摸剧场':spec}):
            self.touch('100',day=31)
            result,_ = self.touch('5',day=1,month=9)
        self.assertEqual('5.00',result['items'][0]['amount'])
        self.assertEqual('2026-09',result['items'][0]['source_period'])

    def test_month_query_backfills_three_months_and_aggregates_collection_day(self):
        spec = dict(revenue.REVENUE_ADAPTERS['触摸剧场'],supports_month_query=True)
        calls = []
        def monthly(_,month):
            calls.append(month)
            return 'success',D({'2026-08':'100','2026-07':'50','2026-06':'20'}[month]),''
        with patch.dict(revenue.REVENUE_ADAPTERS,{'触摸剧场':spec}),patch.dict(revenue.MONTHLY_FETCHERS,{'touch':monthly}):
            first,_ = self.touch('999')
            self.assertEqual(['2026-08','2026-07','2026-06'],calls)
            self.assertEqual('170.00',self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])
            calls.clear()
            second,_ = self.touch('999',day=30)
            self.assertEqual(['2026-08'],calls)
            self.assertEqual('0.00',second['items'][0]['amount'])
            self.assertEqual(3,len(first['items']))

    def test_unimplemented_month_query_is_not_faked_by_latest_endpoint(self):
        spec = dict(revenue.REVENUE_ADAPTERS['触摸剧场'],supports_month_query=True)
        with patch.dict(revenue.REVENUE_ADAPTERS,{'触摸剧场':spec}):
            result,calls = self.touch('999')
        self.assertEqual(0,calls)
        self.assertTrue(all(r['status']=='failed' for r in result['items']))
        self.assertEqual(0,self.conn.execute('SELECT count(*) FROM v2_daily_revenues').fetchone()[0])

    def test_invalid_money_and_failed_retry_do_not_erase_success(self):
        self.touch('100')
        for value in ('-1','NaN','Infinity'):
            result,_ = self.touch(value,day=30)
            self.assertEqual('failed',result['items'][0]['status'])
        self.assertEqual('100.00',self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])
        result,_ = self.touch('130',day=30)
        self.assertEqual('30.00',result['items'][0]['amount'])

    def test_failed_accounting_write_rolls_back_cumulative_baseline(self):
        self.touch('100')
        with patch.object(state,'write_day',side_effect=RuntimeError('模拟写入失败')):
            result,_ = self.touch('130',day=30)
        self.assertEqual('failed',result['items'][0]['status'])
        self.assertEqual(1,self.conn.execute('SELECT count(*) FROM v3_revenue_cumulative_snapshots').fetchone()[0])
        self.assertEqual('30.00',self.touch('130',day=30)[0]['items'][0]['amount'])

    def test_initial_normal_run_defaults_to_backfill_and_reuses_active_run(self):
        with patch.object(service.threading,'Thread') as thread:
            run = service.start_revenue_collection('2026-08-28','2026-08-28',theater_names=['青柠剧场'])
            reused = service.start_revenue_collection('2026-08-28','2026-08-28',theater_names=['青柠剧场'])
            self.assertEqual(90,run['total_units'])
            self.assertEqual(run['run_id'],reused['run_id'])
            self.assertTrue(reused['reused'])
            self.assertEqual(1,thread.call_count)
            with patch.object(revenue,'collect_supported_theaters',return_value={'items':[]} ) as collect:
                thread.call_args.kwargs['target']()
            self.assertTrue(collect.call_args.kwargs['initial_backfill'])
            self.assertEqual(run['run_id'],collect.call_args.kwargs['collection_run_id'])

    def test_clock_uses_shanghai_calendar_and_rejects_today_daily_query(self):
        # 16:30 UTC on Aug 28 is Aug 29 in Shanghai.
        with patch.object(revenue,'fetch_touch_latest',return_value=('success',D('12'),'')):
            result = revenue.collect_supported_theaters(self.conn,'2026-08-28','2026-08-28',['触摸剧场'],
                collected_at=datetime(2026,8,28,16,30,tzinfo=timezone.utc))
        self.assertEqual('2026-08-29',result['items'][0]['date'])
        with self.assertRaisesRegex(ValueError,'昨天'):
            revenue.collect_qingning(self.conn,'2026-08-29','2026-08-29',collected_at=datetime(2026,8,29,10))

    def test_new_tables_are_available_on_current_schema_reopen(self):
        self.conn.execute('DROP TABLE v3_revenue_backfills')
        self.conn.execute('DROP TABLE v3_revenue_cumulative_snapshots')
        self.conn.commit()
        service.DATABASE_INITIALIZED_PATH = None  # simulate a process restart on a current schema
        with closing(service.connection()) as reopened:
            self.assertIsNotNone(reopened.execute("SELECT 1 FROM sqlite_master WHERE name='v3_revenue_backfills'").fetchone())

    def test_explicit_empty_account_selection_and_unknown_theater(self):
        with patch.object(revenue,'fetch_qingning_day_details') as fetch:
            result = revenue.collect_qingning(self.conn,'2026-08-28','2026-08-28',account_ids=[])
        self.assertEqual([],result['items'])
        fetch.assert_not_called()
        with self.assertRaisesRegex(ValueError,'尚未实现'):
            revenue.collect_supported_theaters(self.conn,'2026-08-28','2026-08-28',['未知剧场'])

    def test_existing_cumulative_raw_attempt_becomes_baseline_without_recrediting(self):
        self.conn.execute("""INSERT INTO v2_revenue_collection_attempts
            (id,request_id,account_id,theater_id,adapter_key,revenue_date,collection_status,amount,collected_at,data_kind)
            VALUES('old','old','t','t','touch','2026-08-27','success','100','2026-08-28','account_cumulative')""")
        self.conn.commit()
        result,_ = self.touch('130')
        self.assertEqual('30.00',result['items'][0]['amount'])
        self.assertEqual('130.00',self.conn.execute('SELECT raw_amount FROM v3_revenue_cumulative_snapshots').fetchone()[0])

    def test_failed_newer_result_does_not_erase_successful_day_in_dashboard(self):
        with patch.object(revenue,'fetch_qingning_day_details',return_value=(D('12'),[])):
            revenue.collect_qingning(self.conn,'2026-08-28','2026-08-28')
        with patch.object(revenue,'fetch_qingning_day_details',side_effect=RuntimeError('失败')):
            revenue.collect_qingning(self.conn,'2026-08-28','2026-08-28')
        rows = dashboard_data(service.connection)['revenue_account_periods']
        self.assertEqual(1,len(rows))
        self.assertEqual('12.00',rows[0]['amount'])

    def test_scheduler_uses_shanghai_yesterday_for_timezone_aware_clock(self):
        from server import revenue_auto_scheduler as scheduler
        service.update_v2_settings({'revenue_auto_collection_enabled':True,'revenue_auto_collection_times':['00:00']})
        with patch.object(service,'start_revenue_collection',return_value={}) as start:
            scheduler.run_due_auto_collection(datetime(2026,8,31,17,tzinfo=timezone.utc))
        self.assertEqual(('2026-08-31','2026-08-31'),start.call_args.args)

    def test_month_end_final_read_keeps_unfinished_original_months(self):
        spec = dict(revenue.REVENUE_ADAPTERS['触摸剧场'],supports_month_query=True)
        calls = []
        def first(_,month):
            if month=='2026-06':
                return 'failed',None,'暂时失败'
            return 'success',D('100' if month=='2026-08' else '50'),''
        def next_month(_,month):
            calls.append(month)
            return 'success',D({'2026-09':'5','2026-08':'130','2026-07':'50','2026-06':'20'}[month]),''
        with patch.dict(revenue.REVENUE_ADAPTERS,{'触摸剧场':spec}):
            with patch.dict(revenue.MONTHLY_FETCHERS,{'touch':first}):
                old,_ = self.touch('999',day=31)
            self.assertFalse(old['backfills'][0]['complete'])
            with patch.dict(revenue.MONTHLY_FETCHERS,{'touch':next_month}):
                current,_ = self.touch('999',day=1,month=9)
        self.assertEqual(['2026-09','2026-08','2026-06'],calls)
        self.assertTrue(current['backfills'][0]['complete'])
        # September 5 + August final increment 30 + first June 20.
        row = self.conn.execute("SELECT amount FROM v2_daily_revenues WHERE revenue_date='2026-09-01'").fetchone()
        self.assertEqual('55.00',row['amount'])
        meta = json.loads(self.conn.execute("SELECT raw_result_json FROM v3_revenue_account_periods WHERE period_end='2026-09-01'").fetchone()[0])
        self.assertEqual(3,len(meta['components']))
