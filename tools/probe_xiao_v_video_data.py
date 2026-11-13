"""Capture the currently available Xiao V video-account data without refreshing.

This is an evidence probe for the data-base design stage.  It intentionally
does not call any refresh/sync tool.  The separate refresh was performed once
by the operator before this snapshot was taken.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.publishing.vcat import VcatClient


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"url", "cover", "avatar", "videoUrl", "imageUrl"}:
                result[key + "Present"] = bool(item)
                continue
            result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def list_all_posts(client: VcatClient) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    page = 1
    response: dict[str, Any] = {}
    while page <= 100:
        response = client.call(
            "vcat_list_posts",
            {"platform": "视频号", "page": page, "pageSize": 100},
        )
        batch = response.get("list") or []
        rows.extend(batch)
        if not batch or len(rows) >= int(response.get("total") or len(rows)):
            break
        page += 1
    return response, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-10-22")
    parser.add_argument("--end", default="2026-10-28")
    parser.add_argument(
        "--output",
        default="docs/事项档案/小V猫视频号数据能力实测-2026-10-29.json",
    )
    parser.add_argument(
        "--all-post-data",
        action="store_true",
        help="逐条读取本地缓存中的作品详情和分日数据，不触发平台刷新",
    )
    args = parser.parse_args()

    with VcatClient() as client:
        accounts = client.call("vcat_list_accounts", {"platform": "Channels", "page": 1, "pageSize": 100})
        valid = [row for row in accounts.get("list", []) if row.get("loginStatus") == "登录有效"]
        sync_status = client.call("vcat_get_post_sync", {})
        try:
            sync_records_response = client.request(
                "tools/call",
                {"name": "vcat_list_post_sync_records", "arguments": {"page": 1, "pageSize": 100}},
            )
            sync_records = json.loads(
                sync_records_response["result"]["content"][0]["text"]
            )
        except Exception as exc:  # keep the rest of the field probe useful
            sync_records = {"error": str(exc)}
        post_response, posts = list_all_posts(client)

        account_ranking = client.call(
            "vcat_get_account_stats",
            {
                "platform": "视频号",
                "startDate": args.start,
                "endDate": args.end,
                "includeIncome": True,
                "sortBy": "view",
                "page": 1,
                "pageSize": 100,
            },
        )
        account_details: dict[str, Any] = {}
        for account in valid:
            uid = str(account.get("uid"))
            account_details[uid] = client.call(
                "vcat_get_account_stats",
                {
                    "uid": uid,
                    "startDate": args.start,
                    "endDate": args.end,
                    "includeIncome": True,
                },
            )

        post_stat = client.call(
            "vcat_get_post_stat",
            {
                "platform": "视频号",
                "startDate": args.start,
                "endDate": args.end,
                "granularity": "day",
                "accountLimit": 100,
            },
        )
        post_trend = client.call(
            "vcat_get_post_trend",
            {
                "platform": "视频号",
                "startDate": args.start,
                "endDate": args.end,
                "topLimit": 50,
            },
        )

        # A small cross-section is enough to discover detail and daily schemas;
        # all list rows and all account daily rows are retained above.
        sample_posts: dict[str, Any] = {}
        seen_uids: set[str] = set()
        for post in posts:
            uid = str(post.get("uid"))
            if uid not in {str(row.get("uid")) for row in valid} or uid in seen_uids:
                continue
            post_id = str(post.get("postId"))
            sample_posts[uid] = {
                "postId": post_id,
                "detail": client.call("vcat_get_post", {"postId": post_id, "uid": uid}),
                "daily": client.call(
                    "vcat_get_post_daily",
                    {"postId": post_id, "uid": uid, "startDate": args.start, "endDate": args.end},
                ),
            }
            seen_uids.add(uid)

        all_post_details: dict[str, Any] = {}
        all_post_daily: dict[str, Any] = {}
        if args.all_post_data:
            for index, post in enumerate(posts, start=1):
                uid = str(post.get("uid"))
                post_id = str(post.get("postId"))
                key = f"{uid}:{post_id}"
                try:
                    all_post_details[key] = client.call(
                        "vcat_get_post", {"postId": post_id, "uid": uid}
                    )
                except Exception as exc:
                    all_post_details[key] = {"error": str(exc)}
                try:
                    all_post_daily[key] = client.call(
                        "vcat_get_post_daily",
                        {
                            "postId": post_id,
                            "uid": uid,
                            "startDate": args.start,
                            "endDate": args.end,
                        },
                    )
                except Exception as exc:
                    all_post_daily[key] = {"error": str(exc)}
                if index % 50 == 0:
                    print(f"post-detail-progress {index}/{len(posts)}", flush=True)

        payload = {
            "capturedAt": datetime.now().isoformat(timespec="seconds"),
            "source": "小V猫 MCP / 视频号官方后台同步后的本地数据",
            "dateRange": [args.start, args.end],
            "accounts": redact(accounts),
            "validAccountUids": [row.get("uid") for row in valid],
            "postSync": redact(sync_status),
            "postSyncRecords": redact(sync_records),
            "postProfile": {
                "reportedTotal": post_response.get("total"),
                "rowCount": len(posts),
                "keys": sorted({key for row in posts for key in row}),
                "countsByUid": dict(Counter(str(row.get("uid")) for row in posts)),
                "titleNonEmpty": sum(bool(row.get("title")) for row in posts),
                "descNonEmpty": sum(bool(row.get("desc")) for row in posts),
                "postTimeMin": min((str(row.get("postTime")) for row in posts if row.get("postTime")), default=None),
                "postTimeMax": max((str(row.get("postTime")) for row in posts if row.get("postTime")), default=None),
                "metricPresence": {
                    key: sum(key in row and row.get(key) is not None for row in posts)
                    for key in [
                        "view", "like", "comment", "forward", "love", "fansAdd",
                        "fullView", "viewTime", "url", "cover", "timing",
                    ]
                },
                "rows": [redact(row) for row in posts],
            },
            "accountRanking": redact(account_ranking),
            "accountDetails": redact(account_details),
            "postStat": redact(post_stat),
            "postTrend": redact(post_trend),
            "postDetailSamples": redact(sample_posts),
        }
        if args.all_post_data:
            payload["postDetails"] = redact(all_post_details)
            payload["postDaily"] = redact(all_post_daily)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "validAccounts": len(valid), "posts": len(posts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
