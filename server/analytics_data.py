"""V3 analytics data foundation.

This module owns the normalized evidence layer used by the future operations
dashboard.  Video-account data and theater revenue remain separate domains.
The importer records provenance and freshness instead of turning cached or
legacy values into current business facts.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

SHANGHAI = timezone(timedelta(hours=8))


def stamp() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"), default=str)


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _number(value: Any, default: float | int = 0) -> float | int:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return int(number) if number.is_integer() else number


def _without_excluded(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _without_excluded(v) for k, v in value.items() if str(k) not in {"liveStatus", "live_status"}}
    if isinstance(value, list):
        return [_without_excluded(item) for item in value]
    return value


def _account_id(conn: sqlite3.Connection, uid: str) -> str:
    row = conn.execute("SELECT id FROM accounts WHERE channel_id=? LIMIT 1", (uid,)).fetchone()
    return _text(row[0]) if row else ""


def initialize(conn: sqlite3.Connection) -> None:
    """Create the additive V3 analytics schema without editing old tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS v3_analytics_collection_runs (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL CHECK(domain IN ('video','revenue')),
            source_system TEXT NOT NULL,
            acquisition_layer TEXT NOT NULL,
            storage_layer TEXT NOT NULL,
            requested_start_date TEXT NOT NULL DEFAULT '',
            requested_end_date TEXT NOT NULL DEFAULT '',
            trigger_source TEXT NOT NULL DEFAULT '',
            refresh_triggered INTEGER NOT NULL DEFAULT 0 CHECK(refresh_triggered IN (0,1)),
            source_captured_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'completed',
            coverage_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS v3_analytics_collection_items (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES v3_analytics_collection_runs(id) ON DELETE CASCADE,
            domain TEXT NOT NULL CHECK(domain IN ('video','revenue')),
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            account_id TEXT NOT NULL DEFAULT '',
            uid TEXT NOT NULL DEFAULT '',
            theater_id TEXT NOT NULL DEFAULT '',
            stat_date TEXT NOT NULL DEFAULT '',
            period_start TEXT NOT NULL DEFAULT '',
            period_end TEXT NOT NULL DEFAULT '',
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            error_message TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(run_id, entity_type, entity_key, stat_date, period_start, period_end)
        );
        CREATE TABLE IF NOT EXISTS v3_video_accounts (
            id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            account_id TEXT NOT NULL DEFAULT '',
            account_name TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT 'Channels',
            login_status TEXT NOT NULL DEFAULT '',
            fans_total REAL NOT NULL DEFAULT 0,
            group_name TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            snapshot_date TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL,
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(uid, snapshot_date, source_kind)
        );
        CREATE TABLE IF NOT EXISTS v3_video_account_daily (
            id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            account_id TEXT NOT NULL DEFAULT '',
            stat_date TEXT NOT NULL,
            view REAL NOT NULL DEFAULT 0,
            fans_total REAL NOT NULL DEFAULT 0,
            fans_add REAL NOT NULL DEFAULT 0,
            fans_net REAL NOT NULL DEFAULT 0,
            fans_reduce REAL NOT NULL DEFAULT 0,
            like_count REAL NOT NULL DEFAULT 0,
            favorite_count REAL NOT NULL DEFAULT 0,
            comment_count REAL NOT NULL DEFAULT 0,
            forward_count REAL NOT NULL DEFAULT 0,
            source_kind TEXT NOT NULL,
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            collection_run_id TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(uid, stat_date, source_kind)
        );
        CREATE TABLE IF NOT EXISTS v3_video_posts (
            id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL,
            uid TEXT NOT NULL,
            account_id TEXT NOT NULL DEFAULT '',
            account_name TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT 'Channels',
            post_time TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            cover_present INTEGER NOT NULL DEFAULT 0,
            url_present INTEGER NOT NULL DEFAULT 0,
            post_type TEXT NOT NULL DEFAULT '',
            publish_status TEXT NOT NULL DEFAULT '',
            timing TEXT NOT NULL DEFAULT '',
            view REAL NOT NULL DEFAULT 0,
            like_count REAL NOT NULL DEFAULT 0,
            comment_count REAL NOT NULL DEFAULT 0,
            forward_count REAL NOT NULL DEFAULT 0,
            love_count REAL NOT NULL DEFAULT 0,
            fans_add REAL NOT NULL DEFAULT 0,
            full_view REAL NOT NULL DEFAULT 0,
            view_time REAL NOT NULL DEFAULT 0,
            snapshot_date TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            collection_run_id TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(post_id, snapshot_date, source_kind)
        );
        CREATE TABLE IF NOT EXISTS v3_video_post_daily (
            id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL,
            uid TEXT NOT NULL,
            account_id TEXT NOT NULL DEFAULT '',
            stat_date TEXT NOT NULL,
            view REAL NOT NULL DEFAULT 0,
            like_count REAL NOT NULL DEFAULT 0,
            comment_count REAL NOT NULL DEFAULT 0,
            forward_count REAL NOT NULL DEFAULT 0,
            favorite_count REAL NOT NULL DEFAULT 0,
            fans_add REAL NOT NULL DEFAULT 0,
            metric_grain TEXT NOT NULL DEFAULT 'daily',
            source_kind TEXT NOT NULL,
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            collection_run_id TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(post_id, stat_date, source_kind)
        );
        CREATE TABLE IF NOT EXISTS v3_video_account_diagnostics (
            id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            account_id TEXT NOT NULL DEFAULT '',
            account_name TEXT NOT NULL DEFAULT '',
            verified INTEGER,
            abnormal INTEGER,
            video_status TEXT NOT NULL DEFAULT '',
            heat_status TEXT NOT NULL DEFAULT '',
            abnormal_post_count INTEGER NOT NULL DEFAULT 0,
            last_verify_time TEXT NOT NULL DEFAULT '',
            snapshot_date TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(uid, snapshot_date, source_kind)
        );
        CREATE TABLE IF NOT EXISTS v3_video_post_punishments (
            id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            account_id TEXT NOT NULL DEFAULT '',
            post_id_or_export_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            publish_time TEXT NOT NULL DEFAULT '',
            punish_state TEXT NOT NULL DEFAULT '',
            snapshot_date TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(uid, post_id_or_export_id, publish_time, punish_state, source_kind)
        );
        CREATE TABLE IF NOT EXISTS v3_revenue_sources (
            id TEXT PRIMARY KEY,
            theater_id TEXT NOT NULL DEFAULT '',
            adapter_key TEXT NOT NULL,
            query_url TEXT NOT NULL DEFAULT '',
            query_mode TEXT NOT NULL DEFAULT 'unknown',
            date_precision TEXT NOT NULL DEFAULT 'unknown',
            supports_detail INTEGER NOT NULL DEFAULT 0,
            requires_account_id INTEGER NOT NULL DEFAULT 1,
            requires_date INTEGER NOT NULL DEFAULT 0,
            adapter_status TEXT NOT NULL DEFAULT 'unconfirmed',
            last_checked_at TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            UNIQUE(theater_id, adapter_key)
        );
        CREATE TABLE IF NOT EXISTS v3_revenue_account_periods (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL DEFAULT '',
            theater_id TEXT NOT NULL DEFAULT '',
            period_label TEXT NOT NULL DEFAULT '',
            period_start TEXT NOT NULL DEFAULT '',
            period_end TEXT NOT NULL DEFAULT '',
            period_type TEXT NOT NULL DEFAULT 'unknown',
            date_precision TEXT NOT NULL DEFAULT 'unknown',
            amount TEXT,
            currency TEXT NOT NULL DEFAULT 'CNY',
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            settlement_state TEXT NOT NULL DEFAULT 'unknown',
            include_in_analysis INTEGER NOT NULL DEFAULT 0 CHECK(include_in_analysis IN (0,1)),
            source_kind TEXT NOT NULL,
            source_attempt_id TEXT NOT NULL DEFAULT '',
            collection_run_id TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL,
            raw_result_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(account_id, theater_id, period_label, period_type, source_kind)
        );
        CREATE TABLE IF NOT EXISTS v3_revenue_details (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL DEFAULT '',
            theater_id TEXT NOT NULL DEFAULT '',
            detail_date TEXT NOT NULL DEFAULT '',
            source_video_id TEXT NOT NULL DEFAULT '',
            source_drama_name TEXT NOT NULL DEFAULT '',
            video_views REAL NOT NULL DEFAULT 0,
            drama_views REAL NOT NULL DEFAULT 0,
            gross_revenue TEXT,
            source_rank INTEGER NOT NULL DEFAULT 0,
            matched_drama_id TEXT NOT NULL DEFAULT '',
            match_status TEXT NOT NULL DEFAULT 'unmatched',
            data_state TEXT NOT NULL,
            freshness_state TEXT NOT NULL DEFAULT '',
            include_in_analysis INTEGER NOT NULL DEFAULT 0 CHECK(include_in_analysis IN (0,1)),
            source_kind TEXT NOT NULL,
            source_attempt_id TEXT NOT NULL DEFAULT '',
            collection_run_id TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL,
            raw_result_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(account_id, theater_id, detail_date, source_video_id, source_kind)
        );
        CREATE INDEX IF NOT EXISTS idx_v3_video_account_daily_date ON v3_video_account_daily(stat_date, uid);
        CREATE INDEX IF NOT EXISTS idx_v3_video_posts_snapshot ON v3_video_posts(snapshot_date, uid, view DESC);
        CREATE INDEX IF NOT EXISTS idx_v3_video_post_daily_date ON v3_video_post_daily(stat_date, uid, view DESC);
        CREATE INDEX IF NOT EXISTS idx_v3_revenue_periods_period ON v3_revenue_account_periods(period_start, period_end, theater_id);
        CREATE INDEX IF NOT EXISTS idx_v3_analytics_items_run ON v3_analytics_collection_items(run_id, domain, entity_type);
        """
    )

    from server.operations_collection import initialize as initialize_operations
    initialize_operations(conn)


def _new_run(conn: sqlite3.Connection, *, domain: str, source_system: str, acquisition_layer: str,
             storage_layer: str, start: str, end: str, trigger: str, refresh: bool,
             source_captured_at: str, coverage: dict[str, Any]) -> str:
    run_id = uuid.uuid4().hex
    now = stamp()
    conn.execute(
        """INSERT INTO v3_analytics_collection_runs(
           id,domain,source_system,acquisition_layer,storage_layer,
           requested_start_date,requested_end_date,trigger_source,refresh_triggered,
           source_captured_at,status,coverage_json,created_at,finished_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, domain, source_system, acquisition_layer, storage_layer, start, end,
         trigger, int(refresh), source_captured_at, "completed", _json(coverage), now, now),
    )
    return run_id


def _item(conn: sqlite3.Connection, run_id: str, *, domain: str, entity_type: str,
          entity_key: str, account_id: str = "", uid: str = "", theater_id: str = "",
          stat_date: str = "", period_start: str = "", period_end: str = "",
          data_state: str, freshness_state: str, source_kind: str, fetched_at: str,
          payload: Any = None, error: str = "") -> None:
    conn.execute(
        """INSERT OR REPLACE INTO v3_analytics_collection_items(
           id,run_id,domain,entity_type,entity_key,account_id,uid,theater_id,
           stat_date,period_start,period_end,data_state,freshness_state,source_kind,
           fetched_at,error_message,payload_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uuid.uuid4().hex, run_id, domain, entity_type, entity_key, account_id, uid, theater_id,
         stat_date, period_start, period_end, data_state, freshness_state, source_kind,
         fetched_at, error, _json(_without_excluded(payload))),
    )


def import_video_evidence(conn: sqlite3.Connection, snapshot_path: str | Path,
                          remaining_path: str | Path | None = None,
                          key_post_daily_path: str | Path | None = None) -> dict[str, Any]:
    """Import the inspected Xiao V cache evidence into V3 analytics tables.

    This importer is deliberately evidence-only: it never calls Xiao V and
    marks all imported values as ``cached_only`` freshness.
    """
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    remaining = json.loads(Path(remaining_path).read_text(encoding="utf-8")) if remaining_path else {}
    key_post_daily = json.loads(Path(key_post_daily_path).read_text(encoding="utf-8")) if key_post_daily_path else {}
    start, end = (snapshot.get("dateRange") or ["", ""])[:2]
    captured = _text(snapshot.get("capturedAt"))
    source_kind = "xiao_v_cache"
    freshness = "cached_only"
    accounts = ((snapshot.get("accounts") or {}).get("list") or [])
    rows = ((snapshot.get("postProfile") or {}).get("rows") or [])
    details = snapshot.get("accountDetails") or {}
    diagnostics = (((remaining.get("diagnostics") or {}).get("list") or {}).get("list") or [])
    punishments = (((remaining.get("diagnostics") or {}).get("punishFeeds") or {}).get("list") or [])
    key_daily_rows = []
    for item in (key_post_daily.get("posts") or {}).values():
        if not isinstance(item, dict):
            continue
        post = item.get("post") or {}
        daily_payload = item.get("daily") or {}
        for daily in daily_payload.get("daily") or []:
            if isinstance(daily, dict) and _text(post.get("postId")) and _text(post.get("uid")) and _text(daily.get("date")):
                key_daily_rows.append((post, daily))
    coverage = {
        "accounts": len(accounts),
        "validAccountUids": len(snapshot.get("validAccountUids") or []),
        "accountRanking": int((snapshot.get("accountRanking") or {}).get("total") or 0),
        "posts": len(rows),
        "accountDetails": len(details),
        "diagnostics": len(diagnostics),
        "punishments": len(punishments),
        "postDailyImported": len(key_daily_rows),
    }
    run_id = _new_run(
        conn, domain="video", source_system="video_official", acquisition_layer="xiao_v_mcp",
        storage_layer="v3_snapshot", start=_text(start), end=_text(end), trigger="evidence_import",
        refresh=False, source_captured_at=captured, coverage=coverage,
    )
    snapshot_date = captured[:10] if captured else _text(end)
    account_by_uid = { _text(item.get("uid")): item for item in accounts if _text(item.get("uid")) }
    for uid, item in account_by_uid.items():
        account_id = _account_id(conn, uid)
        conn.execute(
            """INSERT INTO v3_video_accounts(
               id,uid,account_id,account_name,platform,login_status,fans_total,group_name,
               tags_json,snapshot_date,source_kind,data_state,freshness_state,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(uid,snapshot_date,source_kind) DO UPDATE SET
                 account_id=excluded.account_id,account_name=excluded.account_name,
                 login_status=excluded.login_status,fans_total=excluded.fans_total,
                 group_name=excluded.group_name,tags_json=excluded.tags_json,
                 data_state=excluded.data_state,freshness_state=excluded.freshness_state,
                 fetched_at=excluded.fetched_at,payload_json=excluded.payload_json""",
            (uuid.uuid4().hex, uid, account_id, _text(item.get("nickname")), _text(item.get("platform")) or "Channels",
             _text(item.get("loginStatus")), _number(item.get("fansTotal")), _text(item.get("groupName")),
             _json(item.get("tags") or []), snapshot_date, source_kind, "record", freshness, captured, _json(item)),
        )
        _item(conn, run_id, domain="video", entity_type="account", entity_key=uid,
              account_id=account_id, uid=uid, data_state="record", freshness_state=freshness,
              source_kind=source_kind, fetched_at=captured, payload=item)

    for uid, payload in details.items():
        uid = _text(uid)
        if not isinstance(payload, dict):
            continue
        account_id = _account_id(conn, uid)
        for daily in payload.get("daily") or []:
            if not isinstance(daily, dict) or not _text(daily.get("date")):
                continue
            day = _text(daily.get("date"))
            values = (
                uuid.uuid4().hex, uid, account_id, day, _number(daily.get("view")),
                _number(daily.get("fansTotal")), _number(daily.get("fansAdd")), _number(daily.get("fansNet")),
                _number(daily.get("fansReduce")), _number(daily.get("like")), _number(daily.get("favorite")),
                _number(daily.get("comment")), _number(daily.get("forward")), source_kind, "record", freshness,
                run_id, captured, _json(daily),
            )
            conn.execute(
                """INSERT INTO v3_video_account_daily(
                   id,uid,account_id,stat_date,view,fans_total,fans_add,fans_net,fans_reduce,
                   like_count,favorite_count,comment_count,forward_count,source_kind,data_state,
                   freshness_state,collection_run_id,fetched_at,payload_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(uid,stat_date,source_kind) DO UPDATE SET
                     account_id=excluded.account_id,view=excluded.view,fans_total=excluded.fans_total,
                     fans_add=excluded.fans_add,fans_net=excluded.fans_net,fans_reduce=excluded.fans_reduce,
                     like_count=excluded.like_count,favorite_count=excluded.favorite_count,
                     comment_count=excluded.comment_count,forward_count=excluded.forward_count,
                     data_state=excluded.data_state,freshness_state=excluded.freshness_state,
                     collection_run_id=excluded.collection_run_id,fetched_at=excluded.fetched_at,
                     payload_json=excluded.payload_json""", values,
            )
            _item(conn, run_id, domain="video", entity_type="account_daily", entity_key=f"{uid}:{day}",
                  account_id=account_id, uid=uid, stat_date=day, data_state="record",
                  freshness_state=freshness, source_kind=source_kind, fetched_at=captured, payload=daily)

    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("postId")):
            continue
        post_id, uid = _text(row.get("postId")), _text(row.get("uid"))
        account_id = _account_id(conn, uid)
        values = (
            uuid.uuid4().hex, post_id, uid, account_id, _text(row.get("account")), _text(row.get("platform")) or "Channels",
            _text(row.get("postTime")), _text(row.get("title")), _text(row.get("desc")),
            int(bool(row.get("coverPresent"))), int(bool(row.get("urlPresent"))), _text(row.get("postType")),
            _text(row.get("publishStatus")), _text(row.get("timing")), _number(row.get("view")),
            _number(row.get("like")), _number(row.get("comment")), _number(row.get("forward")), _number(row.get("love")),
            _number(row.get("fansAdd")), _number(row.get("fullView")), _number(row.get("viewTime")), snapshot_date,
            source_kind, "record", freshness, run_id, captured, _json(row),
        )
        conn.execute(
            """INSERT INTO v3_video_posts(
               id,post_id,uid,account_id,account_name,platform,post_time,title,description,
               cover_present,url_present,post_type,publish_status,timing,view,like_count,
               comment_count,forward_count,love_count,fans_add,full_view,view_time,snapshot_date,
               source_kind,data_state,freshness_state,collection_run_id,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(post_id,snapshot_date,source_kind) DO UPDATE SET
                 account_id=excluded.account_id,account_name=excluded.account_name,post_time=excluded.post_time,
                 title=excluded.title,description=excluded.description,cover_present=excluded.cover_present,
                 url_present=excluded.url_present,publish_status=excluded.publish_status,timing=excluded.timing,
                 view=excluded.view,like_count=excluded.like_count,comment_count=excluded.comment_count,
                 forward_count=excluded.forward_count,love_count=excluded.love_count,fans_add=excluded.fans_add,
                 full_view=excluded.full_view,view_time=excluded.view_time,data_state=excluded.data_state,
                 freshness_state=excluded.freshness_state,collection_run_id=excluded.collection_run_id,
                 fetched_at=excluded.fetched_at,payload_json=excluded.payload_json""", values,
        )
        _item(conn, run_id, domain="video", entity_type="post", entity_key=post_id,
              account_id=account_id, uid=uid, stat_date=snapshot_date, data_state="record",
              freshness_state=freshness, source_kind=source_kind, fetched_at=captured, payload=row)

    for post, daily in key_daily_rows:
        post_id, uid, day = _text(post.get("postId")), _text(post.get("uid")), _text(daily.get("date"))
        account_id = _account_id(conn, uid)
        values = (
            uuid.uuid4().hex, post_id, uid, account_id, day, _number(daily.get("view")),
            _number(daily.get("like")), _number(daily.get("comment")), _number(daily.get("forward")),
            _number(daily.get("favorite", daily.get("love"))), _number(daily.get("fansAdd")), "daily",
            source_kind, "record", freshness, run_id, captured, _json(daily),
        )
        conn.execute(
            """INSERT INTO v3_video_post_daily(
               id,post_id,uid,account_id,stat_date,view,like_count,comment_count,forward_count,
               favorite_count,fans_add,metric_grain,source_kind,data_state,freshness_state,
               collection_run_id,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(post_id,stat_date,source_kind) DO UPDATE SET
                 account_id=excluded.account_id,view=excluded.view,like_count=excluded.like_count,
                 comment_count=excluded.comment_count,forward_count=excluded.forward_count,
                 favorite_count=excluded.favorite_count,fans_add=excluded.fans_add,
                 data_state=excluded.data_state,freshness_state=excluded.freshness_state,
                 collection_run_id=excluded.collection_run_id,fetched_at=excluded.fetched_at,
                 payload_json=excluded.payload_json""", values,
        )
        _item(conn, run_id, domain="video", entity_type="post_daily", entity_key=f"{uid}:{post_id}:{day}",
              account_id=account_id, uid=uid, stat_date=day, data_state="record",
              freshness_state=freshness, source_kind=source_kind, fetched_at=captured, payload=daily)

    for item in diagnostics:
        if not isinstance(item, dict) or not _text(item.get("uid")):
            continue
        uid = _text(item.get("uid")); account_id = _account_id(conn, uid)
        conn.execute(
            """INSERT INTO v3_video_account_diagnostics(
               id,uid,account_id,account_name,verified,abnormal,video_status,heat_status,
               abnormal_post_count,last_verify_time,snapshot_date,source_kind,data_state,
               freshness_state,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(uid,snapshot_date,source_kind) DO UPDATE SET
                 account_id=excluded.account_id,account_name=excluded.account_name,verified=excluded.verified,
                 abnormal=excluded.abnormal,video_status=excluded.video_status,heat_status=excluded.heat_status,
                 abnormal_post_count=excluded.abnormal_post_count,last_verify_time=excluded.last_verify_time,
                 data_state=excluded.data_state,freshness_state=excluded.freshness_state,
                 fetched_at=excluded.fetched_at,payload_json=excluded.payload_json""",
            (uuid.uuid4().hex, uid, account_id, _text(item.get("nickname")),
             None if "verified" not in item else int(bool(item.get("verified"))),
             None if "abnormal" not in item else int(bool(item.get("abnormal"))),
             _text(item.get("videoStatus")), _text(item.get("heatStatus")), int(_number(item.get("abnormalPostCount"))),
             _text(item.get("lastVerifyTime")), snapshot_date, source_kind, "record", freshness, captured,
             _json(_without_excluded(item))),
        )
    for item in punishments:
        if not isinstance(item, dict) or not _text(item.get("uid")):
            continue
        uid = _text(item.get("uid")); account_id = _account_id(conn, uid); key = _text(item.get("exportId"))
        conn.execute(
            """INSERT OR REPLACE INTO v3_video_post_punishments(
               id,uid,account_id,post_id_or_export_id,title,publish_time,punish_state,
               snapshot_date,source_kind,data_state,freshness_state,fetched_at,payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (uuid.uuid4().hex, uid, account_id, key, _text(item.get("title")), _text(item.get("publishTime")),
             _text(item.get("punishState")), snapshot_date, source_kind, "record", freshness, captured, _json(item)),
        )
    conn.commit()
    return {"run_id": run_id, "coverage": coverage, "source_kind": source_kind, "freshness_state": freshness}


def import_legacy_revenue(conn: sqlite3.Connection) -> dict[str, Any]:
    """Copy old V2 revenue rows into the new contract as unverified evidence.

    No theater URL, date precision, settlement state or comparability is
    inferred from the old rows.  They are excluded from current analysis.
    """
    attempt_count = int(conn.execute("SELECT COUNT(*) FROM v2_revenue_collection_attempts").fetchone()[0])
    daily_count = int(conn.execute("SELECT COUNT(*) FROM v2_daily_revenues").fetchone()[0])
    detail_count = int(conn.execute("SELECT COUNT(*) FROM v2_revenue_video_details").fetchone()[0])
    captured = _text(conn.execute("SELECT MAX(collected_at) FROM v2_revenue_collection_attempts").fetchone()[0])
    run_id = _new_run(
        conn, domain="revenue", source_system="theater_websites", acquisition_layer="legacy_v2",
        storage_layer="v3_snapshot", start="", end="", trigger="legacy_import", refresh=False,
        source_captured_at=captured, coverage={"attempts": attempt_count, "daily": daily_count, "details": detail_count},
    )
    theaters = conn.execute("SELECT DISTINCT theater_id, adapter_key FROM v2_revenue_collection_attempts").fetchall()
    for row in theaters:
        conn.execute(
            """INSERT INTO v3_revenue_sources(id,theater_id,adapter_key,query_mode,date_precision,
               supports_detail,adapter_status,last_checked_at,notes)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(theater_id,adapter_key) DO UPDATE SET last_checked_at=excluded.last_checked_at""",
            (uuid.uuid4().hex, _text(row[0]), _text(row[1]), "unknown", "unknown", 0, "legacy_observed", captured,
             "由旧V2采集记录发现；查询地址和返回能力尚未核实"),
        )
    for row in conn.execute(
        "SELECT account_id,theater_id,revenue_date,amount,source_attempt_id,updated_at FROM v2_daily_revenues"
    ).fetchall():
        account_id, theater_id, day = _text(row[0]), _text(row[1]), _text(row[2])
        conn.execute(
            """INSERT INTO v3_revenue_account_periods(
               id,account_id,theater_id,period_label,period_start,period_end,period_type,date_precision,
               amount,data_state,freshness_state,settlement_state,include_in_analysis,source_kind,
               source_attempt_id,collection_run_id,collected_at,raw_result_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(account_id,theater_id,period_label,period_type,source_kind) DO UPDATE SET
                 amount=excluded.amount,source_attempt_id=excluded.source_attempt_id,
                 collected_at=excluded.collected_at,raw_result_json=excluded.raw_result_json""",
            (uuid.uuid4().hex, account_id, theater_id, day, day, day, "day", "day", _text(row[3]),
             "record", "legacy_unverified", "unknown", 0, "legacy_v2", _text(row[4]), run_id, _text(row[5]),
             _json({"legacy_table": "v2_daily_revenues"})),
        )
    for row in conn.execute(
        """SELECT account_id,theater_id,revenue_date,source_video_id,source_drama_name,
                  video_views,drama_views,gross_revenue,source_rank,matched_drama_id,match_status,
                  attempt_id,updated_at FROM v2_revenue_video_details"""
    ).fetchall():
        conn.execute(
            """INSERT INTO v3_revenue_details(
               id,account_id,theater_id,detail_date,source_video_id,source_drama_name,video_views,
               drama_views,gross_revenue,source_rank,matched_drama_id,match_status,data_state,
               freshness_state,include_in_analysis,source_kind,source_attempt_id,collection_run_id,
               collected_at,raw_result_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(account_id,theater_id,detail_date,source_video_id,source_kind) DO UPDATE SET
                 source_drama_name=excluded.source_drama_name,video_views=excluded.video_views,
                 drama_views=excluded.drama_views,gross_revenue=excluded.gross_revenue,
                 match_status=excluded.match_status,collected_at=excluded.collected_at""",
            (uuid.uuid4().hex, _text(row[0]), _text(row[1]), _text(row[2]), _text(row[3]), _text(row[4]),
             _number(row[5]), _number(row[6]), _text(row[7]), int(_number(row[8])), _text(row[9]), _text(row[10]),
             "record", "legacy_unverified", 0, "legacy_v2", _text(row[11]), run_id, _text(row[12]),
             _json({"legacy_table": "v2_revenue_video_details"})),
        )
    conn.commit()
    return {"run_id": run_id, "coverage": {"attempts": attempt_count, "daily": daily_count, "details": detail_count}}


def data_base_overview(
    connection,
    start_date: str | None = None,
    end_date: str | None = None,
    source_kind: str | None = None,
) -> dict[str, Any]:
    from server.account_visibility import visible_account_sql
    with closing(connection()) as conn:
        def visibility(table: str) -> str:
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            return visible_account_sql(conn,
                account_id=f'{table}.account_id' if 'account_id' in columns else None,
                uid=f'{table}.uid' if 'uid' in columns else None)

        counts = {}
        source_tables = {
            "v3_analytics_collection_items", "v3_video_accounts", "v3_video_account_daily",
            "v3_video_posts", "v3_video_post_daily", "v3_video_account_diagnostics",
            "v3_video_post_punishments", "v3_revenue_account_periods", "v3_revenue_details",
        }
        for table in (
            "v3_analytics_collection_runs", "v3_analytics_collection_items", "v3_video_accounts",
            "v3_video_account_daily", "v3_video_posts", "v3_video_post_daily",
            "v3_video_account_diagnostics", "v3_video_post_punishments", "v3_revenue_sources",
            "v3_revenue_account_periods", "v3_revenue_details",
        ):
            if source_kind and table in source_tables:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE source_kind=? AND {visibility(table)}", (source_kind,)).fetchone()[0])
            elif source_kind and table == "v3_analytics_collection_runs":
                counts[table] = int(conn.execute("SELECT COUNT(*) FROM v3_analytics_collection_runs WHERE acquisition_layer=?", (source_kind,)).fetchone()[0])
            elif source_kind and table == "v3_revenue_sources":
                counts[table] = int(conn.execute("SELECT COUNT(*) FROM v3_revenue_sources WHERE adapter_key LIKE ?", (f"{source_kind.replace('_ui', '')}%",)).fetchone()[0])
            else:
                predicate = visibility(table) if table in source_tables else '1=1'
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicate}").fetchone()[0])
        runs_sql = """SELECT id,domain,source_system,acquisition_layer,requested_start_date,
                      requested_end_date,trigger_source,refresh_triggered,source_captured_at,
                      status,coverage_json,created_at,finished_at
               FROM v3_analytics_collection_runs"""
        run_params: tuple[str, ...] = ()
        if source_kind:
            runs_sql += " WHERE acquisition_layer=?"
            run_params = (source_kind,)
        runs_sql += " ORDER BY created_at DESC LIMIT 20"
        runs = [dict(row) for row in conn.execute(
            runs_sql, run_params
        ).fetchall()]
        for run in runs:
            try: run["coverage"] = json.loads(run.pop("coverage_json") or "{}")
            except json.JSONDecodeError: run["coverage"] = {}
        source_sql = """SELECT id,theater_id,adapter_key,query_url,query_mode,date_precision,
                      supports_detail,requires_account_id,requires_date,adapter_status,
                      last_checked_at,notes
               FROM v3_revenue_sources"""
        source_params: tuple[str, ...] = ()
        if source_kind:
            source_sql += " WHERE adapter_key LIKE ?"
            source_params = (f"{source_kind.replace('_ui', '')}%",)
        source_sql += " ORDER BY theater_id,adapter_key"
        revenue_sources = [dict(row) for row in conn.execute(source_sql, source_params).fetchall()]
        coverage_filter = ""
        coverage_params: tuple[str, ...] = ()
        if source_kind:
            coverage_filter = " WHERE source_kind=?"
            coverage_params = (source_kind,)
        revenue_period_coverage = [dict(row) for row in conn.execute(
            """SELECT source_kind,data_state,include_in_analysis,COUNT(*) AS row_count,
                      MIN(period_start) AS min_period_start,MAX(period_end) AS max_period_end
               FROM v3_revenue_account_periods""" + (coverage_filter or ' WHERE 1=1') + ' AND ' + visibility('v3_revenue_account_periods') + " GROUP BY source_kind,data_state,include_in_analysis ORDER BY source_kind,data_state,include_in_analysis",
            coverage_params,
        ).fetchall()]
        revenue_detail_coverage = [dict(row) for row in conn.execute(
            """SELECT source_kind,data_state,include_in_analysis,COUNT(*) AS row_count,
                      MIN(detail_date) AS min_detail_date,MAX(detail_date) AS max_detail_date
               FROM v3_revenue_details""" + (coverage_filter or ' WHERE 1=1') + ' AND ' + visibility('v3_revenue_details') + " GROUP BY source_kind,data_state,include_in_analysis ORDER BY source_kind,data_state,include_in_analysis",
            coverage_params,
        ).fetchall()]
        range_filter = ""
        params: list[str] = []
        if source_kind:
            range_filter += " AND source_kind=?"
            params.append(source_kind)
        if start_date:
            range_filter += " AND stat_date>=?"; params.append(start_date)
        if end_date:
            range_filter += " AND stat_date<=?"; params.append(end_date)
        daily_rows = [dict(row) for row in conn.execute(
            "SELECT * FROM v3_video_account_daily WHERE " + visibility('v3_video_account_daily') + range_filter + " ORDER BY stat_date,uid", params
        ).fetchall()]
        response: dict[str, Any] = {
            "schema": "v3-analytics-foundation-1",
            "source_kind": source_kind or "all",
            "counts": counts,
            "runs": runs,
            "revenue_source_inventory": revenue_sources,
            "revenue_period_coverage": revenue_period_coverage,
            "revenue_detail_coverage": revenue_detail_coverage,
            "video_account_daily": daily_rows,
            "policy": {
                "page_read_triggers_refresh": False,
                "legacy_revenue_included": False,
                "cached_video_freshness": "cached_only",
            },
        }
        if source_kind:
            def rows(table: str, order: str, extra_filter: str = "", extra_params: list[str] | None = None) -> list[dict[str, Any]]:
                query = f"SELECT * FROM {table} WHERE source_kind=? AND {visibility(table)}"
                query_params: list[str] = [source_kind]
                if extra_filter:
                    query += extra_filter
                    query_params.extend(extra_params or [])
                query += f" ORDER BY {order}"
                return [dict(row) for row in conn.execute(query, query_params).fetchall()]

            response.update({
                "video_accounts": rows("v3_video_accounts", "snapshot_date,account_name"),
                "video_posts": rows("v3_video_posts", "view DESC,account_name"),
                "video_post_daily": rows("v3_video_post_daily", "stat_date,post_id"),
                "video_account_diagnostics": rows("v3_video_account_diagnostics", "abnormal DESC,account_name"),
                "video_post_punishments": rows("v3_video_post_punishments", "snapshot_date DESC,uid"),
                "revenue_account_periods": rows("v3_revenue_account_periods", "period_start,account_id,theater_id"),
                "revenue_details": rows("v3_revenue_details", "detail_date,account_id,source_rank"),
            })
        return response
