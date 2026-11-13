"""Kujiang business isolation, exact-date money and paging; no real network."""
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import kujiang_collector as k
from server import revenue_collectors as collectors
from server import revenue_query_settings as settings
from server import v2_file_service as service
from server import v2_revenue_service as revenue

CHANNEL = "fixture-kujiang"
DAY = "2026-10-31"
NATIVE = "酷匠-端+漫剧"
PAGE_HTML = b"let apiUrl = 'http://api.data.djff.asia/data'; /* /external/find videoAccountId pageNum pageSize */"


def payload(*, theater=NATIVE, amounts=("5.75",), page=1, total=None, summary=None):
    total = len(amounts) if total is None else total
    value = sum(map(Decimal, amounts), Decimal("0")) if summary is None else summary
    return {"code": 200, "data": {"records": [
        {"recordDate": DAY, "videoAccountId": CHANNEL, "theaterName": theater, "income": amount}
        for amount in amounts], "summary": {"recordDate": f"{DAY} ~ {DAY}", "theaterName": theater,
        "videoAccountId": None, "income": str(value) if value is not None else None},
        "total": total, "pageNum": page, "pageSize": 100, "totalPages": (total+99)//100}}


def response(value):
    return BytesIO(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


class KujiangParserTests(unittest.TestCase):
    def fetch(self, value, collector_id="kujiang_native"):
        with patch.object(settings.SafeOpener, "open", return_value=response(value)):
            return k.fetch_day(CHANNEL, DAY, collector_id)

    def test_four_definitions_are_independent_and_have_shared_theater_alias(self):
        self.assertEqual(4, len(collectors.KUJIANG_TYPES))
        for key, (name, _) in collectors.KUJIANG_TYPES.items():
            spec = collectors.definition(key)
            self.assertEqual(name, spec["name"])
            self.assertIn("酷匠剧场", spec["aliases"])
            self.assertEqual("day", spec["date_precision"])
            self.assertFalse(spec["supports_detail"])
            self.assertTrue(spec["empty_result_is_boundary"])

    def test_each_id_sends_only_its_own_business_type_for_exact_day(self):
        for key, (name, _) in collectors.KUJIANG_TYPES.items():
            with self.subTest(collector=key), patch.object(settings.SafeOpener, "open", return_value=response(payload(theater=name))) as opened:
                result = k.fetch_day(CHANNEL, DAY, key)
                self.assertEqual(("success", Decimal("5.75")), result[:2])
                request = opened.call_args.args[0]
                self.assertEqual("http://api.data.djff.asia/data/external/find", request.full_url)
                sent = json.loads(request.data)
                self.assertEqual({"tn":name,"vid":CHANNEL,"sd":DAY,"ed":DAY,"pageNum":1,"pageSize":100}, sent)
                self.assertEqual(1, opened.call_count)

    def test_positive_amount_and_multiple_programs_are_summed_once(self):
        self.assertEqual(("success", Decimal("7.75")), self.fetch(payload(amounts=("5.75", "2.00")))[:2])

    def test_explicit_zero_row_is_success_but_normal_empty_has_no_amount(self):
        self.assertEqual(("success", Decimal("0.00")), self.fetch(payload(amounts=("0",)))[:2])
        value = payload(amounts=())
        value["data"]["summary"]["income"] = None
        self.assertEqual(("no_data", None), self.fetch(value)[:2])

    def test_missing_error_html_or_wrong_code_never_becomes_zero(self):
        for value in [None, [], {}, {"code":500,"msg":"维护中"}, {"code":True,"data":{}}, {"code":200}, {"code":200,"data":{}}, {"code":200,"data":{"records":[]}}]:
            with self.subTest(value=value), self.assertRaises(ValueError): self.fetch(value)
        with patch.object(settings.SafeOpener,"open",return_value=BytesIO(b"<html>maintenance</html>")), self.assertRaises(ValueError):
            k.fetch_day(CHANNEL, DAY, "kujiang_native")

    def test_account_type_and_day_mismatches_are_rejected(self):
        for area in ("summary", "row"):
            for key, wrong in [("recordDate","2026-10-30"),("theaterName","酷匠-IAA"),("videoAccountId","someone-else")]:
                value = payload()
                item = value["data"]["summary"] if area=="summary" else value["data"]["records"][0]
                item[key] = wrong
                with self.subTest(area=area,key=key), self.assertRaises(ValueError): self.fetch(value)

    def test_invalid_missing_negative_or_fractional_cent_amounts_fail(self):
        for area in ("summary", "row"):
            for amount in [None, True, "--", "NaN", "Infinity", "-1", "0.001", {}]:
                value = payload()
                item = value["data"]["summary"] if area=="summary" else value["data"]["records"][0]
                item["income"] = amount
                with self.subTest(area=area,amount=amount), self.assertRaises(ValueError): self.fetch(value)

    def test_summary_is_not_added_to_rows_and_disagreement_fails(self):
        self.assertEqual(Decimal("5.75"), self.fetch(payload())[1])
        with self.assertRaisesRegex(ValueError,"不一致"): self.fetch(payload(summary="6"))
        with self.assertRaisesRegex(ValueError,"不一致"): self.fetch(payload(amounts=(),summary="1"))

    def test_missing_or_inconsistent_pagination_fails(self):
        for key, wrong in [("total",None),("total",True),("pageNum",2),("pageNum",True),("pageSize",20),("totalPages",0),("total",2)]:
            value = payload(); value["data"][key] = wrong
            with self.subTest(key=key,wrong=wrong), self.assertRaises(ValueError): self.fetch(value)

    def test_all_pages_are_read_and_summary_is_counted_once(self):
        pages = [payload(amounts=["1"]*100,total=101,summary="102"),payload(amounts=["2"],page=2,total=101,summary="102")]
        with patch.object(settings.SafeOpener,"open",side_effect=list(map(response,pages))) as opened:
            self.assertEqual(("success",Decimal("102.00")), k.fetch_day(CHANNEL,DAY,"kujiang_native")[:2])
        self.assertEqual([1,2],[json.loads(call.args[0].data)["pageNum"] for call in opened.call_args_list])

    def test_partial_paging_network_error_never_returns_partial_amount(self):
        first = payload(amounts=["1"]*100,total=101,summary="101")
        with patch.object(settings.SafeOpener,"open",side_effect=[response(first),TimeoutError("timeout")]), self.assertRaises(TimeoutError):
            k.fetch_day(CHANNEL,DAY,"kujiang_native")

    def test_changing_totals_or_repeated_page_fails(self):
        first = payload(amounts=["1"]*100,total=200,summary="200")
        for second in [payload(amounts=["1"]*100,page=2,total=200,summary="201"),payload(amounts=["1"]*100,page=2,total=200,summary="200")]:
            with patch.object(settings.SafeOpener,"open",side_effect=[response(first),response(second)]), self.assertRaises(ValueError):
                k.fetch_day(CHANNEL,DAY,"kujiang_native")

    def test_unsupported_type_or_multiple_ids_do_not_send_requests(self):
        with patch.object(settings.SafeOpener,"open") as opened:
            for channel,key in [(CHANNEL,"qingning"),("a,b","kujiang_native"),("a b","kujiang_native"),("","kujiang_native")]:
                with self.assertRaises(ValueError): k.fetch_day(channel,DAY,key)
        opened.assert_not_called()

    def test_candidate_page_must_still_point_at_adapted_api(self):
        self.assertTrue(k.validate_page(PAGE_HTML.decode(),k.DEFAULT_URL))
        for page in ["maintenance",PAGE_HTML.decode().replace("/data'","/changed'"),PAGE_HTML.decode().replace("api.data.djff.asia","other.example")]:
            self.assertFalse(k.validate_page(page,k.DEFAULT_URL))

    def test_link_config_supports_same_source_but_not_other_hosts_or_types(self):
        for key in collectors.KUJIANG_TYPES:
            base = settings.default_config(key)
            self.assertEqual(k.DEFAULT_URL, settings.normalize(key,base)["source_url"])
            newer = {**base,"source_url":k.DEFAULT_URL.replace("find.html","new-find.html")}
            self.assertEqual(newer["source_url"],settings.normalize(key,newer)["source_url"])
            for url in ["http://localhost/query/find.html","http://api.data.djff.asia.evil/query/find.html","http://api.data.djff.asia/data/external/find","http://api.data.djff.asia:8000/query/find.html"]:
                with self.subTest(url=url), self.assertRaises(ValueError): settings.normalize(key,{**base,"source_url":url})

    def test_http_permission_is_limited_to_kujiang_origin(self):
        active = {**settings.default_config("kujiang_native"),"collector_id":"kujiang_native"}
        token = settings.ACTIVE.set(active)
        try:
            settings.validate_request("http://api.data.djff.asia/data/external/find")
            for url in ["http://other.example/data/external/find","https://api.data.djff.asia/data/external/find","http://api.data.djff.asia:8000/data"]:
                with self.assertRaises(ValueError): settings.validate_request(url)
        finally: settings.ACTIVE.reset(token)
        token = settings.ACTIVE.set({**settings.default_config("qingning"),"collector_id":"qingning"})
        try:
            with self.assertRaises(ValueError): settings.validate_request("http://vd.xingvan.com/lpp.html")
        finally: settings.ACTIVE.reset(token)


class KujiangIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name,value in [("WORKSPACE",root/"workspace"),("DATA_ROOT",root/"data"),("DATABASE_INITIALIZED_PATH",None)]:
            target = patch.object(service,name,value); target.start(); self.addCleanup(target.stop)
        self.theater = service.create_theater({"name":"自定义酷匠", "revenue_collector_ids":list(collectors.KUJIANG_TYPES)})
        self.account = service.create_account({"nickname":"隔离账号","channel_id":CHANNEL,"theater_id":self.theater["id"],"revenue_collector_id":"kujiang_native"})
        self.conn = service.connection(); self.addCleanup(self.conn.close)

    def collect(self, **kwargs):
        return revenue.collect_supported_theaters(self.conn,DAY,DAY,account_ids=[self.account["id"]],collected_at=datetime(2026,11,4,12),**kwargs)

    def test_bound_collector_routes_without_theater_name_guess_and_skips_saved_day(self):
        with patch.object(settings.SafeOpener,"open",return_value=response(payload())) as opened:
            self.collect(skip_completed=True)
            self.collect(skip_completed=True)
        self.assertEqual(1,opened.call_count)
        row=self.conn.execute("SELECT revenue_date,amount FROM v2_daily_revenues").fetchone()
        self.assertEqual((DAY,"5.75"),tuple(row))
        self.assertEqual("kujiang_native",self.conn.execute("SELECT adapter_key FROM v2_revenue_collection_attempts").fetchone()[0])
        self.assertEqual(0,self.conn.execute("SELECT count(*) FROM v2_revenue_video_details").fetchone()[0])

    def test_first_backfill_stops_after_seven_normal_empty_days_without_fake_zeros(self):
        with patch.object(k,"fetch_day",return_value=("no_data",None,"正常空记录")) as fetch:
            result=self.collect(initial_backfill=True,skip_completed=True)
            self.assertTrue(result["backfills"][0]["complete"])
            self.assertEqual(7,fetch.call_count)
            self.collect(initial_backfill=True,skip_completed=True)
            self.assertEqual(7,fetch.call_count)
        self.assertEqual(0,self.conn.execute("SELECT count(*) FROM v2_daily_revenues").fetchone()[0])

    def test_failures_are_not_empty_and_retry_keeps_successful_dates(self):
        with patch.object(k,"fetch_day",side_effect=[TimeoutError("timeout")]+[("no_data",None,"正常空记录")]*7):
            first=self.collect(initial_backfill=True,skip_completed=True,max_initial_days=8)
        self.assertFalse(first["backfills"][0]["complete"])
        with patch.object(k,"fetch_day",return_value=("no_data",None,"正常空记录")) as fetch:
            second=self.collect(initial_backfill=True,skip_completed=True,max_initial_days=8)
        self.assertEqual(1,fetch.call_count)
        self.assertTrue(second["backfills"][0]["complete"])

    def test_switching_explicit_business_type_does_not_reuse_other_completion(self):
        with patch.object(k,"fetch_day",return_value=("success",Decimal("5.75"),"")):
            self.collect(skip_completed=True)
        service.update_account(self.account["id"],{"revenue_collector_id":"kujiang_iaa"})
        with patch.object(k,"fetch_day",return_value=("success",Decimal("2.00"),"")) as fetch:
            self.collect(skip_completed=True)
        self.assertEqual("kujiang_iaa",fetch.call_args.args[2])
        self.assertEqual(2,self.conn.execute("SELECT count(*) FROM v2_revenue_collection_attempts").fetchone()[0])

    def test_changed_link_preview_and_activation_are_separate_and_do_not_write_money(self):
        key="kujiang_native"
        candidate={**settings.default_config(key),"source_url":k.DEFAULT_URL.replace("find.html","find-new.html"),"channel_id":CHANNEL,"query_date":DAY,"revision":0}
        with self.assertRaisesRegex(ValueError,"先测试"): settings.save(self.conn,key,candidate)
        with patch.object(settings.SafeOpener,"open",side_effect=[BytesIO(PAGE_HTML),response(payload())]):
            preview=settings.preview(self.conn,key,candidate)
        self.assertTrue(preview["passed"])
        self.assertEqual("5.75",preview["amount"])
        self.assertEqual(0,settings.current(self.conn,key)["revision"])
        for table in ["v2_daily_revenues","v2_revenue_collection_attempts","v3_revenue_backfills"]:
            self.assertEqual(0,self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        settings.save(self.conn,key,{**candidate,"test_token":preview["test_token"]})
        self.assertEqual(candidate["source_url"],settings.current(self.conn,key)["source_url"])

    def test_incompatible_candidate_page_fails_before_sending_id(self):
        key="kujiang_native"
        candidate={**settings.default_config(key),"channel_id":CHANNEL,"query_date":DAY,"revision":0}
        with patch.object(settings.SafeOpener,"open",return_value=BytesIO(b"<html>changed platform</html>")) as opened:
            preview=settings.preview(self.conn,key,candidate)
        self.assertFalse(preview["passed"])
        self.assertEqual(1,opened.call_count)
        self.assertIsNone(opened.call_args.args[0].data)

    def test_disabled_collector_never_sends_requests(self):
        key="kujiang_native"
        settings.save(self.conn,key,{**settings.default_config(key),"enabled":False,"revision":0})
        with patch.object(k,"fetch_day") as fetch:
            result=self.collect()
        fetch.assert_not_called()
        self.assertEqual("failed",result["items"][0]["status"])
