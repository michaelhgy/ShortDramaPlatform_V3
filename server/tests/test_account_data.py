from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from server.account_data import initialize, overview, run_status, start_refresh


class FakeClient:
    calls = []
    fail_refresh = False
    missing_daily_uids = set()
    zero_view_uids = set()
    remote_accounts = [
        {"uid": "uid-a", "platform": "Channels", "loginStatus": "登录有效"},
        {"uid": "uid-b", "platform": "Channels", "loginStatus": "登录有效"},
    ]

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def accounts(self):
        type(self).calls.append(("vcat_list_accounts", {}))
        return list(type(self).remote_accounts)

    def call(self, name, args):
        type(self).calls.append((name, args))
        if name == "vcat_refresh_account_stats":
            if type(self).fail_refresh:
                raise RuntimeError("fixture refresh failed")
            return {"results": [{"uid": uid, "nickname": uid, "success": True} for uid in args["uids"]]}
        if name == "vcat_get_account_stats":
            if args["uid"] in type(self).missing_daily_uids:
                return {"uid": args["uid"], "daily": [], "rangeSum": {"view": 0}, "total": None}
            start = date.fromisoformat(args["startDate"])
            end = date.fromisoformat(args["endDate"])
            daily = []
            while start <= end:
                view = 0 if args["uid"] in type(self).zero_view_uids else 12
                daily.append({"date": start.isoformat(), "view": view})
                start += timedelta(days=1)
            return {"uid": args["uid"], "daily": daily, "total": {"fans": 34}}
        raise AssertionError(name)


class AccountDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "account-data.db"
        with closing(self.connect()) as conn:
            conn.executescript("""
                CREATE TABLE accounts(id TEXT PRIMARY KEY, nickname TEXT, channel_id TEXT, status TEXT);
                INSERT INTO accounts VALUES('account-a','账号A','uid-a','正常');
                INSERT INTO accounts VALUES('account-b','账号B','uid-b','正常');
                INSERT INTO accounts VALUES('account-off','停用账号','uid-off','停用');
                INSERT INTO accounts VALUES('account-no-uid','未绑定','', '正常');
            """)
            initialize(conn)
            conn.commit()
        FakeClient.calls = []
        FakeClient.fail_refresh = False
        FakeClient.missing_daily_uids = set()
        FakeClient.zero_view_uids = set()
        FakeClient.remote_accounts = [
            {"uid": "uid-a", "platform": "Channels", "loginStatus": "登录有效"},
            {"uid": "uid-b", "platform": "Channels", "loginStatus": "登录有效"},
        ]

    def tearDown(self):
        self.temp.cleanup()

    def connect(self):
        conn = sqlite3.connect(self.db, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def wait_for(self, run_id):
        for _ in range(200):
            value = run_status(self.connect, run_id)
            if value["status"] in ("completed", "failed"):
                return value
            time.sleep(0.01)
        self.fail("collector timed out")

    def test_page_read_is_local_and_refresh_saves_payload(self):
        self.assertEqual([], FakeClient.calls)
        initial = overview(self.connect)
        self.assertEqual([], initial["snapshots"])
        self.assertEqual(3, len(initial["accounts"]))
        result = start_refresh(self.connect, client_factory=FakeClient)
        run = self.wait_for(result["run_id"])
        self.assertEqual("completed", run["status"])
        self.assertEqual(["vcat_list_accounts", "vcat_refresh_account_stats", "vcat_get_account_stats", "vcat_get_account_stats"], [name for name, _ in FakeClient.calls])
        data = overview(self.connect)
        self.assertEqual(2, len(data["snapshots"]))
        self.assertEqual("success", data["snapshots"][0]["status"])
        self.assertIn("daily", data["snapshots"][0]["payload"])

    def test_successful_same_day_refresh_is_not_repeated(self):
        first = start_refresh(self.connect, client_factory=FakeClient)
        self.wait_for(first["run_id"])
        call_count = len(FakeClient.calls)
        second = start_refresh(self.connect, client_factory=FakeClient)
        self.assertEqual("skipped", second["status"])
        self.assertEqual(call_count, len(FakeClient.calls))

    def test_range_refresh_saves_each_daily_state_and_refresh_evidence(self):
        result = start_refresh(self.connect, start_date="2026-10-26", end_date="2026-10-28", client_factory=FakeClient)
        run = self.wait_for(result["run_id"])
        self.assertEqual("completed", run["status"])
        self.assertEqual("2026-10-26", run["requested_start_date"])
        self.assertEqual("2026-10-28", run["requested_end_date"])
        snapshots = overview(self.connect, "2026-10-27")["snapshots"]
        self.assertEqual(2, len(snapshots))
        self.assertEqual({"record"}, {item["data_state"] for item in snapshots})
        self.assertEqual({"success"}, {item["refresh_status"] for item in snapshots})
        self.assertTrue(all(item["refresh_result"]["success"] for item in snapshots))

    def test_local_overview_reads_date_range_without_refreshing_platform(self):
        result = start_refresh(self.connect, start_date="2026-10-26", end_date="2026-10-28", client_factory=FakeClient)
        self.wait_for(result["run_id"])
        call_count = len(FakeClient.calls)

        data = overview(self.connect, start_date="2026-10-26", end_date="2026-10-28")

        self.assertEqual("2026-10-26", data["start_date"])
        self.assertEqual("2026-10-28", data["end_date"])
        self.assertEqual(6, len(data["snapshots"]))
        self.assertEqual(call_count, len(FakeClient.calls))

    def test_local_overview_rejects_ranges_over_90_days(self):
        with self.assertRaisesRegex(ValueError, "最多 90 天"):
            overview(self.connect, start_date="2026-01-01", end_date="2026-04-10")

    def test_missing_daily_row_is_not_treated_as_confirmed_zero(self):
        FakeClient.missing_daily_uids = {"uid-a"}
        FakeClient.zero_view_uids = {"uid-b"}
        result = start_refresh(self.connect, start_date="2026-10-27", end_date="2026-10-27", client_factory=FakeClient)
        self.wait_for(result["run_id"])
        snapshots = {item["uid"]: item for item in overview(self.connect, "2026-10-27")["snapshots"]}
        self.assertEqual("no_daily_record", snapshots["uid-a"]["data_state"])
        self.assertEqual([], snapshots["uid-a"]["payload"]["daily"])
        self.assertEqual("record", snapshots["uid-b"]["data_state"])
        self.assertEqual(0, snapshots["uid-b"]["payload"]["daily"][0]["view"])

    def test_failed_refresh_is_visible_and_manual_retry_is_possible(self):
        FakeClient.fail_refresh = True
        first = start_refresh(self.connect, client_factory=FakeClient)
        run = self.wait_for(first["run_id"])
        self.assertEqual("failed", run["status"])
        self.assertEqual(2, len([item for item in overview(self.connect)["snapshots"] if item["status"] == "failed"]))
        FakeClient.fail_refresh = False
        retry = start_refresh(self.connect, client_factory=FakeClient)
        self.assertEqual("queued", retry["status"])
        self.assertEqual("completed", self.wait_for(retry["run_id"])["status"])

    def test_unavailable_accounts_are_classified_before_refresh_and_skipped_same_day(self):
        with closing(self.connect()) as conn:
            conn.execute("INSERT INTO accounts VALUES('account-invalid','已作废账号','uid-invalid','正常')")
            conn.execute("INSERT INTO accounts VALUES('account-missing','小V猫未找到账号','uid-missing','正常')")
            conn.commit()
        FakeClient.remote_accounts.append({"uid": "uid-invalid", "platform": "Channels", "loginStatus": "登录失效"})

        result = start_refresh(self.connect, client_factory=FakeClient)
        run = self.wait_for(result["run_id"])
        self.assertEqual("completed", run["status"])
        self.assertEqual(
            ["vcat_list_accounts", "vcat_refresh_account_stats", "vcat_get_account_stats", "vcat_get_account_stats"],
            [name for name, _ in FakeClient.calls],
        )
        snapshots = {item["uid"]: item for item in overview(self.connect)["snapshots"]}
        self.assertEqual("unavailable", snapshots["uid-invalid"]["status"])
        self.assertIn("作废或登录失效", snapshots["uid-invalid"]["error_message"])
        self.assertEqual("unavailable", snapshots["uid-missing"]["status"])
        self.assertIn("未找到", snapshots["uid-missing"]["error_message"])
        self.assertEqual("success", snapshots["uid-a"]["status"])
        self.assertEqual("success", snapshots["uid-b"]["status"])

        call_count = len(FakeClient.calls)
        second = start_refresh(self.connect, client_factory=FakeClient)
        self.assertEqual("skipped", second["status"])
        self.assertEqual(call_count, len(FakeClient.calls))


if __name__ == "__main__":
    unittest.main()
