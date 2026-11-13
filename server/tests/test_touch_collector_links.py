"""Collector URLs, fixed identity, and explicit verification failure; offline."""
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs
from server import revenue_collectors as collectors
from server import v2_revenue_service as revenue


class TouchCollectorLinkTests(unittest.TestCase):
    def response(self, text):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = text.encode('utf-8')
        return response

    def test_touch_renamed_with_stable_identity_and_registered_link(self):
        spec = collectors.definition('touch')
        self.assertEqual('touch', spec['id'])
        self.assertEqual('触摸端原生/IAA', spec['name'])
        self.assertEqual('https://c3andggd.yichafen.com/qz/167SsX4Q2t', spec['source_url'])
        self.assertIn('触摸端原生/IAA', spec['aliases'])
        self.assertIn('触摸剧场', spec['aliases'])
        self.assertFalse(spec['supports_month_query'])
        self.assertFalse(spec['runtime_verified'])

    def test_qingning_links_match_current_actual_query_functions(self):
        native = collectors.definition('qingning')
        green = collectors.definition('qingning_lpp')
        self.assertEqual('https://vd.xingvan.com/duangg.html', native['source_url'])
        self.assertEqual(native['source_url'], revenue.SOURCE_URL)
        self.assertEqual('https://vd.xingvan.com/lpp.html', green['source_url'])
        self.assertEqual('https://vd.xingvan.com/index.php?s=Home/Home/orderlookupquery', revenue.QINGNING_LPP_URL)
        self.assertEqual('青柠端原生', native['name'])
        self.assertEqual('青柠绿泡泡', green['name'])

    def test_touch_uses_registered_page_and_current_form_field(self):
        opener = MagicMock()
        opener.open.side_effect = [
            self.response('<form><input name="s_shipinhaoid"></form><script>$.post("/public/verifycondition/sqcode/fixture-token/from_device/mobile.html")</script>'),
            self.response(json.dumps({'status':1})),
            self.response('<table><tr><td>广告收益</td><td>12.34</td></tr></table>'),
        ]
        with patch.object(revenue,'build_opener',return_value=opener):
            result = revenue.fetch_touch_latest('fixture-channel')
        self.assertEqual(('success',Decimal('12.34'),''), result)
        calls = opener.open.call_args_list
        self.assertEqual(collectors.definition('touch')['source_url'], calls[0].args[0].full_url)
        self.assertEqual('https://c3andggd.yichafen.com/public/verifycondition/sqcode/fixture-token/from_device/mobile.html', calls[1].args[0].full_url)
        self.assertEqual({'s_shipinhaoid':['fixture-channel']}, parse_qs(calls[1].args[0].data.decode()))

    def test_captcha_does_not_fetch_results_or_become_no_data(self):
        opener = MagicMock()
        opener.open.side_effect = [self.response('"/public/verifycondition/sqcode/fixture-token/from_device/mobile.html"'), self.response(json.dumps({'status':0,'captchaRequired':True,'errNo':100}))]
        with patch.object(revenue,'build_opener',return_value=opener):
            status, amount, message = revenue.fetch_touch_latest('fixture-channel')
        self.assertEqual('failed',status)
        self.assertIsNone(amount)
        self.assertIn('人工验证码',message)
        self.assertEqual(2,opener.open.call_count)


if __name__ == '__main__':
    unittest.main()
