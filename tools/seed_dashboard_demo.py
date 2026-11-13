"""Seed and remove isolated Xiao V Cat post-stat fixtures for dashboard review.

The fixture rows are marked with source_kind='simulation:xiao_v' and can be
removed without touching real account snapshots or theater revenue rows.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime, timedelta

from server.v2_file_service import connection

SOURCE_KIND = "simulation:xiao_v"
def seed(conn) -> int:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)
    rows = conn.execute(
        """SELECT id, nickname, channel_id FROM accounts
           WHERE TRIM(COALESCE(channel_id, '')) <> ''
             AND COALESCE(status, '') NOT IN ('停用', 'disabled')
             AND EXISTS (
               SELECT 1 FROM v3_account_data_snapshots s
               WHERE s.account_id=accounts.id AND s.collection_day=?
                 AND s.status='success' AND s.data_state='record'
             )
           ORDER BY nickname, id LIMIT 6"""
        , (end.isoformat(),)).fetchall()
    if not rows:
        raise RuntimeError("没有可用于看板模拟数据的已登记视频号账号")

    now = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    for account_index, account in enumerate(rows):
        for post_index in range(4):
            post_id = f"demo-xiao-v-{account_index + 1}-{post_index + 1}"
            base = [680, 420, 260, 110][post_index] * (1 + account_index * 0.13)
            for day_offset in range(7):
                collection_day = start + timedelta(days=day_offset)
                wave = [0.72, 0.9, 1.1, 0.82, 1.28, 1.0, 1.55][day_offset]
                spike = 2.4 if account_index == 0 and post_index == 0 and day_offset == 6 else 1
                views = int(base * wave * spike)
                payload = {
                    "postId": post_id,
                    "uid": account["channel_id"],
                    "platform": "Channels",
                    "account": account["nickname"],
                    # The current real Channels response returns title=null
                    # and desc="" for synced posts. Keep fixtures faithful so
                    # the UI never presents a title as a confirmed drama name.
                    "title": None,
                    "desc": "",
                    "postType": "视频",
                    "postTypeCode": "1",
                    "publishStatus": "published",
                    "postTime": f"{collection_day.isoformat()} 18:{10 + post_index:02d}:00",
                    "view": views,
                    "like": round(views * (0.028 + post_index * 0.004)),
                    "comment": round(views * (0.002 + (account_index % 3) * 0.001)),
                    "forward": round(views * (0.004 + post_index * 0.001)),
                    "love": round(views * (0.012 + account_index * 0.001)),
                    "fansAdd": round(views * (0.006 + post_index * 0.001)),
                    "fullView": round(views * (0.18 + post_index * 0.03), 2),
                    "viewTime": round(42 + views / 80 + post_index * 3, 2),
                    "videoTime": 680 + post_index * 25,
                    "daily": [{"date": collection_day.isoformat(), "view": views}],
                }
                conn.execute(
                    """INSERT INTO v3_account_post_snapshots(
                       id, account_id, uid, account_name, platform, collection_day,
                       post_id, post_time, title, post_type, publish_status,
                       data_state, metric_grain, source_kind, fetched_at,
                       payload_json, error_message)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(uid, post_id, collection_day, source_kind) DO UPDATE SET
                         account_name=excluded.account_name, collection_day=excluded.collection_day,
                         post_time=excluded.post_time, title=excluded.title,
                         payload_json=excluded.payload_json, fetched_at=excluded.fetched_at,
                         data_state=excluded.data_state, metric_grain=excluded.metric_grain""",
                    (
                        uuid.uuid4().hex, account["id"], account["channel_id"], account["nickname"],
                        "Channels", collection_day.isoformat(), post_id, payload["postTime"],
                        "", "video", "published", "record", "daily", SOURCE_KIND,
                        now, json.dumps(payload, ensure_ascii=False), "",
                    ),
                )
                inserted += 1
    conn.commit()
    return inserted


def clear(conn) -> int:
    result = conn.execute("DELETE FROM v3_account_post_snapshots WHERE source_kind=?", (SOURCE_KIND,))
    conn.commit()
    return result.rowcount


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "clear"))
    args = parser.parse_args()
    with connection() as conn:
        count = seed(conn) if args.action == "seed" else clear(conn)
    print(json.dumps({"action": args.action, "source_kind": SOURCE_KIND, "rows": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
