"""Seed a complete, clearly marked analytics demo dataset.

The seed is designed for the future dashboard only.  It writes to the V3
analytics tables, never calls Xiao V or a theater website, and never changes
the legacy V2 revenue tables.  All rows use ``simulation_ui`` and can be
removed with ``--reset`` or by rerunning the seed.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.analytics_data import initialize


SIM_SOURCE = "simulation_ui"
SIM_ADAPTER_PREFIX = "simulation_"
CAPTURED_AT = "2026-10-30T10:00:00+08:00"
SNAPSHOT_DATE = date(2026, 10, 29)
DAILY_START = date(2026, 9, 30)
POST_DAILY_START = date(2026, 10, 16)
SHANGHAI = timezone(timedelta(hours=8))
DEFAULT_DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")


PROFILES = [
    ("北辰短剧", "重点账号", 420_000, 0.22, 0.05, 58_000, 1.25),
    ("橙光推剧", "重点账号", 305_000, 0.12, 0.08, 42_000, 1.10),
    ("星野短剧", "成长账号", 188_000, 0.30, 0.13, 26_500, 1.18),
    ("拾光剧推", "成长账号", 142_000, 0.18, 0.10, 19_000, 0.95),
    ("南风短剧", "成长账号", 96_000, 0.42, 0.15, 13_000, 1.05),
    ("小满剧推", "观察账号", 72_000, -0.16, 0.18, 9_800, 0.82),
    ("七月影库", "观察账号", 51_000, 0.06, 0.24, 7_200, 0.76),
    ("锦书短剧", "观察账号", 38_000, -0.28, 0.12, 5_400, 0.68),
    ("微光剧推", "成长账号", 27_000, 0.36, 0.22, 4_100, 0.91),
    ("风铃短剧", "观察账号", 18_000, 0.04, 0.26, 2_900, 0.60),
    ("漫漫剧场", "观察账号", 11_000, 0.65, 0.30, 1_800, 0.73),
    ("白昼剧推", "观察账号", 6_500, -0.42, 0.20, 1_100, 0.48),
]

DRAMAS = [
    ("sim-drama-01", "藏在月光里的秘密"),
    ("sim-drama-02", "再见不负相思意"),
    ("sim-drama-03", "她从风里来"),
    ("sim-drama-04", "错位心动"),
]
HOOKS = ["她终于说出真相", "他把戒指放回桌上", "所有人都看错了", "这一晚彻底失控", "她没有等到道歉", "三年前的秘密", "他决定重新开始", "最后一句让人沉默"]


def stable_id(key: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"short-drama-demo:{key}").hex


def payload(**values: Any) -> str:
    return json.dumps({"simulation": True, "simulationVersion": 1, **values}, ensure_ascii=False, separators=(",", ":"))


def day_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def n(value: float, minimum: int = 0) -> int:
    return max(minimum, int(round(value)))


def account_ids(index: int) -> tuple[str, str]:
    number = index + 1
    return f"sim-uid-{number:02d}", f"sim-account-{number:02d}"


def delete_demo_rows(conn: sqlite3.Connection) -> None:
    for table in (
        "v3_analytics_collection_items",
        "v3_video_accounts",
        "v3_video_account_daily",
        "v3_video_posts",
        "v3_video_post_daily",
        "v3_video_account_diagnostics",
        "v3_video_post_punishments",
        "v3_revenue_account_periods",
        "v3_revenue_details",
    ):
        conn.execute(f"DELETE FROM {table} WHERE source_kind=?", (SIM_SOURCE,))
    conn.execute("DELETE FROM v3_revenue_sources WHERE adapter_key LIKE ?", (f"{SIM_ADAPTER_PREFIX}%",))
    conn.execute(
        "DELETE FROM v3_analytics_collection_runs WHERE trigger_source=? AND acquisition_layer=?",
        ("demo_seed", SIM_SOURCE),
    )


def insert_run(conn: sqlite3.Connection, domain: str, start: str, end: str, coverage: dict[str, int]) -> str:
    run_id = stable_id(f"run:{domain}")
    conn.execute(
        """INSERT INTO v3_analytics_collection_runs(
           id,domain,source_system,acquisition_layer,storage_layer,requested_start_date,
           requested_end_date,trigger_source,refresh_triggered,source_captured_at,status,
           coverage_json,error_message,created_at,finished_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id, domain, "demo_generator", SIM_SOURCE, "v3_snapshot", start, end,
            "demo_seed", 0, CAPTURED_AT, "completed", json.dumps(coverage, ensure_ascii=False),
            "", CAPTURED_AT, CAPTURED_AT,
        ),
    )
    return run_id


def insert_item(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    domain: str,
    entity_type: str,
    entity_key: str,
    account_id: str = "",
    uid: str = "",
    theater_id: str = "",
    stat_date: str = "",
    period_start: str = "",
    period_end: str = "",
    data_state: str = "record",
    payload_json: str = "{}",
) -> None:
    conn.execute(
        """INSERT INTO v3_analytics_collection_items(
           id,run_id,domain,entity_type,entity_key,account_id,uid,theater_id,stat_date,
           period_start,period_end,data_state,freshness_state,source_kind,fetched_at,
           error_message,payload_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            stable_id(f"item:{run_id}:{entity_type}:{entity_key}:{stat_date}:{period_start}"),
            run_id, domain, entity_type, entity_key, account_id, uid, theater_id, stat_date,
            period_start, period_end, data_state, "simulated", SIM_SOURCE, CAPTURED_AT, "", payload_json,
        ),
    )


def theater_ids(conn: sqlite3.Connection) -> tuple[str, str]:
    rows = {row[0]: row[1] for row in conn.execute("SELECT name,id FROM theaters")}
    return rows.get("青柠剧场", "sim-theater-qingning"), rows.get("触摸剧场", "sim-theater-touch")


def seed(conn: sqlite3.Connection) -> dict[str, int]:
    initialize(conn)
    delete_demo_rows(conn)
    qingning_id, touch_id = theater_ids(conn)
    video_run = insert_run(conn, "video", DAILY_START.isoformat(), SNAPSHOT_DATE.isoformat(), {})
    revenue_run = insert_run(conn, "revenue", DAILY_START.isoformat(), SNAPSHOT_DATE.isoformat(), {})

    account_daily: dict[str, dict[date, dict[str, int]]] = {}
    account_info: list[dict[str, Any]] = []
    for index, (name, group, base_view, growth, volatility, fans_start, quality) in enumerate(PROFILES):
        uid, account_id = account_ids(index)
        daily: dict[date, dict[str, int]] = {}
        fans_total = fans_start
        for day_index, current in enumerate(day_range(DAILY_START, SNAPSHOT_DATE)):
            progress = day_index / 29
            wave = math.sin((day_index + index * 1.7) * 0.72) * volatility
            weekend = 1.12 if current.weekday() in (5, 6) else 1.0
            view = n(base_view * (0.88 + growth * progress + wave) * weekend)
            fans_add = n(view / 14_000 * quality * (0.90 + 0.18 * math.sin(day_index + index)))
            fans_reduce = n(view / 90_000 * (1.25 if growth < 0 else 0.55) * (1 + volatility))
            fans_net = fans_add - fans_reduce
            fans_total += fans_net
            daily[current] = {
                "view": view,
                "fans_total": fans_total,
                "fans_add": fans_add,
                "fans_net": fans_net,
                "fans_reduce": fans_reduce,
                "like": n(view * (0.018 + quality * 0.002)),
                "favorite": n(view * (0.009 + quality * 0.001)),
                "comment": n(view * (0.0012 + volatility * 0.0005)),
                "forward": n(view * (0.002 + quality * 0.0004)),
            }
            insert_item(conn, video_run, domain="video", entity_type="account_daily", entity_key=uid,
                        account_id=account_id, uid=uid, stat_date=current.isoformat(),
                        payload_json=payload(accountName=name, generatedDate=current.isoformat()))
            conn.execute(
                """INSERT INTO v3_video_account_daily(
                   id,uid,account_id,stat_date,view,fans_total,fans_add,fans_net,fans_reduce,
                   like_count,favorite_count,comment_count,forward_count,source_kind,data_state,
                   freshness_state,collection_run_id,fetched_at,payload_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stable_id(f"account-daily:{uid}:{current}"), uid, account_id, current.isoformat(),
                    daily[current]["view"], daily[current]["fans_total"], daily[current]["fans_add"],
                    daily[current]["fans_net"], daily[current]["fans_reduce"], daily[current]["like"],
                    daily[current]["favorite"], daily[current]["comment"], daily[current]["forward"],
                    SIM_SOURCE, "record", "simulated", video_run, CAPTURED_AT,
                    payload(accountName=name, generatedDate=current.isoformat()),
                ),
            )
        account_daily[uid] = daily
        account_info.append({
            "uid": uid, "account_id": account_id, "name": name, "group": group,
            "quality": quality, "fans_total": fans_total, "base_view": base_view,
            "growth": growth, "volatility": volatility,
        })

    for info in account_info:
        uid, account_id, name = info["uid"], info["account_id"], info["name"]
        group = info["group"]
        diagnostics = {
            "verified": 0 if uid in {"sim-uid-06", "sim-uid-12"} else 1,
            "abnormal": 1 if uid in {"sim-uid-06", "sim-uid-08", "sim-uid-12"} else 0,
            "videoStatus": "需复核" if uid in {"sim-uid-06", "sim-uid-12"} else "正常",
            "heatStatus": "偏低" if uid == "sim-uid-08" else "正常",
            "abnormalPostCount": 2 if uid == "sim-uid-06" else (1 if uid == "sim-uid-08" else 0),
            "lastVerifyTime": SNAPSHOT_DATE.isoformat(),
        }
        conn.execute(
            """INSERT INTO v3_video_accounts(
               id,uid,account_id,account_name,platform,login_status,fans_total,group_name,
               tags_json,snapshot_date,source_kind,data_state,freshness_state,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                stable_id(f"account:{uid}"), uid, account_id, name, "Channels", "登录有效",
                info["fans_total"], group, json.dumps([group, "演示账号"], ensure_ascii=False),
                SNAPSHOT_DATE.isoformat(), SIM_SOURCE, "record", "simulated", CAPTURED_AT,
                payload(accountName=name, accountGroup=group),
            ),
        )
        insert_item(conn, video_run, domain="video", entity_type="account_snapshot", entity_key=uid,
                    account_id=account_id, uid=uid, stat_date=SNAPSHOT_DATE.isoformat(),
                    payload_json=payload(accountName=name))
        conn.execute(
            """INSERT INTO v3_video_account_diagnostics(
               id,uid,account_id,account_name,verified,abnormal,video_status,heat_status,
               abnormal_post_count,last_verify_time,snapshot_date,source_kind,data_state,
               freshness_state,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                stable_id(f"diagnostic:{uid}"), uid, account_id, name, diagnostics["verified"],
                diagnostics["abnormal"], diagnostics["videoStatus"], diagnostics["heatStatus"],
                diagnostics["abnormalPostCount"], diagnostics["lastVerifyTime"], SNAPSHOT_DATE.isoformat(),
                SIM_SOURCE, "record", "simulated", CAPTURED_AT, payload(**diagnostics),
            ),
        )
        insert_item(conn, video_run, domain="video", entity_type="account_diagnostic", entity_key=uid,
                    account_id=account_id, uid=uid, stat_date=SNAPSHOT_DATE.isoformat(),
                    payload_json=payload(**diagnostics))

    posts: list[dict[str, Any]] = []
    post_daily_dates = list(day_range(POST_DAILY_START, SNAPSHOT_DATE))
    post_quality = [2.8, 1.95, 1.55, 1.2, 0.92, 0.70, 0.48, 0.30]
    for account_index, info in enumerate(account_info):
        uid, account_id, name = info["uid"], info["account_id"], info["name"]
        for post_index in range(8):
            post_id = f"sim-post-{account_index + 1:02d}-{post_index + 1:02d}"
            drama_id, drama_name = DRAMAS[(account_index + post_index) % len(DRAMAS)]
            publish_day = SNAPSHOT_DATE - timedelta(days=post_index * 2 + 1)
            # The Xiao V post response does not reliably provide a work title.
            # Keep the demo faithful: use placement account + post ID as the
            # visible identifiers and leave title/description empty.
            post_title = ""
            post_daily: list[dict[str, Any]] = []
            for metric_index, current in enumerate(post_daily_dates):
                if current < publish_day:
                    view = 0
                else:
                    age = (current - publish_day).days
                    ramp = min(1.0, (age + 1) / 3)
                    decay = max(0.45, 1.0 - max(0, age - 5) * 0.035)
                    wave = 1.0 + 0.10 * math.sin((metric_index + account_index) * 0.9)
                    view = n(info["base_view"] * 0.021 * post_quality[post_index] * ramp * decay * wave * (0.78 + info["quality"] * 0.22))
                like = n(view * (0.016 + info["quality"] * 0.002))
                forward = n(view * (0.0018 + info["quality"] * 0.0004))
                favorite = n(view * (0.008 + info["quality"] * 0.001))
                fans_add = n(view / 16_000 * info["quality"])
                post_daily.append({"date": current, "view": view, "like": like, "forward": forward, "favorite": favorite, "fans_add": fans_add})
                insert_item(conn, video_run, domain="video", entity_type="post_daily", entity_key=post_id,
                            account_id=account_id, uid=uid, stat_date=current.isoformat(),
                            payload_json=payload(postId=post_id, account=name))
                conn.execute(
                    """INSERT INTO v3_video_post_daily(
                       id,post_id,uid,account_id,stat_date,view,like_count,comment_count,
                       forward_count,favorite_count,fans_add,metric_grain,source_kind,data_state,
                       freshness_state,collection_run_id,fetched_at,payload_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        stable_id(f"post-daily:{post_id}:{current}"), post_id, uid, account_id, current.isoformat(),
                        view, like, n(view * 0.0008), forward, favorite, fans_add, "daily", SIM_SOURCE,
                        "record", "simulated", video_run, CAPTURED_AT,
                        payload(postId=post_id, account=name, statDate=current.isoformat()),
                    ),
                )
            total_view = sum(row["view"] for row in post_daily)
            total_like = sum(row["like"] for row in post_daily)
            total_forward = sum(row["forward"] for row in post_daily)
            total_favorite = sum(row["favorite"] for row in post_daily)
            full_view = round(0.22 + ((account_index + post_index) % 6) * 0.065, 3)
            view_time = round(9.5 + ((account_index * 3 + post_index) % 8) * 2.1, 1)
            posts.append({
                "post_id": post_id, "uid": uid, "account_id": account_id, "account_name": name,
                "title": post_title, "drama_id": drama_id, "drama_name": drama_name,
                "publish_day": publish_day, "view": total_view, "like": total_like,
                "forward": total_forward, "favorite": total_favorite, "fans_add": sum(row["fans_add"] for row in post_daily),
                "full_view": full_view, "view_time": view_time,
            })
            conn.execute(
                """INSERT INTO v3_video_posts(
                   id,post_id,uid,account_id,account_name,platform,post_time,title,description,
                   cover_present,url_present,post_type,publish_status,timing,view,like_count,
                   comment_count,forward_count,love_count,fans_add,full_view,view_time,snapshot_date,
                   source_kind,data_state,freshness_state,collection_run_id,fetched_at,payload_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stable_id(f"post:{post_id}"), post_id, uid, account_id, name, "Channels",
                    f"{publish_day.isoformat()} 20:{(post_index * 7) % 60:02d}:00", post_title,
                    "", 1, 1, "短剧", "已发布",
                    "已公开", total_view, total_like, n(total_view * 0.0008), total_forward,
                    n(total_like * 0.08), sum(row["fans_add"] for row in post_daily), full_view, view_time,
                    SNAPSHOT_DATE.isoformat(), SIM_SOURCE, "record", "simulated", video_run, CAPTURED_AT,
                    payload(postId=post_id, account=name),
                ),
            )
            insert_item(conn, video_run, domain="video", entity_type="post_snapshot", entity_key=post_id,
                        account_id=account_id, uid=uid, stat_date=SNAPSHOT_DATE.isoformat(),
                        payload_json=payload(postId=post_id, account=name))

    punish_posts = [posts[5], posts[22], posts[47], posts[63], posts[88]]
    punish_states = ["推荐曝光减少", "内容质量波动", "待复核", "推荐曝光减少", "账号内容异常"]
    for post, state in zip(punish_posts, punish_states):
        conn.execute(
            """INSERT INTO v3_video_post_punishments(
               id,uid,account_id,post_id_or_export_id,title,publish_time,punish_state,
               snapshot_date,source_kind,data_state,freshness_state,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                stable_id(f"punishment:{post['post_id']}"), post["uid"], post["account_id"], post["post_id"],
                post["title"], f"{post['publish_day'].isoformat()} 20:00:00", state,
                SNAPSHOT_DATE.isoformat(), SIM_SOURCE, "record", "simulated", CAPTURED_AT,
                payload(postId=post["post_id"], punishmentState=state),
            ),
        )
        insert_item(conn, video_run, domain="video", entity_type="post_punishment", entity_key=post["post_id"],
                    account_id=post["account_id"], uid=post["uid"], stat_date=SNAPSHOT_DATE.isoformat(),
                    payload_json=payload(postId=post["post_id"], punishmentState=state))

    conn.execute(
        """INSERT INTO v3_revenue_sources(
           id,theater_id,adapter_key,query_url,query_mode,date_precision,supports_detail,
           requires_account_id,requires_date,adapter_status,last_checked_at,notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            stable_id("source:qingning"), qingning_id, "simulation_qingning", "", "date_range", "day", 1,
            1, 1, "simulation_only", CAPTURED_AT, "演示数据；模拟青柠按日明细结构，不代表已查询线上接口",
        ),
    )
    conn.execute(
        """INSERT INTO v3_revenue_sources(
           id,theater_id,adapter_key,query_url,query_mode,date_precision,supports_detail,
           requires_account_id,requires_date,adapter_status,last_checked_at,notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            stable_id("source:touch"), touch_id, "simulation_touch", "", "month_cumulative", "month", 0,
            1, 0, "simulation_only", CAPTURED_AT, "演示数据；模拟触摸累计金额结构，不代表已查询线上接口",
        ),
    )

    revenue_detail_count = 0
    revenue_period_count = 0
    recent_days = list(day_range(POST_DAILY_START, SNAPSHOT_DATE))
    for info in account_info:
        uid, account_id = info["uid"], info["account_id"]
        for current in day_range(DAILY_START, SNAPSHOT_DATE):
            metrics = account_daily[uid][current]
            amount = round(metrics["view"] * (0.00018 + info["quality"] * 0.000018), 2)
            conn.execute(
                """INSERT INTO v3_revenue_account_periods(
                   id,account_id,theater_id,period_label,period_start,period_end,period_type,
                   date_precision,amount,currency,data_state,freshness_state,settlement_state,
                   include_in_analysis,source_kind,source_attempt_id,collection_run_id,collected_at,
                   raw_result_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stable_id(f"revenue-day:{account_id}:{current}"), account_id, qingning_id, current.isoformat(),
                    current.isoformat(), current.isoformat(), "day", "day", f"{amount:.2f}", "CNY", "record",
                    "simulated", "unsettled", 1, SIM_SOURCE, stable_id(f"attempt:{account_id}:{current}"),
                    revenue_run, CAPTURED_AT, payload(shape="account_daily_total", accountId=account_id, date=current.isoformat()),
                ),
            )
            insert_item(conn, revenue_run, domain="revenue", entity_type="account_period", entity_key=f"{account_id}:{current}",
                        account_id=account_id, theater_id=qingning_id, period_start=current.isoformat(), period_end=current.isoformat(),
                        payload_json=payload(shape="account_daily_total", date=current.isoformat()))
            revenue_period_count += 1
        current_month_total = sum(float(account_daily[uid][day]["view"]) * (0.00018 + info["quality"] * 0.000018) for day in day_range(date(2026, 10, 1), SNAPSHOT_DATE))
        previous_month_total = current_month_total * (0.73 + (int(info["uid"][-2:]) % 5) * 0.04)
        for period_label, amount, settlement, include in (
            ("2026-09", previous_month_total, "settled", 0),
            ("2026-10", current_month_total, "unsettled", 1),
        ):
            conn.execute(
                """INSERT INTO v3_revenue_account_periods(
                   id,account_id,theater_id,period_label,period_start,period_end,period_type,
                   date_precision,amount,currency,data_state,freshness_state,settlement_state,
                   include_in_analysis,source_kind,source_attempt_id,collection_run_id,collected_at,
                   raw_result_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stable_id(f"revenue-touch:{account_id}:{period_label}"), account_id, touch_id, period_label,
                    f"{period_label}-01", f"{period_label}-31" if period_label == "2026-10" else "2026-09-30",
                    "month_cumulative", "month", f"{amount:.2f}", "CNY", "record", "simulated", settlement,
                    include, SIM_SOURCE, stable_id(f"touch-attempt:{account_id}:{period_label}"), revenue_run, CAPTURED_AT,
                    payload(shape="monthly_cumulative", accountId=account_id, period=period_label),
                ),
            )
            insert_item(conn, revenue_run, domain="revenue", entity_type="account_period", entity_key=f"{account_id}:{period_label}",
                        account_id=account_id, theater_id=touch_id, period_start=f"{period_label}-01",
                        period_end=f"{period_label}-31" if period_label == "2026-10" else "2026-09-30",
                        payload_json=payload(shape="monthly_cumulative", period=period_label))
            revenue_period_count += 1

    for post in posts:
        if post["publish_day"] > SNAPSHOT_DATE:
            continue
        for current in recent_days:
            if current < post["publish_day"]:
                continue
            age = (current - post["publish_day"]).days
            base = post["view"] / max(1, len(recent_days))
            view = n(base * (0.82 + 0.16 * math.sin(age + len(post["post_id"]))))
            revenue = round(view * 0.00023, 2)
            rank = 1 + ((int(post["post_id"][-2:]) + current.day) % 38)
            matched = post["drama_id"] if int(post["post_id"][-2:]) % 4 != 0 else ""
            match_status = "matched" if matched else "unmatched"
            conn.execute(
                """INSERT INTO v3_revenue_details(
                   id,account_id,theater_id,detail_date,source_video_id,source_drama_name,video_views,
                   drama_views,gross_revenue,source_rank,matched_drama_id,match_status,data_state,
                   freshness_state,include_in_analysis,source_kind,source_attempt_id,collection_run_id,
                   collected_at,raw_result_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stable_id(f"revenue-detail:{post['post_id']}:{current}"), post["account_id"], qingning_id,
                    current.isoformat(), post["post_id"], post["drama_name"], view, n(view * 1.42), f"{revenue:.2f}",
                    rank, matched, match_status, "record", "simulated", 1, SIM_SOURCE,
                    stable_id(f"attempt-detail:{post['post_id']}:{current}"), revenue_run, CAPTURED_AT,
                    payload(shape="video_detail", sourceVideoId=post["post_id"], dramaName=post["drama_name"]),
                ),
            )
            insert_item(conn, revenue_run, domain="revenue", entity_type="revenue_detail", entity_key=f"{post['post_id']}:{current}",
                        account_id=post["account_id"], theater_id=qingning_id, stat_date=current.isoformat(),
                        payload_json=payload(shape="video_detail", sourceVideoId=post["post_id"]))
            revenue_detail_count += 1

    conn.execute(
        "UPDATE v3_analytics_collection_runs SET coverage_json=? WHERE id=?",
        (json.dumps({"accounts": len(account_info), "account_daily": len(account_info) * 30, "posts": len(posts), "post_daily": len(posts) * 14, "diagnostics": len(account_info), "punishments": len(punish_posts)}, ensure_ascii=False), video_run),
    )
    conn.execute(
        "UPDATE v3_analytics_collection_runs SET coverage_json=? WHERE id=?",
        (json.dumps({"periods": revenue_period_count, "details": revenue_detail_count, "sources": 2}, ensure_ascii=False), revenue_run),
    )
    conn.commit()
    return {
        "accounts": len(account_info),
        "account_daily": len(account_info) * 30,
        "posts": len(posts),
        "post_daily": len(posts) * 14,
        "diagnostics": len(account_info),
        "punishments": len(punish_posts),
        "revenue_sources": 2,
        "revenue_periods": revenue_period_count,
        "revenue_details": revenue_detail_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="写入可重复清理的 V3 分析演示数据")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true", help="只清理 simulation_ui 演示数据，不生成新数据")
    args = parser.parse_args()
    args.database = args.database.resolve()
    if not args.database.exists():
        raise SystemExit(f"数据库不存在：{args.database}")
    conn = sqlite3.connect(args.database, timeout=30)
    try:
        initialize(conn)
        delete_demo_rows(conn)
        if args.reset:
            conn.commit()
            print(json.dumps({"reset": True, "source_kind": SIM_SOURCE}, ensure_ascii=False, indent=2))
            return
        result = seed(conn)
        print(json.dumps({"seeded": True, "source_kind": SIM_SOURCE, **result}, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
