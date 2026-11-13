"""Completion follows each collector's real coverage, never task termination alone."""
from datetime import datetime
from decimal import Decimal
import json
import unittest
from unittest.mock import patch
from server import revenue_queue as queue, revenue_collection_state as state
from server import revenue_query_settings as settings, revenue_collectors as collectors
from server import v2_revenue_service as revenue, v2_file_service as service
from server.tests import test_revenue_collection_rules as fixtures

MOMENT=datetime(2026,11,5,12,tzinfo=state.SHANGHAI)


class RevenueCompletionPolicyTests(unittest.TestCase):
    setUp=fixtures.RevenueCollectionRulesTests.setUp

    def bind(self, collector):
        collectors.set_theater(self.conn,'q',[collector]);collectors.set_account(self.conn,'q','q',collector);self.conn.commit()

    def test_recent_no_data_keeps_recheck_state_and_respects_interval(self):
        self.bind('dinghao')
        with patch.object(state,'clock',return_value=MOMENT), patch.object(revenue,'_post_json',return_value={'status_code':1,'data':{'amount':'0.00'}}) as fetch:
            first=queue.collect_account(service.connection,'q',lambda _:None,lambda:False)
            self.assertEqual('partial',first[0]);self.assertEqual(7,fetch.call_count)
            self.assertEqual('missing',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']['state'])
            self.assertEqual('skipped',queue.collect_account(service.connection,'q',lambda _:None,lambda:False)[0])
            self.assertEqual(7,fetch.call_count)

    def test_daily_missing_date_cannot_be_hidden_by_complete_history_flag(self):
        with patch.object(revenue,'fetch_qingning_day_details',return_value=(None,[])):
            revenue.collect_qingning(self.conn,'2026-11-03','2026-11-03',initial_backfill=True,skip_completed=True,collected_at=MOMENT)
        meta=queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']
        self.assertEqual('missing',meta['state']);self.assertEqual('2026-11-04',meta['first_missing'])
        with patch.object(state,'clock',return_value=MOMENT),patch.object(revenue,'fetch_qingning_day_details',return_value=(None,[])) as fetch:
            self.assertEqual('partial',queue.collect_account(service.connection,'q',lambda _:None,lambda:False)[0])
        self.assertEqual(1,fetch.call_count)
        self.assertEqual('missing',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']['state'])

    def test_daily_pending_is_not_a_confirmed_no_data(self):
        self.test_daily_missing_date_cannot_be_hidden_by_complete_history_flag()
        last=self.conn.execute("SELECT id FROM v2_revenue_collection_attempts WHERE account_id='q' AND revenue_date='2026-11-04' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        self.conn.execute('INSERT INTO v3_revenue_pending_queries VALUES(?)',(last,));self.conn.commit()
        self.assertEqual('missing',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']['state'])

    def test_configured_month_is_used_instead_of_builtin_unknown_period(self):
        with patch.object(revenue,'fetch_touch_latest',return_value=('success',Decimal('10'),'')):
            revenue.collect_supported_theaters(self.conn,'2026-11-04','2026-11-04',account_ids=['t'],collected_at=MOMENT)
        self.assertEqual('complete',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['t']['state'])
        cfg={**settings.default_config('touch'),'source_period':'2026-11','baseline_periods':['unknown']}
        self.conn.execute('INSERT INTO v3_revenue_query_revisions VALUES(?,?,?,?)',('touch',1,json.dumps(cfg),MOMENT.isoformat()));self.conn.commit()
        self.assertEqual('missing',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['t']['state'])
        with patch.object(state,'clock',return_value=MOMENT),patch.object(revenue,'fetch_touch_latest',return_value=('success',Decimal('12'),'')) as fetch:
            self.assertEqual('success',queue.collect_account(service.connection,'t',lambda _:None,lambda:False)[0])
        self.assertEqual(1,fetch.call_count)
        self.assertEqual('complete',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['t']['state'])
        self.assertEqual('12.00',self.conn.execute("SELECT amount FROM v2_daily_revenues WHERE account_id='t'").fetchone()[0])

    def test_zishi_current_month_success_does_not_hide_missing_previous_month(self):
        from server import zishi_collector as z
        self.bind('zishi_agency')
        def first(channel,key,cfg,period,today):
            return ('success',Decimal('0.09'),'本月',[]) if period=='2026-11' else ('pending',None,'上月尚未更新',[])
        with patch.object(z,'fetch_month',side_effect=first):
            revenue.collect_supported_theaters(self.conn,'2026-11-04','2026-11-04',account_ids=['q'],skip_completed=True,collected_at=MOMENT)
        meta=queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']
        self.assertEqual('backfill',meta['state']);self.assertIn('2026-10',meta['message'])
        with patch.object(state,'clock',return_value=MOMENT),patch.object(z,'fetch_month',return_value=('success',Decimal('2'),'上月',[])) as fetch:
            self.assertEqual('success',queue.collect_account(service.connection,'q',lambda _:None,lambda:False)[0])
            self.assertEqual(1,fetch.call_count);self.assertEqual('2026-10',fetch.call_args.args[3])
            self.assertEqual('complete',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']['state'])
            self.assertEqual('skipped',queue.collect_account(service.connection,'q',lambda _:None,lambda:False)[0])
            self.assertEqual(1,fetch.call_count)

    def test_closed_historical_month_is_reused_on_later_collection_day(self):
        from server import zishi_collector as z
        self.bind('zishi_agency')
        earlier=datetime(2026,11,3,12,tzinfo=state.SHANGHAI)
        with patch.object(z,'fetch_month',return_value=('success',Decimal('2'),'月份累计',[])):
            revenue.collect_supported_theaters(self.conn,'2026-11-02','2026-11-02',account_ids=['q'],collected_at=earlier)
            revenue.collect_supported_theaters(self.conn,'2026-11-04','2026-11-04',account_ids=['q'],skip_completed=True,collected_at=MOMENT)
        self.assertEqual('complete',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']['state'])
        with patch.object(state,'clock',return_value=MOMENT),patch.object(z,'fetch_month') as fetch:
            self.assertEqual('skipped',queue.collect_account(service.connection,'q',lambda _:None,lambda:False)[0])
            fetch.assert_not_called()

    def test_removed_optional_history_link_is_not_required(self):
        from server import zishi_collector as z
        self.bind('zishi_agency')
        cfg={**settings.default_config('zishi_agency'),'previous_month_url':''}
        self.conn.execute('INSERT INTO v3_revenue_query_revisions VALUES(?,?,?,?)',('zishi_agency',1,json.dumps(cfg),MOMENT.isoformat()));self.conn.commit()
        with patch.object(z,'fetch_month',return_value=('success',Decimal('2'),'本月',[])) as fetch:
            revenue.collect_supported_theaters(self.conn,'2026-11-04','2026-11-04',account_ids=['q'],skip_completed=True,collected_at=MOMENT)
        self.assertEqual(1,fetch.call_count);self.assertEqual('complete',queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['q']['state'])

    def test_interrupted_monthly_history_keeps_original_anchor_months(self):
        spec={**revenue.REVENUE_ADAPTERS['触摸剧场'],'supports_month_query':True,'cumulative_period':'month'}
        with patch.dict(revenue.REVENUE_ADAPTERS,{'触摸剧场':spec}):
            self.conn.execute("INSERT INTO v3_revenue_backfills(account_id,theater_id,adapter_key,anchor_date) VALUES('t','t','touch','2026-09-03')")
            for i,period in enumerate(['2026-11','2026-10','2026-09']):
                self.conn.execute("""INSERT INTO v2_revenue_collection_attempts(id,request_id,account_id,theater_id,adapter_key,revenue_date,collection_status,amount,collected_at,data_kind,period_end)
                    VALUES(?,?,'t','t','touch','2026-11-05','success','1',?,'account_cumulative',?)""",(str(i),str(i),MOMENT.isoformat(),period))
            self.conn.commit()
            meta=queue.account_states(self.conn,'2026-11-04',collected_at=MOMENT)['t']
        self.assertEqual('backfill',meta['state']);self.assertIn('2026-08',meta['message']);self.assertIn('2026-07',meta['message'])

    def test_task_returning_without_required_result_is_not_completed(self):
        with patch.object(state,'clock',return_value=MOMENT),patch.object(revenue,'collect_supported_theaters',return_value={'items':[],'backfills':[]}):
            result=queue.collect_account(service.connection,'t',lambda _:None,lambda:False)
        self.assertEqual('partial',result[0]);self.assertIn('待查询',result[1])


if __name__=='__main__':unittest.main()
