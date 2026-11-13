"""Unified revenue entry against isolated SQLite and stubbed theater responses."""
from contextlib import closing
from datetime import datetime
from decimal import Decimal
import unittest
from unittest.mock import patch

from server import v2_file_service as service
from server import v2_revenue_service as revenue
from server import revenue_collection_state as state
from server import revenue_queue
from server.collection_jobs import CollectionJobs
from server.tests import test_revenue_collection_rules as fixtures


class UnifiedRevenueTests(unittest.TestCase):
    setUp = fixtures.RevenueCollectionRulesTests.setUp

    def jobs(self):
        def forbidden():
            raise AssertionError('收益任务不得连接小V猫')
        jobs = CollectionJobs(service.connection, client_factory=forbidden)
        self.addCleanup(lambda: jobs.thread and jobs.thread.join(5))
        return jobs

    def run_job(self, jobs, **payload):
        request=dict(account_ids=['q'],categories=['revenue'],scope_version=1,scope={'revenue':{'mode':'routine'}})
        request.update(payload)
        job = jobs.start(request)['job']
        jobs.thread.join(10)
        self.assertFalse(jobs.thread.is_alive())
        return jobs.state()['job']

    def test_dinghao_empty_stops_history_but_recent_days_wait_for_recheck(self):
        revenue.collectors.set_theater(self.conn,'q',['dinghao'])
        revenue.collectors.set_account(self.conn,'q','q','dinghao')
        self.conn.commit()
        moment=datetime(2026,11,5,12,tzinfo=state.SHANGHAI)
        with patch.object(state,'clock',return_value=moment), patch.object(revenue,'_post_json',return_value={'status_code':1,'data':{'amount':'0.00'}}) as fetch:
            outcome={}
            first=revenue_queue.collect_account(service.connection,'q',lambda _:None,lambda:False,outcome=outcome)
            second=revenue_queue.collect_account(service.connection,'q',lambda _:None,lambda:False)
        self.assertEqual('partial',first[0]);self.assertEqual('skipped',second[0])
        self.assertEqual(7,fetch.call_count)
        self.assertEqual(7,outcome['empty_days']);self.assertFalse(outcome['history_pending'])
        self.assertEqual('0.00',outcome['saved_amount'])
        self.assertFalse(self.conn.execute('SELECT 1 FROM v2_daily_revenues WHERE account_id=?',('q',)).fetchone())

    def test_resumed_history_does_not_query_newer_failed_day_twice_in_one_run(self):
        with patch.object(revenue,'fetch_qingning_day_details',return_value=(Decimal('12'),[])):
            revenue.collect_qingning(self.conn,'2026-11-02','2026-11-02',skip_completed=True,
                initial_backfill=True,max_initial_days=1,collected_at=datetime(2026,11,3,12))
        days=[]
        def fetch(_,day):
            days.append(day)
            if day=='2026-11-04':raise RuntimeError('临时网络失败')
            return None,[]
        with patch.object(state,'clock',return_value=datetime(2026,11,5,12,tzinfo=state.SHANGHAI)), patch.object(revenue,'fetch_qingning_day_details',side_effect=fetch):
            outcome={}
            status,_=revenue_queue.collect_account(service.connection,'q',lambda _:None,lambda:False,outcome=outcome)
        self.assertEqual('partial',status)
        self.assertEqual(len(days),len(set(days)))
        self.assertEqual(1,days.count('2026-11-04'))
        self.assertEqual(1,outcome['failed_days'])
        self.assertEqual('missing',revenue_queue.account_states(self.conn,'2026-11-04')['q']['state'])

    def test_all_failed_requests_are_reported_as_failed_not_partial_success(self):
        with patch.object(revenue,'_fetch',return_value=('failed',None,'网络失败',[])):
            outcome={}
            status,_=revenue_queue.collect_account(service.connection,'q',lambda _:None,lambda:False,outcome=outcome)
        self.assertEqual('failed',status)
        self.assertEqual(90,outcome['failed_days'])
        self.assertEqual(0,outcome['saved_days'])

    def test_cumulative_record_distinguishes_raw_total_from_credited_amount(self):
        with patch.object(state,'clock',return_value=datetime(2026,11,3,12,tzinfo=state.SHANGHAI)),patch.object(revenue,'fetch_touch_latest',return_value=('success',Decimal('100'),'')):
            revenue_queue.collect_account(service.connection,'t',lambda _:None,lambda:False)
        with patch.object(state,'clock',return_value=datetime(2026,11,5,12,tzinfo=state.SHANGHAI)),patch.object(revenue,'fetch_touch_latest',return_value=('success',Decimal('130'),'')):
            outcome={}
            revenue_queue.collect_account(service.connection,'t',lambda _:None,lambda:False,outcome=outcome)
        self.assertEqual('cumulative',outcome['mode'])
        self.assertEqual('130.00',outcome['source_amount'])
        self.assertEqual('30.00',outcome['saved_amount'])
        self.assertEqual('2026-11-05',outcome['query_end'])

    def test_latest_log_uses_actual_attempt_order_within_the_same_second(self):
        from types import SimpleNamespace
        moment=datetime(2026,11,5,12,tzinfo=state.SHANGHAI)
        for attempt_id,result in [('zzzz',('success',Decimal('12'),'',[])),('aaaa',('failed',None,'重试失败',[]))]:
            with patch.object(revenue.uuid,'uuid4',return_value=SimpleNamespace(hex=attempt_id)),patch.object(revenue,'_fetch',return_value=result):
                revenue.collect_supported_theaters(self.conn,'2026-11-04','2026-11-04',account_ids=['q'],collected_at=moment,collection_run_id='same-second')
        logs=revenue.collection_logs(self.conn)['items']
        self.assertEqual(['aaaa','zzzz'],[r['id'] for r in logs])
        self.assertEqual('12.00',self.conn.execute('SELECT amount FROM v2_daily_revenues WHERE account_id=?',('q',)).fetchone()[0])

    def test_first_backfill_then_skips_then_fills_all_missed_days(self):
        jobs = self.jobs()
        moment = datetime(2026,11,3,12,tzinfo=state.SHANGHAI)
        with patch.object(state,'clock',return_value=moment), patch.object(revenue,'fetch_qingning_day_details',side_effect=[(Decimal('3.70'),[])]+[(Decimal('0'),[])]*7) as fetch:
            job = self.run_job(jobs)
            self.assertEqual('completed',job['state'],job)
            self.assertEqual(8,fetch.call_count)
            events = '\n'.join(item['message'] for item in job['events'])
            self.assertIn('连续无收益 7/7',events)
            job = self.run_job(jobs)
            self.assertEqual('skipped',job['items'][0]['status'])
            self.assertEqual(8,fetch.call_count)
        moment = datetime(2026,11,6,12,tzinfo=state.SHANGHAI)
        days=[]
        with patch.object(state,'clock',return_value=moment), patch.object(revenue,'fetch_qingning_day_details',side_effect=lambda _,day:(days.append(day) or Decimal('2'),[])):
            job=self.run_job(jobs)
        self.assertEqual(['2026-11-03','2026-11-04','2026-11-05'],days)
        self.assertEqual('completed',job['state'])

    def test_failure_preserves_history_and_retry_only_requeries_failed_date(self):
        jobs=self.jobs()
        calls=[]
        def fetch(_,day):
            calls.append(day)
            if len(calls)==1: raise RuntimeError('临时网络失败')
            return Decimal('0'),[]
        with patch.object(revenue,'fetch_qingning_day_details',side_effect=fetch):
            first=self.run_job(jobs)
        self.assertEqual('partial',first['state'])
        failed_day=calls[0]
        calls.clear()
        with patch.object(revenue,'fetch_qingning_day_details',side_effect=lambda _,day:(calls.append(day) or Decimal('0'),[])):
            jobs.start({},retry=True)
            jobs.thread.join(10)
        self.assertEqual([failed_day],calls)
        self.assertEqual('completed',jobs.state()['job']['state'])

    def test_stop_saves_returned_day_and_resume_does_not_query_it_again(self):
        jobs=self.jobs()
        calls=[]
        def fetch(_,day):
            calls.append(day)
            jobs.stop(jobs.job['id'])
            return Decimal('8'),[]
        with patch.object(revenue,'fetch_qingning_day_details',side_effect=fetch):
            first=self.run_job(jobs)
        self.assertEqual('stopped',first['state'])
        saved=calls[0]
        with closing(service.connection()) as conn:
            self.assertEqual('8.00',conn.execute('SELECT amount FROM v2_daily_revenues WHERE account_id=? AND revenue_date=?',('q',saved)).fetchone()[0])
            self.assertFalse(conn.execute("SELECT 1 FROM v2_revenue_collection_runs WHERE status IN ('queued','running')").fetchone())
        calls.clear()
        with patch.object(revenue,'fetch_qingning_day_details',side_effect=lambda _,day:(calls.append(day) or Decimal('0'),[])):
            jobs.start({},retry=True)
            jobs.thread.join(10)
        self.assertNotIn(saved,calls)
        self.assertEqual(7,len(calls))

    def test_pending_is_not_zero_or_completed_and_does_not_count_toward_boundary(self):
        with patch.object(revenue,'_fetch',return_value=('pending',None,'来源尚未出账',[])):
            result=revenue.collect_supported_theaters(self.conn,'2026-11-01','2026-11-01',account_ids=['q'],
                initial_backfill=True,skip_completed=True,max_initial_days=2)
        self.assertFalse(result['backfills'][0]['complete'])
        self.assertTrue(all(item['status']=='pending' for item in result['items']))
        self.assertFalse(self.conn.execute('SELECT 1 FROM v2_daily_revenues').fetchone())
        account=revenue._accounts(self.conn,None,['q'])[0]
        self.assertIsNone(state.completed(self.conn,account,'qingning','2026-11-01'))
        with patch.object(revenue,'_fetch',return_value=('success',Decimal('5'),'',[])) as fetch:
            revenue.collect_supported_theaters(self.conn,'2026-11-01','2026-11-01',account_ids=['q'],skip_completed=True)
        self.assertEqual(1,fetch.call_count)

    def test_existing_revenue_run_blocks_duplicate_theater_requests(self):
        self.conn.execute("INSERT INTO v2_revenue_collection_runs(id,status,start_date,end_date,created_at,updated_at) VALUES('active','running','2026-11-01','2026-11-01','now','now')")
        self.conn.commit()
        with patch.object(revenue,'_fetch') as fetch:
            result=revenue_queue.collect_account(service.connection,'q',lambda _:None,lambda:False)
        self.assertEqual('partial',result[0])
        fetch.assert_not_called()

    def test_missing_configuration_is_visible_and_other_bound_account_can_run(self):
        self.conn.execute("DELETE FROM v3_account_revenue_collectors WHERE account_id='q'")
        self.conn.commit()
        jobs=self.jobs()
        with patch.object(revenue,'_fetch') as fetch:
            job=self.run_job(jobs)
        fetch.assert_not_called()
        self.assertEqual('skipped',job['items'][0]['status'])
        self.assertIn('未配置',job['items'][0]['message'])

    def test_cumulative_respects_refresh_interval_and_only_credits_delta(self):
        moment=datetime(2026,11,3,12,tzinfo=state.SHANGHAI)
        with patch.object(state,'clock',return_value=moment),patch.object(revenue,'fetch_touch_latest',return_value=('success',Decimal('10'),'')) as fetch:
            first=revenue_queue.collect_account(service.connection,'t',lambda _:None,lambda:False)
            second=revenue_queue.collect_account(service.connection,'t',lambda _:None,lambda:False)
        self.assertEqual('success',first[0]);self.assertEqual('skipped',second[0]);self.assertEqual(1,fetch.call_count)
        with patch.object(state,'clock',return_value=datetime(2026,11,4,12,tzinfo=state.SHANGHAI)),patch.object(revenue,'fetch_touch_latest',return_value=('success',Decimal('14'),'')):
            revenue_queue.collect_account(service.connection,'t',lambda _:None,lambda:False)
        with closing(service.connection()) as conn:
            amounts=[row[0] for row in conn.execute("SELECT amount FROM v2_daily_revenues WHERE account_id='t' ORDER BY revenue_date")]
        self.assertEqual(['10.00','4.00'],amounts)

    def test_over_90_days_missing_is_filled_without_manual_date_splitting(self):
        with patch.object(state,'clock',return_value=datetime(2026,7,1,12,tzinfo=state.SHANGHAI)),patch.object(revenue,'fetch_qingning_day_details',return_value=(Decimal('0'),[])):
            revenue_queue.collect_account(service.connection,'q',lambda _:None,lambda:False)
        days=[]
        with patch.object(state,'clock',return_value=datetime(2026,11,3,12,tzinfo=state.SHANGHAI)),patch.object(revenue,'fetch_qingning_day_details',side_effect=lambda _,day:(days.append(day) or Decimal('1'),[])):
            result=revenue_queue.collect_account(service.connection,'q',lambda _:None,lambda:False)
        self.assertEqual('success',result[0]);self.assertEqual('2026-07-01',days[0]);self.assertEqual('2026-11-02',days[-1]);self.assertEqual(125,len(days))

    def test_pending_result_is_exposed_in_summary_logs_and_dashboard(self):
        with patch.object(revenue,'_fetch',return_value=('no_data',None,'来源尚未出账',[])):
            revenue.collect_supported_theaters(self.conn,'2026-11-01','2026-11-01',account_ids=['q'])
        self.assertEqual('pending',next(item for item in revenue.revenue_daily_account_summary(self.conn,'2026-11-01')['items'] if item['account_id']=='q')['collection_status'])
        self.assertEqual('pending',revenue.collection_logs(self.conn)['items'][0]['collection_status'])
        from server.operations_dashboard import rating_revenue_data
        self.assertEqual('pending',rating_revenue_data(self.conn,[])['queries'][0]['collection_status'])

    def test_access_limit_stops_the_remaining_queries(self):
        jobs=self.jobs()
        with patch.object(revenue,'fetch_qingning_day_details',side_effect=RuntimeError('HTTP 429 请求频繁')) as fetch:
            job=self.run_job(jobs,account_ids=['q','t'])
        self.assertEqual('paused',job['state']);self.assertEqual(1,fetch.call_count)
        self.assertEqual('stopped',job['items'][1]['status'])
        self.assertFalse(jobs.detection.state()['paused_reason'])

    def test_revenue_still_succeeds_when_the_video_client_is_unavailable(self):
        jobs=self.jobs()
        with patch.object(revenue,'fetch_qingning_day_details',return_value=(Decimal('0'),[])):
            job=self.run_job(jobs,categories=['revenue','works'])
        self.assertEqual('success',next(i for i in job['items'] if i['category']=='revenue')['status'])
        self.assertEqual('failed',next(i for i in job['items'] if i['category']=='works')['status'])


if __name__ == '__main__':
    unittest.main()
