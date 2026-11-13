"""Guyan anonymous querying and cumulative accounting; no real source requests."""
from datetime import datetime
from decimal import Decimal
from http.cookiejar import Cookie
from io import BytesIO
import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import Request
from unittest.mock import MagicMock, patch
from server import guyan_collector as g, revenue_collectors as collectors, revenue_query_settings as settings
from server import v2_file_service as service, v2_revenue_service as revenue

ID="fixture-guyan"
FIELDS={"account":"account","period":"period","amount":"amount"}


def cookie(name,value):
    return Cookie(0,name,value,None,False,".feishu.cn",True,True,"/",True,True,None,True,None,None,{},False)


def share():
    info={"name":"古言剧场&拓航11月端原生数据查询","fieldMap":{
        "account":{"name":"账号ID","type":1},"period":{"name":"日期","type":1},"amount":{"name":"汇总收益","type":2}},
        "queryFormViewProperty":{"fieldInfos":{"account":{"visible":True,"required":True}}}}
    return {"code":0,"data":{"data":json.dumps(info,ensure_ascii=False)}}


def row(account=ID,amount="92.18",period="2026年11月1日-2026年11月3日"):
    return {"account":{"value":[{"text":account,"type":"text"}]},"period":{"value":[{"text":period}]},"amount":{"value":amount}}


def page(rows=None,**overrides):
    rows={"r1":row()} if rows is None else rows
    return {"code":0,"data":{"total":len(rows),"recordIDs":list(rows),"recordMap":rows,"hasMore":False,"nextOffset":None,**overrides}}


class GuyanParserTests(unittest.TestCase):
    def test_definition_is_independent_cumulative_with_verified_initial_month(self):
        spec=collectors.definition("guyan_native")
        self.assertEqual("古言端原生",spec["name"])
        self.assertIn("古言剧场",spec["aliases"])
        self.assertEqual("cumulative_unknown",spec["date_precision"])
        self.assertFalse(spec["supports_month_query"])
        self.assertFalse(spec["supports_detail"])
        self.assertEqual("2026-11",settings.default_config("guyan_native")["source_period"])

    def test_field_ids_are_discovered_by_exact_names_and_types(self):
        self.assertEqual(FIELDS,g.field_ids(share()))
        value=share();info=json.loads(value["data"]["data"])
        info["fieldMap"]["renamed"]=info["fieldMap"].pop("account")
        info["queryFormViewProperty"]["fieldInfos"]["renamed"]=info["queryFormViewProperty"]["fieldInfos"].pop("account")
        value["data"]["data"]=json.dumps(info)
        self.assertEqual("renamed",g.field_ids(value)["account"])

    def test_wrong_source_missing_duplicate_or_non_numeric_amount_field_fails(self):
        for change in ("title","missing","duplicate","type","condition"):
            value=share();info=json.loads(value["data"]["data"])
            if change=="title":info["name"]="花生查询"
            elif change=="missing":del info["fieldMap"]["amount"]
            elif change=="duplicate":info["fieldMap"]["other"]=info["fieldMap"]["amount"]
            elif change=="type":info["fieldMap"]["amount"]["type"]=1
            else:info["queryFormViewProperty"]["fieldInfos"]["account"]["required"]=False
            value["data"]["data"]=json.dumps(info)
            with self.subTest(change=change),self.assertRaises(ValueError):g.field_ids(value)

    def test_account_is_exact_case_sensitive_and_fuzzy_neighbors_are_ignored(self):
        result=g.parse_records([row(ID+"x",amount="1000"),row(ID.upper(),amount="1000"),row()],FIELDS,ID,"2026-11")
        self.assertEqual(("success",Decimal("92.18")),result[:2])
        self.assertIn("2026-11-01 至 2026-11-03",result[2])
        self.assertEqual(("no_data",None),g.parse_records([row(ID+"x")],FIELDS,ID)[:2])

    def test_explicit_zero_is_success_empty_record_is_not_a_fake_zero(self):
        self.assertEqual(("success",Decimal("0.00")),g.parse_records([row(amount="0")],FIELDS,ID)[:2])
        self.assertEqual(("no_data",None),g.parse_records([],FIELDS,ID)[:2])

    def test_missing_invalid_or_negative_amounts_fail(self):
        for amount in [None,True,"--","NaN","Infinity","-1","0.001"]:
            with self.subTest(amount=amount),self.assertRaises(ValueError):g.parse_records([row(amount=amount)],FIELDS,ID)
        value=row();del value["amount"]
        with self.assertRaises(ValueError):g.parse_records([value],FIELDS,ID)

    def test_invalid_reversed_cross_month_or_wrong_config_period_fails(self):
        for period in ["本月","2026年11月3日-2026年11月1日","2026年10月31日-2026年11月3日","2026年11月31日-2026年11月31日"]:
            with self.subTest(period=period),self.assertRaises(ValueError):g.parse_records([row(period=period)],FIELDS,ID)
        with self.assertRaisesRegex(ValueError,"月份"):g.parse_records([row()],FIELDS,ID,"2026-12")

    def test_overlapping_snapshots_or_duplicate_periods_are_not_summed(self):
        for second in [row(),row(amount="100",period="2026年11月1日-2026年11月4日")]:
            with self.assertRaisesRegex(ValueError,"重叠"):g.parse_records([row(),second],FIELDS,ID)
        result=g.parse_records([row(),row(amount="7.82",period="2026年11月4日-2026年11月4日")],FIELDS,ID)
        self.assertEqual(Decimal("100.00"),result[1])

    def client(self,results):
        client=g.GuestClient(g.DEFAULT_URL)
        client.prepare=MagicMock()
        client.request=MagicMock(side_effect=[share(),*results])
        return client

    def test_actual_record_map_shape_is_parsed(self):
        self.assertEqual(("success",Decimal("92.18")),self.client([page()]).query(ID,"2026-11")[:2])

    def test_paging_is_complete_and_exact_ids_are_counted_only_once(self):
        first=page({"a":row()},total=2,hasMore=True,nextOffset="next")
        second=page({"b":row(amount="7.82",period="2026年11月4日-2026年11月4日")},total=2)
        client=self.client([first,second])
        self.assertEqual(Decimal("100.00"),client.query(ID,"2026-11")[1])
        self.assertEqual("next",client.request.call_args.args[1]["offset"])

    def test_partial_repeated_missing_or_changing_pages_never_return_partial_money(self):
        for second in [page({},total=2),page({"a":row()},total=2),page({"b":row()},total=3),page({"b":row()},total=2,hasMore=True,nextOffset="next")]:
            first=page({"a":row()},total=2,hasMore=True,nextOffset="next")
            with self.subTest(second=second),self.assertRaises(ValueError):self.client([first,second]).query(ID,"2026-11")
        with self.assertRaises(TimeoutError):self.client([page({"a":row()},total=2,hasMore=True,nextOffset=1),TimeoutError("timeout")]).query(ID,"2026-11")

    def test_failed_or_login_required_result_never_becomes_zero(self):
        for payload in [None,{}, {"code":5,"data":{}},{"code":True,"data":{}},{"code":0,"data":None},page(total=True),page(hasMore=None)]:
            with self.subTest(payload=payload),self.assertRaises(ValueError):self.client([payload]).query(ID,"2026-11")

    def test_get_share_sets_form_csrf_before_records_not_passport_csrf(self):
        client=g.GuestClient(g.DEFAULT_URL)
        client.jar.set_cookie(cookie("swp_csrf_token","passport-token"))
        with patch.object(client.opener,"open",return_value=BytesIO(b'{"code":0,"data":{}}')) as opened:
            client.request("get_share",{"shareToken":"fixture"})
        self.assertIsNone(opened.call_args.args[0].get_header("X-csrftoken"))
        with patch.object(client.opener,"open") as opened,self.assertRaises(ValueError):client.request("list_records",{})
        opened.assert_not_called()
        client.jar.set_cookie(cookie("_csrf_token","form-token"))
        with patch.object(client.opener,"open",return_value=BytesIO(b'{"code":0,"data":{}}')) as opened:
            client.request("list_records",{})
        self.assertEqual("form-token",opened.call_args.args[0].get_header("X-csrftoken"))

    def test_guest_bootstrap_is_reused_and_personal_login_is_not_accepted(self):
        client=g.GuestClient(g.DEFAULT_URL)
        client.jar.set_cookie(cookie("is_anonymous_session","1"))
        response=MagicMock();response.__enter__.return_value.geturl.return_value=g.DEFAULT_URL;response.__enter__.return_value.read.return_value=b"page"
        opener=MagicMock();opener.open.return_value=response
        with patch.object(g,"build_opener",return_value=opener):client.prepare();client.prepare()
        self.assertEqual(1,opener.open.call_count)
        client.ready=False;client.jar.set_cookie(cookie("is_anonymous_session","0"))
        with patch.object(g,"build_opener",return_value=opener),self.assertRaisesRegex(ValueError,"匿名"):client.prepare()

    def test_only_bootstrap_get_can_follow_observed_feishu_guest_redirects(self):
        redirect=g.GuestRedirect(g.DEFAULT_URL);req=Request(g.DEFAULT_URL)
        result=redirect.redirect_request(req,None,302,"",{},"https://accounts.feishu.cn/accounts/page/login?with_guest=1")
        self.assertEqual("accounts.feishu.cn",g.urlsplit(result.full_url).hostname)
        for target in ["http://accounts.feishu.cn/accounts/page/login","https://other.example/accounts/page/login","https://accounts.feishu.cn/other"]:
            with self.assertRaises(ValueError):redirect.redirect_request(req,None,302,"",{},target)
        with self.assertRaises(ValueError):redirect.redirect_request(Request(g.DEFAULT_URL,data=b'account'),None,302,"",{},g.DEFAULT_URL)
        with self.assertRaises(ValueError):settings.NoRedirect().redirect_request(req,None,302,"",{},g.DEFAULT_URL)

    def test_source_link_restrictions_and_invalid_id_do_not_send_account(self):
        base=settings.default_config("guyan_native")
        self.assertEqual(g.DEFAULT_URL,settings.normalize("guyan_native",base)["source_url"])
        for url in [g.DEFAULT_URL.replace("scnrzu35lckk","other"),g.DEFAULT_URL+"?foo=1",g.DEFAULT_URL.replace("https:","http:"),"https://localhost/share/base/query/shrcnFixture"]:
            with self.assertRaises(ValueError):settings.normalize("guyan_native",{**base,"source_url":url})
        with patch.object(g.GuestClient,"query") as query:
            for account in ["a,b","a b",""]:
                with self.assertRaises(ValueError):g.fetch_latest(account,base)
        query.assert_not_called()


class GuyanAccountingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        for key,value in [("WORKSPACE",root/"workspace"),("DATA_ROOT",root/"data"),("DATABASE_INITIALIZED_PATH",None)]:
            target=patch.object(service,key,value);target.start();self.addCleanup(target.stop)
        self.theater=service.create_theater({"name":"自建古言端","revenue_collector_ids":["guyan_native"]})
        self.account=service.create_account({"nickname":"隔离账号","channel_id":ID,"theater_id":self.theater["id"],"revenue_collector_id":"guyan_native"})
        self.conn=service.connection();self.addCleanup(self.conn.close)

    def collect(self,value="92.18",day=5,month=11,**kwargs):
        with patch.object(g,"fetch_latest",return_value=("success",Decimal(value),"来源区间汇总")) as fetch:
            result=revenue.collect_supported_theaters(self.conn,"2026-11-01","2026-11-03",account_ids=[self.account["id"]],collected_at=datetime(2026,month,day,12),**kwargs)
        return result,fetch.call_count

    def rows(self):return [tuple(row) for row in self.conn.execute("SELECT revenue_date,amount FROM v2_daily_revenues ORDER BY revenue_date")]

    def test_first_total_is_credited_to_collection_date_and_success_not_requeried(self):
        self.collect(skip_completed=True);self.assertEqual([("2026-11-05","92.18")],self.rows())
        result,calls=self.collect(skip_completed=True)
        self.assertEqual(0,calls)
        self.assertEqual(0,self.conn.execute("SELECT count(*) FROM v2_revenue_video_details").fetchone()[0])
        self.assertEqual("2026-11",self.conn.execute("SELECT source_period FROM v3_revenue_cumulative_snapshots").fetchone()[0])

    def test_next_day_delta_and_missed_days_go_to_actual_collection_date(self):
        self.collect();self.collect("100",day=6);self.collect("120",day=9)
        self.assertEqual([("2026-11-05","92.18"),("2026-11-06","7.82"),("2026-11-09","20.00")],self.rows())

    def test_decreasing_total_fails_without_advancing_baseline_or_credit(self):
        self.collect();result,_=self.collect("10",day=6)
        self.assertEqual("failed",result["items"][0]["status"])
        self.assertEqual([("2026-11-05","92.18")],self.rows())
        self.assertEqual(1,self.conn.execute("SELECT count(*) FROM v3_revenue_cumulative_snapshots").fetchone()[0])

    def test_source_failure_or_empty_does_not_write_zero_or_advance_baseline(self):
        self.collect()
        for value in [ValueError("source failed"),("no_data",None,"正常空记录")]:
            with patch.object(g,"fetch_latest",side_effect=value if isinstance(value,Exception) else None,return_value=value):
                revenue.collect_supported_theaters(self.conn,"2026-11-01","2026-11-03",account_ids=[self.account["id"]],collected_at=datetime(2026,11,6,12))
        self.assertEqual([("2026-11-05","92.18")],self.rows())
        self.assertEqual(1,self.conn.execute("SELECT count(*) FROM v3_revenue_cumulative_snapshots").fetchone()[0])

    def candidate(self,**values):
        return {**settings.default_config("guyan_native"),"channel_id":ID,"query_date":"2026-11-03","revision":0,**values}

    def test_new_month_needs_successful_preview_and_uses_separate_baseline(self):
        self.collect()
        candidate=self.candidate(source_url=g.DEFAULT_URL.replace("shrcnmW22x9VpoIX5qKMILzfFne","shrcnDecember"),source_period="2026-12",period_relation="new")
        with self.assertRaisesRegex(ValueError,"先测试"):settings.save(self.conn,"guyan_native",candidate)
        with patch.object(g,"fetch_latest",return_value=("success",Decimal("5"),"12月来源")):
            preview=settings.preview(self.conn,"guyan_native",candidate)
        self.assertTrue(preview["passed"])
        self.assertEqual([("2026-11-05","92.18")],self.rows())
        settings.save(self.conn,"guyan_native",{**candidate,"test_token":preview["test_token"]})
        self.collect("5",day=5,month=12)
        self.assertEqual([("2026-11-05","92.18"),("2026-12-05","5.00")],self.rows())

    def test_disabled_collector_does_not_connect_to_source(self):
        settings.save(self.conn,"guyan_native",self.candidate(enabled=False))
        _,calls=self.collect()
        self.assertEqual(0,calls)
