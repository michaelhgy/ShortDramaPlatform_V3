"""Collect remaining non-excluded Xiao V data categories from local MCP data.

Only read-only tools are called.  No platform refresh, verification refresh,
order sync, shop query, message query, publish, delete, or settings operation
is performed here.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.publishing.vcat import VcatClient


START = "2026-10-22"
END = "2026-10-28"
OUTPUT = Path("docs/事项档案/小V猫剩余数据全量快照-2026-10-29.json")


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
                return {"message": text}
    return result


def redact(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if lowered in {
        "url", "cover", "avatar", "exportid", "video_path", "videopath",
        "savedir", "file_path", "filepath", "thumburl", "fullthumburl",
        "fullcoverurl", "downloadurl", "mediaurl",
    }:
        return {"present": bool(value)}
    if lowered in {"formdata", "pubpost", "raw", "media", "images"}:
        return {"present": bool(value), "itemCount": len(value) if isinstance(value, list) else None}
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item, key) for item in value]
    if isinstance(value, str) and (value.startswith("http://") or value.startswith("https://") or value.startswith("file://")):
        return {"present": True}
    return value


def call(client: VcatClient, name: str, arguments: dict[str, Any]) -> Any:
    try:
        return parse_result(client.request("tools/call", {"name": name, "arguments": arguments}))
    except Exception as exc:
        return {"error": str(exc)}


def paginate(client: VcatClient, name: str, base: dict[str, Any], *, page_size: int = 100) -> Any:
    rows: list[Any] = []
    first: Any = None
    for page in range(1, 100):
        args = {**base, "page": page, "pageSize": page_size}
        value = call(client, name, args)
        if first is None:
            first = value
        if not isinstance(value, dict):
            return value
        batch = value.get("list") or []
        rows.extend(batch)
        total = value.get("total")
        if not batch or not isinstance(total, int) or len(rows) >= total:
            result = {k: v for k, v in value.items() if k != "list"}
            result["list"] = rows
            return result
    return {"list": rows, "truncated": True, "first": first}


def main() -> None:
    with VcatClient() as client:
        accounts = call(client, "vcat_list_accounts", {"platform": "Channels", "page": 1, "pageSize": 100})
        account_rows = accounts.get("list", []) if isinstance(accounts, dict) else []
        uids = [str(row.get("uid")) for row in account_rows if row.get("uid")]

        diagnostics_detail = {
            uid: call(client, "vcat_get_verify_result", {"uid": uid})
            for uid in uids
        }
        monitor_tasks = paginate(client, "vcat_list_monitor_tasks", {})
        monitor_records = {}
        for task in (monitor_tasks.get("list", []) if isinstance(monitor_tasks, dict) else []):
            task_id = task.get("id")
            if task_id is not None:
                monitor_records[str(task_id)] = call(
                    client,
                    "vcat_list_monitor_records",
                    {"taskId": task_id, "type": "all", "page": 1, "pageSize": 100},
                )

        payload = {
            "capturedAt": datetime.now().isoformat(timespec="seconds"),
            "dateRange": [START, END],
            "scope": {
                "included": [
                    "account_overview", "diagnostics", "punish_feeds", "publish_tasks",
                    "drafts", "publish_options", "groups_tags", "monitor_tasks",
                    "batch_tasks", "flow_report", "sync_records",
                ],
                "excluded": ["live_status", "orders_commission", "shop_goods", "comments_messages"],
                "refreshTriggered": False,
            },
            "accountUniverse": redact(accounts),
            "accountOverview": redact(call(client, "vcat_get_overview", {})),
            "diagnostics": {
                "list": redact(call(client, "vcat_list_verify_results", {"platform": "视频号", "page": 1, "pageSize": 100})),
                "details": redact(diagnostics_detail),
                "punishFeeds": redact(paginate(client, "vcat_list_punish_feeds", {"platform": "视频号"})),
                "logs": redact(call(client, "vcat_list_verify_logs", {"limit": 300})),
                "autoSetting": redact(call(client, "vcat_get_verify_auto_setting", {})),
                "verifyLinks": redact(call(client, "vcat_get_verify_links", {"uids": uids[:50]})) if uids else {},
            },
            "publishing": {
                "options": redact(call(client, "vcat_get_publish_options", {})),
                "drafts": redact(paginate(client, "vcat_list_drafts", {})),
                "tasks": redact(paginate(client, "vcat_list_publish_tasks", {"platform": "视频号"})),
                "stats": redact(call(client, "vcat_get_publish_task_stat", {"platform": "视频号", "startDate": START, "endDate": END})),
            },
            "organization": {
                "groups": redact(call(client, "vcat_list_groups", {})),
                "tags": redact(call(client, "vcat_list_tags", {})),
                "proxies": redact(call(client, "vcat_list_proxies", {})),
                "duplicates": redact(call(client, "vcat_list_duplicate_accounts", {})),
                "loginLinks": redact(call(client, "vcat_list_login_links", {})),
            },
            "operations": {
                "batchTasks": redact(paginate(client, "vcat_list_batch_tasks", {})),
                "monitorTasks": redact(monitor_tasks),
                "monitorRecords": redact(monitor_records),
                "flowReport": redact(call(client, "vcat_get_flow_report", {"platform": "视频号", "points": 60, "page": 1, "pageSize": 50})),
                "postSync": redact(call(client, "vcat_get_post_sync", {})),
                "postSyncRecords": redact(paginate(client, "vcat_list_post_sync_records", {})),
            },
        }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "accounts": len(uids)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
