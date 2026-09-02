#!/usr/bin/env python3
"""Fill the verified local Jianying BGM pool from its current cached catalogue.

Preview URLs are only transient download sources.  Each successful download is
decoded, loudness-normalised and registered as a local `extract_music` asset
before it can be selected by a composition task.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from server.runtime_process import no_window_kwargs, worker_command


SCRIPT_DIR = Path(__file__).resolve().parent
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ready_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        str(item["music_id"])
        for item in read_json(path).get("items", [])
        if isinstance(item, dict) and item.get("status") == "ready" and item.get("music_id")
    }


def download(url: str, output: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "JianyingLocalBgmPool/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response, output.open("wb") as stream:
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("BGM download exceeds 80MB safety limit")
            stream.write(chunk)
    if output.stat().st_size < 16 * 1024:
        raise RuntimeError("BGM download is too small to be usable audio")


def register(record: dict[str, Any], source: Path, args: argparse.Namespace) -> None:
    command = worker_command("server.final_engine.scripts.register_ready_bgm", SCRIPT_DIR / "register_ready_bgm.py", [
        "--source", str(source), "--music-id", str(record["music_id"]),
        "--title", str(record.get("title") or record["music_id"]),
        "--author", str(record.get("author") or "Jianying"),
        "--library-root", str(args.library_root), "--ready-manifest", str(args.ready_manifest),
        "--target-lufs", str(args.target_lufs),
    ])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window_kwargs())
    if result.returncode:
        raise RuntimeError(result.stderr[-1200:] or result.stdout[-1200:] or "BGM registration failed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download, normalize and register local-ready Jianying BGM")
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--library-root", required=True, type=Path)
    parser.add_argument("--ready-manifest", required=True, type=Path)
    parser.add_argument("--target-count", type=int, default=20)
    parser.add_argument("--attempt-limit", type=int, default=60)
    parser.add_argument("--target-lufs", type=float, default=-37.0)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.target_count < 1 or args.attempt_limit < 1:
        raise SystemExit("target-count and attempt-limit must be positive")
    catalogue = read_json(args.catalogue)
    candidates = [
        item for item in catalogue.get("items", [])
        if isinstance(item, dict) and item.get("music_id") and item.get("preview_url")
        and float(item.get("duration_seconds", 0)) >= 30
    ]
    candidates.sort(key=lambda item: (-int(item.get("catalogue_rank", 0)), str(item.get("music_id"))))
    temporary = args.library_root / "临时下载"
    temporary.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    attempted = 0
    for record in candidates:
        existing = ready_ids(args.ready_manifest)
        if len(existing) >= args.target_count or attempted >= args.attempt_limit:
            break
        music_id = str(record["music_id"])
        if music_id in existing:
            continue
        attempted += 1
        source = temporary / f"{music_id}.source"
        try:
            if source.exists():
                source.unlink()
            download(str(record["preview_url"]), source)
            register(record, source, args)
            source.unlink(missing_ok=True)
            events.append({"music_id": music_id, "title": record.get("title"), "status": "READY"})
        except Exception as exc:
            source.unlink(missing_ok=True)
            events.append({"music_id": music_id, "title": record.get("title"), "status": "FAILED", "error": str(exc)[:300]})
    result = {
        "schema": "jianying_bgm_replenish_v1",
        "created_unix": int(time.time()),
        "target_count": args.target_count,
        "ready_count": len(ready_ids(args.ready_manifest)),
        "attempted": attempted,
        "events": events,
        "preview_url_policy": "download then normalize/register; never use preview_url in a finished composition",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ready_count"] >= args.target_count else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
