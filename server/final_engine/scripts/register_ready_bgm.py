from __future__ import annotations

"""Normalize one authorised local BGM file and register it for routine use."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def duration_seconds(path: Path) -> float:
    output = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        text=True,
        encoding="utf-8",
    )
    return float(json.loads(output)["format"]["duration"])


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement keeps a concurrently starting batch from ever reading
    # a half-written manifest while the automatic replenisher is adding music.
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="登记已验证的本地 BGM")
    parser.add_argument("--source", required=True, type=Path, help="用户已通过剪映正常取得的本地音频")
    parser.add_argument("--music-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--library-root", required=True, type=Path)
    parser.add_argument("--ready-manifest", required=True, type=Path)
    parser.add_argument("--target-lufs", type=float, default=-37.0)
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"音频不存在：{source}")
    output = args.library_root.resolve() / "本地音频" / f"{args.music_id}.m4a"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-i", str(source), "-vn",
        "-af", f"loudnorm=I={args.target_lufs}:TP=-2.0:LRA=7.0",
        "-c:a", "aac", "-b:a", "128k", str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(f"BGM 归一化失败：{completed.stderr[-1200:]}")
    record = {
        "music_id": str(args.music_id),
        "title": args.title,
        "author": args.author,
        "status": "ready",
        "relative_audio_path": output.relative_to(args.library_root.resolve()).as_posix(),
        "sha256": sha256_file(output),
        "duration_seconds": round(duration_seconds(output), 3),
        "target_integrated_lufs": args.target_lufs,
        "jianying_clip_volume": 1.0,
        "registered_at_utc": datetime.now(UTC).isoformat(),
    }
    manifest = {"version": 1, "items": []}
    if args.ready_manifest.is_file():
        manifest = json.loads(args.ready_manifest.read_text(encoding="utf-8-sig"))
    items = [item for item in manifest.get("items", []) if str(item.get("music_id")) != record["music_id"]]
    items.append(record)
    manifest["items"] = sorted(items, key=lambda item: str(item["music_id"]))
    write_json(args.ready_manifest, manifest)
    print(json.dumps({"status": "READY", "music_id": record["music_id"], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
