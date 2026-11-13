"""Delayed publication and cumulative accounting, using isolated business schemas."""
from datetime import datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from server import revenue_collection_state as state, revenue_queue as queue
from server import v2_revenue_service as revenue, v2_file_service as service
from server.tests import test_revenue_collection_rules as fixtures

MOMENT = datetime(2026, 11, 5, 12, tzinfo=state.SHANGHAI)


class DelayedRevenueTests(unittest.TestCase):
    setUp = fixtures.RevenueCollectionRulesTests.setUp

    def collect_day(self, day, amount, moment=MOMENT, initial=False):
        with patch.object(revenue, 'fetch_qingning_day_details', return_value=(amount, [])):
            return revenue.collect_qingning(self.conn, day, day, skip_completed=True,
                                           initial_backfill=initial, collected_at=moment)

    def seed_history(self):
        self.collect_day('2026-11-03', Decimal('2'), MOMENT-timedelta(days=1))
        self.conn.execute("INSERT INTO v3_revenue_backfills VALUES('q','q','qingning','2026-11-03','2026-11-03',1)")
        self.conn.commit()

    def test_recent_empty_is_pending_without_erasing_history_or_creating_zero(self):
        self.seed_history()
        self.collect_day('2026-11-04', None)
        meta = queue.account_states(self.conn, '2026-11-04', collected_at=MOMENT)['q']
        self.assertEqual('missing', meta['state'])
        self.assertIn('暂无数据', meta['message'])
        self.assertEqual(1, meta['recheck_days'])
        self.assertFalse(meta['query_due'])
        self.assertTrue(self.conn.execute("SELECT complete FROM v3_revenue_backfills WHERE account_id='q'").fetchone()[0])
        self.assertIsNone(self.conn.execute("SELECT amount FROM v2_daily_revenues WHERE revenue_date='2026-11-04'").fetchone())

    def test_hainan_case_empty_then_late_amount_saved_on_original_revenue_date(self):
        self.seed_history()
        self.collect_day('2026-11-04', None)
        with patch.object(state, 'clock', return_value=MOMENT+timedelta(minutes=30)), patch.object(revenue, 'fetch_qingning_day_details') as fetch:
            self.assertEqual('skipped', queue.collect_account(service.connection, 'q', lambda _: None, lambda: False)[0])
            fetch.assert_not_called()
        with patch.object(state, 'clock', return_value=MOMENT+timedelta(hours=2)), patch.object(revenue, 'fetch_qingning_day_details', return_value=(Decimal('6.78'), [])) as fetch:
            result = queue.collect_account(service.connection, 'q', lambda _: None, lambda: False)
            self.assertEqual('success', result[0])
            self.assertEqual('2026-11-04', fetch.call_args.args[1])
            self.assertEqual(1, fetch.call_count)
            self.assertEqual('complete', queue.account_states(self.conn, '2026-11-04')['q']['state'])
            self.assertEqual('skipped', queue.collect_account(service.connection, 'q', lambda _: None, lambda: False)[0])
            self.assertEqual(1, fetch.call_count)
        self.assertEqual('6.78', self.conn.execute("SELECT amount FROM v2_daily_revenues WHERE revenue_date='2026-11-04'").fetchone()[0])

    def test_next_day_checks_yesterday_and_previous_unpublished_day(self):
        self.seed_history()
        self.collect_day('2026-11-04', None)
        with patch.object(state, 'clock', return_value=MOMENT+timedelta(days=1)), patch.object(revenue, 'fetch_qingning_day_details', return_value=(Decimal('3'), [])) as fetch:
            self.assertEqual('success', queue.collect_account(service.connection, 'q', lambda _: None, lambda: False)[0])
            self.assertEqual(['2026-11-04', '2026-11-05'], [x.args[1] for x in fetch.call_args_list])

    def test_failed_recheck_does_not_complete_the_unpublished_day(self):
        self.seed_history()
        self.collect_day('2026-11-04', None)
        with patch.object(state, 'clock', return_value=MOMENT+timedelta(hours=2)), patch.object(revenue, 'fetch_qingning_day_details', side_effect=RuntimeError('网络失败')):
            self.assertEqual('failed', queue.collect_account(service.connection, 'q', lambda _: None, lambda: False)[0])
            self.assertEqual('missing', queue.account_states(self.conn, '2026-11-04')['q']['state'])

    def test_still_empty_task_reports_source_pending_not_completed(self):
        self.seed_history()
        self.collect_day('2026-11-04', None)
        with patch.object(state, 'clock', return_value=MOMENT+timedelta(hours=2)), patch.object(revenue, 'fetch_qingning_day_details', return_value=(None, [])):
            outcome = {}
            result = queue.collect_account(service.connection, 'q', lambda _: None, lambda: False, outcome=outcome)
            self.assertEqual('partial', result[0])
            self.assertEqual(1, outcome['pending_days'])
            self.assertFalse(outcome['history_pending'])
            self.assertIn('暂无数据', result[1])

    def test_window_and_interval_can_differ_per_collector(self):
        self.collect_day('2026-11-04', None)
        account = revenue._accounts(self.conn, None, ['q'])[0]
        spec = {'empty_recheck_days': 14, 'recheck_interval_minutes': 120}
        self.assertIsNotNone(state.completed(self.conn, account, 'qingning', '2026-11-04', collected_at=MOMENT+timedelta(minutes=90), spec=spec))
        self.assertIsNone(state.completed(self.conn, account, 'qingning', '2026-11-04', collected_at=MOMENT+timedelta(hours=2), spec=spec))
        self.assertIsNone(state.completed(self.conn, account, 'qingning', '2026-11-04', collected_at=MOMENT+timedelta(days=8), spec=spec))
        self.assertIsNotNone(state.completed(self.conn, account, 'qingning', '2026-11-04', collected_at=MOMENT+timedelta(days=8)))
        self.assertEqual(0, self.conn.execute('SELECT count(*) FROM v2_daily_revenues').fetchone()[0])

    def test_legacy_routine_entry_also_catches_recent_empty_day(self):
        self.seed_history()
        self.collect_day('2026-11-04', None)
        estimate = revenue.estimate_collection_units(self.conn, '2026-11-05', '2026-11-05', account_ids=['q'], initial_backfill=True, skip_completed=True, collected_at=MOMENT+timedelta(days=1))
        self.assertEqual(2, estimate)
        with patch.object(revenue, 'fetch_qingning_day_details', return_value=(Decimal('3'), [])) as fetch:
            revenue.collect_qingning(self.conn, '2026-11-05', '2026-11-05', initial_backfill=True,
                                     skip_completed=True, collected_at=MOMENT+timedelta(days=1))
        self.assertEqual(['2026-11-04', '2026-11-05'], [x.args[1] for x in fetch.call_args_list])

    def test_confirmed_zero_is_saved_and_not_rechecked(self):
        self.seed_history()
        self.collect_day('2026-11-04', Decimal('0'))
        with patch.object(state, 'clock', return_value=MOMENT+timedelta(hours=2)), patch.object(revenue, 'fetch_qingning_day_details') as fetch:
            self.assertEqual('complete', queue.account_states(self.conn, '2026-11-04')['q']['state'])
            self.assertEqual('skipped', queue.collect_account(service.connection, 'q', lambda _: None, lambda: False)[0])
            fetch.assert_not_called()

    def test_month_first_same_day_refresh_gap_and_new_month_use_collection_day(self):
        spec = dict(revenue.REVENUE_ADAPTERS['触摸剧场'], cumulative_period='month')
        def collect(amount, moment):
            with patch.object(revenue, 'fetch_touch_latest', return_value=('success', Decimal(amount), '')) as fetch:
                result = revenue.collect_supported_theaters(self.conn, '2026-11-04', '2026-11-04',
                    account_ids=['t'], skip_completed=True, collected_at=moment)
                if amount == '120' and moment == MOMENT+timedelta(hours=2):
                    self.assertEqual('20.00', result['items'][0]['amount'])
                return fetch.call_count
        with patch.dict(revenue.REVENUE_ADAPTERS, {'触摸剧场': spec}):
            self.assertEqual(1, collect('100', MOMENT))
            self.assertEqual(0, collect('120', MOMENT+timedelta(minutes=30)))
            self.assertEqual(1, collect('120', MOMENT+timedelta(hours=2)))
            self.assertEqual(1, collect('120', MOMENT+timedelta(hours=4)))
            collect('150', MOMENT+timedelta(days=1))
            collect('190', MOMENT+timedelta(days=3))
            collect('5', MOMENT.replace(month=12, day=1))
        rows = [tuple(r) for r in self.conn.execute("SELECT revenue_date,amount FROM v2_daily_revenues WHERE account_id='t' ORDER BY revenue_date")]
        self.assertEqual([('2026-11-05', '120.00'), ('2026-11-06', '30.00'), ('2026-11-08', '40.00'), ('2026-12-01', '5.00')], rows)

    def test_cumulative_empty_stays_pending_during_interval(self):
        with patch.object(revenue, 'fetch_touch_latest', return_value=('no_data', None, '暂无数据')):
            revenue.collect_supported_theaters(self.conn, '2026-11-04', '2026-11-04',
                account_ids=['t'], skip_completed=True, collected_at=MOMENT)
        meta = queue.account_states(self.conn, '2026-11-04', collected_at=MOMENT)['t']
        self.assertEqual('missing', meta['state'])
        self.assertFalse(meta['query_due'])
        self.assertIn('暂无数据', meta['message'])
        self.assertTrue(queue.account_states(self.conn, '2026-11-04', collected_at=MOMENT+timedelta(hours=2))['t']['query_due'])

    def test_cumulative_queue_reports_only_increment_while_saving_daily_total(self):
        with patch.object(state, 'clock', return_value=MOMENT), patch.object(revenue, 'fetch_touch_latest', return_value=('success', Decimal('100'), '')):
            queue.collect_account(service.connection, 't', lambda _: None, lambda: False)
        with patch.object(state, 'clock', return_value=MOMENT+timedelta(hours=2)), patch.object(revenue, 'fetch_touch_latest', return_value=('success', Decimal('120'), '')):
            outcome = {}
            self.assertEqual('success', queue.collect_account(service.connection, 't', lambda _: None, lambda: False, outcome=outcome)[0])
        self.assertEqual('20.00', outcome['saved_amount'])
        self.assertEqual('120.00', self.conn.execute("SELECT amount FROM v2_daily_revenues WHERE account_id='t'").fetchone()[0])

    def test_empty_historical_month_is_not_permanently_completed(self):
        self.conn.execute("INSERT INTO v2_revenue_collection_attempts(id,request_id,account_id,theater_id,adapter_key,revenue_date,collection_status,collected_at,data_kind,period_end) VALUES('empty-month','empty-month','t','t','touch','2026-11-05','no_data',?,'account_cumulative','2026-10')", (MOMENT.isoformat(),))
        self.conn.commit()
        self.assertTrue(revenue._cumulative_completed(self.conn, {'id':'t','theater_id':'t'}, 'touch', '2026-10', '2026-11-05', historical=True, collected_at=MOMENT))
        self.assertFalse(revenue._cumulative_completed(self.conn, {'id':'t','theater_id':'t'}, 'touch', '2026-10', '2026-11-05', historical=True, collected_at=MOMENT+timedelta(hours=2)))


if __name__ == '__main__':
    unittest.main()
