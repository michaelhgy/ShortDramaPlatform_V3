from __future__ import annotations

"""Build and select the local Jianying BGM pool without model calls.

The Jianying cache holds metadata for music that has been shown in the audio
library, including tracks not yet downloaded to a draft.  This tool makes that
metadata into a stable local catalogue.  It deliberately does *not* treat a
signed preview URL as a permanent music file: an item becomes selectable for a
real composition only after it is registered in the local ready manifest.
"""

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def iter_nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nodes(child)


def is_music(node: dict[str, Any]) -> bool:
    return bool(
        node.get("title")
        and node.get("author")
        and node.get("duration")
        and node.get("preview_url")
        and (node.get("album") is not None or node.get("is_pgc") is not None)
    )


def music_record(node: dict[str, Any], *, database: Path, rowid: int, url: str) -> dict[str, Any] | None:
    if not is_music(node):
        return None
    music_id = str(node.get("id") or node.get("web_id") or "")
    if not music_id:
        return None
    duration = float(node.get("duration") or 0)
    if duration < 30:
        return None
    source_url = url.casefold()
    catalogue_rank = 0
    if bool(node.get("is_popular_music")):
        catalogue_rank += 100
    if any(token in source_url for token in ("hot", "popular", "recommend", "recommendation")):
        catalogue_rank += 20
    if bool(node.get("has_favorited")):
        catalogue_rank += 5
    return {
        "music_id": music_id,
        "title": str(node.get("title")).strip(),
        "author": str(node.get("author")).strip(),
        "album": str(node.get("album") or "").strip(),
        "duration_seconds": duration,
        "catalogue_rank": catalogue_rank,
        "is_popular_music": bool(node.get("is_popular_music")),
        "is_commerce": bool(node.get("is_commerce")),
        "commercial_scope": node.get("commercial_scope"),
        "paid_type": str(node.get("paid_type") or ""),
        "copyrighted": bool(node.get("copyrighted")),
        "is_pgc": bool(node.get("is_pgc")),
        "has_favorited": bool(node.get("has_favorited")),
        "preview_url": str(node.get("preview_url")),
        "source_database": str(database),
        "source_rowid": rowid,
        "source_endpoint": url,
    }


def load_catalogue(user_data_root: Path) -> list[dict[str, Any]]:
    db_root = user_data_root / "Cache" / "ressdk_db"
    databases = sorted(db_root.glob("*/rp.db"), key=lambda item: item.stat().st_mtime)
    if not databases:
        raise FileNotFoundError(f"未找到剪映资源缓存数据库：{db_root}")
    records: dict[str, dict[str, Any]] = {}
    for database in databases:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            rows = connection.execute("select rowid, url, response_body from http_cache").fetchall()
        finally:
            connection.close()
        for rowid, endpoint, body in rows:
            try:
                parsed = json.loads(body)
            except (TypeError, json.JSONDecodeError):
                continue
            for node in iter_nodes(parsed):
                record = music_record(node, database=database, rowid=int(rowid), url=str(endpoint))
                if record is not None:
                    records[record["music_id"]] = record
    return sorted(records.values(), key=lambda item: (-item["catalogue_rank"], item["title"], item["music_id"]))


def load_ready(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        str(item["music_id"]): item
        for item in data.get("items", [])
        if isinstance(item, dict) and item.get("music_id") and item.get("status") == "ready"
    }


def load_usage_events(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and value.get("music_id"):
                values.append(value)
        except json.JSONDecodeError:
            continue
    return values


def load_recent_ids(path: Path | None, limit: int) -> list[str]:
    if limit <= 0:
        return []
    values = [str(item["music_id"]) for item in load_usage_events(path)]
    return list(reversed(values[-limit:]))


def append_usage(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "used_at_utc": datetime.now(UTC).isoformat(),
        "music_id": str(item["music_id"]),
        "title": item["title"],
        "task_key": item["task_key"],
        "selection_seed": item["selection_seed"],
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def build(args: argparse.Namespace) -> None:
    records = load_catalogue(args.user_data_root.resolve())
    output = {
        "version": 1,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "source": "Jianying local ressdk_db cache",
        "usage_boundary": "catalogue_only; signed preview_url is transient and cannot be used as a production asset",
        "policy": {
            "prefer_popular": True,
            "allow_vocal_music": True,
            "minimum_duration_seconds": 30,
            "target_integrated_lufs": -37,
        },
        "count": len(records),
        "items": records,
    }
    write_json(args.output, output)
    print(json.dumps({"status": "PASS", "catalogue_count": len(records), "output": str(args.output)}, ensure_ascii=False))


def select(args: argparse.Namespace) -> None:
    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8-sig"))
    ready = load_ready(args.ready_manifest)
    all_items = [item for item in catalogue.get("items", []) if isinstance(item, dict)]
    candidates = [item for item in all_items if str(item.get("music_id")) in ready]
    if not args.require_ready:
        candidates = all_items
    if not candidates:
        state = "NO_READY_BGM" if args.require_ready else "NO_CATALOGUE_BGM"
        raise RuntimeError(f"{state}: 先将一首已下载并校准的音乐登记到本地 ready 清单")
    candidates.sort(key=lambda item: (-int(item.get("catalogue_rank", 0)), item["title"], str(item["music_id"])))
    recent_ids = set(load_recent_ids(args.usage_log, args.avoid_recent))
    fresh_candidates = [item for item in candidates if str(item["music_id"]) not in recent_ids]
    if fresh_candidates:
        candidates = fresh_candidates
    token = f"{args.seed}|{args.task_key}|{'|'.join(str(item['music_id']) for item in candidates)}"
    index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % len(candidates)
    chosen = dict(candidates[index])
    chosen["selection_seed"] = args.seed
    chosen["task_key"] = args.task_key
    chosen["selection_index"] = index
    chosen["availability"] = "ready" if str(chosen["music_id"]) in ready else "catalogue_only"
    if chosen["availability"] == "ready":
        chosen["local_asset"] = ready[str(chosen["music_id"])]
    write_json(args.output, chosen)
    if args.usage_log is not None and chosen["availability"] == "ready":
        append_usage(args.usage_log, chosen)
    print(json.dumps({"status": "PASS", "availability": chosen["availability"], "title": chosen["title"], "author": chosen["author"], "output": str(args.output)}, ensure_ascii=False))


def status(args: argparse.Namespace) -> None:
    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8-sig"))
    built_at = datetime.fromisoformat(str(catalogue["built_at_utc"]).replace("Z", "+00:00"))
    if built_at.tzinfo is None:
        built_at = built_at.replace(tzinfo=UTC)
    age_days = (datetime.now(UTC) - built_at).total_seconds() / 86400
    usage_count = 0
    for event in load_usage_events(args.usage_log):
        try:
            used_at = datetime.fromisoformat(str(event["used_at_utc"]).replace("Z", "+00:00"))
            if used_at.tzinfo is None:
                used_at = used_at.replace(tzinfo=UTC)
            if used_at >= built_at:
                usage_count += 1
        except (KeyError, TypeError, ValueError):
            continue
    reasons = []
    if age_days >= args.refresh_days:
        reasons.append(f"catalogue_age_{age_days:.1f}d")
    if usage_count >= args.refresh_after_uses:
        reasons.append(f"usage_since_last_rotation_{usage_count}")
    output = {
        "status": "REFRESH_DUE" if reasons else "CURRENT",
        "catalogue_age_days": round(age_days, 2),
        "usage_events": usage_count,
        "refresh_days": args.refresh_days,
        "refresh_after_uses": args.refresh_after_uses,
        "reasons": reasons,
        "next_action": (
            "在剪映打开一次音频-热门页以刷新本机缓存，然后运行 build 覆盖目录。"
            if reasons else "继续从 ready 本地音乐池选择。"
        ),
    }
    if args.output:
        write_json(args.output, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="建立并选择剪映本地 BGM 目录")
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--user-data-root", required=True, type=Path)
    build_parser.add_argument("--output", required=True, type=Path)
    build_parser.set_defaults(func=build)
    select_parser = sub.add_parser("select")
    select_parser.add_argument("--catalogue", required=True, type=Path)
    select_parser.add_argument("--ready-manifest", type=Path)
    select_parser.add_argument("--seed", required=True, type=int)
    select_parser.add_argument("--task-key", required=True)
    select_parser.add_argument("--output", required=True, type=Path)
    select_parser.add_argument("--require-ready", action="store_true")
    select_parser.add_argument("--usage-log", type=Path)
    select_parser.add_argument("--avoid-recent", type=int, default=50)
    select_parser.set_defaults(func=select)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--catalogue", required=True, type=Path)
    status_parser.add_argument("--usage-log", type=Path)
    status_parser.add_argument("--refresh-days", type=int, default=7)
    status_parser.add_argument("--refresh-after-uses", type=int, default=120)
    status_parser.add_argument("--output", type=Path)
    status_parser.set_defaults(func=status)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
