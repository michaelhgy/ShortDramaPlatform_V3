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

            self.assertEqual({'a1': 'uncollected', 'a-no-data': 'no_data', 'a-failed': 'failed'}, statuses)
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
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28')
            changed = revenue.QingningRow(1, 'video-1', '测试剧集', 150, 240, revenue.Decimal('15.00'))
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('15.00'), [changed])):
                revenue.collect_qingning(conn, '2026-08-28', '2026-08-28')
            result = revenue.revenue_video_details(conn, '2026-08-28', '2026-08-28')
            self.assertEqual(1, len(result['items']))
            self.assertEqual(150, result['items'][0]['video_views'])
            self.assertEqual('unmatched', result['items'][0]['match_status'])
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
            self.assertEqual(2, revenue.estimate_collection_units(conn, '2026-08-27', '2026-08-28', ['青柠剧场']))
        finally:
            conn.close()

    def test_only_disabled_account_is_excluded_from_collection(self) -> None:
        conn = service.connection()
        try:
            now = "2026-08-29T10:00:00"
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a2', '异常账号', 'channel-2', 't1', '异常', ?, ?)", (now, now))
            conn.execute("INSERT INTO accounts (id, nickname, channel_id, theater_id, status, created_at, updated_at) VALUES ('a3', '停用账号', 'channel-3', 't1', '停用', ?, ?)", (now, now))
            conn.commit()
            with patch.object(revenue, 'fetch_qingning_day_details', return_value=(None, [])) as collect:
                result = revenue.collect_qingning(conn, '2026-08-28', '2026-08-28')
            self.assertEqual(2, result['total_accounts'])
            self.assertEqual(2, collect.call_count)
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
