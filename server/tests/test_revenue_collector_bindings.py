"""Software-owned collector routing with isolated catalog data."""
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service
from server import v2_revenue_service as revenue
from server import revenue_collectors as collectors


class CollectorBindingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in [('WORKSPACE', root/'workspace'), ('DATA_ROOT', root/'data'), ('DATABASE_INITIALIZED_PATH', None)]:
            obj = patch.object(service, name, value)
            obj.start()
            self.addCleanup(obj.stop)

    def theater(self, name='自定义剧场', ids=None):
        data = {'name': name, 'default_commission_rate': 40, 'default_tax_rate': 6}
        if ids is not None:
            data['revenue_collector_ids'] = ids
        return service.create_theater(data)

    def account(self, theater, collector='', **extra):
        return service.create_account({'nickname': '测试账号', 'channel_id': 'channel-test', 'theater_id': theater['id'], 'revenue_collector_id': collector, **extra})

    def test_software_definitions_exist_without_any_user_theater(self):
        with closing(service.connection()) as conn:
            result = revenue.revenue_collector_inventory(conn)
        self.assertEqual([], result['items'])
        self.assertEqual({'qingning', 'qingning_lpp', 'dinghao', 'touch', 'huasheng', 'pingyue', 'kujiang_iaa', 'kujiang_self', 'kujiang_lpp', 'kujiang_native', 'guyan_native', 'zishi_expert', 'zishi_agency', 'zishi_expert_iaa', 'zishi_lpp'}, {item['id'] for item in result['definitions']})
        self.assertTrue(all(item['aliases'] for item in result['definitions']))

    def test_name_does_not_automatically_bind_and_empty_confirmation_survives(self):
        theater = self.theater('青柠端')
        self.assertEqual([], theater['revenue_collector_ids'])
        self.assertFalse(theater['revenue_collectors_confirmed'])
        updated = service.update_theater(theater['id'], {'revenue_collector_ids': []})
        self.assertTrue(updated['revenue_collectors_confirmed'])
        self.assertEqual([], service.list_theaters()['items'][0]['revenue_collector_ids'])
        self.assertTrue(service.list_theaters()['items'][0]['revenue_collectors_confirmed'])

    def test_rename_retains_fixed_ids_and_collection_uses_account_choice(self):
        theater = self.theater('任意名称', ['qingning', 'dinghao'])
        account = self.account(theater, 'qingning')
        service.update_theater(theater['id'], {'name': '改名以后'})
        self.assertEqual('qingning', service.get_account(account['id'])['revenue_collector_id'])
        with closing(service.connection()) as conn, patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('2.50'), [])) as q, patch.object(revenue, 'fetch_dinghao_day') as d:
            result = revenue.collect_supported_theaters(conn, '2026-08-28', '2026-08-28', ['改名以后'], collected_at=datetime(2026, 8, 29, 10))
        self.assertEqual('success', result['items'][0]['status'])
        self.assertEqual(1, q.call_count)
        d.assert_not_called()

    def test_cross_theater_selection_is_rejected_atomically(self):
        theater = self.theater(ids=['qingning'])
        account = self.account(theater, 'qingning')
        with self.assertRaisesRegex(ValueError, '未关联'):
            service.update_account(account['id'], {'nickname': '不应保存', 'revenue_collector_id': 'touch'})
        current = service.get_account(account['id'])
        self.assertEqual('测试账号', current['nickname'])
        self.assertEqual('qingning', current['revenue_collector_id'])

    def test_change_theater_clears_selection_even_if_both_offer_same_collector(self):
        first = self.theater('甲', ['qingning'])
        second = self.theater('乙', ['qingning'])
        account = self.account(first, 'qingning')
        updated = service.update_account(account['id'], {'theater_id': second['id']})
        self.assertEqual('', updated['revenue_collector_id'])
        self.assertEqual(second['id'], updated['theater_id'])

    def test_removing_theater_collector_clears_choice_and_preserves_financial_history(self):
        theater = self.theater(ids=['qingning', 'touch'])
        account = self.account(theater, 'qingning')
        with closing(service.connection()) as conn, patch.object(revenue, 'fetch_qingning_day_details', return_value=(revenue.Decimal('2.50'), [])):
            revenue.collect_supported_theaters(conn, '2026-08-28', '2026-08-28', collected_at=datetime(2026, 8, 29, 10))
        service.update_theater(theater['id'], {'revenue_collector_ids': ['touch']})
        self.assertEqual('', service.get_account(account['id'])['revenue_collector_id'])
        with closing(service.connection()) as conn:
            self.assertEqual('2.50', conn.execute('SELECT amount FROM v2_daily_revenues WHERE account_id=?', (account['id'],)).fetchone()[0])

    def test_unconfigured_account_fails_without_network_or_fake_zero(self):
        theater = self.theater('青柠剧场', ['qingning'])
        self.account(theater)
        with closing(service.connection()) as conn, patch.object(revenue, 'fetch_qingning_day_details') as fetch:
            result = revenue.collect_supported_theaters(conn, '2026-08-28', '2026-08-28', collected_at=datetime(2026, 8, 29, 10))
            self.assertEqual(0, conn.execute('SELECT COUNT(*) FROM v2_daily_revenues').fetchone()[0])
        fetch.assert_not_called()
        self.assertEqual('failed', result['items'][0]['status'])
        self.assertIsNone(result['items'][0]['amount'])
        self.assertIn('待配置', result['items'][0]['message'])

    def test_create_rejects_unknown_implementation_without_creating_record(self):
        with self.assertRaisesRegex(ValueError, '已有'):
            self.theater(ids=['zishi_unimplemented'])
        self.assertEqual([], service.list_theaters()['items'])

    def test_narrow_patch_preserves_other_fields_and_list_get_return_binding(self):
        theater = self.theater(ids=['qingning'])
        account = self.account(theater, notes='保留备注', reporting_date='2026-01-02', registration_date='2026-01-01')
        updated = service.update_account(account['id'], {'revenue_collector_id': 'qingning'})
        self.assertEqual('保留备注', updated['notes'])
        self.assertEqual('2026-01-02', updated['reporting_date'])
        self.assertEqual('2026-01-01', updated['registration_date'])
        self.assertEqual('qingning', service.list_accounts()['items'][0]['revenue_collector_id'])

    def test_batch_theater_and_account_respect_explicit_bindings(self):
        result = service.create_theaters_batch({'items': [{'name':'批量剧场','revenue_collector_ids':['qingning']}, {'name':'未配置剧场'}]})
        by_name = {item['name']:item for item in result['items']}
        self.assertTrue(by_name['批量剧场']['revenue_collectors_confirmed'])
        self.assertFalse(by_name['未配置剧场']['revenue_collectors_confirmed'])
        accounts = service.create_accounts_batch({'items':[{'nickname':'批量账号','channel_id':'batch-channel','theater_name':'批量剧场','revenue_collector_id':'qingning'}]})
        self.assertEqual('qingning', accounts['items'][0]['revenue_collector_id'])

    def test_reopen_current_schema_keeps_confirmation_and_account_binding(self):
        theater = self.theater(ids=['qingning'])
        account = self.account(theater, 'qingning')
        with patch.object(service, 'DATABASE_INITIALIZED_PATH', None):
            self.assertEqual('qingning', service.get_account(account['id'])['revenue_collector_id'])
        self.assertTrue(service.list_theaters()['items'][0]['revenue_collectors_confirmed'])


if __name__ == '__main__':
    unittest.main()
