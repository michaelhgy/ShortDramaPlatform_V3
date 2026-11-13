"""V3 原片下载共用的逐集对账和视频检查；不操作手机或业务数据库。"""
from __future__ import annotations
import json
import re
import subprocess
import time
from pathlib import Path


class VideoValidationError(RuntimeError):
    pass


def episode_number(value) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def title_episode(title: str) -> int | None:
    match = re.search(r"第\s*(\d+)\s*集", title or "")
    return int(match.group(1)) if match else None


def fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def probe_video(path: Path, *, executable=None, cancelled=lambda: False, timeout=30) -> dict:
    if not path.is_file() or path.stat().st_size < 100_000:
        raise VideoValidationError("视频不存在或文件过小")
    if executable is None:
        from server.tool_resolver import resolve_ffprobe
        executable = resolve_ffprobe()
    process = subprocess.Popen([str(executable), "-v", "error", "-show_entries",
        "format=duration:stream=codec_type", "-of", "json", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancelled():
                raise InterruptedError("已停止视频检查")
            if time.monotonic() >= deadline:
                raise TimeoutError("视频检查超时")
            try:
                output, error = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise VideoValidationError("视频容器无法读取")
        data = json.loads(output.decode("utf-8"))
        duration = float(data.get("format", {}).get("duration") or 0)
        if duration <= 0 or not any(row.get("codec_type") == "video" for row in data.get("streams", [])):
            raise VideoValidationError("视频缺少有效画面轨道或时长")
        return {**fingerprint(path), "duration": duration}
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def receipt_matches(record: dict, path: Path, link: str) -> bool:
    """只复用相同链接、确认过集数且文件未变化的成果。"""
    try:
        return bool(record.get("verified") and record.get("status") == "ok"
            and Path(str(record.get("file") or "")).resolve() == path.resolve() and record.get("link") == link
            and record.get("confirmation_source") in {"parser", "phone"}
            and all(record.get(key) == value for key, value in fingerprint(path).items()))
    except OSError:
        return False


def reconcile(expected: int, records: dict, files: list[Path]) -> dict:
    """完成以集号集合和每集有效凭据为准，未知总数绝不宣告整剧完成。"""
    by_episode: dict[int, list[Path]] = {}
    for path in files:
        number = title_episode(path.stem)
        if number:
            by_episode.setdefault(number, []).append(path)
    verified = []
    unconfirmed = []
    for number, paths in by_episode.items():
        record = records.get(str(number), {})
        if len(paths) == 1 and receipt_matches(record, paths[0], str(record.get("link") or "")):
            verified.append(number)
        else:
            unconfirmed.append(number)
    wanted = set(range(1, expected + 1)) if expected > 0 else set()
    return {"complete": bool(wanted) and wanted <= set(verified),
        "verified_episodes": sorted(verified), "verified_count": len(verified),
        "missing_video_episodes": sorted(wanted - set(verified)),
        "unconfirmed_video_episodes": sorted(unconfirmed),
        "duplicate_video_episodes": sorted(n for n, paths in by_episode.items() if len(paths) > 1),
        "expected_count": expected, "downloaded_file_count": len(files)}
