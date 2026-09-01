#!/usr/bin/env python3
"""Find the short opening-cover cut point with local CV + local Ollama vision.

This tool never changes a source video.  It writes a report and a small set of
opening thumbnails so a rule can be validated before the final composer uses a
cut point.  Routine inference is entirely local and uses no cloud-model token.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from .ollama_local import VISION_CONTEXT_TOKENS, request_chat
except ImportError:  # Direct execution keeps the script directory on sys.path.
    from ollama_local import VISION_CONTEXT_TOKENS, request_chat


DEFAULT_MODEL = "qwen2.5vl:7b"


@dataclass
class Frame:
    index: int
    time_seconds: float
    path: str
    scene_score_from_previous: float = 0.0


def safe_json(value: Any) -> str:
    # ASCII JSON keeps reports parseable even when an invoking shell uses a
    # legacy Windows code page for a Chinese source filename.
    return json.dumps(value, ensure_ascii=True, indent=2)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "是"}


def image_difference(previous: np.ndarray, current: np.ndarray) -> float:
    """A simple 0..1 scene-change score; VLM makes the semantic decision."""
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    mad = float(np.mean(cv2.absdiff(previous_gray, current_gray))) / 255.0
    previous_hist = cv2.calcHist([previous_gray], [0], None, [32], [0, 256])
    current_hist = cv2.calcHist([current_gray], [0], None, [32], [0, 256])
    hist_distance = min(1.0, max(0.0, 1.0 - float(cv2.compareHist(previous_hist, current_hist, cv2.HISTCMP_CORREL))))
    return round(min(1.0, 0.65 * mad + 0.35 * hist_distance), 5)


def read_opening_frames(video: Path, evidence_dir: Path, seconds: float, sample_fps: float) -> tuple[list[Frame], dict[str, float]]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot decode video: {video}")
    native_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    duration = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0) / native_fps if native_fps else 0.0
    sample_count = max(2, int(round(seconds * sample_fps)))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Frame] = []
    previous_image: np.ndarray | None = None
    for index in range(sample_count):
        timestamp = index / sample_fps
        if duration and timestamp >= duration:
            break
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, image = capture.read()
        if not ok or image is None:
            continue
        height, width = image.shape[:2]
        if width > 480:
            resized_height = max(2, round(height * 480 / width))
            image = cv2.resize(image, (480, resized_height), interpolation=cv2.INTER_AREA)
        score = image_difference(previous_image, image) if previous_image is not None else 0.0
        output = evidence_dir / f"frame_{index:03d}_{timestamp:05.2f}s.jpg"
        encoded_ok, encoded_image = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not encoded_ok:
            raise RuntimeError(f"Cannot write evidence image: {output}")
        # cv2.imwrite does not reliably support Chinese Windows paths.
        output.write_bytes(encoded_image.tobytes())
        frames.append(Frame(index=index, time_seconds=round(timestamp, 3), path=str(output), scene_score_from_previous=score))
        previous_image = image
    capture.release()
    if len(frames) < 4:
        raise RuntimeError("Too few opening frames decoded")
    return frames, {"native_fps": native_fps, "duration_seconds": round(duration, 3)}


def image_as_base64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def extract_json(text: str) -> dict[str, Any]:
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict):
            return candidate
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"Model did not return JSON: {text[:300]}")


def ask_local_vision(model: str, selected: list[Frame]) -> dict[str, Any]:
    prompt = """你在判断短剧爆款视频的开头切点。下面四张图按时间顺序排列：前两张在候选切点之前，后两张在候选切点之后。
“封面”指开头一闪而过的剧名海报、宣传卡、标题卡或非剧情首帧；“剧情”指真实剧情开始的画面。
只输出一个 JSON 对象，不要 markdown：
{"pre_is_cover":true或false,"pre_is_plot":true或false,"post_is_plot":true或false,"confidence":0到100整数,"reason":"不超过30字"}
只有独立的海报、宣传卡、标题卡才是封面。画面已经在演剧情、仅顶部有常驻剧名或人物在走动，都不是封面。
如果前两张是封面、后两张是剧情，则 post_is_plot 必须为 true。不要因为人物静止就把剧情误认为封面。"""
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 180, "num_ctx": VISION_CONTEXT_TOKENS},
        "messages": [{"role": "user", "content": prompt, "images": [image_as_base64(frame.path) for frame in selected]}],
    }
    response_payload = request_chat(payload)
    raw = str(response_payload.get("message", {}).get("content", ""))
    try:
        answer = extract_json(raw)
    except ValueError as error:
        # A selected local model is a required dependency.  Do not silently
        # downgrade to fixed rules: the task must expose the model failure so
        # the operator can retry after Ollama/model recovery.
        raise ValueError(f"本地视觉模型返回无效结果（{model}）：{error}") from error
    return {
        "pre_is_cover": as_bool(answer.get("pre_is_cover")),
        "pre_is_plot": as_bool(answer.get("pre_is_plot")),
        "post_is_plot": as_bool(answer.get("post_is_plot")),
        "confidence": max(0, min(100, int(float(answer.get("confidence", 0))))),
        "reason": str(answer.get("reason", ""))[:120],
        "raw": raw,
    }


def candidate_group(frames: list[Frame], boundary_index: int) -> list[Frame] | None:
    # Two before + the first two plot-side frames.  Boundary points to the
    # first post-cover frame, so index 0/last-index cannot form a group.
    if boundary_index < 2 or boundary_index + 1 >= len(frames):
        return None
    return [frames[boundary_index - 2], frames[boundary_index - 1], frames[boundary_index], frames[boundary_index + 1]]


def choose_candidates(frames: list[Frame], maximum: int, minimum_scene_score: float) -> list[int]:
    # A title/character overlay often persists over a real opening scene.  It
    # is never sufficient by itself: a real cover exit must also have a
    # meaningful visual boundary.
    indexes = [
        index for index in range(2, len(frames) - 1)
        if frames[index].scene_score_from_previous >= minimum_scene_score
    ]
    # Keep a few earliest high-change boundaries: covers normally end early.
    indexes.sort(key=lambda index: (frames[index].scene_score_from_previous, -frames[index].time_seconds), reverse=True)
    return indexes[:maximum]


def detect(video: Path, report_path: Path, evidence_dir: Path, model: str | None, seconds: float, sample_fps: float, maximum: int, minimum_scene_score: float) -> dict[str, Any]:
    frames, metadata = read_opening_frames(video, evidence_dir, seconds, sample_fps)
    candidate_indexes = choose_candidates(frames, maximum, minimum_scene_score)
    assessed: list[dict[str, Any]] = []
    for boundary_index in candidate_indexes:
        group = candidate_group(frames, boundary_index)
        if group is None:
            continue
        vision = ask_local_vision(model, group) if model else {"pre_is_cover": False, "pre_is_plot": False, "post_is_plot": False, "confidence": 0, "reason": "LOCAL_VISION_DISABLED"}
        confidence = vision["confidence"] / 100.0
        accepted = vision["pre_is_cover"] and not vision["pre_is_plot"] and vision["post_is_plot"]
        assessed.append({
            "cut_seconds": frames[boundary_index].time_seconds,
            "scene_score": frames[boundary_index].scene_score_from_previous,
            "combined_score": round(0.65 * confidence + 0.35 * frames[boundary_index].scene_score_from_previous, 5),
            "accepted": accepted,
            "frames": [asdict(frame) for frame in group],
            "vision": vision,
        })
    accepted = [item for item in assessed if item["accepted"]]
    if accepted:
        chosen = max(accepted, key=lambda item: (item["combined_score"], -item["cut_seconds"]))
        mode = "AUTO_CUT_LOCAL_VISION"
    elif assessed:
        # A source may already begin with plot material.  Never cut a real
        # opening merely because it contains a persistent drama-title overlay.
        chosen = None
        mode = "NO_CONFIRMED_OPENING_COVER"
    else:
        chosen = None
        mode = "NO_CONFIRMED_OPENING_COVER"
    with video.open("rb") as source_file:
        digest = hashlib.sha256(source_file.read(1024 * 1024)).hexdigest()
    result = {
        "schema": "opening_cover_detection_v1",
        "created_unix": int(time.time()),
        "source": {"path": str(video), "size_bytes": video.stat().st_size, "first_megabyte_sha256": digest},
        "sampling": {"opening_seconds": seconds, "sample_fps": sample_fps, "minimum_scene_score": minimum_scene_score, **metadata},
        "local_model": model,
        "decision": {"action": mode, "cut_start_seconds": chosen["cut_seconds"] if chosen else None, "selected": chosen},
        "candidates": assessed,
        "evidence_dir": str(evidence_dir),
        "source_was_modified": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(safe_json(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect a short opening-cover cut point without modifying a video")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--disable-vlm", action="store_true", help="Use only local fixed rules; never call Ollama")
    parser.add_argument("--opening-seconds", type=float, default=3.0)
    parser.add_argument("--sample-fps", type=float, default=10.0)
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--min-scene-score", type=float, default=0.12)
    args = parser.parse_args()
    if not args.video.is_file():
        raise SystemExit(f"Video does not exist: {args.video}")
    if args.opening_seconds <= 0 or args.opening_seconds > 8 or args.sample_fps < 2 or args.sample_fps > 30 or args.max_candidates < 1 or not 0 < args.min_scene_score < 1:
        raise SystemExit("Invalid sampling arguments")
    evidence = args.evidence_dir or (args.report.parent / "封面检测证据" / hashlib.sha256(str(args.video).encode("utf-8")).hexdigest()[:12])
    result = detect(args.video, args.report, evidence, None if args.disable_vlm else args.model, args.opening_seconds, args.sample_fps, args.max_candidates, args.min_scene_score)
    print(safe_json({"action": result["decision"]["action"], "cut_start_seconds": result["decision"]["cut_start_seconds"], "report": str(args.report)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # Keep batch callers machine-readable.
        print(safe_json({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
