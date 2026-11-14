import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import gpt_relay


class GptRelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp.name) / "系统数据" / "gpt-relay.json"
        self.path_patch = patch.object(gpt_relay, "_config_path", return_value=self.config_path)
        self.path_patch.start()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp.cleanup()

    def test_save_masks_key_and_retains_it_when_omitted(self) -> None:
        first = gpt_relay.save_config({
            "provider_name": "M2AI",
            "base_url": "https://m2ai.top/",
            "api_key": "sk-test-secret-1234",
            "model_routes": {"highlight": "gpt-6-sol"},
        })
        self.assertTrue(first["api_key_set"])
        self.assertNotIn("api_key", first)
        self.assertEqual("sk-t…1234", first["api_key_masked"])

        second = gpt_relay.save_config({
            "provider_name": "M2AI",
            "base_url": "https://m2ai.top/v1",
            "model_routes": {"highlight": ""},
        })
        self.assertTrue(second["api_key_set"])
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual("sk-test-secret-1234", raw["api_key"])
        self.assertEqual("https://m2ai.top/v1", second["base_url"])

    def test_fetch_models_normalizes_and_persists_available_ids(self) -> None:
        gpt_relay.save_config({
            "base_url": "https://m2ai.top",
            "api_key": "sk-test",
            "model_routes": {},
        })
        with patch.object(gpt_relay, "_request_json", return_value=(200, {
            "data": [
                {"id": "gpt-6-sol", "owned_by": "openai"},
                {"id": "gpt-5.6-terra"},
            ]
        })) as request:
            result = gpt_relay.fetch_models()
        request.assert_called_once_with("https://m2ai.top/v1/models", "sk-test", use_proxy=False)
        self.assertEqual(["gpt-5.6-terra", "gpt-6-sol"], [item["id"] for item in result["models"]])
        self.assertTrue(result["models_fetched_at"])

    def test_requests_default_direct_connection_passes_use_proxy(self) -> None:
        """默认直连：fetch_models 要带 use_proxy=False；开了开关则 True。"""
        gpt_relay.save_config({"base_url": "https://m2ai.top", "api_key": "sk-test", "model_routes": {}})
        stored = gpt_relay._read_raw()
        self.assertFalse(stored["use_system_proxy"])
        with patch.object(gpt_relay, "_request_json", return_value=(200, {"data": []})) as request:
            gpt_relay.fetch_models()
        self.assertFalse(request.call_args.kwargs["use_proxy"])
        gpt_relay.save_config({"use_system_proxy": True, "model_routes": {}})
        self.assertTrue(gpt_relay._read_raw()["use_system_proxy"])
        with patch.object(gpt_relay, "_request_json", return_value=(200, {"data": []})) as request:
            gpt_relay.fetch_models()
        self.assertTrue(request.call_args.kwargs["use_proxy"])

    def test_test_connection_uses_selected_model_without_exposing_key(self) -> None:
        gpt_relay.save_config({
            "base_url": "https://m2ai.top",
            "api_key": "sk-test-secret",
            "model_routes": {"highlight": "gpt-6-sol"},
        })
        with patch.object(gpt_relay, "_request_json", return_value=(200, {"usage": {"total_tokens": 4}})) as request:
            result = gpt_relay.test_connection()
        request.assert_called_once()
        self.assertEqual("https://m2ai.top/v1/responses", request.call_args.args[0])
        self.assertEqual("gpt-6-sol", request.call_args.args[2]["model"])
        self.assertNotIn("sk-test-secret", json.dumps(result, ensure_ascii=False))

    def test_generate_json_parses_response_and_records_usage_without_prompt(self) -> None:
        gpt_relay.save_config({
            "base_url": "https://m2ai.top",
            "api_key": "sk-test-secret",
            "model_routes": {"highlight": "gpt-6-sol"},
        })
        stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        stored["models"] = [{"id": "gpt-6-sol"}]
        self.config_path.write_text(json.dumps(stored), encoding="utf-8")
        raw_response = {"output_text": '{"picks":[{"episode_id":"E1","anchor_start_s":12.5}]}', "usage": {"total_tokens": 21}}
        with patch.object(gpt_relay, "_request_json", return_value=(200, raw_response)) as request:
            result = gpt_relay.generate_json({
                "task_role": "highlight",
                "prompt": "返回高光JSON",
                "schema_name": "highlight_picks",
                "schema": {"type": "object", "properties": {"picks": {"type": "array"}}},
            })
        self.assertEqual("gpt-6-sol", result["model"])
        self.assertEqual(12.5, result["data"]["picks"][0]["anchor_start_s"])
        self.assertEqual(21, result["usage"]["total_tokens"])
        request.assert_called_once()
        request_body = request.call_args.args[2]
        self.assertEqual("user", request_body["input"][0]["role"])
        self.assertEqual("返回高光JSON", request_body["input"][0]["content"][0]["text"])
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertNotIn("prompt", json.dumps(raw, ensure_ascii=False))

    def test_request_retries_on_connection_error_then_succeeds(self):
        """中转站偶发掐断：连接层错误应自动重试，几次内恢复就算成功。"""
        class _Resp:
            status_code = 200
            content = b'{"ok": true}'
            reason = "OK"
            def json(self):
                return {"ok": True}
        class _Session:
            calls = 0
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def request(self, *a, **k):
                _Session.calls += 1
                if _Session.calls < 3:
                    raise ConnectionError("Remote end closed connection without response")
                return _Resp()
        fake_requests = type("M", (), {"Session": _Session})
        with patch.object(gpt_relay, "NETWORK_RETRY_BACKOFF_S", 0), \
             patch.dict("sys.modules", {"requests": fake_requests}):
            status, payload = gpt_relay._request_json("https://m2ai.top/v1/x", "k", {"a": 1})
        self.assertEqual(status, 200)
        self.assertEqual(_Session.calls, 3)  # 前两次失败，第三次成功

    def test_request_does_not_retry_http_error(self):
        """HTTP 4xx 是请求本身的问题，不应重试。"""
        class _Resp:
            status_code = 401
            content = b'{"error": {"message": "bad key"}}'
            reason = "Unauthorized"
            def json(self):
                return {"error": {"message": "bad key"}}
        class _Session:
            calls = 0
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def request(self, *a, **k):
                _Session.calls += 1
                return _Resp()
        fake_requests = type("M", (), {"Session": _Session})
        with patch.object(gpt_relay, "NETWORK_RETRY_BACKOFF_S", 0), \
             patch.dict("sys.modules", {"requests": fake_requests}):
            with self.assertRaises(RuntimeError):
                gpt_relay._request_json("https://m2ai.top/v1/x", "k", {"a": 1})
        self.assertEqual(_Session.calls, 1)  # 只调一次，不重试


if __name__ == "__main__":
    unittest.main()
