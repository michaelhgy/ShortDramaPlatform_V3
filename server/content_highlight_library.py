"""剧目级高光库。

高光库保存模型从资料版本中选出的原片短片段及其来源信息。
它只保存可追溯的时间范围和判断信息；正式成片仍从原片读取，不把预览文件当作主素材。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .tool_resolver import resolve_ffmpeg


LIBRARY_ROOT_NAME = "content_highlight_libraries"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(value)).strip(" ._") or "未命名"


def _library_root(data_root: Path) -> Path:
    return data_root / "系统数据" / LIBRARY_ROOT_NAME


def _version_id(drama_id: str, source_fingerprint: str, method_version: str) -> str:
    raw = f"{drama_id}|{source_fingerprint}|{method_version}".encode("utf-8")
    return f"hlv-{hashlib.sha256(raw).hexdigest()[:16]}"


def _highlight_id(version_id: str, start_line: str, end_line: str) -> str:
    raw = f"{version_id}|{start_line}|{end_line}".encode("utf-8")
    return f"hl-{hashlib.sha256(raw).hexdigest()[:16]}"


def build_library_payload(
    *,
    drama_id: str,
    drama_title: str,
    source_fingerprint: str,
    method_version: str,
    lines: list[dict[str, Any]],
    story_map: dict[str, Any],
    inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    """把剧情地图转换成可供 UI 和生产任务引用的高光库版本。

    这里不调用模型，也不猜测高光范围。范围来自模型返回的 start_line/end_line；
    老版本地图没有 end_line 时会标记为 needs_boundary_review，便于人工补边界。
    """
    version_id = _version_id(drama_id, source_fingerprint, method_version)
    line_index = {str(line["id"]): line for line in lines}
    inventory_by_episode = {int(row["episode"]): row for row in inventory}
    items: list[dict[str, Any]] = []
    for rank, raw in enumerate(story_map.get("highlights") or [], 1):
        start_line_id = str(raw.get("start_line") or "")
        end_line_id = str(raw.get("end_line") or start_line_id)
        start_line = line_index.get(start_line_id)
        end_line = line_index.get(end_line_id)
        if not start_line:
            continue
        end_line = end_line or start_line
        episode = int(start_line["episode"])
        source_row = inventory_by_episode.get(episode) or {}
        start_time = max(0.0, float(start_line.get("start") or 0.0) - 0.3)
        end_time = float(end_line.get("end") or start_time) + min(float(end_line.get("pause_after") or 0.0), 0.6)
        duration = max(0.0, end_time - start_time)
        boundary_status = "ready" if raw.get("end_line") else "needs_boundary_review"
        item = {
            "id": _highlight_id(version_id, start_line_id, end_line_id),
            "libraryVersionId": version_id,
            "dramaId": drama_id,
            "dramaTitle": drama_title,
            "analysisVersion": method_version,
            "sourceFingerprint": source_fingerprint,
            "rank": rank,
            "episode": episode,
            "startLine": start_line_id,
            "endLine": end_line_id,
            "startTime": round(start_time, 3),
            "endTime": round(end_time, 3),
            "durationSec": round(duration, 3),
            "sourcePath": str(source_row.get("source") or ""),
            "anchorText": " ".join(str(line_index[line_id].get("text") or "") for line_id in (start_line_id, end_line_id) if line_id in line_index),
            "hookLabel": str(raw.get("hook_label") or ""),
            "conflictId": str(raw.get("conflict_id") or ""),
            "viewerQuestion": str(raw.get("viewer_question") or ""),
            "reason": str(raw.get("reason") or ""),
            "boundaryStatus": boundary_status,
            "status": "candidate",
            "usageCount": 0,
            "previewUrl": f"/api/v3/content-remix/highlights/{_safe_name(drama_id)}/items/{_highlight_id(version_id, start_line_id, end_line_id)}/preview",
            "createdAt": _now(),
        }
        items.append(item)
    return {
        "versionId": version_id,
        "dramaId": drama_id,
        "dramaTitle": drama_title,
        "analysisVersion": method_version,
        "sourceFingerprint": source_fingerprint,
        "createdAt": _now(),
        "items": items,
    }


def save_library(data_root: Path, payload: dict[str, Any]) -> Path:
    path = _library_root(data_root) / _safe_name(str(payload["dramaId"])) / f"{_safe_name(str(payload['versionId']))}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def list_libraries(data_root: Path, drama_id: str) -> list[dict[str, Any]]:
    folder = _library_root(data_root) / _safe_name(drama_id)
    if not folder.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({
            "versionId": payload.get("versionId"),
            "dramaId": payload.get("dramaId"),
            "dramaTitle": payload.get("dramaTitle"),
            "analysisVersion": payload.get("analysisVersion"),
            "sourceFingerprint": payload.get("sourceFingerprint"),
            "createdAt": payload.get("createdAt"),
            "highlightCount": len(payload.get("items") or []),
        })
    return rows


def get_library(data_root: Path, drama_id: str, version_id: str | None = None) -> dict[str, Any] | None:
    folder = _library_root(data_root) / _safe_name(drama_id)
    if not folder.is_dir():
        return None
    if version_id:
        paths = [folder / f"{_safe_name(version_id)}.json"]
    else:
        paths = sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def find_highlight(data_root: Path, drama_id: str, highlight_id: str) -> dict[str, Any] | None:
    """在当前剧目所有资料版本中查找一个稳定的高光 ID。"""
    folder = _library_root(data_root) / _safe_name(drama_id)
    if not folder.is_dir():
        return None
    for path in sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in payload.get("items") or []:
            if str(item.get("id") or "") == highlight_id:
                return item
    return None


def preview_path(data_root: Path, drama_id: str, highlight_id: str) -> Path:
    return data_root / "系统数据" / "content_highlight_previews" / _safe_name(drama_id) / f"{_safe_name(highlight_id)}.mp4"


def ensure_preview(data_root: Path, drama_id: str, highlight_id: str) -> Path:
    """按需从原片生成低分辨率预览；正式成片不使用该预览文件。"""
    item = find_highlight(data_root, drama_id, highlight_id)
    if item is None:
        raise FileNotFoundError("高光不存在")
    source = Path(str(item.get("sourcePath") or ""))
    if not source.is_file():
        raise FileNotFoundError("高光来源原片不存在")
    destination = preview_path(data_root, drama_id, highlight_id)
    if destination.is_file() and destination.stat().st_mtime_ns >= source.stat().st_mtime_ns:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.5, float(item.get("endTime") or 0.0) - float(item.get("startTime") or 0.0))
    command = [
        str(resolve_ffmpeg()), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{float(item.get('startTime') or 0.0):.3f}", "-i", str(source),
        "-t", f"{duration:.3f}", "-vf", "scale=540:-2:force_original_aspect_ratio=decrease",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, check=False)
    if result.returncode != 0 or not destination.is_file():
        destination.unlink(missing_ok=True)
        raise RuntimeError("高光预览生成失败：" + (result.stderr[-500:] or "无输出"))
    return destination

