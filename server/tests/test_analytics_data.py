import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from server.analytics_data import data_base_overview, import_legacy_revenue, import_video_evidence, initialize


class AnalyticsDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.conn = sqlite3.connect(self.root / "analytics.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE accounts(id TEXT PRIMARY KEY, channel_id TEXT);
            CREATE TABLE v2_revenue_collection_attempts(
              id TEXT PRIMARY KEY, theater_id TEXT, adapter_key TEXT, collected_at TEXT
            );
            CREATE TABLE v2_daily_revenues(
              account_id TEXT, theater_id TEXT, revenue_date TEXT, amount TEXT,
              source_attempt_id TEXT, updated_at TEXT
            );
            CREATE TABLE v2_revenue_video_details(
              account_id TEXT, theater_id TEXT, revenue_date TEXT, source_video_id TEXT,
              source_drama_name TEXT, video_views INTEGER, drama_views INTEGER,
              gross_revenue TEXT, source_rank INTEGER, matched_drama_id TEXT,
              match_status TEXT, attempt_id TEXT, updated_at TEXT
            );
            INSERT INTO accounts VALUES ('a1','uid-1');
            INSERT INTO v2_revenue_collection_attempts VALUES ('attempt-1','t1','legacy','2026-10-29T10:00:00');
            INSERT INTO v2_daily_revenues VALUES ('a1','t1','2026-10-28','12.30','attempt-1','2026-10-29T10:00:00');
            INSERT INTO v2_revenue_video_details VALUES ('a1','t1','2026-10-28','video-1','剧名',10,20,'1.20',1,'','unmatched','attempt-1','2026-10-29T10:00:00');
            """
        )
        initialize(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def write_video_fixture(self):
        path = self.root / "video.json"
        path.write_text(json.dumps({
            "capturedAt": "2026-10-30T00:00:00+08:00",
            "dateRange": ["2026-10-23", "2026-10-29"],
            "validAccountUids": ["uid-1"],
            "accounts": {"list": [{
                "uid": "uid-1", "nickname": "账号一", "platform": "Channels",
                "loginStatus": "登录有效", "fansTotal": 100, "groupName": "组一", "tags": [],
            }]},
            "accountDetails": {"uid-1": {"daily": [{
                "date": "2026-10-29", "view": 123, "fansTotal": 100,
                "fansAdd": 4, "fansNet": 3, "fansReduce": 1,
                "like": 8, "favorite": 2, "comment": 1, "forward": 0,
            }]}},
            "postProfile": {"rows": [{
                "postId": "post-1", "uid": "uid-1", "account": "账号一",
                "postTime": "2026-10-29 10:00:00", "title": None, "desc": "",
                "coverPresent": True, "urlPresent": True, "view": 90,
                "like": 5, "comment": 0, "forward": 1, "love": 0,
                "fansAdd": 2, "fullView": 50, "viewTime": 10,
            }]},
            "accountRanking": {"total": 1},
        }, ensure_ascii=False), encoding="utf-8")
        remaining = self.root / "remaining.json"
        remaining.write_text(json.dumps({
            "diagnostics": {
                "list": {"list": [{
                    "uid": "uid-1", "nickname": "账号一", "verified": True,
                    "abnormal": False, "videoStatus": "正常", "heatStatus": "正常",
                    "abnormalPostCount": 0, "lastVerifyTime": "2026-10-30",
                    "liveStatus": "ignored",
                }]},
                "punishFeeds": {"list": [{
                    "uid": "uid-1", "exportId": "export-1", "title": "作品",
                    "publishTime": "2026-10-29", "punishState": "推荐曝光减少",
                }]},
            }
        }, ensure_ascii=False), encoding="utf-8")
        return path, remaining

    def test_import_video_keeps_cache_provenance_and_excludes_live_status(self):
        video, remaining = self.write_video_fixture()
        result = import_video_evidence(self.conn, video, remaining)
        self.assertEqual(1, result["coverage"]["posts"])
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM v3_video_account_daily").fetchone()[0])
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM v3_video_posts").fetchone()[0])
        self.assertEqual("cached_only", self.conn.execute("SELECT freshness_state FROM v3_video_posts").fetchone()[0])
        payload = self.conn.execute("SELECT payload_json FROM v3_video_account_diagnostics").fetchone()[0]
        self.assertNotIn("liveStatus", payload)

    def test_legacy_revenue_is_retained_but_excluded(self):
        result = import_legacy_revenue(self.conn)
        self.assertEqual(1, result["coverage"]["daily"])
        row = self.conn.execute("SELECT data_state,freshness_state,include_in_analysis FROM v3_revenue_account_periods").fetchone()
        self.assertEqual(("record", "legacy_unverified", 0), tuple(row))
        overview = data_base_overview(lambda: self.conn)
        self.assertEqual(1, overview["counts"]["v3_revenue_account_periods"])
        self.assertFalse(overview["policy"]["legacy_revenue_included"])
        self.assertEqual(1, len(overview["revenue_source_inventory"]))
        self.assertEqual("legacy", overview["revenue_source_inventory"][0]["adapter_key"])
        self.assertEqual(1, overview["revenue_period_coverage"][0]["row_count"])
        self.assertEqual("legacy_v2", overview["revenue_period_coverage"][0]["source_kind"])

    def test_source_filtered_overview_returns_only_selected_rows(self):
        self.conn.execute(
            """INSERT INTO v3_video_accounts(
               id,uid,account_id,account_name,platform,login_status,fans_total,group_name,
               tags_json,snapshot_date,source_kind,data_state,freshness_state,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("demo-account", "demo-uid", "demo-id", "演示账号", "Channels", "登录有效", 100, "演示",
             "[]", "2026-10-29", "simulation_ui", "record", "simulated", "2026-10-30", "{}"),
        )
        self.conn.commit()
        overview = data_base_overview(lambda: self.conn, source_kind="simulation_ui")
        self.assertEqual("simulation_ui", overview["source_kind"])
        self.assertEqual(1, overview["counts"]["v3_video_accounts"])
        self.assertEqual(1, len(overview["video_accounts"]))
        self.assertEqual(0, overview["counts"]["v3_revenue_account_periods"])


if __name__ == "__main__":
    unittest.main()
