"""Read daily metrics only for posts needed by the dashboard rankings.

This is a cache read. It does not call a refresh or post-sync operation.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.publishing.vcat import VcatClient


def main() -> None:
    source = Path("docs/事项档案/小V猫视频号数据补采-2026-10-30.json")
    output = Path("docs/事项档案/小V猫看板关键作品日数据-2026-10-30.json")
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    top = [item for item in (snapshot.get("postTrend") or {}).get("top") or [] if item.get("postId") and item.get("uid")]
    result: dict[str, object] = {
        "capturedAt": datetime.now().isoformat(timespec="seconds"),
        "source": "小V猫 MCP / 已有本地作品缓存",
        "dateRange": snapshot.get("dateRange") or [],
        "refreshTriggered": False,
        "requestedCount": len(top),
        "posts": {},
    }
    with VcatClient() as client:
        for item in top:
            key = f"{item['uid']}:{item['postId']}"
            result["posts"][key] = {
                "post": item,
                "daily": client.call("vcat_get_post_daily", {
                    "postId": str(item["postId"]),
                    "uid": str(item["uid"]),
                    "startDate": str((snapshot.get("dateRange") or ["", ""])[0]),
                    "endDate": str((snapshot.get("dateRange") or ["", ""])[1]),
                }),
            }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "requested": len(top)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
