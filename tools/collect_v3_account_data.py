"""Collect V3 workbench data via the existing local Xiao V Cat MCP adapter.

Default: read local cache only. --refresh and --sync-posts explicitly request
platform statistics refresh / work sync. No V3 database, publishing, deletion,
account diagnosis refresh, or theater revenue is changed. Each run is separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.publishing.vcat import VcatClient

SHANGHAI = timezone(timedelta(hours=8))
MEDIA_KEYS = {"url", "cover", "avatar", "videourl", "imageurl", "thumburl", "downloadurl"}
SECRET_KEYS = {"token", "accesstoken", "refreshtoken", "authorization", "cookie", "cookies", "password", "signature", "sessionkey"}


def stamp() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = re.sub(r"[_-]", "", str(key)).lower()
            if normalized in {"livestatus", "heatstatus"}:
                continue
            if normalized in MEDIA_KEYS:
                result[str(key) + "Present"] = bool(item)
            elif normalized in SECRET_KEYS:
                result[str(key)] = "[redacted]"
            else:
                result[str(key)] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"https?://[^\s\"<>]+", "[url-redacted]", value)
    return value


def number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return int(result) if result.is_integer() else result


def paginate(client: Any, tool: str, args: dict, identity: tuple[str, ...], limit: int = 200) -> dict:
    rows, seen = [], set()
    reported = None
    for page in range(1, limit + 1):
        result = client.call(tool, {**args, "page": page, "pageSize": 100})
        if not isinstance(result, dict) or not isinstance(result.get("list"), list):
            raise RuntimeError(f"{tool}: malformed page")
        total = number(result.get("total"))
        if total is not None:
            if total < 0 or int(total) != total:
                raise RuntimeError(f"{tool}: invalid total")
            if reported is not None and reported != total:
                raise RuntimeError(f"{tool}: total changed during pagination; read again")
            reported = int(total)
        batch = result["list"]
        for item in batch:
            if not isinstance(item, dict):
                raise RuntimeError(f"{tool}: malformed row")
            key = tuple(str(item.get(k, "")) for k in identity)
            if not all(key):
                raise RuntimeError(f"{tool}: missing stable identity")
            if key in seen:
                raise RuntimeError(f"{tool}: duplicate row across pages")
            seen.add(key)
            rows.append(item)
        if reported is not None and len(rows) > reported:
            raise RuntimeError(f"{tool}: returned more rows than total")
        if reported is not None and len(rows) == reported:
            return {"list": rows, "total": reported, "complete": True}
        if not batch:
            if reported is not None:
                raise RuntimeError(f"{tool}: empty page before total reached")
            return {"list": rows, "total": len(rows), "complete": True}
        if reported is None and len(batch) < 100:
            return {"list": rows, "total": len(rows), "complete": True}
    raise RuntimeError(f"{tool}: pagination limit reached")


def build_account_core(stats: dict) -> dict:
    total = stats.get("total") or {}
    daily = []
    for row in stats.get("daily") or []:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        daily.append({
            "date": row["date"], "views": number(row.get("view")),
            "followsAdded": number(row.get("fansAdd")),
            "followsNet": number(row.get("fansNet")),
            "followsReduced": number(row.get("fansReduce")),
            "hearts": number(row.get("like")),
            "comments": number(row.get("comment")),
        })
    return {"videoTotal": number(total.get("postCount")),
            "followerTotal": number(total.get("fans")),
            "sourceUpdatedAt": total.get("updateTime"), "daily": daily}


def build_post_core(row: dict) -> dict:
    # Xiao V uses different interaction names for account daily vs work metrics.
    return {"postId": row.get("postId"), "uid": row.get("uid"),
            "publishTime": row.get("postTime"), "publishStatus": row.get("publishStatus"),
            "views": number(row.get("view")), "completionRate": number(row.get("fullView")),
            "hearts": number(row.get("love")), "comments": number(row.get("comment")),
            "shares": number(row.get("forward")), "thumbsUp": number(row.get("like")),
            "coverPresent": bool(row.get("cover")), "urlPresent": bool(row.get("url"))}


def collect(client: Any, args: Any, emit: Any, checkpoint: Any = None) -> dict:
    available = paginate(client, "vcat_list_accounts", {"platform": "Channels"}, ("uid",))
    all_accounts = available["list"]
    requested = set(args.uid or [])
    selected = [a for a in all_accounts if str(a.get("uid")) in requested] if requested else [a for a in all_accounts if a.get("loginStatus") == "登录有效"]
    found = {str(a.get("uid")) for a in selected}
    if requested - found:
        raise ValueError("Requested account UID not found")
    if not selected:
        raise ValueError("No available account; log into Xiao V Cat first")
    result: dict[str, Any] = {"schemaVersion": 1, "startedAt": stamp(), "dateRange": [args.start, args.end],
        "source": "xiao_v_mcp", "mode": "platform_refresh" if args.refresh or args.sync_posts else "cache_with_official_analysis" if getattr(args, "optimization_details", False) else "cache_read",
        "scope": {"uids": sorted(found), "dailyPosts": False, "revenue": False, "v3DatabaseWritten": False},
        "accounts": redact(available), "accountResults": {}, "accountDetails": {},
        "postProfile": {"rows": []}, "core": {"accounts": {}, "posts": []}, "errors": [],
        "platformRefresh": {}, "postSync": {"requested": bool(args.sync_posts)}, "status": "running"}
    def save() -> None:
        if checkpoint is not None:
            checkpoint(redact(result))
    save()
    emit("accounts", {"available": len(all_accounts), "selected": len(selected)})
    if args.sync_posts or getattr(args, "sync_records", False):
        before = client.call("vcat_get_post_sync", {})
        result["postSync"]["before"] = redact(before)
        save()
        if args.sync_posts and before.get("looping"):
            raise RuntimeError("Another work sync is running; it was not interrupted")
    if args.refresh:
        valid = [str(a["uid"]) for a in selected if a.get("loginStatus") == "登录有效"]
        for offset in range(0, len(valid), 10):
            batch = valid[offset:offset + 10]
            emit("refresh_start", {"accounts": len(batch)})
            try:
                refreshed = client.call("vcat_refresh_account_stats", {"uids": batch})
                result["platformRefresh"][str(offset // 10)] = redact(refreshed)
                confirmed = {str(row.get("uid")): row.get("success") is True for row in refreshed.get("results", []) if isinstance(row, dict)}
                for uid in batch:
                    if not confirmed.get(uid):
                        result["errors"].append({"stage": "account_refresh", "uid": uid, "message": "No successful platform refresh confirmation; cached data kept separately"})
            except Exception as exc:
                result["errors"].append({"stage": "account_refresh", "message": str(exc)})
            save()
            emit("refresh_finished", {"accounts": len(batch)})
    if args.sync_posts:
        sync_uids = [str(a["uid"]) for a in selected if a.get("loginStatus") == "登录有效"]
        if not sync_uids:
            raise RuntimeError("No logged-in accounts to sync")
        emit("post_sync_start", {"accounts": len(sync_uids), "range": "all", "daily": False})
        # One submission only. Ambiguous outcomes must be inspected, never retried.
        try:
            result["postSync"]["startResult"] = redact(client.call("vcat_start_post_sync", {
                "uids": sync_uids, "postRangeType": "all", "daily": False, "dailyDays": 0,
                "maxRun": 1, "errorNotice": False}))
            if result["postSync"]["startResult"].get("started") is not True:
                raise RuntimeError("Xiao V did not confirm work sync start; no retry submitted")
            deadline = time.monotonic() + args.wait_seconds
            while True:
                state = client.call("vcat_get_post_sync", {})
                result["postSync"]["after"] = redact(state)
                save()
                if not state.get("looping"):
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Work sync still running; snapshot is partial. Inspect Xiao V before a new sync")
                emit("post_sync_wait", {"state": state.get("loopingText"), "localCount": state.get("localCount")})
                time.sleep(5)
        except Exception as exc:
            result["errors"].append({"stage": "post_sync", "message": str(exc)})
    if args.sync_posts or getattr(args, "sync_records", False):
        cutoff = ((result["postSync"].get("after") or {}).get("task") or {}).get("lastRun")
        for account in selected:
            uid = str(account["uid"])
            for kind in ("summary", "error"):
                try:
                    records = paginate(client, "vcat_list_post_sync_records", {"uid": uid, "type": kind}, ("recordId",))
                    result["postSync"].setdefault("records", {}).setdefault(uid, {})[kind] = redact(records)
                    if args.sync_posts and kind == "error" and cutoff:
                        for record in records["list"]:
                            if str(record.get("time") or "") >= str(cutoff):
                                result["errors"].append({"stage": "post_sync_account", "uid": uid,
                                    "recordId": record.get("recordId"), "message": record.get("text") or "Work sync error"})
                except Exception as exc:
                    result["errors"].append({"stage": "sync_records", "uid": uid, "message": str(exc)})
    for account in selected:
        uid = str(account["uid"])
        account_result = {"nickname": account.get("nickname"), "loginStatus": account.get("loginStatus"),
                          "dataState": "cached_only", "fetchedAt": stamp()}
        for kind in ("statistics", "posts", "optimization"):
            try:
                if kind == "statistics":
                    stats = client.call("vcat_get_account_stats", {"uid": uid, "startDate": args.start, "endDate": args.end, "includeIncome": False})
                    result["accountDetails"][uid] = redact(stats)
                    core = build_account_core(stats)
                    result["core"]["accounts"][uid] = core
                    account_result.update({"videoTotal": core["videoTotal"], "followerTotal": core["followerTotal"],
                        "sourceUpdatedAt": core["sourceUpdatedAt"], "dailyRows": len(core["daily"])})
                elif kind == "posts":
                    posts = paginate(client, "vcat_list_posts", {"uid": uid, "platform": "视频号"}, ("uid", "postId"))
                    result["postProfile"]["rows"].extend(redact(posts["list"]))
                    result["core"]["posts"].extend(build_post_core(p) for p in posts["list"])
                    account_result["postRows"] = len(posts["list"])
                    account_result["publishedPostRows"] = sum(p.get("publishStatus") == "published" for p in posts["list"])
                    account_result["scheduledPostRows"] = sum(p.get("publishStatus") == "scheduled" for p in posts["list"])
                    account_result["unknownPostRows"] = sum(p.get("publishStatus") not in {"published", "scheduled"} for p in posts["list"])
                else:
                    # Existing diagnostic cache only; no diagnosis/appeal/delete calls.
                    diagnosis = client.call("vcat_get_verify_result", {"uid": uid})
                    result.setdefault("optimizationCache", {})[uid] = redact(diagnosis)
                    account_result["optimizationCacheRead"] = True
                    account_result["optimizationState"] = "cached_diagnosis" if diagnosis.get("verified") else "not_checked"
                    account_result["optimizationSourceUpdatedAt"] = diagnosis.get("lastVerifyTime")
                    account_result["optimizationRows"] = len(diagnosis.get("abnormalFeeds") or []) if diagnosis.get("verified") else None
                    if getattr(args, "optimization_details", False) and diagnosis.get("verified"):
                        details = []
                        seen_exports = set()
                        for feed in diagnosis.get("abnormalFeeds") or []:
                            export_id = feed.get("exportId")
                            if not export_id or export_id in seen_exports:
                                continue
                            seen_exports.add(export_id)
                            try:
                                detail = client.optimization_detail(uid, export_id)
                                details.append({**detail, "publishTime": feed.get("publishTime"),
                                                "platformStatus": feed.get("punishState"), "fetchedAt": stamp()})
                            except Exception as exc:
                                result["errors"].append({"stage": "optimization_detail", "uid": uid,
                                                         "exportId": export_id, "message": str(exc)})
                        result.setdefault("optimizationDetails", {})[uid] = redact(details)
                        account_result["optimizationDetailsRead"] = len(details)
            except Exception as exc:
                account_result[kind + "Error"] = str(exc)
                result["errors"].append({"stage": kind, "uid": uid, "message": str(exc)})
        result["accountResults"][uid] = account_result
        save()
        emit("account_read", {"uid": uid, **account_result})
    result["capturedAt"] = stamp()
    result["status"] = "partial" if result["errors"] else "completed_cache_read"
    # 'Completed read' deliberately does not imply every official field is fresh.
    result["postProfile"]["rowCount"] = len(result["postProfile"]["rows"])
    return redact(result)


def main() -> int:
    today = datetime.now(SHANGHAI).date()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--start", default=(today - timedelta(days=7)).isoformat())
    parser.add_argument("--end", default=(today - timedelta(days=1)).isoformat())
    parser.add_argument("--uid", action="append", default=[])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sync-posts", action="store_true")
    parser.add_argument("--sync-records", action="store_true", help="Read sync logs without starting another sync")
    parser.add_argument("--optimization-details", action="store_true", help="Read official analysis for cached abnormal works; never submit appeals")
    parser.add_argument("--wait-seconds", type=int, default=600)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/account-data-collection"))
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start or (end - start).days > 90:
        parser.error("date range must be ordered and at most 90 days apart")
    if args.wait_seconds < 1:
        parser.error("wait-seconds must be positive")
    directory = args.output_root / (datetime.now(SHANGHAI).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    directory.mkdir(parents=True, exist_ok=False)
    def emit(event: str, values: dict) -> None:
        row = redact({"at": stamp(), "event": event, **values})
        with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False), flush=True)
    try:
        with VcatClient(args.port, account_data=args.refresh or args.sync_posts or args.optimization_details) as client:
            snapshot = collect(client, args, emit, lambda data: (directory / "checkpoint.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"))
        destination = directory / "snapshot.json"
        destination.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {"status": snapshot["status"], "dateRange": snapshot["dateRange"],
                   "accounts": snapshot["accountResults"], "posts": snapshot["postProfile"]["rowCount"],
                   "errors": snapshot["errors"], "snapshotSha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                   "snapshot": str(destination.resolve())}
        (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        emit("finished", summary)
        return 2 if snapshot["errors"] else 0
    except Exception as exc:
        emit("failed", {"message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
