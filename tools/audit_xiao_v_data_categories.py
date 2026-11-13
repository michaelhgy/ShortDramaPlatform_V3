"""Audit read-only Xiao V MCP data categories without refreshing or mutating data.

The output is a shape/presence report.  It deliberately does not persist
message text, comment text, URLs, cookies, or other payload contents.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.publishing.vcat import VcatClient


START = (date.today() - timedelta(days=7)).isoformat()
END = (date.today() - timedelta(days=1)).isoformat()


def parse_result(raw: dict[str, Any]) -> Any:
    result = raw.get("result") or {}
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    for item in result.get("content") or []:
        if item.get("type") == "text":
            text = item.get("text", "")
            try:
                return json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return {"textType": "non_json", "textLength": len(text)}
    return result


def shape(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        item_keys = sorted({key for item in value if isinstance(item, dict) for key in item})
        return {"kind": "list", "length": len(value), "itemKeys": item_keys}
    if isinstance(value, dict):
        result: dict[str, Any] = {"kind": "object", "keys": sorted(value)}
        for key in ("total", "count", "page", "pageSize", "dateRange", "status", "success", "error"):
            if key in value and not isinstance(value[key], (dict, list)):
                result[key] = value[key]
        for key, item in value.items():
            if isinstance(item, list):
                result[f"{key}Count"] = len(item)
                result[f"{key}ItemKeys"] = sorted({k for row in item if isinstance(row, dict) for k in row})
        return result
    return {"kind": type(value).__name__, "valuePresent": value is not None}


def invoke(client: VcatClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = client.request("tools/call", {"name": name, "arguments": arguments})
        if raw.get("error"):
            return {"status": "error", "error": raw["error"]}
        value = parse_result(raw)
        return {"status": "success", "shape": shape(value)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def main() -> None:
    output = Path("docs/事项档案/小V猫MCP数据类别审计-2026-10-29.json")
    with VcatClient() as client:
        tool_list_raw = client.request("tools/list", {})
        all_tools = (tool_list_raw.get("result") or {}).get("tools") or []
        account_raw = client.request(
            "tools/call",
            {"name": "vcat_list_accounts", "arguments": {"platform": "Channels", "page": 1, "pageSize": 100}},
        )
        accounts = parse_result(account_raw)
        valid_uids = [
            row.get("uid") for row in (accounts.get("list") or [])
            if row.get("loginStatus") == "登录有效"
        ]
        uid = valid_uids[0] if valid_uids else ""

        calls: dict[str, dict[str, Any]] = {
            "vcat_list_accounts": {"platform": "Channels", "page": 1, "pageSize": 100},
            "vcat_get_overview": {},
            "vcat_get_account_stats": {
                "platform": "视频号", "startDate": START, "endDate": END,
                "includeIncome": True, "sortBy": "view", "page": 1, "pageSize": 100,
            },
            "vcat_get_order_stats": {"mode": "summary", "platform": "视频号"},
            "vcat_get_publish_options": {"platform": "视频号"},
            "vcat_list_publish_tasks": {"platform": "视频号", "page": 1, "pageSize": 100},
            "vcat_get_publish_task_stat": {"platform": "视频号", "startDate": START, "endDate": END},
            "vcat_list_drafts": {"page": 1, "pageSize": 100},
            "vcat_list_posts": {"platform": "视频号", "page": 1, "pageSize": 100},
            "vcat_get_post_stat": {"platform": "视频号", "startDate": START, "endDate": END, "granularity": "day", "accountLimit": 100},
            "vcat_get_post_trend": {"platform": "视频号", "startDate": START, "endDate": END, "topLimit": 50},
            "vcat_get_post_sync": {},
            "vcat_list_post_sync_records": {"page": 1, "pageSize": 100},
            "vcat_list_batch_tasks": {"page": 1, "pageSize": 100},
            "vcat_list_orders": {"platform": "视频号带货助手", "startDate": START, "endDate": END, "page": 1, "pageSize": 100},
            "vcat_get_order_overview": {"platform": "视频号带货助手"},
            "vcat_get_order_daily": {"platform": "视频号带货助手", "startDate": START, "endDate": END, "page": 1, "pageSize": 100},
            "vcat_get_order_sync_status": {"platform": "视频号带货助手"},
            "vcat_list_shop_tasks": {"page": 1, "pageSize": 100},
            "vcat_get_shop_options": {"platform": "视频号带货助手"},
            "vcat_list_monitor_tasks": {"page": 1, "pageSize": 100},
            "vcat_list_monitor_records": {"taskId": 1, "type": "all", "page": 1, "pageSize": 100},
            "vcat_get_flow_report": {"platform": "视频号", "points": 12, "page": 1, "pageSize": 50},
            "vcat_get_comment_summary": {},
            "vcat_list_comments": {"startDate": START, "endDate": END, "page": 1, "pageSize": 100},
            "vcat_get_unread_messages": {},
            "vcat_list_message_sessions": {"startDate": START, "endDate": END, "page": 1, "pageSize": 100},
            "vcat_list_groups": {},
            "vcat_list_tags": {},
            "vcat_list_proxies": {},
            "vcat_list_login_links": {},
            "vcat_list_duplicate_accounts": {},
            "vcat_list_verify_results": {"platform": "视频号", "page": 1, "pageSize": 100},
            "vcat_list_punish_feeds": {"platform": "视频号", "page": 1, "pageSize": 100},
            "vcat_get_verify_auto_setting": {},
            "vcat_list_verify_logs": {"limit": 100},
        }
        if uid:
            calls["vcat_list_shop_goods"] = {"platform": "Channels", "uid": uid, "page": 1, "includeRaw": False}
            calls["vcat_search_shop_goods"] = {"platform": "Channels", "uid": uid, "items": ["短剧"], "page": 1}
            calls["vcat_get_verify_result"] = {"uid": uid}
            calls["vcat_get_verify_links"] = {"uids": valid_uids[:50]}

        results = {name: invoke(client, name, args) for name, args in calls.items()}
        payload = {
            "capturedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "dateRange": [START, END],
            "toolListCount": len(all_tools),
            "readOnlyToolCount": sum(1 for tool in all_tools if (tool.get("annotations") or {}).get("readOnlyHint")),
            "nonReadOnlyToolCount": sum(1 for tool in all_tools if not (tool.get("annotations") or {}).get("readOnlyHint")),
            "toolNames": [tool.get("name") for tool in all_tools],
            "currentValidAccountCount": len(valid_uids),
            "readOnlyProbes": results,
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "probed": len(results), "validAccounts": len(valid_uids)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
