"""Zishi source dates, monthly/daily reconciliation, editable links and accounting."""
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server import zishi_collector as z, guyan_collector as g
from server import revenue_query_settings as q, revenue_collectors as c
from server import v2_revenue_service as revenue, v2_file_service as service

DAY = date(2026, 11, 5)
CHANNEL = "fixture-zishi"


def obs(label, amount):
    return z.observation(label, amount, DAY)


def share(label="至11.4当月收益"):
    return {"code": 0, "data": {"data": json.dumps({"fieldMap": {
        "a": {"name": "视频号ID", "type": 1}, "v": {"name": label, "type": 2},
        "hidden": {"name": "其他收益", "type": 2}},
        "queryFormViewProperty": {"fieldInfos": {"a": {"required": True, "visible": True}},
        "queryFormConfig": {"resultFieldInfos": [{"fieldId": "a", "permission": 1}, {"fieldId": "v", "permission": 1}]}}})}}


class ZishiParsingTests(unittest.TestCase):
    def test_four_independent_definitions_and_source_roles(self):
        self.assertEqual(4, len(c.ZISHI_TYPES))
        self.assertEqual("子诗达人IAA", c.definition("zishi_expert_iaa")["name"])
        self.assertTrue(q.default_config("zishi_expert_iaa")["source_url"].endswith("M1r0syY2Et"))
        self.assertFalse(c.definition("zishi_agency")["supports_month_query"])

    def test_daily_label_is_actual_third_not_assumed_fourth(self):
        value = obs("昨日11.3广告收益", "0.03")
        self.assertEqual("2026-11-03", value["source_date"])
        self.assertEqual("day", value["kind"])

    def test_month_cutoff_and_green_bubble_month(self):
        self.assertEqual(("month", "2026-11", "2026-11-04"), z.label_period("至11.4当月收益", DAY))
        self.assertEqual(("month", "2026-11", ""), z.label_period("11月绿泡泡挂载总收益", DAY))

    def test_rollover_and_leap_year_date_validation(self):
        self.assertEqual(("day", "2026-12", "2026-12-31"), z.label_period("昨日12.31广告收益", date(2027,1,2)))
        for label in ("昨日广告收益", "本月收益", "11.5广告收益", "11.6广告收益", "11.31广告收益"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                z.label_period(label, DAY)

    def test_invalid_money_is_never_zero(self):
        for value in (None, True, "", "NaN", "Infinity", "-1", "0.03元", "--", "1,2"):
            with self.subTest(value=value), self.assertRaises(ValueError): z.money(value)
        self.assertEqual(Decimal("0"), z.money("0"))
        self.assertEqual(Decimal("1234.56"), z.money("1,234.56"))

    def test_only_visible_income_column_and_exact_account(self):
        fields = z.resolve_fields(share("11.4广告收益"))
        rows = [{"a": {"value": [{"text": CHANNEL}]}, "v": {"value": "0.03"}},
                {"a": CHANNEL, "v": "0.02"}, {"a": CHANNEL+"x", "v": "999"}]
        self.assertEqual("0.05", z.parse_records(rows, fields, CHANNEL, DAY.isoformat())["amount"])
        self.assertIsNone(z.parse_records(rows, fields, "other", DAY.isoformat()))
        with self.assertRaises(ValueError): z.parse_records(rows, z.resolve_fields(share()), CHANNEL, DAY.isoformat())

    def test_html_result_requires_matching_id_and_unique_income(self):
        html = f'<tr><td>视频号ID</td><td>{CHANNEL}</td></tr><tr><td>昨日11.3广告收益</td><td>0.03</td></tr>'
        self.assertEqual("2026-11-03", z.parse_yichafen(html, CHANNEL, DAY)["source_date"])
        with self.assertRaises(ValueError): z.parse_yichafen(html, "wrong", DAY)
        with self.assertRaises(ValueError): z.parse_yichafen(html+"<tr><td>其他收益</td><td>1</td></tr>", CHANNEL, DAY)

    def test_month_is_primary_daily_not_added_twice(self):
        cfg=q.default_config("zishi_agency")
        with patch.object(z, "fetch_observation", side_effect=[obs("11月累计广告收益", "0.09"), obs("昨日11.3广告收益", "0.03")]):
            status, amount, message, evidence=z.fetch_month(CHANNEL,"zishi_agency",cfg,"2026-11",DAY)
        self.assertEqual(("success", Decimal("0.09")), (status,amount))
        self.assertIn("有延迟", message)
        self.assertEqual(2,len(evidence))

    def test_mismatch_lagging_month_missing_record_and_swapped_roles_wait(self):
        cfg=q.default_config("zishi_agency")
        cases = [([None],"pending"),
                 ([obs("10月累计广告收益","1")],"pending"),
                 ([obs("11月累计广告收益","0.02"),obs("11.3广告收益","0.03")],"pending"),
                 ([obs("至11.2当月收益","1"),obs("11.3广告收益","0.03")],"pending"),
                 ([obs("11月累计广告收益","1"),None],"pending")]
        for values,status in cases:
            with self.subTest(values=values),patch.object(z,"fetch_observation",side_effect=values):
                result=z.fetch_month(CHANNEL,"zishi_agency",cfg,"2026-11",DAY)
                self.assertEqual(status,result[0]);self.assertIsNone(result[1])
        with patch.object(z,"fetch_observation",side_effect=[obs("11月累计广告收益","1"),obs("11月累计广告收益","1")]),self.assertRaises(ValueError):
            z.fetch_month(CHANNEL,"zishi_agency",cfg,"2026-11",DAY)

    def test_valid_zero_and_cross_month_are_not_invented_errors(self):
        cfg=q.default_config("zishi_agency")
        with patch.object(z,"fetch_observation",side_effect=[obs("11月累计广告收益","0"),obs("10.31广告收益","2")]):
            result=z.fetch_month(CHANNEL,"zishi_agency",cfg,"2026-11",DAY)
        self.assertEqual(("success",Decimal("0")),result[:2]);self.assertIn("跨月",result[2])

    def test_guest_transport_recognizes_explicit_empty_without_record_maps(self):
        client=g.GuestClient(q.default_config("zishi_lpp")["source_url"],validator=lambda u:z.validate_source(u,z.FEISHU_HOST),resolve_fields=z.resolve_fields,parse_rows=z.parse_records,allow_empty_records=True)
        with patch.object(client,"prepare"), patch.object(client,"request",side_effect=[share(),{"code":0,"data":{"total":0,"hasMore":False}}]):
            self.assertIsNone(client.query(CHANNEL,DAY.isoformat()))
        with patch.object(client,"prepare"), patch.object(client,"request",side_effect=[share(),{"code":0,"data":{"total":1,"hasMore":False}}]),self.assertRaises(ValueError):
            client.query(CHANNEL,DAY.isoformat())

    def test_source_domain_role_and_optional_previous_link_validation(self):
        for key in c.ZISHI_TYPES:
            cfg=q.default_config(key)
            self.assertEqual(cfg,q.normalize(key,cfg))
        cfg=q.default_config("zishi_agency")
        for change in ({"daily_url":"https://evil.example/query"},{"source_url":"https://127.0.0.1/"},{"daily_url":""},{"daily_url":cfg["source_url"]},{"source_period":"2026-11"}):
            with self.subTest(change=change),self.assertRaises(ValueError):q.normalize("zishi_agency",{**cfg,**change})


class ZishiAccountingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        for name,value in [("WORKSPACE",root/"workspace"),("DATA_ROOT",root/"data"),("DATABASE_INITIALIZED_PATH",None)]:
            patched=patch.object(service,name,value);patched.start();self.addCleanup(patched.stop)
        self.conn=service.connection();self.addCleanup(self.conn.close)
        self.conn.execute("INSERT INTO theaters(id,name,created_at,updated_at) VALUES('z','自定义子诗','2026-11-01','2026-11-01')")
        self.conn.execute("INSERT INTO accounts(id,nickname,channel_id,theater_id,created_at,updated_at) VALUES('z','测试子诗',?,'z','2026-11-01','2026-11-01')",(CHANNEL,))
        c.set_theater(self.conn,'z',['zishi_agency']);c.set_account(self.conn,'z','z','zishi_agency');self.conn.commit()
        self.conn.execute('PRAGMA foreign_keys=ON')

    def collect(self, amount="0.09", day=5, month=11, skip=True, status="success"):
        def fetch(channel, collector_id, cfg, period, today):
            if period == today.isoformat()[:7]:
                return status,Decimal(amount) if status=='success' else None,'核对结果',[obs('昨日11.3广告收益','0.03')]
            return 'success',Decimal('203.98'),'上月累计',[]
        with patch.object(z,'fetch_month',side_effect=fetch) as source:
            result=revenue.collect_supported_theaters(self.conn,'2026-11-04','2026-11-04',account_ids=['z'],skip_completed=skip,collected_at=datetime(2026,month,day,10))
        return result,source.call_count

    def test_initial_month_plus_previous_then_repeat_then_delta(self):
        first,calls=self.collect();self.assertEqual(2,calls)
        self.assertEqual('204.07',self.conn.execute("SELECT amount FROM v2_daily_revenues WHERE revenue_date='2026-11-05'").fetchone()[0])
        self.assertEqual(0,self.conn.execute("SELECT COUNT(*) FROM v2_daily_revenues WHERE revenue_date IN ('2026-11-03','2026-11-04')").fetchone()[0])
        first_metadata=json.loads(self.conn.execute("SELECT raw_result_json FROM v3_revenue_account_periods WHERE period_label='2026-11-05'").fetchone()[0])
        self.assertEqual('2026-11-03', first_metadata['source_observations'][0]['source_date'])
        self.assertEqual(0,self.collect()[1])
        self.assertEqual(1,self.collect('0.12',day=6)[1])
        self.assertEqual('0.03',self.conn.execute("SELECT amount FROM v2_daily_revenues WHERE revenue_date='2026-11-06'").fetchone()[0])
        metadata=json.loads(self.conn.execute("SELECT raw_result_json FROM v3_revenue_account_periods WHERE period_label='2026-11-06'").fetchone()[0])
        self.assertEqual('cross_check_only',metadata['daily_use'])
        self.assertEqual('2026-11-03',metadata['source_observations'][0]['source_date'])

    def test_pending_keeps_month_retryable_and_does_not_create_false_zero(self):
        self.collect(status='pending')
        self.assertEqual(0,self.conn.execute("SELECT COUNT(*) FROM v3_revenue_cumulative_snapshots WHERE source_period='2026-11'").fetchone()[0])
        self.assertEqual(1,self.collect()[1])

    def test_forced_repeat_does_not_double_credit_and_reduction_keeps_baseline(self):
        self.collect();self.collect(skip=False)
        self.assertEqual('204.07',self.conn.execute('SELECT amount FROM v2_daily_revenues').fetchone()[0])
        result,_=self.collect('0.08',day=6)
        self.assertEqual('failed',result['items'][0]['status'])
        self.assertEqual('0.09',self.conn.execute("SELECT raw_amount FROM v3_revenue_cumulative_snapshots WHERE source_period='2026-11'").fetchone()[0])

    def test_new_month_has_its_own_baseline(self):
        self.collect();self.collect('0.02',month=12,day=2)
        self.assertEqual('0.02',self.conn.execute("SELECT raw_amount FROM v3_revenue_cumulative_snapshots WHERE source_period='2026-12'").fetchone()[0])

    def test_changing_daily_link_requires_exact_matching_preview_token(self):
        cfg={**q.current(self.conn,'zishi_agency'), 'daily_url':'https://c3andggd.yichafen.com/qz/newLink'}
        with self.assertRaisesRegex(ValueError,'先测试通过'):q.save(self.conn,'zishi_agency',cfg)
        self.assertEqual(0,q.current(self.conn,'zishi_agency')['revision'])

    def test_preview_checks_all_links_and_never_writes_financial_data(self):
        cfg={**q.current(self.conn,'zishi_agency'),'channel_id':CHANNEL}
        with patch.object(q,'now',return_value=datetime(2026,11,5,2)),patch.object(z,'fetch_month',return_value=('success',Decimal('0.09'),'仅核对',[])) as fetch:
            result=q.preview(self.conn,'zishi_agency',cfg)
        self.assertTrue(result['passed']);self.assertEqual(2,fetch.call_count)
        self.assertEqual(0,self.conn.execute('SELECT COUNT(*) FROM v2_daily_revenues').fetchone()[0])
        self.assertEqual(0,self.conn.execute('SELECT COUNT(*) FROM v3_revenue_cumulative_snapshots').fetchone()[0])


if __name__=='__main__':unittest.main()
