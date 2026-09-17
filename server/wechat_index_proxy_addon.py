"""mitmproxy addon: persist only an authorized wxindex request, never flows."""
from __future__ import annotations

import json
import os
from pathlib import Path

from mitmproxy import http
from server.wechat_index_client import WECHAT_INDEX_HOST, WECHAT_INDEX_PATH, save_captured_response, save_connection_template


class CaptureWechatIndexRequest:
    def request(self, flow: http.HTTPFlow) -> None:
        if flow.request.method != "POST" or flow.request.host != WECHAT_INDEX_HOST or flow.request.path.split("?", 1)[0] != WECHAT_INDEX_PATH:
            return
        try:
            body = json.loads(flow.request.get_text(strict=False))
            query = str(body.get("query", [""])[0] if isinstance(body.get("query"), list) else "").strip()
            flow.metadata["wechat_index_query"] = query
            # Only the actual history request is reusable as a query template.
            # Other wxindex-family calls have different request contracts.
            if body.get("action_type") == 1:
                save_connection_template(Path(os.environ["WECHAT_INDEX_DATA_ROOT"]), {"url": flow.request.pretty_url, "headers": dict(flow.request.headers), "body": body})
        except Exception:
            # Request traffic is intentionally never logged or written on failure.
            return

    def response(self, flow: http.HTTPFlow) -> None:
        if flow.request.method != "POST" or flow.request.host != WECHAT_INDEX_HOST or flow.request.path.split("?", 1)[0] != WECHAT_INDEX_PATH:
            return
        try:
            response = json.loads(flow.response.get_text(strict=False))
            query = str(flow.metadata.get("wechat_index_query") or "").strip()
            if not query or not isinstance(response, dict): return
            index = response.get("index")
            if isinstance(index, dict) and isinstance(index.get("resp_list"), list):
                save_captured_response(Path(os.environ["WECHAT_INDEX_DATA_ROOT"]), "history", query, response)
            elif isinstance(response.get("content"), list):
                save_captured_response(Path(os.environ["WECHAT_INDEX_DATA_ROOT"]), "suggestions", query, response)
        except Exception:
            return


addons = [CaptureWechatIndexRequest()]
