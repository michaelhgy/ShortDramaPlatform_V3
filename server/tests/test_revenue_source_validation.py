"""Source failures and malformed amounts must never become successful empty days."""
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock,patch
from server import v2_revenue_service as revenue


def response(text):
    result=MagicMock()
    result.__enter__.return_value.read.return_value=text.encode('utf-8')
    result.__enter__.return_value.headers.get_content_charset.return_value='utf-8'
    return result


class SourceValidationTests(unittest.TestCase):
    def test_qingning_blank_or_garbled_numeric_cells_fail_before_empty_boundary(self):
        for cell in ['', '--', '接口错误500', '-1.00', 'NaN']:
            html=f'<table><tr><td>1</td><td>x</td><td>v</td><td>剧目</td><td>12</td><td>12</td><td>{cell}</td></tr></table>共1条记录'
            with self.subTest(cell=cell),patch.object(revenue,'_source_open',return_value=response(html)):
                with self.assertRaises(revenue.RevenueError):revenue.fetch_qingning_day_details('sph-test','2026-11-04')

    def test_qingning_display_format_and_explicit_zero_are_preserved(self):
        self.assertEqual(Decimal('1234.56'),revenue._amount('￥1,234.56 元'))
        self.assertEqual(Decimal('0.00'),revenue._amount('0.00'))

    def test_touch_negative_blank_or_duplicate_amounts_are_not_read_as_positive(self):
        for cells in [['-1.00'],[''],['--'],['维护500'],['1.00','2.00']]:
            opener=MagicMock()
            html='<table>'+''.join(f'<tr><td>广告收益</td><td>{value}</td></tr>' for value in cells)+'</table>'
            opener.open.side_effect=[response('"/public/verifycondition/sqcode/test/from_device/mobile.html"'),response(json.dumps({'status':1})),response(html)]
            with self.subTest(cells=cells),patch.object(revenue,'_source_opener',return_value=opener):
                status,amount,_=revenue.fetch_touch_latest('sph-test')
            self.assertEqual('failed',status);self.assertIsNone(amount)

    def test_huasheng_incomplete_results_are_not_normal_empty(self):
        for data in [{}, {'total':None}, {'total':False}, {'total':0,'hasMore':True},
                     {'total':0,'recordMap':{'r':{'value':1}}}, {'total':1,'recordMap':{}}]:
            opener=MagicMock()
            opener.open.side_effect=[response('source'),response(json.dumps({'code':0,'data':{}})),response(json.dumps({'code':0,'data':data}))]
            with self.subTest(data=data),patch.object(revenue,'_source_opener',return_value=opener):
                status,amount,_=revenue.fetch_huasheng_latest('sph-test')
            self.assertEqual('failed',status);self.assertIsNone(amount)

    def test_huasheng_explicit_complete_empty_and_positive_results(self):
        row={'fld3P2QILX':{'value':[{'text':'sph-test'}]},'fld4Za6Nvm':{'value':'12.34'}}
        for data,expected in [({'total':0,'recordMap':{},'hasMore':False},('no_data',None)),
                              ({'total':1,'recordMap':{'r':row},'hasMore':False},('success',Decimal('12.34')))]:
            opener=MagicMock()
            opener.open.side_effect=[response('source'),response(json.dumps({'code':0,'data':{}})),response(json.dumps({'code':0,'data':data}))]
            with self.subTest(data=data),patch.object(revenue,'_source_opener',return_value=opener):
                status,amount,_=revenue.fetch_huasheng_latest('sph-test')
            self.assertEqual(expected,(status,amount))


if __name__=='__main__':unittest.main()
