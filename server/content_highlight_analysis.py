"""异步生成剧目高光库的资料分析任务。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import remix_planner as planner
from .content_highlight_library import build_library_payload, save_library
from .content_remix_service import _asr_model_path, _data_root, _drama_cache_dir, _model_caller, _scan, _transcribe
from .remix_materials import build_lines

_LOCK = threading.RLock()
_THREADS: dict[str, threading.Thread] = {}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _root() -> Path:
    root = _data_root() / "content_highlight_analysis_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path(run_id: str) -> Path:
    return _root() / run_id / "run.json"


def _write(run: dict[str, Any]) -> None:
    path = _path(str(run["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load(run_id: str) -> dict[str, Any] | None:
    path = _path(run_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_run(run_id: str) -> dict[str, Any]:
    with _LOCK:
        run = _load(run_id)
        if run is None:
            raise ValueError("高光资料任务不存在")
        return run


def _update(run_id: str, **fields: Any) -> None:
    with _LOCK:
        run = _load(run_id)
        if run is None:
            return
        run.update(fields)
        _write(run)


def _worker(run_id: str) -> None:
    try:
        run = get_run(run_id)
        source = Path(run["sourceDirectory"])
        _update(run_id, status="running", stage="scan_raw", detail="正在扫描原片")
        inventory = _scan(source)
        _update(run_id, totalEpisodes=len(inventory), stage="local_recognize", detail="正在复用或生成本地转写")
        cache_dir = _drama_cache_dir("识别缓存", run["dramaTitle"])
        transcripts = [_transcribe(row, cache_dir) for row in inventory]
        lines = build_lines(transcripts)
        if len(lines) < 20:
            raise RuntimeError("识别到的台词太少，无法判断高光")
        _update(run_id, lineCount=len(lines), stage="highlight_judge", detail="正在分段提取高光并全局去重")
        story_map = planner.build_story_map_chunked(lines, _model_caller(run_id), include_skippable=False)
        if not story_map.get("highlights"):
            raise RuntimeError("模型没有找到合格高光：" + "；".join(story_map.get("rejected", [])[:5]))
        fingerprint = __import__("hashlib").sha256(
            json.dumps([(line["id"], line["text"]) for line in lines], ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
        story_map["fingerprint"] = fingerprint
        story_map["createdAt"] = _now()
        library = build_library_payload(
            drama_id=run["dramaId"], drama_title=run["dramaTitle"],
            source_fingerprint=fingerprint, method_version=planner.METHOD_VERSION,
            lines=lines, story_map=story_map, inventory=inventory,
        )
        save_library(_data_root(), library)
        _update(
            run_id, status="completed", stage="completed", detail="高光库已生成",
            finishedAt=_now(), libraryVersionId=library["versionId"], highlightCount=len(library.get("items") or []),
        )
    except Exception as exc:  # noqa: BLE001
        _update(run_id, status="failed", stage="failed", detail=str(exc), error=str(exc), finishedAt=_now())
    finally:
        _THREADS.pop(run_id, None)


def start(payload: dict[str, Any]) -> dict[str, Any]:
    source = Path(str(payload.get("source_directory") or "")).expanduser()
    if not source.is_dir():
        raise ValueError("原剧目录不存在")
    if not str(payload.get("drama_id") or "").strip():
        raise ValueError("缺少剧目 ID")
    run_id = uuid.uuid4().hex
    run = {
        "id": run_id,
        "dramaId": str(payload.get("drama_id")),
        "dramaTitle": str(payload.get("drama_title") or source.name),
        "sourceDirectory": str(source.resolve()),
        "status": "queued",
        "stage": "queued",
        "detail": "等待执行",
        "createdAt": _now(),
        "totalEpisodes": 0,
        "lineCount": 0,
        "highlightCount": 0,
        "asrModelAvailable": _asr_model_path().is_dir(),
    }
    with _LOCK:
        _write(run)
        thread = threading.Thread(target=_worker, args=(run_id,), daemon=True, name=f"v3-highlight-analysis-{run_id[:8]}")
        _THREADS[run_id] = thread
        thread.start()
    return run

