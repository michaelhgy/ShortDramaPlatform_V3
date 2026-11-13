import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from server import revenue_auto_scheduler as scheduler
from server import v2_file_service as service
from server import v2_revenue_service as revenue


class V2RevenueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        service.WORKSPACE = Path(self.temp.name) / "workspace"
        service.DATA_ROOT = Path(self.temp.name) / "system-data"
        now = "2026-08-29T10:00:00"
        conn = service.connection()
        try:
            conn.execute("INSERT INTO theaters (id, name, created_at, updated_at) VALUES ('t1', '青柠剧场', ?, ?)", (now, now))
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, created_at, updated_at) VALUES ('a1', '青柠账号', 'channel-1', 't1', ?, ?)", (now, now))
            revenue.collectors.set_theater(conn, 't1', ['qingning'])
            revenue.collectors.set_account(conn, 'a1', 't1', 'qingning')
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_success_upserts_direct_revenue_and_exposes_source_data(self) -> None:
        conn = service.connection()
        try:
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('12.34'), [])):
                result = revenue.collect_qingning(conn, '2026-08-28', '2026-08-28')
            self.assertEqual('success', result['items'][0]['status'])
            data = revenue.revenue_source_data(conn)
            self.assertEqual('12.34', data['rows'][0]['amount'])
            self.assertEqual('direct', data['rows'][0]['quality'])
        finally:
            conn.close()

    def test_daily_account_summary_keeps_real_zero_separate_from_missing_collection(self) -> None:
        conn = service.connection()
        try:
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('0.00'), [])):
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28')
            summary = revenue.revenue_daily_account_summary(conn, '2026-08-28')
            self.assertEqual('success', summary['items'][0]['collection_status'])
            self.assertEqual('0.00', summary['items'][0]['amount'])
        finally:
            conn.close()

    def test_daily_account_summary_uses_non_disabled_accounts_and_counts_no_data_as_collected(self) -> None:
        conn = service.connection()
        try:
            now = "2026-08-29T10:00:00"
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a-no-data', '无结算', 'channel-2', 't1', '正常', ?, ?)", (now, now))
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a-failed', '采集失败', 'channel-3', 't1', '正常', ?, ?)", (now, now))
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a-disabled', '停用账号', 'channel-4', 't1', '停用', ?, ?)", (now, now))
            for attempt_id, account_id, status in (
                ('attempt-no-data', 'a-no-data', 'no_data'), ('attempt-failed', 'a-failed', 'failed'), ('attempt-disabled', 'a-disabled', 'success'),
            ):
                conn.execute(
                    """INSERT INTO v2_revenue_collection_attempts
                       (id, request_id, account_id, theater_id, adapter_key, revenue_date, collection_status, amount, error_message, collected_at)
                       VALUES (?, 'request', ?, 't1', 'qingning', '2026-08-28', ?, NULL, '', ?)""",
                    (attempt_id, account_id, status, now),
                )
            conn.commit()

            statuses = {item['account_id']: item['collection_status'] for item in revenue.revenue_daily_account_summary(conn, '2026-08-28')['items']}

            self.assertEqual({'a1': 'uncollected', 'a-no-data': 'no_data', 'a-failed': 'failed','a-disabled':'success'}, statuses)
        finally:
            conn.close()

    def test_no_data_and_failed_never_become_zero_revenue(self) -> None:
        conn = service.connection()
        try:
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(None, [])):
                no_data = revenue.collect_qingning(conn, '2026-08-27', '2026-08-27')
            self.assertEqual('no_data', no_data['items'][0]['status'])
            with patch.object(revenue, 'fetch_qingning_day_details', side_effect=RevenueError('network unavailable')):
                failed = revenue.collect_qingning(conn, '2026-08-26', '2026-08-26')
            self.assertEqual('failed', failed['items'][0]['status'])
            self.assertEqual(0, len(revenue.revenue_source_data(conn)['rows']))
            self.assertEqual(2, len(revenue.collection_logs(conn)['items']))
        finally:
            conn.close()

    def test_video_details_keep_one_latest_row_per_date_account_and_video(self) -> None:
        conn = service.connection()
        try:
            detail = revenue.QingningRow(1, 'video-1', '测试剧集', 100, 200, revenue.Decimal('12.34'))
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('12.34'), [detail])):
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28', save_details=True)
            changed = revenue.QingningRow(1, 'video-1', '测试剧集', 150, 240, revenue.Decimal('15.00'))
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('15.00'), [changed])):
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28', save_details=True)
            result = revenue.revenue_video_details(conn, '2026-08-28', '2026-08-28')
            self.assertEqual(1, len(result['items']))
            self.assertEqual(150, result['items'][0]['video_views'])
            self.assertEqual('unmatched', result['items'][0]['match_status'])
        finally:
            conn.close()


    def test_default_qingning_collection_keeps_detail_capability_without_persisting_details(self) -> None:
        conn = service.connection()
        try:
            detail = revenue.QingningRow(1, 'video-1', '测试剧集', 100, 200, revenue.Decimal('12.34'))
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('12.34'), [detail])):
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28')
            self.assertEqual(0, conn.execute('SELECT COUNT(*) FROM v2_revenue_video_details').fetchone()[0])
            self.assertEqual(1, conn.execute('SELECT COUNT(*) FROM v2_daily_revenues').fetchone()[0])
        finally:
            conn.close()

    def test_completed_qingning_day_is_not_requested_again_when_skip_enabled(self) -> None:
        conn = service.connection()
        try:
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('12.34'), [])) as fetch:
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28', skip_completed=True)
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28', skip_completed=True)
            self.assertEqual(1, fetch.call_count)
            self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM v2_revenue_collection_attempts WHERE revenue_date='2026-08-28'").fetchone()[0])
        finally:
            conn.close()


    def test_cumulative_theater_amount_is_written_to_collection_date(self) -> None:
        conn = service.connection()
        try:
            now = "2026-08-29T10:00:00"
            conn.execute("INSERT INTO theaters (id, name, created_at, updated_at) VALUES ('t-touch', '触摸剧场', ?, ?)", (now, now))
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, created_at, updated_at) VALUES ('a-touch', '触摸账号', 'touch-1', 't-touch', ?, ?)", (now, now))
            conn.commit()
            revenue.collectors.set_theater(conn, 't-touch', ['touch'])
            revenue.collectors.set_account(conn, 'a-touch', 't-touch', 'touch')
            with patch.object(revenue, 'fetch_touch_latest', return_value=('success', revenue.Decimal('88.00'), '')):
                result = revenue.collect_supported_theaters(conn, '2026-08-28', '2026-08-28', ['触摸剧场'], skip_completed=True, collected_at=datetime(2026, 8, 29, 10))
            self.assertEqual('2026-08-29', result['items'][0]['date'])
            row = conn.execute("SELECT revenue_date,amount FROM v2_daily_revenues WHERE account_id='a-touch'").fetchone()
            self.assertEqual(('2026-08-29', '88.00'), (row['revenue_date'], row['amount']))
        finally:
            conn.close()


    def test_first_qingning_collection_backfills_until_seven_explicit_empty_days(self) -> None:
        conn = service.connection()
        try:
            calls = []
            def fetch(_channel: str, day: str):
                calls.append(day)
                return (revenue.Decimal('12.00'), []) if len(calls) == 1 else (None, [])
            with patch.object(revenue, 'fetch_qingning_day_details', side_effect=fetch):
                result = revenue.collect_qingning(conn, '2026-08-28', '2026-08-28', initial_backfill=True, max_initial_days=20, empty_streak_stop=7, skip_completed=True)
            self.assertEqual(8, len(result['items']))
            self.assertEqual('2026-08-28', calls[0])
            self.assertEqual('2026-08-21', calls[-1])
        finally:
            conn.close()

    def test_collector_inventory_marks_registered_and_unimplemented_theaters(self) -> None:
        conn = service.connection()
        try:
            now = "2026-08-29T10:00:00"
            conn.execute("INSERT INTO theaters (id, name, status, created_at, updated_at) VALUES ('t-new', '添翼剧场', '启用', ?, ?)", (now, now))
            conn.commit()
            inventory = revenue.revenue_collector_inventory(conn)
            by_name = {item['name']: item for item in inventory['items']}
            self.assertEqual('ready', by_name['青柠剧场']['adapter_status'])
            self.assertEqual('unimplemented', by_name['添翼剧场']['adapter_status'])
            self.assertIn('青柠剧场', inventory['supported_theaters'])
            self.assertNotIn('添翼剧场', inventory['supported_theaters'])
        finally:
            conn.close()

    def test_qingning_normal_empty_page_is_no_data_not_unpack_failure(self) -> None:
        with patch.object(revenue, '_fetch_page', return_value=([], 1, 0, None)):
            amount, details = revenue.fetch_qingning_day_details('channel-1', '2026-08-28')
        self.assertIsNone(amount)
        self.assertEqual([], details)

    def test_progress_total_uses_real_account_date_reads(self) -> None:
        conn = service.connection()
        try:
            total = revenue.estimate_collection_units(conn, '2026-08-27', '2026-08-28', ['青柠剧场'])
            self.assertEqual(2, total)
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a-disabled', '停用账号', 'channel-2', 't1', '停用', '2026-08-29T10:00:00', '2026-08-29T10:00:00')")
            conn.commit()
            self.assertEqual(3, revenue.estimate_collection_units(conn, '2026-08-27', '2026-08-28', ['青柠剧场']))
        finally:
            conn.close()

    def test_paused_accounts_still_collect_revenue(self) -> None:
        conn = service.connection()
        try:
            now = "2026-08-29T10:00:00"
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a2', '异常账号', 'channel-2', 't1', '异常', ?, ?)", (now, now))
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a3', '停用账号', 'channel-3', 't1', '停用', ?, ?)", (now, now))
            conn.commit()
            revenue.collectors.set_account(conn, 'a2', 't1', 'qingning')
            revenue.collectors.set_account(conn, 'a3', 't1', 'qingning')
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(None, [])) as collect:
                result = revenue.collect_qingning(conn, '2026-08-28', '2026-08-28')
            self.assertEqual(3, result['total_accounts'])
            self.assertEqual(3, collect.call_count)
        finally:
            conn.close()

    def test_auto_collection_catches_up_missed_slots_once_per_day(self) -> None:
        service.update_v2_settings({
            'revenue_auto_collection_enabled': True,
            'revenue_auto_collection_times': ['06:00', '12:00', '20:00'],
        })
        calls: list[dict[str, object]] = []

        def start_collection(*args, **kwargs):
            calls.append({'args': args, 'kwargs': kwargs})
            conn = service.connection()
            try:
                conn.execute(
                    """INSERT INTO v2_revenue_collection_runs
                       (id, status, start_date, end_date, trigger_source, scheduled_slots_json, total_units, created_at, updated_at)
                       VALUES (?, 'completed', ?, ?, 'automatic', ?, 0, ?, ?)""",
                    (f'run-{len(calls)}', args[0], args[1], json.dumps(kwargs['scheduled_slots']), '2026-09-01T14:00:00', '2026-09-01T14:00:00'),
                )
                conn.commit()
            finally:
                conn.close()
            return {'run_id': f'run-{len(calls)}'}

        with patch.object(scheduler.service, 'start_revenue_collection', side_effect=start_collection):
            scheduler.run_due_auto_collection(datetime(2026, 9, 1, 14, 0))
            scheduler.run_due_auto_collection(datetime(2026, 9, 1, 14, 5))
            scheduler.run_due_auto_collection(datetime(2026, 9, 1, 20, 0))

        self.assertEqual(2, len(calls))
        self.assertEqual(('2026-08-31', '2026-08-31'), calls[0]['args'])
        self.assertEqual(['06:00', '12:00'], calls[0]['kwargs']['scheduled_slots'])
        self.assertEqual(['20:00'], calls[1]['kwargs']['scheduled_slots'])

    def test_auto_collection_does_not_start_when_disabled_or_another_run_is_active(self) -> None:
        now = datetime(2026, 9, 1, 14, 0)
        service.update_v2_settings({'revenue_auto_collection_enabled': False})
        with patch.object(scheduler.service, 'start_revenue_collection') as start:
            self.assertIsNone(scheduler.run_due_auto_collection(now))
            start.assert_not_called()

        service.update_v2_settings({'revenue_auto_collection_enabled': True})
        conn = service.connection()
        try:
            conn.execute(
                """INSERT INTO v2_revenue_collection_runs
                   (id, status, start_date, end_date, total_units, created_at, updated_at)
                   VALUES ('active-run', 'running', '2026-08-31', '2026-08-31', 0, '2026-09-01T14:00:00', '2026-09-01T14:00:00')"""
            )
            conn.commit()
        finally:
            conn.close()
        with patch.object(scheduler.service, 'start_revenue_collection') as start:
            self.assertIsNone(scheduler.run_due_auto_collection(now))
            start.assert_not_called()

    def test_auto_collection_settings_require_unique_clock_times(self) -> None:
        with self.assertRaisesRegex(ValueError, '收益自动采集时间'):
            service.update_v2_settings({'revenue_auto_collection_times': ['06:00', '06:00']})
        with self.assertRaisesRegex(ValueError, '收益自动采集时间'):
            service.update_v2_settings({'revenue_auto_collection_times': ['25:00']})


class RevenueError(Exception):
    pass
