#!/usr/bin/env python3
"""Detect a trailing non-plot guidance/end-card section with local Ollama VL.

The caller supplies the already budget-capped source range.  This tool writes
only evidence frames and a JSON decision; it never changes the source video.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

try:
    from .ollama_local import VISION_CONTEXT_TOKENS, request_chat
except ImportError:  # Direct execution keeps the script directory on sys.path.
    from ollama_local import VISION_CONTEXT_TOKENS, request_chat


DEFAULT_MODEL = "qwen2.5vl:7b"
# Qwen vision converts every supplied image into a substantial number of
# context entries.  Three masked, downscaled samples keep a request safely
# below this product's fixed 8K local context while still showing the start,
# middle and end of a six-second group.
MAX_VISION_SAMPLES = 3
MODEL_IMAGE_MAX_WIDTH = 320
MODEL_IMAGE_JPEG_QUALITY = 80


@dataclass
class Frame:
    index: int
    time_seconds: float
    path: str
    scene_score_from_previous: float = 0.0


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2)


def as_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in {"true", "1", "yes", "是"}


def parse_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"Model did not return JSON: {text[:300]}")


def probe_video(video: Path) -> tuple[float, float]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot decode video: {video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()
    if fps <= 0 or count <= 0:
        raise RuntimeError(f"Cannot obtain duration: {video}")
    return count / fps, fps


def scene_difference(previous: np.ndarray, current: np.ndarray) -> float:
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    mad = float(np.mean(cv2.absdiff(previous_gray, current_gray))) / 255.0
    previous_hist = cv2.calcHist([previous_gray], [0], None, [32], [0, 256])
    current_hist = cv2.calcHist([current_gray], [0], None, [32], [0, 256])
    hist_distance = min(1.0, max(0.0, 1.0 - float(cv2.compareHist(previous_hist, current_hist, cv2.HISTCMP_CORREL))))
    return round(min(1.0, 0.65 * mad + 0.35 * hist_distance), 5)


def extract_frames(video: Path, start: float, end: float, sample_fps: float, evidence_dir: Path) -> list[Frame]:
    capture = cv2.VideoCapture(str(video))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    frame_count = max(2, int(np.ceil((end - start) * sample_fps)))
    frames: list[Frame] = []
    previous_image: np.ndarray | None = None
    for index in range(frame_count):
        timestamp = min(end - 0.001, start + index / sample_fps)
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, image = capture.read()
        if not ok or image is None:
            continue
        height, width = image.shape[:2]
        if width > 480:
            image = cv2.resize(image, (480, max(2, round(height * 480 / width))), interpolation=cv2.INTER_AREA)
        output = evidence_dir / f"frame_{index:03d}_{timestamp:08.3f}s.jpg"
        encoded_ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not encoded_ok:
            raise RuntimeError(f"Cannot encode evidence frame: {output}")
        output.write_bytes(encoded.tobytes())
        score = scene_difference(previous_image, image) if previous_image is not None else 0.0
        frames.append(Frame(index=index, time_seconds=round(timestamp, 3), path=str(output), scene_score_from_previous=score))
        previous_image = image
    capture.release()
    if len(frames) < 4:
        raise RuntimeError("Too few tail frames decoded")
    return frames


def even_samples(frames: list[Frame], maximum: int = 6) -> list[Frame]:
    if len(frames) <= maximum:
        return frames
    positions = np.linspace(0, len(frames) - 1, maximum).round().astype(int)
    return [frames[int(position)] for position in positions]


def image_b64(path: str) -> str:
    """Hide likely persistent title/CTA bands before semantic tail judgment.

    The original evidence frame remains untouched. This only prevents a
    side-mounted "click link" or top drama-title watermark from dominating the
    local model when the centre is still normal story footage.
    """
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read evidence image: {path}")
    height, width = image.shape[:2]
    side = round(width * 0.16)
    top = round(height * 0.07)
    image[:, :side] = 0
    image[:, width - side :] = 0
    image[:top, :] = 0
    if width > MODEL_IMAGE_MAX_WIDTH:
        image = cv2.resize(
            image,
            (MODEL_IMAGE_MAX_WIDTH, max(2, round(height * MODEL_IMAGE_MAX_WIDTH / width))),
            interpolation=cv2.INTER_AREA,
        )
    ok, masked = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), MODEL_IMAGE_JPEG_QUALITY])
    if not ok:
        raise RuntimeError(f"Cannot encode masked evidence image: {path}")
    return base64.b64encode(masked.tobytes()).decode("ascii")


def ask_tail_model(model: str, frames: list[Frame]) -> dict[str, Any]:
    prompt = """你在判断短剧视频结尾。以下图片按时间顺序，来自同一段连续视频。为排除常驻水印干扰，左右窄边和顶部已被遮住。
请判断它属于：
- plot：仍在正常讲剧情，即使画面有剧名、水印、人物花字或“点击链接”等常驻覆盖文字；
- guidance：剧情已经结束，当前片段主要在引导用户看全集、下一集、跳转、去主页、点击按钮、搜索等；
- endcard：非剧情结尾卡、logo、黑屏、完结提示、静态宣传页。
只有与剧情无关的结尾引导或结尾卡，才能裁掉。不要把剧情画面上的常驻引流文字误判为 guidance。
只输出 JSON，不要 markdown：
{"kind":"plot或guidance或endcard","primary_is_plot":true或false,"contains_guidance":true或false,"confidence":0到100整数,"reason":"不超过35字"}
只要人物仍在表演、对白或推进剧情，primary_is_plot 必须为 true 且 kind 必须为 plot；常驻的竖排/横排引流文字不能改变这个结论。"""
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
            "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 180, "num_ctx": VISION_CONTEXT_TOKENS},
        "messages": [{"role": "user", "content": prompt, "images": [image_b64(frame.path) for frame in frames]}],
    }
    payload_out = request_chat(payload)
    raw = str(payload_out.get("message", {}).get("content", ""))
    answer = parse_json(raw)
    kind = str(answer.get("kind", "plot")).strip().lower()
    if kind not in {"plot", "guidance", "endcard"}:
        kind = "plot"
    return {
        "kind": kind,
        "primary_is_plot": as_bool(answer.get("primary_is_plot")),
        "contains_guidance": as_bool(answer.get("contains_guidance")),
        "confidence": max(0, min(100, int(float(answer.get("confidence", 0))))),
        "reason": str(answer.get("reason", ""))[:140],
        "raw": raw,
    }


def ask_short_tail_model(model: str, frames: list[Frame]) -> dict[str, Any]:
    """Find a brief final non-plot card missed by the coarse 45-second pass."""
    prompt = """You are checking only the final 3 seconds of a short-drama video.
The images are in time order. Treat a brief end marker as non-plot even when
the drama background remains visible: to-be-continued, final card, next-episode
preview, drama title card, poster, ending animation or static promotional card.
Do not treat ordinary spoken-dialogue subtitles as non-plot. Return the first
image index (starting from zero) which is no longer normal plot progression.
Return JSON only:
{"has_nonplot_tail":true_or_false,"first_nonplot_frame_index":integer,"confidence":0_to_100,"reason":"short"}"""
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
            "keep_alive": "10m",
        "options": {"temperature": 0, "num_predict": 160, "num_ctx": VISION_CONTEXT_TOKENS},
        "messages": [{"role": "user", "content": prompt, "images": [image_b64(frame.path) for frame in frames]}],
    }
    payload_out = request_chat(payload)
    raw = str(payload_out.get("message", {}).get("content", ""))
    answer = parse_json(raw)
    has_nonplot_tail = as_bool(answer.get("has_nonplot_tail"))
    try:
        index = int(answer.get("first_nonplot_frame_index", -1))
    except (TypeError, ValueError):
        index = -1
    confidence = max(0, min(100, int(float(answer.get("confidence", 0)))))
    if not has_nonplot_tail or not 0 <= index < len(frames):
        has_nonplot_tail, index = False, -1
    return {
        "has_nonplot_tail": has_nonplot_tail,
        "first_nonplot_frame_index": index,
        "confidence": confidence,
        "reason": str(answer.get("reason", ""))[:140],
        "raw": raw,
    }


def find_tail_ocr_endcard(frames: list[Frame]) -> dict[str, Any]:
    """Recognize explicit final-card text without asking a vision model to infer it.

    Vertical Chinese `未完待续` is often drawn over the last story frame.  It
    is not reliably distinguished by visual semantics, while local OCR reads
    it well. The character-set test accepts either the stable front half
    `未完待` or the stable `未待续` combination when one vertical character is
    cropped or misread by OCR.
    """
    try:
        engine = RapidOCR()
        matches: list[dict[str, Any]] = []
        for frame in frames:
            raw = np.fromfile(frame.path, dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if image is None:
                continue
            texts: list[str] = []
            for item in engine(image)[0] or []:
                _points, text, confidence = item
                if float(confidence) >= 0.72:
                    texts.append(str(text))
            normalized = "".join(char for text in texts for char in text if "\u4e00" <= char <= "\u9fff")
            # `未完待续` is the hard business cue. The tail may begin too late
            # for the final vertical character to be fully visible, so accept
            # either 未+完+待 or 未+待+续. Both are limited to the final 3s.
            unfinished = (
                all(character in normalized for character in ("\u672a", "\u5b8c", "\u5f85"))
                or all(character in normalized for character in ("\u672a", "\u5f85", "\u7eed"))
            )
            next_episode = "\u4e0b\u4e00\u96c6" in normalized or "\u4e0b\u96c6" in normalized
            if unfinished or next_episode:
                matches.append({
                    "time_seconds": frame.time_seconds,
                    "text": texts,
                    "marker": "unfinished" if unfinished else "next_episode",
                })
        return {
            "available": True,
            "has_endcard_marker": bool(matches),
            "first_marker": matches[0] if matches else None,
            "match_count": len(matches),
        }
    except Exception as exc:
        # OCR is an enhancement to the existing detector. A missing local OCR
        # runtime must not prevent the remaining local vision safeguards.
        return {"available": False, "has_endcard_marker": False, "error": str(exc)[:180]}


def final_visual_endcard_transition(frames: list[Frame], guard_start: float) -> Frame | None:
    """Return the first strong visual change inside the true final three seconds.

    Some source end cards use a drama-title illustration or a very brief
    ``to be continued`` transition.  Local vision can call those frames plot,
    even though their abrupt end-of-source switch is precisely the user-facing
    tail we must not keep.  This fallback intentionally prefers sacrificing a
    final second of plot over exposing such a tail card.
    """
    candidates = [
        frame for frame in frames
        if frame.time_seconds >= guard_start + 0.8 and frame.scene_score_from_previous >= 0.60
    ]
    return candidates[0] if candidates else None


def chunks(frames: list[Frame], sample_fps: float, chunk_seconds: float) -> list[list[Frame]]:
    size = max(2, int(round(sample_fps * chunk_seconds)))
    return [frames[start : start + size] for start in range(0, len(frames), size)]


def vision_samples(frames: list[Frame]) -> list[Frame]:
    """Choose a bounded, evenly spread set for one local VLM request."""
    return even_samples(frames, maximum=MAX_VISION_SAMPLES)


def disabled_vision_decision() -> dict[str, Any]:
    """Keep the no-VLM route conservative: OCR and scene rules may still trim."""
    return {
        "kind": "plot",
        "primary_is_plot": True,
        "contains_guidance": False,
        "confidence": 0,
        "reason": "local vision disabled",
        "raw": "",
    }


def detect(video: Path, report: Path, evidence_dir: Path, model: str | None, range_start: float, range_end: float, window_seconds: float, sample_fps: float, chunk_seconds: float, min_confidence: int) -> dict[str, Any]:
    duration, native_fps = probe_video(video)
    # Container duration (FFprobe) can extend a few audio packets beyond the
    # last decodable video frame reported by OpenCV. Clamp only that tiny tail
    # discrepancy; a materially invalid requested range remains an error.
    if range_end > duration and range_end <= duration + 1.0:
        range_end = duration
    if range_start < 0 or range_end > duration + 0.05 or range_end <= range_start:
        raise RuntimeError("Invalid source analysis range")
    analysis_start = max(range_start, range_end - window_seconds)
    frames = extract_frames(video, analysis_start, range_end, sample_fps, evidence_dir)
    groups: list[dict[str, Any]] = []
    for group in chunks(frames, sample_fps, chunk_seconds):
        selected = vision_samples(group)
        vision = ask_tail_model(model, selected) if model else disabled_vision_decision()
        groups.append({
            "start_seconds": group[0].time_seconds,
            "end_seconds": round(group[-1].time_seconds + 1.0 / sample_fps, 3),
            "frames": [asdict(frame) for frame in selected],
            "vision": vision,
        })
    # Only a trailing continuous run may be removed.  It must contain guidance,
    # but may finish with an end card or logo after the actual CTA.
    trailing: list[dict[str, Any]] = []
    guidance_seen = False
    for group in reversed(groups):
        vision = group["vision"]
        qualifies = (
            vision["confidence"] >= min_confidence
            and not vision["primary_is_plot"]
            and vision["kind"] in {"guidance", "endcard"}
        )
        if not qualifies:
            break
        trailing.append(group)
        guidance_seen = guidance_seen or vision["kind"] == "guidance" or vision["contains_guidance"]
    # The start of a removable tail must be observable. A full 45-second
    # window classified alike without a preceding plot group could be normal
    # story carrying a persistent CTA overlay, so it is not auto-trimmed.
    first_trailing_index = len(groups) - len(trailing)
    preceding_is_plot = first_trailing_index > 0 and groups[first_trailing_index - 1]["vision"]["kind"] == "plot"
    if trailing and guidance_seen and preceding_is_plot:
        selected_group = trailing[-1]  # earliest because list is reverse chronological
        action = "AUTO_TRIM_TRAILING_GUIDANCE"
        # The local model has already classified this *entire earliest group*
        # as non-plot guidance/end-card.  Do not advance the cut to a later
        # scene change inside that group: a CTA can begin on a still plot-like
        # image and that old refinement leaked its first 1-3 seconds.
        selected_start = selected_group["start_seconds"]
        # Sampling cannot prove the first guide frame is exactly at the first
        # retained 0.5-second sample.  The business rule prioritises never
        # exposing a flash of tail guidance over retaining the final second of
        # plot, so leave a one-second safety lead before the earliest accepted
        # guidance group.
        safety_lead_seconds = 1.0
        trim_end = max(range_start, selected_start - safety_lead_seconds)
        selected = {
            **selected_group,
            "coarse_start_seconds": selected_start,
            "refined_by_scene_boundary": False,
            "safety_lead_seconds": safety_lead_seconds,
            "refined_start_seconds": trim_end,
        }
    else:
        action = "NO_TRAILING_GUIDANCE"
        trim_end = range_end
        selected = None
    # A short end card can be missed by the coarse 45-second 6-second-group
    # pass. When that pass finds no tail, inspect the final 3 seconds at 10fps
    # in one additional local model call.
    short_tail_guard: dict[str, Any] | None = None
    if action == "NO_TRAILING_GUIDANCE":
        guard_start = max(range_start, range_end - 3.0)
        guard_frames = extract_frames(video, guard_start, range_end, 10.0, evidence_dir / "短尾兜底")
        guard_samples = vision_samples(guard_frames)
        ocr_guard = find_tail_ocr_endcard(guard_frames)
        short_tail_guard = {
            "range_start_seconds": guard_start,
            "sample_fps": 10.0,
            "sample_count": len(guard_samples),
            "ocr": ocr_guard,
        }
        if ocr_guard["has_endcard_marker"]:
            first_marker = ocr_guard["first_marker"]
            safety_lead_seconds = 1.0
            trim_end = max(range_start, float(first_marker["time_seconds"]) - safety_lead_seconds)
            action = "AUTO_TRIM_FINAL_OCR_ENDCARD"
            selected = {
                "start_seconds": first_marker["time_seconds"],
                "short_tail_guard": True,
                "ocr_marker": first_marker,
                "safety_lead_seconds": safety_lead_seconds,
                "trim_end_seconds": trim_end,
            }
        elif model:
            guard = ask_short_tail_model(model, guard_samples)
            short_tail_guard["decision"] = guard
            if guard["has_nonplot_tail"] and guard["confidence"] >= 50:
                first_frame = guard_samples[guard["first_nonplot_frame_index"]]
                safety_lead_seconds = 1.0
                trim_end = max(range_start, first_frame.time_seconds - safety_lead_seconds)
                action = "AUTO_TRIM_FINAL_NON_PLOT"
                selected = {
                    "start_seconds": first_frame.time_seconds,
                    "short_tail_guard": True,
                    "safety_lead_seconds": safety_lead_seconds,
                    "trim_end_seconds": trim_end,
                    "vision": guard,
                }
        else:
            short_tail_guard["decision"] = {"status": "disabled", "reason": "local vision disabled"}
        # Final visual-transition fallback is deliberately limited to the final
        # three seconds.  It remains available when local vision is disabled.
        if action == "NO_TRAILING_GUIDANCE":
            endcard_frame = final_visual_endcard_transition(guard_frames, guard_start)
            if endcard_frame is not None:
                safety_lead_seconds = 1.0
                trim_end = max(range_start, endcard_frame.time_seconds - safety_lead_seconds)
                action = "AUTO_TRIM_FINAL_VISUAL_ENDCARD"
                selected = {
                    "start_seconds": endcard_frame.time_seconds,
                    "short_tail_guard": True,
                    "visual_transition_fallback": True,
                    "scene_score": endcard_frame.scene_score_from_previous,
                    "safety_lead_seconds": safety_lead_seconds,
                    "trim_end_seconds": trim_end,
                }
    with video.open("rb") as source_file:
        digest = hashlib.sha256(source_file.read(1024 * 1024)).hexdigest()
    result = {
        "schema": "tail_guidance_detection_v1",
        "created_unix": int(time.time()),
        "source": {"path": str(video), "size_bytes": video.stat().st_size, "first_megabyte_sha256": digest},
        "input_range": {"start_seconds": range_start, "end_seconds": range_end, "native_duration_seconds": round(duration, 3)},
        "sampling": {"analysis_start_seconds": analysis_start, "window_seconds": window_seconds, "sample_fps": sample_fps, "chunk_seconds": chunk_seconds, "native_fps": native_fps, "max_vision_samples_per_request": MAX_VISION_SAMPLES, "model_image_max_width": MODEL_IMAGE_MAX_WIDTH, "model_overlay_mask": {"left_right_width_percent": 16, "top_height_percent": 7}},
        "local_model": model or "disabled",
        "decision": {"action": action, "trim_end_seconds": trim_end, "selected": selected},
        "short_tail_guard": short_tail_guard,
        "groups": groups,
        "evidence_dir": str(evidence_dir),
        "source_was_modified": False,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(dump(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect trailing guidance/end cards without modifying a video")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--source-start", type=float, default=0.0)
    parser.add_argument("--source-end", type=float)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--disable-vlm", action="store_true", help="Use only OCR and fixed rules; never call Ollama")
    parser.add_argument("--window-seconds", type=float, default=45.0)
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--chunk-seconds", type=float, default=6.0)
    parser.add_argument("--min-confidence", type=int, default=60)
    args = parser.parse_args()
    if not args.video.is_file():
        raise SystemExit(f"Video does not exist: {args.video}")
    duration, _ = probe_video(args.video)
    source_end = args.source_end if args.source_end is not None else duration
    if args.window_seconds < 6 or args.window_seconds > 90 or args.sample_fps < 1 or args.sample_fps > 8 or args.chunk_seconds < 2 or args.chunk_seconds > 15:
        raise SystemExit("Invalid sampling arguments")
    evidence = args.evidence_dir or (args.report.parent / "片尾检测证据" / hashlib.sha256(str(args.video).encode("utf-8")).hexdigest()[:12])
    result = detect(args.video, args.report, evidence, None if args.disable_vlm else args.model, args.source_start, source_end, args.window_seconds, args.sample_fps, args.chunk_seconds, args.min_confidence)
    print(dump({"action": result["decision"]["action"], "trim_end_seconds": result["decision"]["trim_end_seconds"], "report": str(args.report)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(dump({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
