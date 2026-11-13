"""Populate the current V3 development database with recent linked business data.

This is an explicit CLI, never a startup hook. Existing rows and media survive.
The caller owns the transaction. The CLI makes a SQLite-consistent backup first.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SOURCE = "development_seed"
BEIJING = timezone(timedelta(hours=8))
THEATERS = ["青柠剧场", "触摸剧场", "九州剧场", "麦芽剧场", "蜜糖剧场", "容量剧场",
            "星河剧场", "花生剧场", "添翼剧场", "爱看剧场", "山海剧场", "爆米花剧场"]
NAMES = ["星野", "北辰", "拾光", "南风", "小满", "七月", "锦书", "微光", "风铃", "白昼", "橙光", "长安"]
DRAMAS = ["迟来的团圆", "老屋里的秘密", "归来仍是你", "三十年后的重逢", "小院春风", "父亲的承诺",
          "一家人的灯火", "不负余生", "旧信里的真相", "半生风雨半生情", "回家的路", "岁月有回声"]
NOTICE_CONFIG = json.loads((Path(__file__).resolve().parents[1] / "src/data/optimizationNoticeRules.json").read_text(encoding="utf-8"))
NOTICE_RULES = NOTICE_CONFIG["rules"]
REASONS = [rule["tag"] for rule in NOTICE_RULES]


def key(value: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, "v3-recent-operations:" + value).hex


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def put(conn, table: str, values: dict) -> None:
    columns = list(values)
    conn.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)}) "
                 + "ON CONFLICT(id) DO UPDATE SET " + ','.join(f"{c}=excluded.{c}" for c in columns if c != 'id'),
                 tuple(values.values()))


def seed(conn: sqlite3.Connection, end: date, days: int = 60, account_count: int = 48) -> dict:
    rng = random.Random(20261031)
    start = end - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    stamp = datetime.now(BEIJING).isoformat(timespec="seconds")
    counters = defaultdict(int)
    theaters = {}
    for name in THEATERS:
        row = conn.execute("SELECT id FROM theaters WHERE name=?", (name,)).fetchone()
        tid = row[0] if row else key("theater:" + name)
        if not row:
            put(conn, "theaters", dict(id=tid, name=name, default_commission_rate=40, default_tax_rate=6,
                                      status="启用", created_at=stamp, updated_at=stamp))
        theaters[name] = tid
    accounts = [dict(r) for r in conn.execute("SELECT a.*,t.name AS theater_name FROM accounts a JOIN theaters t ON t.id=a.theater_id ORDER BY a.id")]
    for i in range(max(0, account_count - len(accounts))):
        aid = key(f"account:{i}")
        name = THEATERS[i % len(THEATERS)]
        values = dict(id=aid, nickname=f"{NAMES[i % len(NAMES)]}剧推{i + 1:02d}", channel_id=f"dev-channels-{i + 1:03d}",
                      theater_id=theaters[name], sub_theater_name="", status="正常" if i % 9 else "观察",
                      reporting_date=start.isoformat(), registration_date=(start - timedelta(days=30)).isoformat(),
                      notes="开发阶段生成的业务数据，完成开发后随数据库统一重置。", created_at=stamp, updated_at=stamp)
        put(conn, "accounts", values)
        accounts.append({**values, "theater_name": name})
        counters["new_accounts"] += 1
    accounts.sort(key=lambda a: a['id'])
    # Same IDs are used by the catalog, account snapshots, works and revenue.
    for domain in ("video", "revenue"):
        rid = key(f"run:{domain}:{end}:{days}")
        put(conn, "v3_analytics_collection_runs", dict(id=rid, domain=domain, source_system=SOURCE,
            acquisition_layer="local_generator", storage_layer="v3_snapshot", requested_start_date=start.isoformat(),
            requested_end_date=end.isoformat(), trigger_source=SOURCE, refresh_triggered=0, source_captured_at=stamp,
            status="completed", coverage_json="{}", error_message="", created_at=stamp, finished_at=stamp))
    video_run, revenue_run = (key(f"run:{d}:{end}:{days}") for d in ("video", "revenue"))
    for tid in {a['theater_id'] for a in accounts}:
        monthly = tid == theaters["触摸剧场"]
        put(conn, "v3_revenue_sources", dict(id=key("source:" + tid), theater_id=tid, adapter_key=SOURCE,
            query_url="", query_mode="month_cumulative" if monthly else "date_range", date_precision="month" if monthly else "day",
            supports_detail=0 if monthly else 1, requires_account_id=1, requires_date=0 if monthly else 1,
            adapter_status="development", last_checked_at=stamp, notes="开发造数；不代表已接入该剧场网站。"))
    for ai, account in enumerate(accounts):
        aid, uid, tid = account['id'], account['channel_id'] or f"dev-{account['id']}", account['theater_id']
        totals = defaultdict(lambda: defaultdict(int))
        revenues = defaultdict(float)
        monthly = tid == theaters["触摸剧场"]
        fans = rng.randint(1800, 140000)
        tier = ["头部爆款", "腰部主力", "新锐测试", "限流观察"][ai % 4]
        reason_count = 0
        for di, published in enumerate(dates):
            if (di + ai) % 6 == 0:
                continue
            post_id = key(f"post:{aid}:{published}")
            drama_name = DRAMAS[(di // 6 + ai) % len(DRAMAS)]
            drama_id = key(f"drama:{tid}:{drama_name}")
            # Catalog drama names remain unique; existing master identities are reused.
            found = conn.execute("SELECT id FROM dramas WHERE current_name=?", (drama_name,)).fetchone()
            if found:
                drama_id = found[0]
            else:
                put(conn, "dramas", dict(id=drama_id, current_name=drama_name, theater_id=tid, created_at=stamp, updated_at=stamp))
            episode = di + 1
            post_time = f"{published} {('12:10', '18:30', '20:45')[di % 3]}:00"
            optimized = rng.random() < (0.035, 0.08, 0.14, 0.32)[ai % 4]
            base = (60000, 18000, 5500, 1600)[ai % 4] * rng.uniform(.35, 2.1)
            if (ai + di) % 41 == 0:
                base *= 12  # A few breakout works; most works remain ordinary.
            if optimized:
                base *= .36
            total = defaultdict(int)
            cumulative_revenue = 0.0
            for age in range((end - published).days + 1):
                day = published + timedelta(days=age)
                views = max(0, round(base * math.exp(-age / 4.5) * rng.uniform(.8, 1.2)))
                likes = round(views * rng.uniform(.008, .036))
                favorites = round(likes * .23)
                comments, shares, follows = round(likes * .12), round(likes * .18), round(views * .0018)
                for field, value in dict(view=views, like_count=likes, favorite_count=favorites,
                                         comment_count=comments, forward_count=shares, fans_add=follows).items():
                    totals[day][field] += value
                    total[field] += value
                put(conn, "v3_video_post_daily", dict(id=key(f"post-day:{post_id}:{day}"), post_id=post_id, uid=uid,
                    account_id=aid, stat_date=str(day), view=views, like_count=likes, comment_count=comments,
                    forward_count=shares, favorite_count=favorites, fans_add=follows, metric_grain="daily",
                    source_kind=SOURCE, data_state="confirmed_zero" if not views else "record", freshness_state="simulated",
                    collection_run_id=video_run, fetched_at=stamp, payload_json=dump({"generated": True})))
                counters['post_daily'] += 1
                amount = round(views * (.004 + (ai % 5) * .0006) * rng.uniform(.85, 1.15), 2)
                revenues[day] += amount
                cumulative_revenue += amount
                if not monthly and age < 14:
                    put(conn, "v3_revenue_details", dict(id=key(f"detail:{post_id}:{day}"), account_id=aid, theater_id=tid,
                        detail_date=str(day), source_video_id=post_id, source_drama_name=drama_name, video_views=views,
                        drama_views=round(views * 1.2), gross_revenue=f"{amount:.2f}", source_rank=1,
                        matched_drama_id=drama_id, match_status="matched", data_state="record", freshness_state="simulated",
                        include_in_analysis=1, source_kind=SOURCE, source_attempt_id="", collection_run_id=revenue_run,
                        collected_at=stamp, raw_result_json=dump({"generated": True})))
                    counters['revenue_details'] += 1
            filename = f"{drama_name}-{episode}.mp4"
            meta = dict(generated=True, file_name=filename, drama_name=drama_name, drama_id=drama_id,
                        episode=episode, tier=tier)
            put(conn, "v3_video_posts", dict(id=key(f"post-snapshot:{post_id}:{end}"), post_id=post_id, uid=uid,
                account_id=aid, account_name=account['nickname'], platform="Channels", post_time=post_time,
                title="", description="", cover_present=0, url_present=0, post_type="video", publish_status="已发布", timing="",
                view=total['view'], like_count=total['like_count'], comment_count=total['comment_count'],
                forward_count=total['forward_count'], love_count=total['favorite_count'], fans_add=total['fans_add'],
                full_view=round(rng.uniform(.14, .69), 4), view_time=round(rng.uniform(14, 78), 2), snapshot_date=str(end),
                source_kind=SOURCE, data_state="record", freshness_state="simulated", collection_run_id=video_run,
                fetched_at=stamp, payload_json=dump(meta)))
            counters['posts'] += 1
            if optimized:
                rule = NOTICE_RULES[(ai + di) % len(NOTICE_RULES)]
                reason = rule["tag"]
                put(conn, "v3_video_post_punishments", dict(id=key(f"punishment:{post_id}"), uid=uid, account_id=aid,
                    post_id_or_export_id=post_id, title="", publish_time=post_time, punish_state="",
                    snapshot_date=str(end), source_kind=SOURCE, data_state="record", freshness_state="simulated", fetched_at=stamp,
                    payload_json=dump({"generated": True, "simplifiedReason": reason,
                                       "notice": rule["analysis"], "noticeRuleId": rule["id"],
                                       "noticeMappingVersion": NOTICE_CONFIG["version"], "detectedDate": str(published)})))
                reason_count += 1
                counters['punishments'] += 1
        for di, day in enumerate(dates):
            traffic = totals[day]
            adds = traffic['fans_add']
            reduce = round(adds * (1.25 if ai % 8 == 7 else rng.uniform(.05, .3)))
            fans += adds - reduce
            state = "failed" if ai % 13 == 0 and di == days - 3 else "record"
            if ai % 11 == 0 and di == days - 8:
                state = "confirmed_zero"
            metric = {f: (0 if state != "record" else traffic[f]) for f in
                      ('view', 'like_count', 'favorite_count', 'comment_count', 'forward_count')}
            put(conn, "v3_video_account_daily", dict(id=key(f"account-day:{aid}:{day}"), uid=uid, account_id=aid,
                stat_date=str(day), **metric, fans_total=fans, fans_add=adds if state == "record" else 0,
                fans_net=adds-reduce if state == "record" else 0, fans_reduce=reduce if state == "record" else 0,
                source_kind=SOURCE, data_state=state, freshness_state="simulated", collection_run_id=video_run,
                fetched_at=stamp, payload_json=dump({"generated": True, "error": "开发场景：采集失败" if state == 'failed' else ''})))
            counters['account_daily'] += 1
            if monthly:
                continue
            amount = round(revenues[day], 2)
            revenue_state = "failed" if ai % 17 == 0 and di == days - 2 else "confirmed_zero" if (ai+di) % 47 == 0 else "record"
            if revenue_state == 'confirmed_zero':
                amount = 0.0
            attempt = key(f"attempt:{aid}:{day}")
            put(conn, "v2_revenue_collection_attempts", dict(id=attempt, request_id=revenue_run, account_id=aid, theater_id=tid,
                adapter_key=SOURCE, revenue_date=str(day), collection_status="failed" if revenue_state=='failed' else "success",
                amount=None if revenue_state=='failed' else f"{amount:.2f}", error_message="开发场景：读取失败" if revenue_state=='failed' else "",
                collected_at=stamp, data_kind="account_daily_total", period_end=str(day), period_type="day"))
            if revenue_state != 'failed':
                # Upsert the current account/date total using its existing ID when present.
                old = conn.execute("SELECT id FROM v2_daily_revenues WHERE account_id=? AND revenue_date=?", (aid, str(day))).fetchone()
                put(conn, "v2_daily_revenues", dict(id=old[0] if old else key(f"daily-revenue:{aid}:{day}"), account_id=aid,
                    theater_id=tid, revenue_date=str(day), amount=f"{amount:.2f}", quality="direct", source_attempt_id=attempt,
                    created_at=stamp, updated_at=stamp))
            put(conn, "v3_revenue_account_periods", dict(id=key(f"period:{aid}:{day}"), account_id=aid, theater_id=tid,
                period_label=str(day), period_start=str(day), period_end=str(day), period_type="day", date_precision="day",
                amount=None if revenue_state=='failed' else f"{amount:.2f}", currency="CNY", data_state=revenue_state,
                freshness_state="simulated", settlement_state="settled" if day.month != end.month else "unsettled",
                include_in_analysis=int(day.month == end.month and revenue_state!='failed'), source_kind=SOURCE,
                source_attempt_id=attempt, collection_run_id=revenue_run, collected_at=stamp, raw_result_json=dump({"generated": True})))
            counters['revenue_periods'] += 1
        if monthly:
            by_month = defaultdict(float)
            for day, value in revenues.items():
                by_month[day.strftime('%Y-%m')] += value
            for month, value in by_month.items():
                first = date.fromisoformat(month+'-01')
                last = min(end, (first.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1))
                current = month == end.strftime('%Y-%m')
                put(conn, "v3_revenue_account_periods", dict(id=key(f"monthly:{aid}:{month}"), account_id=aid, theater_id=tid,
                    period_label=month, period_start=str(first), period_end=str(last), period_type="month_cumulative", date_precision="month",
                    amount=f"{value:.2f}", currency="CNY", data_state="record", freshness_state="simulated",
                    settlement_state="unsettled" if current else "settled", include_in_analysis=int(current), source_kind=SOURCE,
                    source_attempt_id="", collection_run_id=revenue_run, collected_at=stamp, raw_result_json=dump({"generated": True})))
                counters['revenue_periods'] += 1
        put(conn, "v3_video_accounts", dict(id=key(f"account-snapshot:{aid}:{end}"), uid=uid, account_id=aid,
            account_name=account['nickname'], platform="Channels", login_status="登录有效", fans_total=fans, group_name=tier,
            tags_json="[]", snapshot_date=str(end), source_kind=SOURCE, data_state="record", freshness_state="simulated",
            fetched_at=stamp, payload_json=dump({"generated": True, "tier": tier})))
        put(conn, "v3_video_account_diagnostics", dict(id=key(f"diagnostic:{aid}:{end}"), uid=uid, account_id=aid,
            account_name=account['nickname'], verified=1, abnormal=int(reason_count > 9), video_status="需关注" if reason_count > 9 else "正常",
            heat_status="正常", abnormal_post_count=reason_count, last_verify_time=stamp, snapshot_date=str(end),
            source_kind=SOURCE, data_state="record", freshness_state="simulated", fetched_at=stamp, payload_json=dump({"generated": True})))
    return dict(counters, accounts=len(accounts), theaters=len({a['theater_id'] for a in accounts}), start=str(start), end=str(end))


def main():
    parser = argparse.ArgumentParser(description="向当前 V3 数据库补充近期业务数据，先备份，不清库，不触发外部采集")
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--end-date', type=date.fromisoformat, default=datetime.now(BEIJING).date()-timedelta(days=1))
    parser.add_argument('--days', type=int, default=60)
    parser.add_argument('--accounts', type=int, default=48)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error('数据库必须已存在；此工具不初始化空业务库。')
    if not 7 <= args.days <= 90 or not 1 <= args.accounts <= 100:
        parser.error('天数须为7—90，目标账号数须为1—100。')
    conn = sqlite3.connect(args.database, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    backup = args.database.with_name(args.database.name + '.before-recent-operations-' + datetime.now(BEIJING).strftime('%Y%m%d-%H%M%S-%f'))
    try:
        with sqlite3.connect(backup) as target:
            conn.backup(target)
        conn.execute('BEGIN IMMEDIATE')
        result = seed(conn, args.end_date, args.days, args.accounts)
        conn.commit()
        print(dump({"database": str(args.database), "backup": str(backup), **result}))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
