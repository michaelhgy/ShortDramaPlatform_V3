"""Confirm delivery to the platform independently of public release and analytics."""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timedelta, timezone

SH = timezone(timedelta(hours=8))
SUCCESS = {"2", "success", "published", "已发布", "发布成功"}


def epoch(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            result = int(value / 1000 if value > 1e12 else value)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            result = int((parsed if parsed.tzinfo else parsed.replace(tzinfo=SH)).timestamp())
        return result if result > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def delivery_confirmation(item, matched_post_id=None):
    """Require a successful, identified platform task; local scheduling is not delivery."""
    if item.get("status") != "success":
        return None
    payload = item.get("accepted_payload") or item.get("payload") or {}
    if payload.get("scheduleType") not in {"now", "timing"}:
        return None
    remote = item.get("remote") or {}
    source = remote.get("_source") or {}
    if str(remote.get("statusCode", remote.get("status", ""))) not in SUCCESS:
        return None
    if not item.get("uid") or remote.get("uid") != item["uid"]:
        return None
    if not item.get("local_id") or str(remote.get("localId") or "") != str(item["local_id"]):
        return None
    if remote.get("platform") not in (None, "", "Channels", "视频号"):
        return None
    checks = item.get("checks") or {}
    if checks and not all(checks.values()):
        return None
    post_id = str(source.get("postId") or matched_post_id or "")
    if not post_id:
        return None
    # postTime/createdAt and the planned timing are not delivery completion times.
    delivered_at = epoch(source.get("postEndTime")) or epoch(remote.get("postEndTime"))
    delivered_at = delivered_at or epoch(item.get("delivery_confirmed_at"))
    return {"post_id": post_id, "delivered_unix": delivered_at}


def retention_settings(conn):
    values = {"short_term_cleanup_hours": 24, "raw_material_retention_days": 7}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='v2_settings'").fetchone():
        for key, raw in conn.execute("SELECT key,value_json FROM v2_settings WHERE key IN (?,?)", tuple(values)):
            value = json.loads(raw)
            limit = 168 if key == "short_term_cleanup_hours" else 90
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= limit:
                values[key] = value
    return values


def apply_completion(conn, task_id, gate, settings=None, expected_content=None):
    if not gate.get("complete"):
        return False
    values = settings or retention_settings(conn)
    completed = datetime.fromtimestamp(int(gate["latest_delivery_unix"]), SH)
    fmt = lambda value: value.strftime("%Y-%m-%d %H:%M:%S")
    # Keep actual public release / revenue dates independent of delivery completion.
    sql = """UPDATE production_tasks SET release_status='registered',
        delivery_completed_at=?,process_cleanup_at=?,raw_cleanup_at=?,updated_at=?
        WHERE id=? AND release_status<>'registered' AND COALESCE(cleanup_status,'active')='active'"""
    params = [fmt(completed), fmt(completed + timedelta(hours=values["short_term_cleanup_hours"])),
              fmt(completed + timedelta(days=values["raw_material_retention_days"])),
              datetime.now(SH).isoformat(timespec="seconds"), task_id]
    if expected_content is not None:
        # Do not finish or overwrite a newer publishing attempt that arrived
        # after this snapshot was read. This comparison and the write are atomic.
        sql += " AND EXISTS(SELECT 1 FROM v3_publish_documents WHERE kind='publish_execution' AND key=? AND content=?)"
        params.extend([task_id, expected_content])
    changed = conn.execute(sql, params).rowcount
    return bool(changed)


def confirm_saved_deliveries(connection):
    """Local-only convergence, including cards that are not currently selected."""
    from server.operations_collection import _publication_completion
    with closing(connection()) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"production_tasks", "v3_publish_documents"} <= tables:
            return 0
        columns = {r[1] for r in conn.execute("PRAGMA table_info(production_tasks)")}
        if not {"cleanup_status", "delivery_completed_at", "process_cleanup_at", "raw_cleanup_at", "updated_at"} <= columns:
            return 0
        rows = conn.execute("""SELECT d.key,d.content FROM v3_publish_documents d
            JOIN production_tasks t ON t.id=d.key WHERE d.kind='publish_execution'
            AND t.release_status<>'registered' AND COALESCE(t.cleanup_status,'active')='active'""").fetchall()
        count = 0
        for row in rows:
            state = json.loads(row["content"])
            gate = _publication_completion(conn, row["key"], state)
            if apply_completion(conn, row["key"], gate, expected_content=row["content"]):
                count += 1
                confirmed = set(gate.get("confirmed_keys", []))
                observed = datetime.now(SH).isoformat(timespec="seconds")
                for item in state.get("items", []):
                    item["delivery_confirmed"] = item.get("key") in confirmed
                    if item["delivery_confirmed"]:
                        item.setdefault("delivery_confirmed_at", observed)
                conn.execute("UPDATE v3_publish_documents SET content=? WHERE kind='publish_execution' AND key=?",
                             (json.dumps(state, ensure_ascii=False), row["key"]))
        conn.commit()
        return count


def sync_public_release_times(conn):
    """Preserve the legacy actual-release date for revenue matching, independently.

    Public release can be observed after production delivery and even after file
    cleanup. Filling this date must never recalculate already saved deadlines.
    """
    import hashlib
    columns = {r[1] for r in conn.execute("PRAGMA table_info(production_tasks)")}
    if not {"actual_release_time", "delivery_completed_at"} <= columns:
        return
    rows = conn.execute("""SELECT d.key,d.content FROM v3_publish_documents d
        JOIN production_tasks t ON t.id=d.key WHERE d.kind='publish_execution'
        AND t.release_status='registered' AND t.actual_release_time=''
        AND t.delivery_completed_at<>''""").fetchall()
    for row in rows:
        items = json.loads(row['content']).get('items', [])
        if not items or any(not item.get('key') or item.get('status') != 'success' for item in items):
            continue
        times = []
        for item in items:
            identity = hashlib.sha256((row['key'] + '\0' + item['key']).encode()).hexdigest()
            observed = conn.execute("""SELECT publish_unix FROM v3_publication_history
                WHERE id=? AND uid=? AND match_state='matched' AND publication_state='published'
                AND post_id<>'' AND publish_unix>0""", (identity, item.get('uid'))).fetchone()
            if not observed:
                break
            times.append(int(observed['publish_unix']))
        if len(times) == len(items):
            actual = datetime.fromtimestamp(max(times), SH).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("UPDATE production_tasks SET actual_release_time=? WHERE id=? AND actual_release_time=''", (actual, row['key']))
