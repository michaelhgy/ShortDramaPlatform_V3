"""Query-link management: isolated config, financial boundaries and offline source protocols."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock
from server import v2_file_service as service
from server import v2_revenue_service as revenue
from server import revenue_query_settings as settings


class QuerySettingsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for key, value in [("WORKSPACE", root / "workspace"), ("DATA_ROOT", root / "data"), ("DATABASE_INITIALIZED_PATH", None)]:
            target = patch.object(service, key, value)
            target.start()
            self.addCleanup(target.stop)
        self.conn = service.connection()
        self.addCleanup(self.conn.close)
        self.conn.execute("INSERT INTO theaters(id,name,created_at,updated_at) VALUES('t','自建触摸','2026-11-01','2026-11-01')")
        self.conn.execute("INSERT INTO accounts(id,nickname,channel_id,theater_id,created_at,updated_at) VALUES('a','测试账号','fixture-channel','t','2026-11-01','2026-11-01')")
        revenue.collectors.set_theater(self.conn, 't', ['touch'])
        revenue.collectors.set_account(self.conn, 'a', 't', 'touch')
        self.conn.commit()

    def payload(self, **values):
        return {**settings.default_config('touch'), 'revision': settings.current(self.conn, 'touch')['revision'],
                'channel_id': 'fixture-channel', 'query_date': '2026-11-01', 'period_relation': 'same', **values}

    def activate(self, **values):
        payload = self.payload(**values)
        with patch.object(revenue, '_fetch', return_value=('success', Decimal('12.34'), '', [])):
            result = settings.preview(self.conn, 'touch', payload)
        payload['test_token'] = result['test_token']
        return settings.save(self.conn, 'touch', payload)

    def collect(self, amount, day=2, month=11):
        with patch.object(revenue, 'fetch_touch_latest', return_value=('success', Decimal(amount), '')):
            return revenue.collect_supported_theaters(self.conn, '2026-10-29', '2026-10-29', account_ids=['a'],
                collected_at=datetime(2026, month, day, 12), skip_completed=False)

    def test_empty_catalog_still_lists_software_collectors(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        settings.initialize(conn)
        items = settings.inventory(conn)['items']
        self.assertEqual({item["id"] for item in revenue.collectors.definitions()}, {item["id"] for item in items})
        self.assertTrue(all(item['revision'] == 0 for item in items))
        self.assertEqual('https://scnrzu35lckk.feishu.cn/share/base/query/shrcnCXYADPz9wc4apC1pZ6Fvvb', next(item for item in items if item['id'] == 'huasheng')['source_url'])

    def test_preview_leaves_financial_progress_and_bindings_unchanged(self):
        tables = ['v2_daily_revenues', 'v2_revenue_collection_attempts', 'v3_revenue_backfills', 'v3_revenue_cumulative_snapshots', 'v3_theater_revenue_collectors', 'v3_account_revenue_collectors']
        before = {table: self.conn.execute(f'SELECT * FROM {table}').fetchall() for table in tables}
        with patch.object(revenue, '_fetch', return_value=('success', Decimal('12.34'), '', [])):
            result = settings.preview(self.conn, 'touch', self.payload(source_url='https://c3andggd.yichafen.com/qz/newMonth'))
        self.assertTrue(result['passed'])
        self.assertEqual('12.34', result['amount'])
        self.assertEqual(before, {table: self.conn.execute(f'SELECT * FROM {table}').fetchall() for table in tables})
        self.assertEqual(0, settings.current(self.conn, 'touch')['revision'])

    def test_untested_changed_link_is_not_activated(self):
        with self.assertRaisesRegex(ValueError, '先测试'):
            settings.save(self.conn, 'touch', self.payload(source_url='https://c3andggd.yichafen.com/qz/newMonth'))
        self.assertEqual(0, settings.current(self.conn, 'touch')['revision'])

    def test_test_a_cannot_activate_b(self):
        payload = self.payload(source_url='https://c3andggd.yichafen.com/qz/linkA')
        with patch.object(revenue, '_fetch', return_value=('success', Decimal('1'), '', [])):
            result = settings.preview(self.conn, 'touch', payload)
        with self.assertRaisesRegex(ValueError, '先测试'):
            settings.save(self.conn, 'touch', {**payload, 'source_url': 'https://c3andggd.yichafen.com/qz/linkB', 'test_token': result['test_token']})

    def test_failed_and_normal_empty_test_dont_issue_activation_token(self):
        for status in ['failed', 'no_data', 'indeterminate']:
            with self.subTest(status=status), patch.object(revenue, '_fetch', return_value=(status, None, 'fixture', [])):
                result = settings.preview(self.conn, 'touch', self.payload())
                self.assertFalse(result['passed'])
                self.assertEqual('', result['test_token'])
        self.assertEqual(0, settings.current(self.conn, 'touch')['revision'])

    def test_zero_is_valid_only_if_adapter_explicitly_returns_success(self):
        with patch.object(revenue, '_fetch', return_value=('success', Decimal('0'), '', [])):
            self.assertTrue(settings.preview(self.conn, 'touch', self.payload())['passed'])

    def test_nan_negative_or_missing_amount_cannot_pass(self):
        for amount in [None, Decimal('NaN'), Decimal('-1')]:
            with patch.object(revenue, '_fetch', return_value=('success', amount, '', [])):
                self.assertFalse(settings.preview(self.conn, 'touch', self.payload())['passed'])

    def test_saved_configuration_persists_and_bindings_are_stable(self):
        saved = self.activate(source_url='https://c3andggd.yichafen.com/qz/newMonth')
        self.assertEqual(1, saved['revision'])
        other = service.connection()
        self.addCleanup(other.close)
        self.assertEqual(saved, settings.current(other, 'touch'))
        self.assertEqual('touch', revenue.collectors.account_id(other, 'a', 't'))
        history = next(item for item in settings.inventory(other)['items'] if item['id'] == 'touch')['history']
        self.assertEqual([1, 0], [item['revision'] for item in history])

    def test_stale_window_and_expired_token_rejected(self):
        payload = self.payload(source_url='https://c3andggd.yichafen.com/qz/newMonth')
        with patch.object(revenue, '_fetch', return_value=('success', Decimal('1'), '', [])):
            result = settings.preview(self.conn, 'touch', payload)
        with self.conn:
            self.conn.execute("UPDATE v3_revenue_query_tests SET expires_at='2000-01-01'")
        with self.assertRaisesRegex(ValueError, '先测试'):
            settings.save(self.conn, 'touch', {**payload, 'test_token': result['test_token']})
        settings.save(self.conn, 'touch', self.payload(enabled=False))
        with self.assertRaisesRegex(ValueError, '其他窗口'):
            settings.save(self.conn, 'touch', payload)
        with self.assertRaisesRegex(ValueError, '其他窗口'):
            settings.preview(self.conn, 'touch', payload)

    def test_restore_builtin_link_requires_retest_and_appends_history(self):
        self.activate(source_url='https://c3andggd.yichafen.com/qz/newMonth')
        with self.assertRaises(ValueError):
            settings.save(self.conn, 'touch', self.payload())
        saved = self.activate()
        self.assertEqual(2, saved['revision'])
        self.assertEqual(settings.default_config('touch')['source_url'], saved['source_url'])
        self.assertEqual(2, self.conn.execute('SELECT count(*) FROM v3_revenue_query_revisions').fetchone()[0])

    def test_disable_does_not_query_or_delete_data(self):
        self.collect('100')
        settings.save(self.conn, 'touch', self.payload(enabled=False))
        with patch.object(revenue, '_fetch') as fetch:
            result = revenue.collect_supported_theaters(self.conn, '2026-10-30', '2026-10-31', account_ids=['a'], initial_backfill=True, collected_at=datetime(2026,11,3,12))
        fetch.assert_not_called()
        self.assertEqual(1, len(result['items']))
        self.assertIn('停用', result['items'][0]['message'])
        self.assertEqual('100.00', self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])
        self.assertEqual('touch', revenue.collectors.account_id(self.conn, 'a', 't'))
        with self.assertRaisesRegex(ValueError, '先测试'):
            settings.save(self.conn, 'touch', self.payload(enabled=True))

    def test_unknown_period_relabel_uses_old_baseline_without_double_credit(self):
        self.collect('100')
        self.activate(source_period='2026-11')
        result = self.collect('110', day=3)
        self.assertEqual('10.00', result['items'][0]['amount'])
        self.assertEqual('2026-11', result['items'][0]['source_period'])

    def test_same_day_period_relabel_does_not_add_old_credit_twice(self):
        self.collect('100')
        self.activate(source_period='2026-11')
        result = self.collect('110')
        self.assertEqual('10.00', result['items'][0]['amount'])
        self.assertEqual('110.00', self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])

    def test_different_month_has_own_baseline_not_old_total(self):
        self.activate(source_period='2026-10')
        self.collect('100', day=31, month=10)
        self.activate(source_period='2026-11', period_relation='new', source_url='https://c3andggd.yichafen.com/qz/nextMonth')
        result = self.collect('5')
        self.assertEqual('5.00', result['items'][0]['amount'])

    def test_cannot_silently_treat_different_month_as_same(self):
        self.activate(source_period='2026-10')
        with self.assertRaisesRegex(ValueError, '不同月份'):
            settings.preview(self.conn, 'touch', self.payload(source_period='2026-11'))

    def test_malicious_and_incompatible_links_are_rejected_before_network(self):
        urls = ['http://c3andggd.yichafen.com/qz/a', 'https://127.0.0.1/qz/a', 'file:///etc/passwd',
                'https://c3andggd.yichafen.com.evil.test/qz/a', 'https://evil@c3andggd.yichafen.com/qz/a',
                'https://c3andggd.yichafen.com:8443/qz/a', 'https://c3andggd.yichafen.com/qz/a#x',
                'https://c3andggd.yichafen.com/other', 'https://c3andggd.yichafen.com/qz/aaa\\@evil.test']
        with patch.object(revenue, '_fetch') as fetch:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    settings.preview(self.conn, 'touch', self.payload(source_url=url))
        fetch.assert_not_called()

    def test_runtime_rejects_foreign_origin_and_redirects(self):
        token = settings.ACTIVE.set({**settings.default_config('touch'), 'collector_id': 'touch'})
        self.addCleanup(settings.ACTIVE.reset, token)
        with self.assertRaisesRegex(ValueError, '超出'):
            settings.SafeOpener().open('https://127.0.0.1/private')
        with self.assertRaisesRegex(ValueError, '跳转'):
            settings.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test')

    def test_actual_touch_requests_use_configured_link_not_old_link(self):
        link = 'https://c3andggd.yichafen.com/qz/configuredLink'
        self.activate(source_url=link)
        spec = settings.effective_spec(self.conn, revenue.collectors.definition('touch'))
        opener = MagicMock()
        def response(text):
            value = MagicMock(); value.__enter__.return_value.read.return_value = text.encode(); return value
        opener.open.side_effect = [response('sqcode="fixture-token"'), response('{"status":1}'), response('<td>广告收益</td><td>8.88</td>')]
        with patch.object(settings, 'build_opener', return_value=opener):
            result = revenue._fetch({'channel_id':'fixture-channel'}, 'touch', '2026-11-01', spec, 'unknown')
        self.assertEqual('success', result[0])
        self.assertEqual(link, opener.open.call_args_list[0].args[0].full_url)
        self.assertIsNone(settings.ACTIVE.get())

    def test_feishu_new_token_used_and_changed_schema_is_not_zero(self):
        config = {**settings.default_config('huasheng'), 'source_url': 'https://scnrzu35lckk.feishu.cn/share/base/query/shrcnNewToken', 'collector_id':'huasheng'}
        token = settings.ACTIVE.set(config)
        self.addCleanup(settings.ACTIVE.reset, token)
        opener = MagicMock()
        def response(payload):
            value=MagicMock(); value.__enter__.return_value.read.return_value=json.dumps(payload).encode(); return value
        opener.open.side_effect=[response({}),response({'code':0,'data':{}}),response({'code':0,'data':{'total':1,'recordMap':{}}})]
        with patch.object(settings,'build_opener',return_value=opener):
            status, amount, _ = revenue.fetch_huasheng_latest('fixture-channel')
        self.assertEqual('failed',status)
        self.assertIsNone(amount)
        self.assertEqual('shrcnNewToken',json.loads(opener.open.call_args_list[1].args[0].data)['shareToken'])

    def test_feishu_requires_exact_account_match_and_recognized_revenue(self):
        config = {**settings.default_config('huasheng'), 'collector_id':'huasheng'}
        token = settings.ACTIVE.set(config)
        self.addCleanup(settings.ACTIVE.reset, token)
        def response(payload):
            value=MagicMock(); value.__enter__.return_value.read.return_value=json.dumps(payload).encode(); return value
        rows = [{'fields':{'fld3P2QILX':[{'text':'fixture-channel'}],'fld4Za6Nvm':'12.34'}},
                {'fields':{'fld3P2QILX':'fixture-channel-other','fld4Za6Nvm':'999'}}]
        opener=MagicMock()
        opener.open.side_effect=[response({}),response({'code':0,'data':{}}),response({'code':0,'data':{'total':2,'records':rows}})]
        with patch.object(settings,'build_opener',return_value=opener):
            self.assertEqual(('success',Decimal('12.34'),''),revenue.fetch_huasheng_latest('fixture-channel'))

    def test_dinghao_and_green_page_are_checked_even_with_working_api(self):
        for collector_id in ['dinghao','qingning_lpp']:
            opener=MagicMock(); response=MagicMock()
            response.__enter__.return_value.read.return_value=b'<html>incompatible page</html>'
            opener.open.return_value=response
            candidate={**settings.default_config(collector_id),'revision':0,'channel_id':'fixture-channel','query_date':'2026-11-01'}
            with patch.object(settings,'build_opener',return_value=opener),patch.object(revenue,'_fetch') as fetch:
                result=settings.preview(self.conn,collector_id,candidate)
            self.assertFalse(result['passed'])
            fetch.assert_not_called()
            self.assertEqual(candidate['source_url'],opener.open.call_args.args[0].full_url)

    def test_native_url_flows_into_actual_post_request(self):
        config={**settings.default_config('qingning'),'source_url':'https://vd.xingvan.com/newNative.html','collector_id':'qingning'}
        opener=MagicMock(); response=MagicMock()
        response.__enter__.return_value.read.return_value='暂时还没有数据'.encode()
        response.__enter__.return_value.headers.get_content_charset.return_value='utf-8'
        opener.open.return_value=response
        spec={**revenue.collectors.definition('qingning'),'_query_settings':config}
        with patch.object(settings,'build_opener',return_value=opener):
            result=revenue._fetch({'channel_id':'fixture-channel'},'qingning','2026-11-01',spec,'')
        self.assertEqual('no_data',result[0])
        self.assertEqual(config['source_url'],opener.open.call_args.args[0].full_url)
        self.assertIn(b'spfindid=fixture-channel',opener.open.call_args.args[0].data)

    def test_source_context_does_not_leak_after_parser_exception(self):
        spec=settings.effective_spec(self.conn,revenue.collectors.definition('touch'))
        with patch.object(revenue,'_fetch_impl',side_effect=RuntimeError('offline')),self.assertRaises(RuntimeError):
            revenue._fetch({'channel_id':'fixture-channel'},'touch','2026-11-01',spec,'unknown')
        self.assertIsNone(settings.ACTIVE.get())

    def test_today_cannot_be_tested(self):
        with patch.object(settings,'now',return_value=datetime(2026,11,3,8,tzinfo=timezone.utc)),self.assertRaisesRegex(ValueError,'昨天'):
            settings.preview(self.conn,'touch',self.payload(query_date='2026-11-03'))


if __name__ == '__main__':
    unittest.main()
