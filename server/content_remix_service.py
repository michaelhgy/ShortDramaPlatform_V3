"""真实的原剧二创生产任务。

链路：扫描原片 → 本地识别（按剧缓存，跨任务复用）→ 整理材料 → 剧情地图（一次模型调用，按剧缓存）
→ 本地组合候选 → 逐条复核（小调用）→ FFmpeg 合成并叠加通版模板 → 完整解码检查 → 写入成片目录。

方法与提示词在 remix_planner.py；材料整理在 remix_materials.py。
任务状态保存在系统数据目录，前端只读取状态。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import remix_planner as planner
from .content_highlight_library import build_library_payload, save_library
from .content_template_renderer import render_overlay
from .gpt_relay import generate_json, get_config
from .remix_materials import build_lines
from .tool_resolver import resolve_ffmpeg, resolve_ffprobe


TEMPLATE_RENDERER_IDS = {
    "tpl-mumu-original": "mumu-original",
    "tpl-mumu-blue": "mumu-blue",
    "tpl-mumu-cyan": "mumu-cyan",
    "tpl-mumu-red": "mumu-red",
}
CANVAS = (1080, 1920)
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "huggingface" / "hub" / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
REVIEWS_PER_CLIP = 3  # 每要一条成片最多复核几个候选，防止失控调用
_LOCK = threading.RLock()
_THREADS: dict[str, threading.Thread] = {}
_ASR_MODEL: Any = None


# ---------------------------------------------------------------------------
# 路径与任务记录
# ---------------------------------------------------------------------------

def _data_root() -> Path:
    from . import v2_file_service
    if v2_file_service.DATA_ROOT is None:
        raise RuntimeError("需要先配置数据盘")
    return Path(v2_file_service.DATA_ROOT)


def _output_root() -> Path:
    """Resolve the user-configured root for finished remix videos."""
    from . import v2_file_service
    settings = v2_file_service.get_v2_settings()
    configured = str(settings.get("content_remix_output_root") or r"Z:\05短剧二创").strip()
    return Path(configured).expanduser()


def _runs_root() -> Path:
    root = _data_root() / "系统数据" / "content_remix_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(text)).strip(" ._") or "未命名"


def _drama_cache_dir(kind: str, title: str) -> Path:
    path = _data_root() / "内容资产" / kind / _safe_name(title)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_dir(run_id: str) -> Path:
    return _runs_root() / run_id


def _run_path(run_id: str) -> Path:
    return _run_dir(run_id) / "run.json"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _save(run: dict[str, Any]) -> None:
    _write_json(_run_path(str(run["id"])), run)


def _load(run_id: str) -> dict[str, Any] | None:
    path = _run_path(run_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _mark_interrupted(run: dict[str, Any]) -> dict[str, Any]:
    """程序重启后，没有后台线程的"执行中"任务改为失败，避免永远显示执行中。"""
    if run.get("status") in ("queued", "running") and run.get("id") not in _THREADS:
        run["status"] = "failed"
        run["error"] = "软件重启或异常退出，任务已中断。识别结果和剧情地图已保存，重新发起同一部剧会直接复用。"
        run["finishedAt"] = run.get("finishedAt") or _now()
        for step in run.get("pipelineSteps", []):
            if step.get("status") == "running":
                step["status"] = "failed"
                step["errorReason"] = run["error"]
        _save(run)
    return run


def list_runs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _runs_root().glob("*/run.json"):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        with _LOCK:
            rows.append(_mark_interrupted(run))
    return sorted(rows, key=lambda item: str(item.get("createdAt", "")), reverse=True)


def get_run(run_id: str) -> dict[str, Any]:
    with _LOCK:
        run = _load(run_id)
        if run is None:
            raise ValueError("二创任务不存在")
        return _mark_interrupted(run)


def _update(run_id: str, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        run = _load(run_id)
        if run is None:
            raise RuntimeError("任务记录不存在")
        run.update(fields)
        _save(run)
        return run


def _set_stage(run_id: str, stage: str, detail: str, *, status: str = "running") -> None:
    with _LOCK:
        run = _load(run_id)
        if run is None:
            raise RuntimeError("任务记录不存在")
        run["status"] = "running"
        for item in run["pipelineSteps"]:
            if item["key"] == stage:
                item["status"] = status
                item["detailText"] = detail
                item["durationText"] = "执行中" if status == "running" else "已完成" if status == "completed" else item.get("durationText", "")
        _save(run)


# ---------------------------------------------------------------------------
# 原片扫描与本地识别
# ---------------------------------------------------------------------------

def _probe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [str(resolve_ffprobe()), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"无法读取视频：{path.name}")
    data = json.loads(result.stdout)
    video = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), None)
    audio = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise RuntimeError(f"视频缺少画面或声音：{path.name}")
    return {
        "duration": float(data["format"]["duration"]),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": str(video.get("avg_frame_rate") or ""),
        "source": str(path.resolve()),
        "size": path.stat().st_size,
        "mtime": int(path.stat().st_mtime),
    }


def _scan(source_dir: Path) -> list[dict[str, Any]]:
    files = sorted(
        (path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() == ".mp4"),
        key=lambda path: [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)],
    )
    if not files:
        raise ValueError("原剧目录中没有 MP4 原片")
    return [{"episode": episode, **_probe(path)} for episode, path in enumerate(files, 1)]


def _asr_model_path() -> Path:
    configured = os.environ.get("SHORT_DRAMA_ASR_MODEL")
    if configured:
        return Path(configured)
    snapshots = DEFAULT_MODEL_DIR / "snapshots"
    if snapshots.is_dir():
        found = sorted((p for p in snapshots.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        if found:
            return found[0]
    return DEFAULT_MODEL_DIR


def _load_asr_model(device: str) -> Any:
    model_path = _asr_model_path()
    if not model_path.is_dir():
        raise RuntimeError(f"未找到本地语音识别模型：{model_path}")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from faster_whisper import WhisperModel
    if device == "cuda":
        return WhisperModel(str(model_path), device="cuda", compute_type="float16", local_files_only=True)
    return WhisperModel(str(model_path), device="cpu", compute_type="int8", local_files_only=True)


def _transcribe(row: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    """同一部剧的识别结果按集缓存在内容资产目录，跨任务复用；原片变化时重新识别。"""
    global _ASR_MODEL
    destination = cache_dir / f"ep{int(row['episode']):03d}.json"
    identity = {"source": row["source"], "size": row["size"], "mtime": row["mtime"]}
    if destination.is_file():
        try:
            cached = json.loads(destination.read_text(encoding="utf-8"))
            if cached.get("identity") == identity:
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    if _ASR_MODEL is None:
        try:
            _ASR_MODEL = _load_asr_model("cuda")
        except Exception:
            _ASR_MODEL = _load_asr_model("cpu")
    options = dict(language="zh", beam_size=5, vad_filter=True, condition_on_previous_text=False)
    try:
        segment_iter, info = _ASR_MODEL.transcribe(row["source"], **options)
        segments = list(segment_iter)
    except Exception:
        # 部分 Windows 环境能创建 CUDA 模型但首次调用 cuBLAS 失败，改用 CPU 继续。
        _ASR_MODEL = _load_asr_model("cpu")
        segment_iter, info = _ASR_MODEL.transcribe(row["source"], **options)
        segments = list(segment_iter)
    payload = {
        "identity": identity,
        "episode": int(row["episode"]),
        "duration": float(info.duration),
        "provider": "local_faster_whisper",
        "segments": [
            {"start": float(s.start), "end": float(s.end), "text": str(s.text).strip()}
            for s in segments if str(s.text).strip()
        ],
    }
    _write_json(destination, payload)
    return payload


# ---------------------------------------------------------------------------
# 模型调用（记录每次用量）
# ---------------------------------------------------------------------------

def _model_caller(run_id: str):
    routes = (get_config() or {}).get("model_routes") or {}

    def call(task_role: str, prompt: str, schema: dict[str, Any], schema_name: str) -> dict[str, Any]:
        model = routes.get(task_role) or routes.get("highlight") or ""
        if not model:
            raise RuntimeError("系统设置里还没有为「高光判断」分配模型，请先到系统设置 → GPT中转 选择模型")
        result = generate_json({
            "task_role": task_role, "model": model, "prompt": prompt, "schema": schema,
            "schema_name": schema_name,
            "reasoning_effort": "low" if task_role in ("highlight", "skippable") else "medium",
            "timeout_s": 600 if task_role in ("highlight", "skippable") else 180,
            "max_output_tokens": 6000 if task_role in ("highlight", "skippable") else 1200,
        })
        with _LOCK:
            run = _load(run_id)
            if run is not None:
                run.setdefault("modelCalls", []).append({
                    "taskRole": task_role, "model": result.get("model"), "usage": result.get("usage") or {},
                    "elapsedS": result.get("elapsed_s"), "createdAt": _now(),
                })
                _save(run)
        return result

    return call


def _story_map_for(drama_title: str, lines: list[dict[str, Any]], call, *, include_skippable: bool = True, chunked: bool = False) -> tuple[dict[str, Any], bool]:
    """同一部剧、同样的台词、同一版方法，只生成一次剧情地图。返回 (地图, 是否复用)。"""
    fingerprint = hashlib.sha256(json.dumps(
        [(line["id"], line["text"]) for line in lines], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    path = _drama_cache_dir("剧情地图", drama_title) / f"{planner.METHOD_VERSION}_{fingerprint}.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8")), True
        except (OSError, json.JSONDecodeError):
            pass
    story_map = (
        planner.build_story_map_chunked(lines, call, include_skippable=include_skippable)
        if chunked
        else planner.build_story_map(lines, call, include_skippable=include_skippable)
    )
    story_map["fingerprint"] = fingerprint
    story_map["createdAt"] = _now()
    _write_json(path, story_map)
    return story_map, False


# ---------------------------------------------------------------------------
# 合成
# ---------------------------------------------------------------------------

def _render_clip(segments: list[dict[str, Any]], output_path: Path, overlay_path: Path) -> None:
    """按比例缩放并补边到 1080×1920，不裁切画面，保证原片字幕完整；叠加通版模板。"""
    width, height = CANVAS
    ffmpeg = str(resolve_ffmpeg())
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y"]
    filters: list[str] = []
    labels: list[str] = []
    for index, part in enumerate(segments):
        duration = part["end"] - part["start"]
        command += ["-ss", f"{part['start']:.3f}", "-t", f"{duration:.3f}", "-i", part["source"]]
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
        filters.append(
            f"[{index}:a]aresample=48000:async=1:first_pts=0,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]"
        )
        labels.extend([f"[v{index}]", f"[a{index}]"])
    filters.append("".join(labels) + f"concat=n={len(segments)}:v=1:a=1[basev][basea]")
    overlay_index = len(segments)
    command += ["-loop", "1", "-i", str(overlay_path)]
    filters.append(f"[{overlay_index}:v]format=rgba,scale={width}:{height}[tpl]")
    filters.append("[basev][tpl]overlay=0:0:shortest=1,format=yuv420p[outv]")
    command += ["-filter_complex", ";".join(filters), "-map", "[outv]", "-map", "[basea]",
                "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "22", "-b:v", "0",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output_path)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        start = command.index("-c:v")
        end = command.index("-c:a", start)
        command[start:end] = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        raise RuntimeError("FFmpeg 合成失败：" + (result.stderr[-800:] or "无输出"))
    verify = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-i", str(output_path), "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if verify.returncode != 0:
        raise RuntimeError(f"成片完整解码失败：{verify.stderr[-600:]}")
    metadata = _probe(output_path)
    if (metadata["width"], metadata["height"]) != CANVAS:
        raise RuntimeError(f"成片画布不是 1080×1920：{metadata['width']}×{metadata['height']}")
    planned = sum(part["end"] - part["start"] for part in segments)
    if abs(metadata["duration"] - planned) > 2.0:
        raise RuntimeError(f"成片时长 {metadata['duration']:.1f} 秒与计划 {planned:.1f} 秒不一致")


def _fmt_time(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _result_row(run: dict[str, Any], run_id: str, index: int, plan: dict[str, Any], output: Path) -> dict[str, Any]:
    segments = plan["segments"]
    jumps = []
    elapsed = 0.0
    for a, b in zip(segments, segments[1:]):
        elapsed += a["end"] - a["start"]
        if not (a["episode"] == b["episode"] - 1 and b["start"] < 3.0) and not (a["episode"] == b["episode"] and abs(a["end"] - b["start"]) < 0.1):
            jumps.append(f"{_fmt_time(elapsed)} 第{a['episode']:03d}集 → 第{b['episode']:03d}集")
    highlight = plan["highlight"]
    duration = plan["duration"]
    return {
        "id": f"res-{run_id}-{index}", "jobId": run_id, "videoName": output.name,
        "dramaId": run["dramaId"], "dramaTitle": run["dramaTitle"],
        "durationSec": round(duration, 3), "durationFormatted": f"{int(duration // 60):02d}分{int(duration % 60):02d}秒",
        "episodeRange": f"第{segments[0]['episode']:03d}集 ~ 第{segments[-1]['episode']:03d}集",
        "highlightCutPoint": f"第{segments[0]['episode']:03d}集 {segments[0]['start']:.1f}s {highlight.get('hook_label', '')}",
        "highlightId": highlight.get("highlight_id") or "",
        "jumpCutPositions": jumps if plan["mode"] == "jump" else [],
        "playStrategy": "连续播放" if plan["mode"] == "continuous" else "跳集播放",
        "endType": plan["end_type"],
        "templateId": run["templateId"], "templateVersion": run["templateVersion"], "filePath": str(output),
        "techStatus": "合格", "techReport": "完整解码通过 · 1080×1920 · 原声原字幕保留",
        "manualStatus": "待审核",
        "sourceReasoning": f"开头：{highlight.get('reason', '')}｜观众想知道：{highlight.get('viewer_question', '')}｜结尾（{plan['end_type']}）：{plan['end'].get('reason', '')}",
        "previewHue": "from-indigo-950 via-slate-900 to-purple-950", "createdAt": _now(),
    }


# ---------------------------------------------------------------------------
# 后台任务
# ---------------------------------------------------------------------------

def _worker(run_id: str) -> None:
    try:
        _run_pipeline(run_id)
    except Exception as exc:  # noqa: BLE001
        with _LOCK:
            current = _load(run_id)
            if current is not None:
                current["status"] = "failed"
                current["error"] = str(exc)
                current["finishedAt"] = _now()
                for item in current["pipelineSteps"]:
                    if item["status"] == "running":
                        item["status"] = "failed"
                        item["errorReason"] = str(exc)
                _save(current)
    finally:
        _THREADS.pop(run_id, None)


def _run_pipeline(run_id: str) -> None:
    run = get_run(run_id)
    work = _run_dir(run_id)
    title = run["dramaTitle"]

    _set_stage(run_id, "scan_raw", "正在扫描原剧 MP4 并读取时长")
    inventory = _scan(Path(run["sourceDirectory"]))
    _write_json(work / "inventory.json", inventory)
    _update(run_id, totalSourceEpisodes=len(inventory), sourceFilesStatus=f"{len(inventory)}/{len(inventory)}集可用")
    _set_stage(run_id, "scan_raw", f"已扫描 {len(inventory)} 集原片", status="completed")

    _set_stage(run_id, "local_recognize", "正在本地识别对白（同一部剧已识别过的集直接复用）")
    asr_dir = _drama_cache_dir("识别缓存", title)
    transcripts = []
    for row in inventory:
        _set_stage(run_id, "local_recognize", f"本地识别第 {row['episode']}/{len(inventory)} 集")
        transcripts.append(_transcribe(row, asr_dir))
    lines = build_lines(transcripts)
    if len(lines) < 20:
        raise RuntimeError("识别到的台词太少，无法判断剧情（请确认原片有对白声音）")
    _set_stage(run_id, "local_recognize", f"完成 {len(inventory)} 集本地识别，整理出 {len(lines)} 句台词", status="completed")

    call = _model_caller(run_id)
    counts = run.get("strategyCounts") or {}
    _set_stage(run_id, "highlight_judge", "模型正在通读全剧，生成剧情地图（高光起点、结束点、可跳过段）")
    story_map, reused = _story_map_for(
        title,
        lines,
        call,
        include_skippable=int(counts.get("跳集播放", 0) or 0) > 0,
        chunked=True,
    )
    _write_json(work / "story_map.json", story_map)
    if not story_map["highlights"]:
        raise RuntimeError("模型没有找到合格的高光起点：" + "；".join(story_map.get("rejected", [])[:5]))

    # 将本次资料分析物化为剧目级高光库。高光库只保存原片范围和判断信息，
    # 正式成片仍直接从原片切，避免每次生产都重新寻找高光。
    library = build_library_payload(
        drama_id=str(run["dramaId"]),
        drama_title=title,
        source_fingerprint=str(story_map.get("fingerprint") or ""),
        method_version=str(story_map.get("method_version") or planner.METHOD_VERSION),
        lines=lines,
        story_map=story_map,
        inventory=inventory,
    )
    save_library(_data_root(), library)
    library_ids = {
        (str(item.get("startLine") or ""), str(item.get("endLine") or "")): str(item.get("id") or "")
        for item in library.get("items") or []
    }
    for highlight in story_map.get("highlights") or []:
        key = (str(highlight.get("start_line") or ""), str(highlight.get("end_line") or highlight.get("start_line") or ""))
        highlight["highlight_id"] = library_ids.get(key, "")
    _write_json(work / "highlight_library.json", library)
    _update(run_id, highlightLibraryVersion=library.get("versionId"), highlightCount=len(library.get("items") or []))

    requested_highlights = [str(item).strip() for item in (run.get("highlightIds") or []) if str(item).strip()]
    if requested_highlights:
        available = {str(item.get("id")): item for item in library.get("items") or []}
        missing = [item for item in requested_highlights if item not in available]
        if missing:
            raise RuntimeError("所选高光不属于本次资料版本：" + "、".join(missing[:5]))
        selected_ids = set(requested_highlights)
        story_map["highlights"] = [item for item in story_map["highlights"] if item.get("highlight_id") in selected_ids]
        if not story_map["highlights"]:
            raise RuntimeError("所选高光没有可用于本次生产的片段")
    _write_json(work / "story_map.json", story_map)
    _set_stage(run_id, "highlight_judge",
               f"{'复用已有剧情地图' if reused else '剧情地图已生成'}：{len(story_map['highlights'])} 个高光起点、"
               f"{len(story_map['end_points'])} 个结束点、{len(story_map['skippable'])} 个可跳过段",
               status="completed")

    _set_stage(run_id, "continuity_plan", "正在组合方案并逐条复核开头、跳点和结尾")
    timeline = planner.Timeline(lines, inventory)
    minimum = float(run["durationRangeMin"][0]) * 60
    maximum = float(run["durationRangeMin"][1]) * 60
    plans: list[dict[str, Any]] = []
    notes: list[str] = []
    for mode, label in (("continuous", "连续播放"), ("jump", "跳集播放")):
        count = int(counts.get(label, 0))
        if count <= 0:
            continue
        candidates = planner.build_candidates(story_map, timeline, mode, minimum, maximum, seed=len(plans))
        candidates = [c for c in candidates if all(planner._overlap(c["segments"], p["segments"]) <= 0.8 for p in plans)]
        chosen, rejected = planner.pick_with_review(
            candidates, count, lambda c: planner.review_candidate(c, timeline, call), max_reviews=count * REVIEWS_PER_CLIP)
        plans.extend(chosen)
        if len(chosen) < count:
            notes.append(f"{label}要求 {count} 条，只组合出 {len(chosen)} 条合格方案（候选 {len(candidates)} 个，复核淘汰 {len(rejected)} 个）")
        _write_json(work / f"plans_{mode}.json", {"chosen": chosen, "rejected": rejected})
    if not plans:
        raise RuntimeError("没有组合出合格方案。" + "；".join(notes))
    _update(run_id, planNotes=notes)
    _set_stage(run_id, "continuity_plan", f"复核通过 {len(plans)} 条方案" + (f"（{'；'.join(notes)}）" if notes else ""), status="completed")

    renderer_id = str(run.get("rendererTemplateId") or TEMPLATE_RENDERER_IDS.get(run["templateId"], "mumu-original"))
    overlay_path = work / "template_overlay.png"
    render_overlay(renderer_id, title, overlay_path, canvas=CANVAS)
    output_root = _output_root() / _safe_name(title)
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for index, plan in enumerate(plans, 1):
        _set_stage(run_id, "video_synthesize", f"正在合成第 {index}/{len(plans)} 条")
        label = _safe_name(str(plan["highlight"].get("hook_label") or f"高光{index}"))[:30]
        mode_text = "连续" if plan["mode"] == "continuous" else "跳集"
        output = output_root / f"{run['jobCode']}_{index:02d}_{label}_{mode_text}_{plan['end_type']}.mp4"
        try:
            _render_clip(plan["segments"], output, overlay_path)
        except Exception as exc:  # noqa: BLE001 一条失败不影响其他条
            failures.append(f"第{index}条：{exc}")
            continue
        results.append(_result_row(run, run_id, index, plan, output))
        _update(run_id, results=results)
    if not results:
        raise RuntimeError("所有成片合成失败：" + "；".join(failures)[:600])
    _set_stage(run_id, "video_synthesize", f"已生成 {len(results)} 条 MP4" + (f"，{len(failures)} 条失败" if failures else ""), status="completed")
    _set_stage(run_id, "tech_inspect", "每条成片已完成完整解码、画布和时长检查", status="completed")
    _set_stage(run_id, "auto_ingest", f"成片已保存到 {output_root}", status="completed")
    _update(run_id, status="completed", finishedAt=_now(), synthFailures=failures)


def start_run(payload: dict[str, Any]) -> dict[str, Any]:
    source = Path(str(payload.get("source_directory") or "")).expanduser()
    if not source.is_dir():
        raise ValueError("原剧目录不存在")
    template_id = str(payload.get("template_id") or "")
    if template_id not in TEMPLATE_RENDERER_IDS:
        raise ValueError("模板编号无效")
    counts = payload.get("strategy_counts") if isinstance(payload.get("strategy_counts"), dict) else {}
    counts = {key: max(0, int(counts.get(key, 0) or 0)) for key in ("连续播放", "跳集播放")}
    if sum(counts.values()) <= 0:
        raise ValueError("至少选择一种生成方式并设置数量")
    if sum(counts.values()) > 30:
        raise ValueError("单次最多生成 30 条")
    duration = payload.get("duration_range_min") or [5, 10]
    if len(duration) != 2 or float(duration[0]) <= 0 or float(duration[1]) < float(duration[0]):
        raise ValueError("时长范围无效")
    run_id = uuid.uuid4().hex
    job_code = f"RMX-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{run_id[:4]}"
    run = {
        "id": run_id, "jobCode": job_code, "dramaId": str(payload.get("drama_id") or source.name),
        "dramaTitle": str(payload.get("drama_title") or source.name), "sourceDirectory": str(source.resolve()),
        "totalSourceEpisodes": 0, "sourceFilesStatus": "等待扫描", "templateId": template_id,
        "templateName": str(payload.get("template_name") or template_id), "templateVersion": str(payload.get("template_version") or "mumu-v1.0"),
        "rendererTemplateId": TEMPLATE_RENDERER_IDS[template_id],
        "playStrategy": "连续播放" if counts["连续播放"] else "跳集播放",
        "playStrategies": [key for key, value in counts.items() if value > 0], "strategyCounts": counts,
        "durationRangeMin": [float(duration[0]), float(duration[1])], "targetCount": sum(counts.values()),
        "methodVersion": planner.METHOD_VERSION,
        "modelId": str(payload.get("model_id") or ""), "modelAssignments": payload.get("model_assignments") or {},
        "productionPurpose": str(payload.get("production_purpose") or "首轮覆盖"),
        "highlightIds": [str(item).strip() for item in (payload.get("highlight_ids") or []) if str(item).strip()],
        "highlightLibraryVersion": str(payload.get("highlight_library_version") or ""),
        "modelCalls": [],
        "status": "queued", "createdAt": _now(), "results": [],
        "pipelineSteps": [
            {"key": "scan_raw", "label": "扫描原片", "status": "pending", "durationText": "等待执行", "detailText": "等待扫描原剧 MP4"},
            {"key": "local_recognize", "label": "本地识别", "status": "pending", "durationText": "等待执行", "detailText": "等待本地识别对白"},
            {"key": "highlight_judge", "label": "剧情地图", "status": "pending", "durationText": "等待执行", "detailText": "等待模型通读全剧"},
            {"key": "continuity_plan", "label": "组合与复核", "status": "pending", "durationText": "等待执行", "detailText": "等待组合方案"},
            {"key": "video_synthesize", "label": "视频合成", "status": "pending", "durationText": "等待执行", "detailText": "等待 FFmpeg"},
            {"key": "tech_inspect", "label": "技术检查", "status": "pending", "durationText": "等待执行", "detailText": "等待完整解码检查"},
            {"key": "auto_ingest", "label": "保存成片", "status": "pending", "durationText": "等待执行", "detailText": "等待写入成片目录"},
        ],
    }
    with _LOCK:
        _save(run)
        thread = threading.Thread(target=_worker, args=(run_id,), daemon=True, name=f"v3-content-remix-{run_id[:8]}")
        _THREADS[run_id] = thread
        thread.start()
    return run
