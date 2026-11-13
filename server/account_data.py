"""Controlled local snapshots for Xiao V Cat account statistics.

The collector keeps the MCP payload except explicitly excluded metrics. The response
shape is controlled by Xiao V Cat and must not be turned into business facts
until the real payload has been inspected.
"""
from __future__ import annotations

import json
import threading
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

from server.publishing.vcat import VcatClient

SHANGHAI = timezone(timedelta(hours=8))
RUN_LOCK = threading.Lock()
RUNS: dict[str, dict[str, object]] = {}


def stamp() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def today() -> str:
    return (datetime.now(SHANGHAI).date() - timedelta(days=1)).isoformat()


def initialize(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS v3_account_data_runs (
            id TEXT PRIMARY KEY,
            data_kind TEXT NOT NULL,
            collection_day TEXT NOT NULL,
            requested_start_date TEXT NOT NULL DEFAULT '',
            requested_end_date TEXT NOT NULL DEFAULT '',
            requested_account_ids_json TEXT NOT NULL DEFAULT '[]',
            requested_uids_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','skipped')),
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v3_account_data_snapshots (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES v3_account_data_runs(id) ON DELETE CASCADE,
            account_id TEXT NOT NULL DEFAULT '',
            uid TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT '视频号',
            data_kind TEXT NOT NULL,
            collection_day TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('success','failed','unavailable')),
            data_state TEXT NOT NULL DEFAULT 'legacy_unknown',
            refresh_status TEXT NOT NULL DEFAULT 'legacy_unknown',
            refresh_result_json TEXT NOT NULL DEFAULT '{}',
            payload_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_v3_account_data_snapshots_day
            ON v3_account_data_snapshots(collection_day, data_kind, uid);
        CREATE INDEX IF NOT EXISTS idx_v3_account_data_runs_created
            ON v3_account_data_runs(created_at DESC);
        CREATE TABLE IF NOT EXISTS v3_account_post_snapshots (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL DEFAULT '',
            uid TEXT NOT NULL,
            account_name TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT 'Channels',
            collection_day TEXT NOT NULL,
            post_id TEXT NOT NULL,
            post_time TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            post_type TEXT NOT NULL DEFAULT 'video',
            publish_status TEXT NOT NULL DEFAULT '',
            data_state TEXT NOT NULL DEFAULT 'record',
            metric_grain TEXT NOT NULL DEFAULT 'daily',
            source_kind TEXT NOT NULL DEFAULT 'xiao_v',
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT '',
            UNIQUE(uid, post_id, collection_day, source_kind)
        );
        CREATE INDEX IF NOT EXISTS idx_v3_account_post_snapshots_day
            ON v3_account_post_snapshots(collection_day, uid, post_id);
        """
    )
    run_columns = {row[1] for row in conn.execute("PRAGMA table_info(v3_account_data_runs)")}
    for name, definition in (
        ("requested_start_date", "TEXT NOT NULL DEFAULT ''"),
        ("requested_end_date", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in run_columns:
            conn.execute(f"ALTER TABLE v3_account_data_runs ADD COLUMN {name} {definition}")
    snapshot_columns = {row[1] for row in conn.execute("PRAGMA table_info(v3_account_data_snapshots)")}
    for name, definition in (
        ("data_state", "TEXT NOT NULL DEFAULT 'legacy_unknown'"),
        ("refresh_status", "TEXT NOT NULL DEFAULT 'legacy_unknown'"),
        ("refresh_result_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if name not in snapshot_columns:
            conn.execute(f"ALTER TABLE v3_account_data_snapshots ADD COLUMN {name} {definition}")


def recover_interrupted(conn) -> None:
    conn.execute(
        """UPDATE v3_account_data_runs SET status='failed', finished_at=?,
             error_message='程序退出时任务未完成，请确认小V猫状态后再手动重试'
           WHERE status IN ('queued','running')""", (stamp(),)
    )


def _row_dict(row):
    return dict(row) if row is not None else None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _load_json(value, fallback):
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, json.JSONDecodeError):
        return fallback
    return parsed


def _target_accounts(conn, account_ids: list[str] | None, uids: list[str] | None) -> list[dict[str, str]]:
    rows = conn.execute(
        """SELECT id, nickname, channel_id, status FROM accounts
           WHERE COALESCE(status, '') <> '注销'
             AND TRIM(COALESCE(channel_id, '')) <> ''
           ORDER BY nickname, id"""
    ).fetchall()
    wanted_ids = {str(value) for value in (account_ids or []) if str(value).strip()}
    wanted_uids = {str(value) for value in (uids or []) if str(value).strip()}
    result = []
    for row in rows:
        if not wanted_ids and not wanted_uids and row['status'] in ('停用', 'disabled'):
            continue
        item = {"id": str(row["id"]), "nickname": str(row["nickname"]), "uid": str(row["channel_id"])}
        if wanted_ids and item["id"] not in wanted_ids:
            continue
        if wanted_uids and item["uid"] not in wanted_uids:
            continue
        result.append(item)
    return result


def _active_run(conn):
    row = conn.execute(
        """SELECT id, status, collection_day, created_at
           FROM v3_account_data_runs
           WHERE status IN ('queued','running')
           ORDER BY created_at DESC LIMIT 1"""
    ).fetchone()
    return _row_dict(row)


def overview(connection, collection_day: str | None = None, start_date: str | None = None,
             end_date: str | None = None) -> dict[str, object]:
    from server.account_visibility import visible_account_sql
    day = collection_day or end_date or today()
    start = start_date or day
    end = end_date or day
    _dates(start, end)
    with closing(connection()) as conn:
        accounts = [dict(row) for row in conn.execute(
            """SELECT id, nickname, channel_id AS uid, status
               FROM accounts
               WHERE TRIM(COALESCE(channel_id, '')) <> ''
               ORDER BY nickname, id"""
        ).fetchall()]
        snapshots = [dict(row) for row in conn.execute(
            f"""SELECT s.id, s.run_id, s.account_id, s.uid, s.platform, s.data_kind,
                      s.collection_day, s.fetched_at, s.status, s.data_state,
                      s.refresh_status, s.refresh_result_json, s.payload_json,
                      s.error_message, a.nickname AS account_name
               FROM v3_account_data_snapshots s
               LEFT JOIN accounts a ON a.id=s.account_id
               WHERE s.collection_day BETWEEN ? AND ? AND s.data_kind='account_stats'
                  AND {visible_account_sql(conn, account_id='s.account_id', uid='s.uid')}
                 AND s.id=(SELECT latest.id FROM v3_account_data_snapshots latest
                           WHERE latest.uid=s.uid AND latest.data_kind=s.data_kind
                             AND latest.collection_day=s.collection_day
                           ORDER BY latest.fetched_at DESC, latest.id DESC LIMIT 1)
               ORDER BY s.collection_day, COALESCE(a.nickname, s.uid), s.uid""", (start, end)
        ).fetchall()]
        for snapshot in snapshots:
            snapshot["payload"] = _load_json(snapshot.pop("payload_json"), {})
            snapshot["refresh_result"] = _load_json(snapshot.pop("refresh_result_json"), {})
        post_snapshots = [dict(row) for row in conn.execute(
            f"""SELECT p.id, p.account_id, p.uid, COALESCE(a.nickname, p.account_name) AS account_name,
                      p.platform, p.collection_day, p.post_id, p.post_time, p.title, p.post_type,
                      p.publish_status, p.data_state, p.metric_grain, p.source_kind, p.fetched_at,
                      p.payload_json, p.error_message
               FROM v3_account_post_snapshots p
               LEFT JOIN accounts a ON a.id=p.account_id
               WHERE p.collection_day BETWEEN ? AND ?
                  AND {visible_account_sql(conn, account_id='p.account_id', uid='p.uid')}
                 AND p.id=(SELECT latest.id FROM v3_account_post_snapshots latest
                           WHERE latest.uid=p.uid AND latest.post_id=p.post_id
                             AND latest.collection_day=p.collection_day AND latest.source_kind=p.source_kind
                           ORDER BY latest.fetched_at DESC, latest.id DESC LIMIT 1)
               ORDER BY p.collection_day, account_name, p.post_id""", (start, end)
        ).fetchall()]
        for post in post_snapshots:
            post["payload"] = _load_json(post.pop("payload_json"), {})
        latest_run = conn.execute(
            """SELECT id, data_kind, collection_day, requested_start_date,
                      requested_end_date, requested_account_ids_json,
                      requested_uids_json, status, started_at, finished_at,
                      error_message, created_at
               FROM v3_account_data_runs ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        active = _active_run(conn)
    run = _row_dict(latest_run)
    if run:
        run["requested_account_ids"] = _load_json(run.pop("requested_account_ids_json"), [])
        run["requested_uids"] = _load_json(run.pop("requested_uids_json"), [])
    return {
        "collection_day": day,
        "start_date": start,
        "end_date": end,
        "accounts": accounts,
        "snapshots": snapshots,
        "post_snapshots": post_snapshots,
        "latest_run": run,
        "active_run": active,
        "policy": {
            "automatic_enabled": False,
            "same_day_success_is_reused": True,
            "platform_refresh_is_never_triggered_by_page_read": True,
        },
    }


def _save_snapshot(conn, run_id: str, account: dict[str, str], day: str, status: str, payload=None,
                   error: str = "", data_state: str = "legacy_unknown", refresh_status: str = "legacy_unknown",
                   refresh_result=None) -> None:
    conn.execute(
        """INSERT INTO v3_account_data_snapshots(
             id, run_id, account_id, uid, platform, data_kind, collection_day,
             fetched_at, status, data_state, refresh_status, refresh_result_json,
             payload_json, error_message)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uuid.uuid4().hex, run_id, account["id"], account["uid"], "视频号", "account_stats",
         day, stamp(), status, data_state, refresh_status, _json(refresh_result if refresh_result is not None else {}),
         _json(payload if payload is not None else {}), error),
    )


def _is_unavailable_vcat_account(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    value = str(item.get("loginStatus") or item.get("login_status") or "").strip().lower()
    if not value:
        return False
    return value in {"invalid", "登录失效", "失效", "已失效", "作废", "已作废", "未登录", "登录过期"} or "失效" in value or "作废" in value


def _precheck_vcat_accounts(client, accounts: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[tuple[dict[str, str], str]]]:
    remote_by_uid = {
        str(item.get("uid") or "").strip(): item
        for item in client.accounts()
        if isinstance(item, dict) and item.get("platform") in (None, "Channels") and str(item.get("uid") or "").strip()
    }
    available = []
    unavailable = []
    for account in accounts:
        remote = remote_by_uid.get(account["uid"])
        if remote is None:
            unavailable.append((account, "小V猫账号列表中未找到，可能已删除或作废，请在小V猫中核对"))
        elif _is_unavailable_vcat_account(remote):
            unavailable.append((account, "账号已作废或登录失效，请在小V猫中处理"))
        else:
            available.append(account)
    return available, unavailable


def _dates(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    if (end - start).days > 90:
        raise ValueError("单次日期范围最多 90 天")
    return [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]


def _refresh_results(value, uids: list[str]) -> dict[str, dict[str, object]]:
    results = value.get("results") if isinstance(value, dict) else None
    if not isinstance(results, list):
        raise RuntimeError("小V猫刷新未返回逐账号结果，不能确认数据是否已从平台更新")
    mapped = {str(item.get("uid") or ""): item for item in results if isinstance(item, dict)}
    return {uid: mapped.get(uid, {"uid": uid, "success": False, "error": "刷新结果中缺少该账号"}) for uid in uids}


def _run_refresh(connection, run_id: str, accounts: list[dict[str, str]], start_date: str, end_date: str,
                 client_factory) -> None:
    conn = connection()
    dates = _dates(start_date, end_date)
    try:
        conn.execute("UPDATE v3_account_data_runs SET status='running', started_at=? WHERE id=?", (stamp(), run_id))
        conn.commit()
        try:
            with client_factory(writable=False, account_data=True) as client:
                try:
                    available, unavailable = _precheck_vcat_accounts(client, accounts)
                except Exception as exc:
                    message = str(exc)[:800]
                    for account in accounts:
                        for day in dates:
                            _save_snapshot(conn, run_id, account, day, "failed", error=message,
                                           data_state="refresh_precheck_failed", refresh_status="not_confirmed")
                    conn.commit()
                    available, unavailable = [], []
                for account, message in unavailable:
                    for day in dates:
                        _save_snapshot(conn, run_id, account, day, "unavailable", error=message,
                                       data_state="unavailable", refresh_status="not_attempted")
                conn.commit()
                for offset in range(0, len(available), 10):
                    chunk = available[offset:offset + 10]
                    uids = [item["uid"] for item in chunk]
                    try:
                        refresh_payload = client.call("vcat_refresh_account_stats", {"uids": uids})
                        refresh_by_uid = _refresh_results(refresh_payload, uids)
                    except Exception as exc:
                        message = str(exc)[:800]
                        for account in chunk:
                            for day in dates:
                                _save_snapshot(conn, run_id, account, day, "failed", error=message,
                                               data_state="refresh_failed", refresh_status="failed")
                        conn.commit()
                        continue
                    for account in chunk:
                        refresh_result = refresh_by_uid[account["uid"]]
                        if not refresh_result.get("success"):
                            message = str(refresh_result.get("error") or "小V猫未能确认该账号刷新成功")[:800]
                            for day in dates:
                                _save_snapshot(conn, run_id, account, day, "failed", error=message,
                                               data_state="refresh_failed", refresh_status="failed",
                                               refresh_result=refresh_result)
                            conn.commit()
                            continue
                        try:
                            payload = client.call("vcat_get_account_stats", {
                                "uid": account["uid"],
                                "startDate": start_date,
                                "endDate": end_date,
                                "includeIncome": False,
                            })
                            daily_by_date = {
                                str(item.get("date") or ""): item
                                for item in (payload.get("daily") or [])
                                if isinstance(item, dict)
                            } if isinstance(payload, dict) else {}
                            for day in dates:
                                data_state = "record" if day in daily_by_date else "no_daily_record"
                                _save_snapshot(conn, run_id, account, day, "success", payload=payload,
                                               data_state=data_state, refresh_status="success",
                                               refresh_result=refresh_result)
                        except Exception as exc:
                            for day in dates:
                                _save_snapshot(conn, run_id, account, day, "failed", error=str(exc)[:800],
                                               data_state="query_failed", refresh_status="success",
                                               refresh_result=refresh_result)
                        conn.commit()
            counts = conn.execute(
                """SELECT SUM(status='success') AS successes, SUM(status='unavailable') AS unavailable,
                          COUNT(*) AS total
                   FROM v3_account_data_snapshots WHERE run_id=?""", (run_id,)
            ).fetchone()
            status = "failed" if not counts or int(counts["total"] or 0) == 0 or (
                int(counts["successes"] or 0) == 0 and int(counts["unavailable"] or 0) == 0
            ) else "completed"
            error = ""
            if status == "failed":
                error = "所有账号均未能获取统计快照"
        except Exception as exc:
            status = "failed"
            error = str(exc)[:800]
        conn.execute("UPDATE v3_account_data_runs SET status=?, finished_at=?, error_message=? WHERE id=?", (status, stamp(), error, run_id))
        conn.commit()
    finally:
        conn.close()
        with RUN_LOCK:
            RUNS.pop(run_id, None)


def start_refresh(connection, account_ids=None, uids=None, force=False, start_date=None, end_date=None,
                  client_factory=VcatClient) -> dict[str, object]:
    with RUN_LOCK:
        conn = connection()
        try:
            active = _active_run(conn)
            if active:
                raise ValueError("账号数据获取正在进行，请先查看当前任务状态")
            start = str(start_date or today())
            end = str(end_date or start)
            dates = _dates(start, end)
            accounts = _target_accounts(conn, account_ids, uids)
            if not accounts:
                raise ValueError("没有可获取的已登记视频号账号")
            if not force:
                placeholders = ",".join("?" for _ in accounts)
                uid_values = [item["uid"] for item in accounts]
                day_placeholders = ",".join("?" for _ in dates)
                rows = conn.execute(
                    f"""SELECT uid, collection_day FROM v3_account_data_snapshots
                        WHERE data_kind='account_stats' AND collection_day IN ({day_placeholders})
                          AND uid IN ({placeholders})
                          AND (status='unavailable' OR (status='success' AND refresh_status='success'))""",
                    [*dates, *uid_values],
                ).fetchall()
                done = {(str(row["uid"]), str(row["collection_day"])) for row in rows}
                accounts = [item for item in accounts if not all((item["uid"], day) in done for day in dates)]
                if not accounts:
                    return {"run_id": "", "status": "skipped", "collection_day": end, "account_count": 0, "message": "所选日期的数据已获取或账号已标记失效，未重复访问平台"}
            run_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO v3_account_data_runs(
                   id, data_kind, collection_day, requested_start_date, requested_end_date,
                   requested_account_ids_json, requested_uids_json, status, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (run_id, "account_stats", end, start, end, _json([item["id"] for item in accounts]), _json([item["uid"] for item in accounts]), "queued", stamp()),
            )
            conn.commit()
            RUNS[run_id] = {"status": "queued"}
            thread = threading.Thread(target=_run_refresh, args=(connection, run_id, accounts, start, end, client_factory), daemon=True, name="v3-account-data-refresh")
            RUNS[run_id]["thread"] = thread
            thread.start()
            return {"run_id": run_id, "status": "queued", "collection_day": end, "start_date": start, "end_date": end, "account_count": len(accounts)}
        finally:
            conn.close()


def run_status(connection, run_id: str) -> dict[str, object]:
    with closing(connection()) as conn:
        row = conn.execute("SELECT * FROM v3_account_data_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("未找到账号数据获取任务")
        result = _row_dict(row)
        result["requested_account_ids"] = _load_json(result.pop("requested_account_ids_json"), [])
        result["requested_uids"] = _load_json(result.pop("requested_uids_json"), [])
        result["snapshots"] = [dict(item) for item in conn.execute(
            """SELECT uid, account_id, status, data_state, refresh_status,
                      refresh_result_json, fetched_at, error_message
               FROM v3_account_data_snapshots WHERE run_id=? ORDER BY uid""", (run_id,)
        ).fetchall()]
        for snapshot in result["snapshots"]:
            snapshot["refresh_result"] = _load_json(snapshot.pop("refresh_result_json"), {})
        return result
