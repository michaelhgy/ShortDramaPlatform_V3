import io
import json
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from tools.collect_v3_account_data import build_account_core, build_post_core, collect, paginate, redact
from server.publishing.vcat import VcatClient


class FakeClient:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        value = self.answers[name]
        if callable(value):
            return value(arguments)
        if isinstance(value, Exception):
            raise value
        return value


class AccountDataCollectionTests(unittest.TestCase):
    def test_account_daily_uses_hearts_and_preserves_net_vs_added(self):
        core = build_account_core({"total": {"postCount": 36, "fans": 108}, "daily": [
            {"date": "2026-10-31", "view": 60367, "fansAdd": 93, "fansNet": 90,
             "fansReduce": 3, "like": 251, "favorite": 270, "comment": 5}]})
        self.assertEqual(core["videoTotal"], 36)
        self.assertEqual(core["daily"][0]["hearts"], 251)
        self.assertEqual(core["daily"][0]["followsAdded"], 93)
        self.assertEqual(core["daily"][0]["followsNet"], 90)

    def test_missing_and_zero_are_distinct(self):
        core = build_account_core({"daily": [{"date": "2026-11-01", "view": 0}]})
        self.assertIsNone(core["videoTotal"])
        self.assertEqual(core["daily"][0]["views"], 0)
        self.assertIsNone(core["daily"][0]["hearts"])
        self.assertIsNone(build_post_core({"view": "NaN"})["views"])

    def test_work_interaction_mapping_is_different_from_account_daily(self):
        core = build_post_core({"love": 4, "like": 3})
        self.assertEqual(core["hearts"], 4)
        self.assertEqual(core["thumbsUp"], 3)

    def test_redaction_removes_media_urls_and_secrets_but_keeps_identifiers(self):
        value = redact({"cover": "https://example.invalid/?token=secret", "cookie": "secret",
                        "nested": {"access_token": "secret", "postId": "p1", "uid": "u1"},
                        "message": "see https://example.invalid/?key=secret"})
        self.assertTrue(value["coverPresent"])
        self.assertNotIn("secret", str(value))
        self.assertEqual(value["nested"]["postId"], "p1")

    def test_pagination_uses_both_account_and_post_identity(self):
        client = FakeClient({"posts": {"total": 2, "list": [
            {"uid": "u1", "postId": "p1"}, {"uid": "u2", "postId": "p1"}]}})
        self.assertEqual(paginate(client, "posts", {}, ("uid", "postId"))["total"], 2)

    def test_pagination_does_not_silently_accept_incomplete_or_repeated_pages(self):
        for answer in [lambda a: {"total": 2, "list": []},
                       lambda a: {"total": 2, "list": [{"uid": "u1"}]}]:
            with self.subTest(answer=answer):
                with self.assertRaises(RuntimeError):
                    paginate(FakeClient({"accounts": answer}), "accounts", {}, ("uid",))

    def test_refresh_failed_still_returns_available_cache_without_claiming_fresh(self):
        client = FakeClient({
            "vcat_list_accounts": {"list": [{"uid": "u1", "loginStatus": "登录有效"}], "total": 1},
            "vcat_refresh_account_stats": RuntimeError("refresh failed"),
            "vcat_get_account_stats": {"total": {"postCount": 1}, "daily": []},
            "vcat_list_posts": {"list": [], "total": 0}, "vcat_get_verify_result": {},
        })
        args = SimpleNamespace(uid=[], start="2026-10-26", end="2026-11-01", refresh=True, sync_posts=False)
        result = collect(client, args, lambda *a: None)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["accountResults"]["u1"]["dataState"], "cached_only")
        self.assertEqual(result["core"]["accounts"]["u1"]["videoTotal"], 1)

    def test_cache_read_has_no_external_refresh_or_publish(self):
        client = FakeClient({
            "vcat_list_accounts": {"list": [{"uid": "u1", "loginStatus": "登录有效"}], "total": 1},
            "vcat_get_account_stats": {"daily": []}, "vcat_list_posts": {"list": [], "total": 0},
            "vcat_get_verify_result": {},
        })
        args = SimpleNamespace(uid=[], start="2026-10-26", end="2026-11-01", refresh=False, sync_posts=False)
        collect(client, args, lambda *a: None)
        self.assertEqual({name for name, _ in client.calls}, {
            "vcat_list_accounts", "vcat_get_account_stats", "vcat_list_posts", "vcat_get_verify_result"})

    def test_running_sync_is_not_replaced(self):
        client = FakeClient({
            "vcat_list_accounts": {"list": [{"uid": "u1", "loginStatus": "登录有效"}], "total": 1},
            "vcat_get_post_sync": {"looping": 1},
        })
        args = SimpleNamespace(uid=[], start="2026-10-26", end="2026-11-01", refresh=True, sync_posts=True)
        with self.assertRaises(RuntimeError):
            collect(client, args, lambda *a: None)
        self.assertFalse(any(name == "vcat_start_post_sync" for name, _ in client.calls))

    def test_sync_records_use_real_record_id_and_checkpoint_precedes_external_actions(self):
        checkpoints = []
        client = FakeClient({
            "vcat_list_accounts": {"list": [{"uid": "u1", "loginStatus": "登录有效"}], "total": 1},
            "vcat_get_post_sync": {"looping": 0, "task": {"uids": ["old-uid"]}},
            "vcat_start_post_sync": {"started": True},
            "vcat_list_post_sync_records": {"list": [{"recordId": 1, "uid": "u1"}], "total": 1},
            "vcat_get_account_stats": {"daily": []},
            "vcat_list_posts": {"list": [{"uid": "u1", "postId": "p1", "publishStatus": "scheduled"}], "total": 1},
            "vcat_get_verify_result": {"verified": False},
        })
        args = SimpleNamespace(uid=[], start="2026-10-26", end="2026-11-01", refresh=False, sync_posts=True, wait_seconds=1)
        result = collect(client, args, lambda *a: None, lambda data: checkpoints.append(data))
        self.assertEqual(result["status"], "completed_cache_read")
        self.assertEqual(result["postSync"]["records"]["u1"]["summary"]["list"][0]["recordId"], 1)
        self.assertEqual(checkpoints[1]["postSync"]["before"]["task"]["uids"], ["old-uid"])
        self.assertEqual(result["accountResults"]["u1"]["publishedPostRows"], 0)
        self.assertEqual(result["accountResults"]["u1"]["scheduledPostRows"], 1)
        self.assertEqual(result["accountResults"]["u1"]["optimizationState"], "not_checked")
        self.assertIsNone(result["accountResults"]["u1"]["optimizationRows"])

    def test_sync_account_errors_are_partial_and_old_errors_do_not_taint_new_sync(self):
        def sync_records(args):
            if args["type"] == "summary":
                return {"list": [], "total": 0}
            return {"list": [
                {"recordId": 1, "time": "2026-10-01 10:00:00", "text": "old error"},
                {"recordId": 2, "time": "2026-11-02 10:01:00", "text": "new error"}], "total": 2}
        client = FakeClient({
            "vcat_list_accounts": {"list": [{"uid": "u1", "loginStatus": "登录有效"}], "total": 1},
            "vcat_get_post_sync": {"looping": 0, "task": {"lastRun": "2026-11-02 10:00:00"}},
            "vcat_start_post_sync": {"started": True}, "vcat_list_post_sync_records": sync_records,
            "vcat_get_account_stats": {"daily": []}, "vcat_list_posts": {"list": [], "total": 0},
            "vcat_get_verify_result": {},
        })
        args = SimpleNamespace(uid=[], start="2026-10-26", end="2026-11-01", refresh=False, sync_posts=True, wait_seconds=1)
        result = collect(client, args, lambda *a: None)
        self.assertEqual(result["status"], "partial")
        self.assertEqual([e["message"] for e in result["errors"]], ["new error"])

    def test_official_detail_get_uses_current_session_without_returning_credentials(self):
        client = VcatClient.__new__(VcatClient)
        client.account_data = True
        client.evaluate = Mock(return_value=[{"name": "_finder_auth", "value": "private-session"}, {"name": "wxuin", "value": "private-user"}])
        payload = {"errCode": 0, "data": {"operate_items": [{"reason": "官方作品分析", "tips": ["官方建议"], "unique_id": "notice-1"}],
                    "video_url": "https://example.invalid/?token=private-media"}}
        response = io.BytesIO(json.dumps(payload).encode())
        response.status = 200
        opener = Mock()
        opener.open.return_value = response
        with patch("server.publishing.vcat.urllib.request.build_opener", return_value=opener):
            result = client.optimization_detail("u1", "export/example+id")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("get_finder_appeal_detail_by_export_id?export_id=export%2Fexample%2Bid", request.full_url)
        self.assertIn("private-session", request.get_header("Cookie"))
        self.assertEqual(result["reason"], "官方作品分析")
        self.assertNotIn("private-", str(result))
        self.assertNotIn("video_url", result)

    def test_official_detail_fails_without_session_or_valid_analysis(self):
        client = VcatClient.__new__(VcatClient)
        client.account_data = False
        with self.assertRaises(ValueError):
            client.optimization_detail("u1", "export-1")
        client.account_data = True
        client.evaluate = Mock(return_value=[])
        with self.assertRaises(RuntimeError):
            client.optimization_detail("u1", "export-1")
        client.evaluate.return_value = [{"name": "_finder_auth", "value": "private-session"}]
        for body in [{"errCode": 1}, {"errCode": 0, "data": {"operate_items": [{"tips": ["only tip"]}]}}]:
            response = io.BytesIO(json.dumps(body).encode())
            response.status = 200
            opener = Mock()
            opener.open.return_value = response
            with patch("server.publishing.vcat.urllib.request.build_opener", return_value=opener), self.assertRaises(RuntimeError):
                client.optimization_detail("u1", "export-1")

    def test_failed_per_account_refresh_is_not_reported_as_complete(self):
        client = FakeClient({
            "vcat_list_accounts": {"list": [{"uid": "u1", "loginStatus": "登录有效"}], "total": 1},
            "vcat_refresh_account_stats": {"results": [{"uid": "u1", "success": False}]},
            "vcat_get_account_stats": {"daily": []},
            "vcat_list_posts": {"list": [], "total": 0}, "vcat_get_verify_result": {},
        })
        args = SimpleNamespace(uid=[], start="2026-10-26", end="2026-11-01", refresh=True, sync_posts=False)
        result = collect(client, args, lambda *a: None)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"][0]["uid"], "u1")

    def test_official_detail_is_not_called_for_unchecked_diagnosis(self):
        client = FakeClient({
            "vcat_list_accounts": {"list": [{"uid": "u1", "loginStatus": "登录有效"}], "total": 1},
            "vcat_get_account_stats": {"daily": []}, "vcat_list_posts": {"list": [], "total": 0},
            "vcat_get_verify_result": {"verified": False},
        })
        client.optimization_detail = Mock(side_effect=AssertionError("unchecked diagnosis"))
        args = SimpleNamespace(uid=[], start="2026-10-26", end="2026-11-01", refresh=False, sync_posts=False, optimization_details=True)
        result = collect(client, args, lambda *a: None)
        client.optimization_detail.assert_not_called()
        self.assertEqual(result["accountResults"]["u1"]["optimizationState"], "not_checked")

    def test_external_collection_gate_and_publish_gate_stay_separate(self):
        client = VcatClient.__new__(VcatClient)
        client.account_data = False
        client.writable = False
        client.publishing = False
        client.request = lambda *a: self.fail("Unauthorized request reached transport")
        for name in ["vcat_refresh_account_stats", "vcat_start_post_sync", "vcat_delete_punish_post", "vcat_create_publish_task"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                client.call(name, {})
        client.account_data = True
        for name in ["vcat_delete_punish_post", "vcat_hide_punish_post", "vcat_cancel_post_sync", "vcat_create_publish_task"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                client.call(name, {})


if __name__ == "__main__":
    unittest.main()
