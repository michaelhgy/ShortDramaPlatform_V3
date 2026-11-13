"""Native collector identities and green-bubble daily accounting; no real network."""
import json
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

from server import v2_file_service as service
from server import v2_revenue_service as revenue
from server import revenue_collectors as collectors


def sample():
    return {'ok': True, 'rows': [
        {'drama_name': '剧目甲', 'amount': 3.04, 'video_count': 5},
        {'drama_name': '剧目乙', 'amount': 0.66, 'video_count': 14},
    ], 'total': 3.7, 'count': 2, 'channel_count': 1}


class SourceParserTests(unittest.TestCase):
    def test_named_native_ids_remain_stable_and_green_is_separate(self):
        definitions = {item['id']:item for item in collectors.definitions()}
        self.assertEqual('青柠端原生', definitions['qingning']['name'])
        self.assertEqual('顶好端原生', definitions['dinghao']['name'])
        self.assertEqual('青柠绿泡泡', definitions['qingning_lpp']['name'])
        self.assertEqual('day', definitions['qingning_lpp']['date_precision'])
        self.assertFalse(definitions['qingning_lpp']['supports_detail'])
        self.assertIn('青柠', definitions['qingning_lpp']['aliases'])
        self.assertNotIn('青柠端', definitions['qingning_lpp']['aliases'])

    def test_green_positive_total_agrees_with_drama_rows(self):
        status, amount, message = revenue.parse_qingning_lpp_result(sample())
        self.assertEqual(('success', Decimal('3.70'), ''), (status, amount, message))

    def test_green_empty_is_no_data_not_a_zero_amount(self):
        status, amount, message = revenue.parse_qingning_lpp_result({'ok':True,'rows':[],'total':0,'count':0,'channel_count':1})
        self.assertEqual('no_data', status)
        self.assertIsNone(amount)
        self.assertIn('正常返回', message)

    def test_explicit_record_with_zero_is_success(self):
        value = sample()
        value['total'] = 0
        for row in value['rows']: row['amount'] = 0
        self.assertEqual(('success', Decimal('0.00'), ''), revenue.parse_qingning_lpp_result(value))

    def test_malformed_or_partial_responses_do_not_become_zero(self):
        variants = [None, [], {}, {'ok':False,'message':'查询暂不可用'}]
        for key, value in [('rows',{}), ('count',3), ('count',True), ('channel_count',2), ('channel_count',True), ('total',None), ('total','--'), ('total','NaN'), ('total',True), ('total',-1)]:
            item = sample(); item[key] = value; variants.append(item)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(revenue.RevenueError):
                revenue.parse_qingning_lpp_result(value)

    def test_partial_or_invalid_drama_rows_fail(self):
        for key, value in [('amount',None), ('amount','0abc'), ('amount',float('inf')), ('video_count','5'), ('video_count',-1), ('drama_name','')]:
            item = sample(); item['rows'][0][key] = value
            with self.subTest(key=key,value=value), self.assertRaises(revenue.RevenueError):
                revenue.parse_qingning_lpp_result(item)
        item = sample(); item['total'] = 3.71
        with self.assertRaisesRegex(revenue.RevenueError, '不一致'):
            revenue.parse_qingning_lpp_result(item)
        with self.assertRaisesRegex(revenue.RevenueError, '不一致'):
            revenue.parse_qingning_lpp_result({'ok':True,'rows':[],'total':1,'count':0,'channel_count':1})

    def test_green_request_is_one_account_one_day_and_read_only_endpoint(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(sample()).encode()
        with patch.object(revenue, 'urlopen', return_value=response) as request:
            result = revenue.fetch_qingning_lpp_day('channel-1', '2026-10-31')
        self.assertEqual(('success',Decimal('3.70'),''),result)
        sent = request.call_args.args[0]
        self.assertEqual(revenue.QINGNING_LPP_URL, sent.full_url)
        self.assertEqual({'spfindid':['channel-1'],'start_date':['2026-10-31'],'end_date':['2026-10-31']}, parse_qs(sent.data.decode()))
        self.assertNotIn('registration', sent.full_url)

    def test_green_failure_network_and_invalid_json_have_no_amount(self):
        for exception in [TimeoutError('timeout'), ValueError('invalid JSON')]:
            with patch.object(revenue,'urlopen',side_effect=exception):
                result = revenue.fetch_qingning_lpp_day('channel-1','2026-10-31')
            self.assertEqual('failed',result[0]); self.assertIsNone(result[1])
        response = MagicMock(); response.__enter__.return_value.read.return_value = b'<html>maintenance</html>'
        with patch.object(revenue,'urlopen',return_value=response):
            self.assertEqual('failed',revenue.fetch_qingning_lpp_day('channel-1','2026-10-31')[0])

    def test_green_rejects_multiple_ids_without_network(self):
        with patch.object(revenue,'urlopen') as request:
            for value in ['', 'a,b', 'a b', 'a，b', 'a\nb']:
                self.assertEqual('failed', revenue.fetch_qingning_lpp_day(value,'2026-10-31')[0])
        request.assert_not_called()

    def test_dinghao_uses_native_advertising_endpoint_and_full_day(self):
        with patch.object(revenue,'_post_json',return_value={'status_code':1,'data':{'amount':'12.34'}}) as request:
            self.assertEqual(('success',Decimal('12.34'),''),revenue.fetch_dinghao_day('channel-d','2026-10-31'))
        url, payload = request.call_args.args
        self.assertEqual('https://zyu.wozhangwan.com/api/api/order/getVideoAdIncome',url)
        self.assertEqual('2026-10-31 00:00:00',payload['income_date_start'])
        self.assertEqual('2026-10-31 23:59:59',payload['income_date_end'])
        self.assertEqual('channel-d',payload['advertiser_id'])
        self.assertNotIn('account_id',payload)

    def test_dinghao_source_zero_is_normal_empty_and_invalid_values_fail(self):
        with patch.object(revenue,'_post_json',return_value={'status_code':1,'data':{'amount':'0.00'}}):
            status, amount, message = revenue.fetch_dinghao_day('x','2026-10-31')
            self.assertEqual('no_data',status)
            self.assertIsNone(amount)
            self.assertIn('没有收益记录',message)
            self.assertTrue(revenue._is_empty('dinghao',status,amount))
        for value in [None, [], {'status_code':0}, {'status_code':True,'data':{'amount':1}}, {'status_code':1}, {'status_code':1,'data':{}}, *[{'status_code':1,'data':{'amount':amount}} for amount in [None,'','--','abc0','NaN',True,-1]]]:
            with self.subTest(value=value), patch.object(revenue,'_post_json',return_value=value):
                status, amount, message = revenue.fetch_dinghao_day('x','2026-10-31')
                self.assertEqual('failed',status); self.assertIsNone(amount)


class GreenCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name,value in [('WORKSPACE',root/'workspace'),('DATA_ROOT',root/'data'),('DATABASE_INITIALIZED_PATH',None)]:
            obj = patch.object(service,name,value); obj.start(); self.addCleanup(obj.stop)
        self.theater = service.create_theater({'name':'青柠端与绿泡泡自定名称','revenue_collector_ids':['qingning','qingning_lpp']})
        self.account = service.create_account({'nickname':'绿泡泡测试','channel_id':'fixture-lpp','theater_id':self.theater['id'],'revenue_collector_id':'qingning_lpp'})
        self.conn = service.connection(); self.addCleanup(self.conn.close)

    def collect(self, **kwargs):
        return revenue.collect_supported_theaters(self.conn,'2026-11-02','2026-11-02',collected_at=datetime(2026,11,3,10),**kwargs)

    def test_selection_routes_green_only_and_persists_daily_without_video_details(self):
        with patch.object(revenue,'fetch_qingning_lpp_day',return_value=('success',Decimal('3.70'),'')) as green, patch.object(revenue,'fetch_qingning_day_details') as native:
            result = self.collect()
        self.assertEqual(1,green.call_count); native.assert_not_called()
        self.assertEqual('success',result['items'][0]['status'])
        self.assertEqual(('2026-11-02','3.70'),tuple(self.conn.execute('SELECT revenue_date,amount FROM v2_daily_revenues').fetchone()))
        self.assertEqual(0,self.conn.execute('SELECT COUNT(*) FROM v2_revenue_video_details').fetchone()[0])
        self.assertEqual('qingning_lpp',self.conn.execute('SELECT adapter_key FROM v2_revenue_collection_attempts').fetchone()[0])
        self.assertTrue(revenue.revenue_source_data(self.conn)['rows'])

    def test_completed_day_not_requested_again(self):
        with patch.object(revenue,'fetch_qingning_lpp_day',return_value=('success',Decimal('3.70'),'')) as green:
            self.collect(skip_completed=True); self.collect(skip_completed=True)
        self.assertEqual(1,green.call_count)
        self.assertEqual(1,self.conn.execute('SELECT COUNT(*) FROM v2_revenue_collection_attempts').fetchone()[0])

    def test_first_backfill_stops_after_seven_explicit_empty_days_without_fake_zero(self):
        with patch.object(revenue,'fetch_qingning_lpp_day',return_value=('no_data',None,'正常空记录')) as green:
            result = self.collect(initial_backfill=True,skip_completed=True)
            self.assertEqual(7,green.call_count)
            self.assertTrue(result['backfills'][0]['complete'])
            self.assertEqual('2026-10-27',result['backfills'][0]['boundary_date'])
            self.collect(initial_backfill=True,skip_completed=True)
            self.assertEqual(7,green.call_count)
        self.assertEqual(0,self.conn.execute('SELECT COUNT(*) FROM v2_daily_revenues').fetchone()[0])

    def test_failures_do_not_count_as_empty_and_history_resumes(self):
        with patch.object(revenue,'fetch_qingning_lpp_day',side_effect=[('failed',None,'维护中')]+[('no_data',None,'正常空记录')]*7):
            result = self.collect(initial_backfill=True,skip_completed=True,max_initial_days=8)
        self.assertFalse(result['backfills'][0]['complete'])
        with patch.object(revenue,'fetch_qingning_lpp_day',return_value=('no_data',None,'正常空记录')) as green:
            result = self.collect(initial_backfill=True,skip_completed=True,max_initial_days=8)
        self.assertTrue(result['backfills'][0]['complete'])
        self.assertEqual(1,green.call_count)

    def test_native_completion_does_not_skip_green_after_explicit_switch(self):
        service.update_account(self.account['id'],{'revenue_collector_id':'qingning'})
        with patch.object(revenue,'fetch_qingning_day_details',return_value=(Decimal('1.00'),[])):
            self.collect(skip_completed=True)
        service.update_account(self.account['id'],{'revenue_collector_id':'qingning_lpp'})
        with patch.object(revenue,'fetch_qingning_lpp_day',return_value=('success',Decimal('3.70'),'')) as green:
            self.collect(skip_completed=True)
        self.assertEqual(1,green.call_count)
        self.assertEqual({'qingning','qingning_lpp'},{row[0] for row in self.conn.execute('SELECT adapter_key FROM v2_revenue_collection_attempts')})

    def test_registry_names_flow_into_theater_and_account_without_migration(self):
        self.assertEqual(['qingning','qingning_lpp'],service.list_theaters()['items'][0]['revenue_collector_ids'])
        self.assertEqual('qingning_lpp',service.get_account(self.account['id'])['revenue_collector_id'])
        definition = collectors.definition('qingning_lpp')
        self.assertEqual('青柠绿泡泡',definition['name'])
        self.assertEqual('day',definition['date_precision'])


if __name__ == '__main__':
    unittest.main()
