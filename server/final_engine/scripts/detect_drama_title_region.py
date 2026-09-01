#!/usr/bin/env python3
"""Locate a persistent on-screen drama-title overlay with local OCR.

The script only writes an evidence/report JSON.  Its normalized rectangle is
intended for a later full-duration mosaic/blur on the viral-video track.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

try:
    from .ollama_local import DEFAULT_MODEL as DEFAULT_VLM_MODEL, VISION_CONTEXT_TOKENS, request_chat
except ImportError:  # Direct execution keeps the script directory on sys.path.
    from ollama_local import DEFAULT_MODEL as DEFAULT_VLM_MODEL, VISION_CONTEXT_TOKENS, request_chat


@dataclass
class Detection:
    frame_time_seconds: float
    text: str
    confidence: float
    left: float
    top: float
    right: float
    bottom: float


@dataclass
class Cluster:
    normalized_text: str
    detections: list[Detection] = field(default_factory=list)


TITLE_EXCLUSIONS = (
    "\u5267\u60c5\u7eaf\u5c5e\u865a\u6784", "\u65e0\u4e0d\u826f\u5f15\u5bfc", "\u6b63\u786e\u4ef7\u503c\u89c2",
    "\u5185\u5bb9\u7531ai", "\u5f71\u89c6\u6548\u679c\u8bf7\u52ff\u6a21\u4eff", "\u70b9\u51fb\u94fe\u63a5",
    "\u514d\u8d39\u89c2\u770b", "\u514d\u8d39", "\u5168\u96c6", "\u4e0b\u4e00\u96c6", "\u5173\u6ce8",
    "\u70b9\u8d5e", "\u77ed\u5267",
)

# Target classification runs only after persistence verification.  These are
# notice/disclaimer phrases rather than candidate-detection exclusions: they
# remain visible in the report but must never enter a delogo render region.
DISCLAIMER_PHRASES = (
    "剧情纯属虚构", "本故事纯属虚构", "故事纯属虚构", "请勿模仿", "无不良引导",
    "内容由AI生成", "内容由AI制作", "树立正确价值观", "影视效果请勿模仿",
)
# Exact generic platform labels are not work titles even when they are stable.
# Keep this list deliberately narrow; longer or mixed text stays UNCERTAIN and
# reaches the local VLM instead of being guessed from a keyword.
GENERIC_NOTICE_LABELS = ("热门短剧", "热播短剧")
DISCLAIMER_FUZZY_MIN_RATIO = 0.86

# Stage 1 is deliberately permissive: its only job is to nominate a small
# number of possible overlays.  It must never by itself authorize a full-video
# blur.  Stage 2 makes that conservative production decision over the actual
# retained source range.
OCR_MINIMUM_CONFIDENCE = 0.72
CANDIDATE_MIN_INITIAL_RATIO = 0.25
PERSISTENCE_VERIFICATION_SAMPLE_COUNT = 14
PERSISTENCE_VERIFICATION_EDGE_FRACTION = 0.05
PERSISTENCE_MIN_RATIO = 0.80
ACTIVE_PICTURE_MIN_OVERLAP_RATIO = 0.50
TEXT_SIMILARITY_MIN_RATIO = 0.76
POSITION_TOLERANCE_X = 0.10
POSITION_TOLERANCE_Y = 0.12
LINE_BASELINE_TOLERANCE = 0.028
# Safe adaptive render padding is derived from the text's short dimension.
# The independent horizontal/vertical ratios intentionally provide room for
# stroke/glow while neighbour OCR boxes remain hard barriers.
RENDER_DESIRED_PADDING_SIDE_RATIO = 0.13
RENDER_DESIRED_PADDING_VERTICAL_RATIO = 0.15
RENDER_DESIRED_PADDING_MIN_PIXELS = 4
RENDER_DESIRED_PADDING_MAX_PIXELS = 12
RENDER_SAFETY_GAP_PIXELS = 3
RENDER_BARRIER_OVERLAP_RATIO = 0.25
MAX_RENDER_REGIONS = 4
VLM_CONTEXT_PADDING_RATIO = 0.25
VLM_CONTEXT_PADDING_MIN_PIXELS = 40
VLM_ALLOWED_CLASSES = {"TITLE", "NOTICE", "GUIDANCE", "WATERMARK", "OTHER", "UNCERTAIN"}


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2)


def normalize(text: str) -> str:
    return re.sub(r"[\s《》〈〉<>#_~`!！?？,，.。:：;；'\"“”‘’（）()【】\[\]{}]", "", text).strip()


def _disclaimer_phrase_match(text: str, phrase: str) -> bool:
    """Allow punctuation/space removal and small OCR errors in a notice phrase."""
    if phrase in text:
        return True
    if len(phrase) < 4:
        return False
    lower = max(2, len(phrase) - 2)
    upper = min(len(text), len(phrase) + 2)
    return any(SequenceMatcher(None, phrase, text[start:start + length]).ratio() >= DISCLAIMER_FUZZY_MIN_RATIO for length in range(lower, upper + 1) for start in range(0, max(1, len(text) - length + 1)))


def strong_title_signal(candidate: dict[str, Any]) -> bool:
    """Book-title brackets are sufficient, but never required, evidence."""
    texts = [str(item.get("text", "")) for item in candidate.get("detections", [])]
    return any("《" in text and "》" in text for text in texts)


def classify_target(candidate: dict[str, Any]) -> dict[str, Any]:
    """Make only the inexpensive first-pass classification decision."""
    if not candidate.get("accepted"):
        return {
            "rule_class": "UNVERIFIED", "rule_reason": "PERSISTENCE_REJECTED",
            "vlm_called": False, "vlm_class": None, "vlm_confidence": None, "vlm_reason": None,
            "final_target_class": "UNVERIFIED", "target_class": "UNVERIFIED", "classification_reason": "PERSISTENCE_REJECTED", "render": False,
        }
    text = normalize(candidate["normalized_text"]).lower()
    matched = [phrase for phrase in DISCLAIMER_PHRASES if _disclaimer_phrase_match(text, normalize(phrase).lower())]
    if matched:
        reason = "DISCLAIMER_PHRASE_MATCH:" + ",".join(matched)
        return {
            "rule_class": "DISCLAIMER", "rule_reason": reason,
            "vlm_called": False, "vlm_class": None, "vlm_confidence": None, "vlm_reason": None,
            "final_target_class": "DISCLAIMER", "target_class": "DISCLAIMER", "classification_reason": reason, "render": False,
        }
    if text in GENERIC_NOTICE_LABELS:
        reason = "GENERIC_NOTICE_LABEL_EXACT_MATCH:" + text
        return {
            "rule_class": "NOTICE", "rule_reason": reason,
            "vlm_called": False, "vlm_class": None, "vlm_confidence": None, "vlm_reason": None,
            "final_target_class": "NOTICE", "target_class": "NOTICE", "classification_reason": reason, "render": False,
        }
    if strong_title_signal(candidate):
        return {
            "rule_class": "TITLE", "rule_reason": "STRONG_TITLE_SIGNAL:BOOK_TITLE_BRACKETS",
            "vlm_called": False, "vlm_class": None, "vlm_confidence": None, "vlm_reason": None,
            "final_target_class": "TITLE", "target_class": "TITLE", "classification_reason": "STRONG_TITLE_SIGNAL:BOOK_TITLE_BRACKETS", "render": True,
        }
    return {
        "rule_class": "UNCERTAIN", "rule_reason": "NO_DISCLAIMER_OR_STRONG_TITLE_SIGNAL",
        "vlm_called": False, "vlm_class": None, "vlm_confidence": None, "vlm_reason": None,
        "final_target_class": "UNCERTAIN", "target_class": "UNCERTAIN", "classification_reason": "VLM_REQUIRED", "render": False,
    }


def _image_b64(image: np.ndarray) -> str:
    saved, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not saved:
        raise RuntimeError("Cannot encode VLM evidence image")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _parse_vlm_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return JSON")
        value = json.loads(raw[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Model JSON must be an object")
    return value


def finalize_vlm_classification(answer: dict[str, Any]) -> tuple[str, float, str]:
    """Validate the model contract; unknown output is deliberately non-rendering."""
    vlm_class = str(answer.get("class", "UNCERTAIN")).upper().strip()
    if vlm_class not in VLM_ALLOWED_CLASSES:
        vlm_class = "UNCERTAIN"
    try:
        confidence = max(0.0, min(1.0, float(answer.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return vlm_class, confidence, str(answer.get("reason", ""))[:160]


def classify_uncertain_with_vlm(video: Path, candidate: dict[str, Any], evidence_dir: Path, model: str) -> dict[str, Any]:
    """Classify one already-persistent, rule-uncertain overlay exactly once."""
    sample = next((item for item in candidate.get("detections", []) if item.get("text")), None)
    if sample is None:
        return {"vlm_called": False, "vlm_class": "UNCERTAIN", "vlm_confidence": 0.0, "vlm_reason": "NO_OCR_EVIDENCE", "final_target_class": "UNCERTAIN", "target_class": "UNCERTAIN", "classification_reason": "VLM_EVIDENCE_UNAVAILABLE", "render": False}
    capture = cv2.VideoCapture(str(video))
    capture.set(cv2.CAP_PROP_POS_MSEC, float(sample["frame_time_seconds"]) * 1000)
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        return {"vlm_called": False, "vlm_class": "UNCERTAIN", "vlm_confidence": 0.0, "vlm_reason": "FRAME_DECODE_FAILED", "final_target_class": "UNCERTAIN", "target_class": "UNCERTAIN", "classification_reason": "VLM_EVIDENCE_UNAVAILABLE", "render": False}
    height, width = frame.shape[:2]
    left = max(0, min(width - 1, round(float(sample["left"]) * width)))
    top = max(0, min(height - 1, round(float(sample["top"]) * height)))
    right = max(left + 1, min(width, round(float(sample["right"]) * width)))
    bottom = max(top + 1, min(height, round(float(sample["bottom"]) * height)))
    target = frame[top:bottom, left:right]
    pad = max(VLM_CONTEXT_PADDING_MIN_PIXELS, round(max(right - left, bottom - top) * VLM_CONTEXT_PADDING_RATIO))
    context = frame[max(0, top - pad):min(height, bottom + pad), max(0, left - pad):min(width, right + pad)]
    evidence = evidence_dir / "vlm_classification"
    evidence.mkdir(parents=True, exist_ok=True)
    target_path, context_path = evidence / f"{candidate['normalized_text'][:24]}_target.jpg", evidence / f"{candidate['normalized_text'][:24]}_context.jpg"
    cv2.imwrite(str(target_path), target)
    cv2.imwrite(str(context_path), context)
    prompt = f'''你在判断短剧视频的长期固定覆盖文字是否是作品剧名。OCR 文本：{candidate["normalized_text"]}
第一张图是文字紧框，第二张图是包含附近画面的上下文。只判断这段长期固定文字本身。
剧名/作品标题返回 TITLE；免责声明、提示、引导、账号名/水印、平台文案或无法确认的内容不要返回 TITLE。
只输出 JSON，不要 markdown：{{"class":"TITLE | NOTICE | GUIDANCE | WATERMARK | OTHER | UNCERTAIN","confidence":0.0,"reason":"不超过40字"}}'''
    started = time.monotonic()
    try:
        response = request_chat({
            "model": model, "stream": False, "format": "json", "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": 140, "num_ctx": VISION_CONTEXT_TOKENS},
            "messages": [{"role": "user", "content": prompt, "images": [_image_b64(target), _image_b64(context)]}],
        }, attempts=1)
        raw = str(response.get("message", {}).get("content", ""))
        answer = _parse_vlm_json(raw)
        vlm_class, confidence, reason = finalize_vlm_classification(answer)
    except Exception as error:
        vlm_class, confidence, reason = "UNCERTAIN", 0.0, f"VLM_ERROR:{type(error).__name__}:{error}"[:160]
    elapsed = round(time.monotonic() - started, 3)
    final = "TITLE" if vlm_class == "TITLE" else vlm_class
    return {
        "vlm_called": True, "vlm_model": model, "vlm_elapsed_seconds": elapsed,
        "vlm_class": vlm_class, "vlm_confidence": confidence, "vlm_reason": reason,
        "vlm_evidence": {"target_roi": str(target_path), "context": str(context_path), "sample_time_seconds": sample["frame_time_seconds"]},
        "final_target_class": final, "target_class": final,
        "classification_reason": "VLM_TITLE" if final == "TITLE" else "VLM_KEEP:" + final,
        "render": final == "TITLE",
    }


def probe(video: Path) -> tuple[float, float]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot decode video: {video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()
    if fps <= 0 or count <= 0:
        raise RuntimeError("Cannot determine video duration")
    return count / fps, fps


def extract_and_ocr(video: Path, start: float, seconds: float, sample_fps: float, evidence_dir: Path, engine: Any | None = None) -> tuple[list[Detection], int]:
    capture = cv2.VideoCapture(str(video))
    engine = engine or RapidOCR()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    detections: list[Detection] = []
    frame_total = max(3, int(math.ceil(seconds * sample_fps)))
    sampled = 0
    for index in range(frame_total):
        timestamp = start + index / sample_fps
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ok, image = capture.read()
        if not ok or image is None:
            continue
        height, width = image.shape[:2]
        # OCR on 720px-wide copies is fast but the report stores normalized
        # coordinates, so it remains valid for sources of different sizes.
        if width > 720:
            image = cv2.resize(image, (720, max(2, round(height * 720 / width))), interpolation=cv2.INTER_AREA)
            height, width = image.shape[:2]
        output = evidence_dir / f"frame_{index:03d}_{timestamp:08.3f}s.jpg"
        saved, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if saved:
            output.write_bytes(encoded.tobytes())
        result, _elapsed = engine(image)
        sampled += 1
        for item in result or []:
            points, text, confidence = item
            if float(confidence) < OCR_MINIMUM_CONFIDENCE:
                continue
            xy = np.array(points, dtype=float)
            detections.append(Detection(
                frame_time_seconds=round(timestamp, 3),
                text=str(text),
                confidence=round(float(confidence), 5),
                left=round(float(xy[:, 0].min()) / width, 6),
                top=round(float(xy[:, 1].min()) / height, 6),
                right=round(float(xy[:, 0].max()) / width, 6),
                bottom=round(float(xy[:, 1].max()) / height, 6),
            ))
    capture.release()
    if not sampled:
        raise RuntimeError("No title-detection frames decoded")
    return detections, sampled


def centre(detection: Detection) -> tuple[float, float]:
    return ((detection.left + detection.right) / 2, (detection.top + detection.bottom) / 2)


def similar_title(cluster: Cluster, detection: Detection) -> bool:
    if not cluster.detections:
        return False
    sample = cluster.detections[0]
    text_similarity = SequenceMatcher(None, cluster.normalized_text, normalize(detection.text)).ratio()
    sx, sy = centre(sample)
    dx, dy = centre(detection)
    return text_similarity >= TEXT_SIMILARITY_MIN_RATIO and abs(sx - dx) <= POSITION_TOLERANCE_X and abs(sy - dy) <= POSITION_TOLERANCE_Y


def title_like(cluster: Cluster, sample_count: int) -> tuple[bool, float, dict[str, Any]]:
    detections = cluster.detections
    left = min(item.left for item in detections)
    top = min(item.top for item in detections)
    right = max(item.right for item in detections)
    bottom = max(item.bottom for item in detections)
    width, height = right - left, bottom - top
    cx, cy = (left + right) / 2, (top + bottom) / 2
    persistence = len({item.frame_time_seconds for item in detections}) / max(1, sample_count)
    side_vertical = (height / max(width, 0.001) >= 1.55) and (cx <= 0.27 or cx >= 0.73)
    raw_text = "".join(item.text for item in detections)
    # Source titles use several bracket styles.  Do not treat only 《》 as a
    # title signal: the common full-width/ASCII parentheses form was causing
    # persistent top-centre drama titles to be missed.
    bracketed = any(mark in raw_text for mark in ("《", "》", "（", "）", "(", ")", "【", "】"))
    excluded = any(word in cluster.normalized_text.lower() for word in TITLE_EXCLUSIONS)
    # This is intentionally a *fixed-overlay* detector, not a title-semantic
    # classifier.  Drama-title styling varies too much to make name/shape a
    # safe gate.  The only protected class is ordinary dialogue subtitles:
    # they are typically lower-centre, non-vertical and change frequently.
    top_persistent = persistence >= CANDIDATE_MIN_INITIAL_RATIO and cy <= 0.16
    subtitle_zone = cy >= 0.58 and 0.14 <= cx <= 0.86 and not side_vertical and not bracketed
    fixed_overlay = persistence >= CANDIDATE_MIN_INITIAL_RATIO and len(cluster.normalized_text) >= 2 and not subtitle_zone
    score = 4.0 * persistence + 2.0 * float(side_vertical) + float(bracketed) + float(cy <= 0.16) + float(len(cluster.normalized_text) >= 4)
    # Do not exclude a candidate merely because it looks like a CTA/watermark:
    # the operating preference is to blur any stable non-subtitle overlay
    # rather than leak a mismatched drama title.
    valid = fixed_overlay
    return valid, round(score, 4), {
        "normalized_text": cluster.normalized_text,
        "persistence": round(persistence, 4),
        "side_vertical": side_vertical,
        "bracketed": bracketed,
        "top_persistent": top_persistent,
        "subtitle_zone": subtitle_zone,
        "fixed_overlay": fixed_overlay,
        "excluded": excluded,
        "bounds_normalized": {"left": left, "top": top, "right": right, "bottom": bottom},
        "centre_normalized": {"x": cx, "y": cy},
    }


def verification_times(source_start: float, source_end: float, count: int = PERSISTENCE_VERIFICATION_SAMPLE_COUNT) -> list[float]:
    """Return evenly distributed interior samples of the effective source range."""
    if count <= 0 or source_end <= source_start:
        return []
    duration = source_end - source_start
    lower = source_start + duration * PERSISTENCE_VERIFICATION_EDGE_FRACTION
    upper = source_end - duration * PERSISTENCE_VERIFICATION_EDGE_FRACTION
    if count == 1:
        return [round((lower + upper) / 2, 3)]
    return [round(lower + (upper - lower) * index / (count - 1), 3) for index in range(count)]


def candidate_box(candidate: dict[str, Any]) -> dict[str, float]:
    return {key: float(candidate["bounds_normalized"][key]) for key in ("left", "top", "right", "bottom")}


def normalize_active_picture(value: tuple[float, float, float, float] | list[float]) -> dict[str, float]:
    if len(value) != 4:
        raise ValueError("Active picture must have four normalized coordinates")
    left, top, right, bottom = (float(item) for item in value)
    if not 0 <= left < right <= 1 or not 0 <= top < bottom <= 1:
        raise ValueError("Active picture coordinates are invalid")
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def candidate_active_overlap_ratio(box: dict[str, float], active_picture: dict[str, float]) -> float:
    left, top, right, bottom = (float(box[key]) for key in ("left", "top", "right", "bottom"))
    area = (right - left) * (bottom - top)
    if area <= 0:
        return 0.0
    overlap_width = max(0.0, min(right, active_picture["right"]) - max(left, active_picture["left"]))
    overlap_height = max(0.0, min(bottom, active_picture["bottom"]) - max(top, active_picture["top"]))
    return overlap_width * overlap_height / area


def candidate_is_mainly_in_active_picture(box: dict[str, float], active_picture: dict[str, float]) -> bool:
    return candidate_active_overlap_ratio(box, active_picture) >= ACTIVE_PICTURE_MIN_OVERLAP_RATIO


def verification_roi(box: dict[str, float]) -> dict[str, float]:
    """Add a small OCR-only margin without ever expanding a candidate to a screen."""
    return {
        "left": max(0.0, box["left"] - 0.025),
        "top": max(0.0, box["top"] - 0.02),
        "right": min(1.0, box["right"] + 0.025),
        "bottom": min(1.0, box["bottom"] + 0.02),
    }


def _map_ocr_box(points: np.ndarray, roi: dict[str, float], crop_shape: tuple[int, int]) -> dict[str, float]:
    crop_height, crop_width = crop_shape
    return {
        "left": roi["left"] + (roi["right"] - roi["left"]) * float(points[:, 0].min()) / crop_width,
        "top": roi["top"] + (roi["bottom"] - roi["top"]) * float(points[:, 1].min()) / crop_height,
        "right": roi["left"] + (roi["right"] - roi["left"]) * float(points[:, 0].max()) / crop_width,
        "bottom": roi["top"] + (roi["bottom"] - roi["top"]) * float(points[:, 1].max()) / crop_height,
    }


def _centre_y(box: dict[str, float]) -> float:
    return (box["top"] + box["bottom"]) / 2


def _line_boxes(candidate: dict[str, Any], roi: dict[str, float], image: np.ndarray, engine: Any, *, resize: bool) -> list[dict[str, Any]]:
    """OCR one local area and retain candidate text lines without vertical union."""
    height, width = image.shape[:2]
    left = max(0, min(width - 1, int(math.floor(roi["left"] * width))))
    top = max(0, min(height - 1, int(math.floor(roi["top"] * height))))
    right = max(left + 1, min(width, int(math.ceil(roi["right"] * width))))
    bottom = max(top + 1, min(height, int(math.ceil(roi["bottom"] * height))))
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return False
    if resize and crop.shape[1] > 720:
        crop = cv2.resize(crop, (720, max(2, round(crop.shape[0] * 720 / crop.shape[1]))), interpolation=cv2.INTER_AREA)
    result, _elapsed = engine(crop)
    expected = candidate["normalized_text"]
    expected_centre = candidate["centre_normalized"]
    parts: list[dict[str, Any]] = []
    for item in result or []:
        points, text, confidence = item
        if float(confidence) < OCR_MINIMUM_CONFIDENCE:
            continue
        normalized = normalize(str(text))
        box = _map_ocr_box(np.array(points, dtype=float), roi, crop.shape[:2])
        if abs(_centre_y(box) - expected_centre["y"]) <= LINE_BASELINE_TOLERANCE:
            parts.append({"text": str(text), "normalized_text": normalized, "confidence": round(float(confidence), 5), "box": box})
    parts.sort(key=lambda item: item["box"]["left"])
    if not parts:
        return []
    # This candidate is one OCR line.  Multiple horizontal fragments are
    # allowed, but no fragment from another baseline is admitted above.
    text = "".join(item["normalized_text"] for item in parts)
    left = min(item["box"]["left"] for item in parts)
    top = min(item["box"]["top"] for item in parts)
    right = max(item["box"]["right"] for item in parts)
    bottom = max(item["box"]["bottom"] for item in parts)
    box = {"left": left, "top": top, "right": right, "bottom": bottom}
    if SequenceMatcher(None, expected, text).ratio() < TEXT_SIMILARITY_MIN_RATIO:
        return []
    if abs((left + right) / 2 - expected_centre["x"]) > POSITION_TOLERANCE_X:
        return []
    return [{"text": text, "box": box, "source_ocr_boxes": [{"text": item["text"], "confidence": item["confidence"], **item["box"]} for item in parts]}]


def verification_hit(candidate: dict[str, Any], roi: dict[str, float], image: np.ndarray, engine: Any) -> bool:
    """Stage 2 still answers only whether a candidate is present."""
    return bool(_line_boxes(candidate, roi, image, engine, resize=True))


def _full_frame_ocr_parts(image: np.ndarray, engine: Any) -> list[dict[str, Any]]:
    """Return native RapidOCR boxes in source-frame coordinates.

    This is deliberately separate from persistence verification: it is used
    only after a candidate has already passed Stage 2, so a rendering box is
    measured from the original OCR geometry rather than from the enlarged
    verification crop.
    """
    height, width = image.shape[:2]
    result, _elapsed = engine(image)
    parts: list[dict[str, Any]] = []
    for item in result or []:
        points, text, confidence = item
        if float(confidence) < OCR_MINIMUM_CONFIDENCE:
            continue
        xy = np.asarray(points, dtype=float)
        parts.append({
            "text": str(text),
            "normalized_text": normalize(str(text)),
            "confidence": round(float(confidence), 5),
            "box": {
                "left": float(xy[:, 0].min()) / width,
                "top": float(xy[:, 1].min()) / height,
                "right": float(xy[:, 0].max()) / width,
                "bottom": float(xy[:, 1].max()) / height,
            },
        })
    return parts


def _centre_x(box: dict[str, float]) -> float:
    return (box["left"] + box["right"]) / 2


def _interval_overlap(first: tuple[float, float], second: tuple[float, float]) -> float:
    return max(0.0, min(first[1], second[1]) - max(first[0], second[0]))


def _merge_parts(parts: list[dict[str, Any]], orientation: str) -> list[dict[str, Any]]:
    """Merge only fragments in one physical text row or text column."""
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError(f"Unsupported orientation: {orientation}")
    cross_centre = _centre_y if orientation == "horizontal" else _centre_x
    cross_start, cross_end = (("top", "bottom") if orientation == "horizontal" else ("left", "right"))
    main_start = "left" if orientation == "horizontal" else "top"
    groups: list[list[dict[str, Any]]] = []
    for part in sorted(parts, key=lambda item: (cross_centre(item["box"]), item["box"][main_start])):
        box = part["box"]
        compatible = None
        for group in groups:
            group_centre = float(np.median([cross_centre(item["box"]) for item in group]))
            group_start = min(item["box"][cross_start] for item in group)
            group_end = max(item["box"][cross_end] for item in group)
            overlap = _interval_overlap((box[cross_start], box[cross_end]), (group_start, group_end))
            smaller = min(box[cross_end] - box[cross_start], group_end - group_start)
            if abs(cross_centre(box) - group_centre) <= LINE_BASELINE_TOLERANCE and overlap / max(1e-6, smaller) >= 0.45:
                compatible = group
                break
        if compatible is None:
            compatible = []
            groups.append(compatible)
        compatible.append(part)
    result = []
    for group in groups:
        ordered = sorted(group, key=lambda item: item["box"][main_start])
        result.append({
            "orientation": orientation,
            "text": "".join(item["normalized_text"] for item in ordered),
            "box": {
                "left": min(item["box"]["left"] for item in ordered),
                "top": min(item["box"]["top"] for item in ordered),
                "right": max(item["box"]["right"] for item in ordered),
                "bottom": max(item["box"]["bottom"] for item in ordered),
            },
            "source_ocr_boxes": [{"text": item["text"], "confidence": item["confidence"], **item["box"]} for item in ordered],
        })
    return sorted(result, key=lambda item: (cross_centre(item["box"]), item["box"][main_start]))


def merge_parts_into_lines(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _merge_parts(parts, "horizontal")


def merge_parts_into_columns(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _merge_parts(parts, "vertical")


def _combined_structure(groups: list[dict[str, Any]], orientation: str) -> dict[str, Any]:
    return {
        "orientation": orientation,
        "text": "".join(group["text"] for group in groups),
        "box": {
            "left": min(group["box"]["left"] for group in groups),
            "top": min(group["box"]["top"] for group in groups),
            "right": max(group["box"]["right"] for group in groups),
            "bottom": max(group["box"]["bottom"] for group in groups),
        },
        "groups": groups,
    }


def candidate_text_structures(candidate: dict[str, Any], parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the physical row(s) or column(s) that spell the accepted text.

    A multi-row/column title is matched semantically as a whole, then returned
    as its independent physical structures.  This is the point where the old
    broad candidate rectangle is deliberately *not* used for rendering.
    """
    expected = candidate["normalized_text"]
    expected_centre = candidate["centre_normalized"]
    choices: list[tuple[float, int, list[dict[str, Any]]]] = []
    for orientation, groups in (("horizontal", merge_parts_into_lines(parts)), ("vertical", merge_parts_into_columns(parts))):
        for start in range(len(groups)):
            for end in range(start + 1, min(len(groups), start + 4) + 1):
                structure = _combined_structure(groups[start:end], orientation)
                score = SequenceMatcher(None, expected, structure["text"]).ratio()
                if score < TEXT_SIMILARITY_MIN_RATIO:
                    continue
                if abs(_centre_x(structure["box"]) - expected_centre["x"]) > POSITION_TOLERANCE_X:
                    continue
                if abs(_centre_y(structure["box"]) - expected_centre["y"]) > POSITION_TOLERANCE_Y:
                    continue
                width = structure["box"]["right"] - structure["box"]["left"]
                height = structure["box"]["bottom"] - structure["box"]["top"]
                geometry_fit = int((orientation == "horizontal" and width >= height) or (orientation == "vertical" and height > width))
                choices.append((score, geometry_fit, structure["groups"]))
    if not choices:
        return []
    # Prefer the strongest OCR reading, then the fewest physical regions.
    return max(choices, key=lambda choice: (choice[0], choice[1], -len(choice[2])))[2]


def _same_box(first: dict[str, float], second: dict[str, float]) -> bool:
    return all(abs(first[key] - second[key]) < 1e-7 for key in ("left", "top", "right", "bottom"))


def _desired_padding(text_width: float, text_height: float) -> dict[str, int]:
    """Desired stroke/glow coverage before any neighbour OCR safety limit."""
    short_side = min(text_width, text_height)
    side = min(RENDER_DESIRED_PADDING_MAX_PIXELS, max(RENDER_DESIRED_PADDING_MIN_PIXELS, int(round(short_side * RENDER_DESIRED_PADDING_SIDE_RATIO))))
    vertical = min(RENDER_DESIRED_PADDING_MAX_PIXELS, max(RENDER_DESIRED_PADDING_MIN_PIXELS, int(round(short_side * RENDER_DESIRED_PADDING_VERTICAL_RATIO))))
    return {"left": side, "right": side, "top": vertical, "bottom": vertical}


def _significant_overlap(first: tuple[float, float], second: tuple[float, float]) -> bool:
    overlap = _interval_overlap(first, second)
    return overlap / max(1e-6, min(first[1] - first[0], second[1] - second[0])) >= RENDER_BARRIER_OVERLAP_RATIO


def _blocker_record(other: dict[str, Any]) -> dict[str, Any]:
    return {key: other[key] for key in ("text", "confidence", "left", "top", "right", "bottom") if key in other}


def _safe_max_padding(stable: np.ndarray, nearby_boxes: list[dict[str, Any]], source_size: tuple[int, int]) -> tuple[dict[str, int], dict[str, dict[str, Any] | None]]:
    """Return four independent safe maxima and their nearest true barriers."""
    width, height = source_size
    left, top, right, bottom = stable
    safe = {
        "left": max(0, int(math.floor(left * width)) - RENDER_SAFETY_GAP_PIXELS),
        "right": max(0, int(math.floor((1.0 - right) * width)) - RENDER_SAFETY_GAP_PIXELS),
        "top": max(0, int(math.floor(top * height)) - RENDER_SAFETY_GAP_PIXELS),
        "bottom": max(0, int(math.floor((1.0 - bottom) * height)) - RENDER_SAFETY_GAP_PIXELS),
    }
    blockers: dict[str, dict[str, Any] | None] = {"left": None, "right": None, "top": None, "bottom": None}
    for other in nearby_boxes:
        if _significant_overlap((left, right), (other["left"], other["right"])):
            if other["bottom"] <= top:
                allowed = max(0, int(math.floor((top - other["bottom"]) * height)) - RENDER_SAFETY_GAP_PIXELS)
                if allowed < safe["top"]:
                    safe["top"], blockers["top"] = allowed, _blocker_record(other)
            if other["top"] >= bottom:
                allowed = max(0, int(math.floor((other["top"] - bottom) * height)) - RENDER_SAFETY_GAP_PIXELS)
                if allowed < safe["bottom"]:
                    safe["bottom"], blockers["bottom"] = allowed, _blocker_record(other)
        if _significant_overlap((top, bottom), (other["top"], other["bottom"])):
            if other["right"] <= left:
                allowed = max(0, int(math.floor((left - other["right"]) * width)) - RENDER_SAFETY_GAP_PIXELS)
                if allowed < safe["left"]:
                    safe["left"], blockers["left"] = allowed, _blocker_record(other)
            if other["left"] >= right:
                allowed = max(0, int(math.floor((other["left"] - right) * width)) - RENDER_SAFETY_GAP_PIXELS)
                if allowed < safe["right"]:
                    safe["right"], blockers["right"] = allowed, _blocker_record(other)
    return safe, blockers


def stable_line_regions(observations: list[dict[str, Any]], source_size: tuple[int, int], nearby_boxes: list[dict[str, float]] | None = None) -> list[dict[str, Any]]:
    """Calculate independent horizontal/vertical stable regions with MAD."""
    source_width, source_height = source_size
    nearby_boxes = nearby_boxes or []
    grouped: dict[str, list[list[dict[str, Any]]]] = {"horizontal": [], "vertical": []}
    for item in observations:
        orientation = item.get("orientation", "horizontal")
        cross_centre = _centre_y if orientation == "horizontal" else _centre_x
        target = next((group for group in grouped[orientation] if abs(cross_centre(item["box"]) - float(np.median([cross_centre(value["box"]) for value in group]))) <= LINE_BASELINE_TOLERANCE), None)
        if target is None:
            grouped[orientation].append([item])
        else:
            target.append(item)
    regions = []
    for orientation in ("horizontal", "vertical"):
        ordered_groups = sorted(grouped[orientation], key=lambda group: float(np.median([_centre_y(item["box"]) if orientation == "horizontal" else _centre_x(item["box"]) for item in group])))
        for structure_index, group in enumerate(ordered_groups):
            values = np.asarray([[item["box"][key] for key in ("left", "top", "right", "bottom")] for item in group], dtype=float)
            # OCR can occasionally return an incomplete geometry for one
            # otherwise valid candidate. A title delogo is optional: omit
            # that region instead of turning the whole composition into a
            # NumPy NaN failure.
            values = values[np.all(np.isfinite(values), axis=1)]
            if not len(values):
                continue
            median = np.median(values, axis=0)
            mad = np.median(np.abs(values - median), axis=0)
            tolerance = np.maximum(mad * 3, np.asarray([2 / source_width, 2 / source_height, 2 / source_width, 2 / source_height]))
            inliers = np.all(np.abs(values - median) <= tolerance, axis=1)
            if not np.any(inliers):
                continue
            stable = np.median(values[inliers], axis=0)
            text_height = (stable[3] - stable[1]) * source_height
            text_width = (stable[2] - stable[0]) * source_width
            desired = _desired_padding(text_width, text_height)
            safe_max, blockers = _safe_max_padding(stable, nearby_boxes, source_size)
            padding = {side: min(desired[side], safe_max[side]) for side in desired}
            final = {
                "left": max(0.0, stable[0] - padding["left"] / source_width),
                "top": max(0.0, stable[1] - padding["top"] / source_height),
                "right": min(1.0, stable[2] + padding["right"] / source_width),
                "bottom": min(1.0, stable[3] + padding["bottom"] / source_height),
            }
            region = {
                "orientation": orientation,
                "line_or_column_index": structure_index,
                "source_ocr_boxes": [{"sample_time_seconds": item["sample_time_seconds"], "boxes": item["source_ocr_boxes"]} for item, keep in zip(group, inliers) if keep],
                "source_ocr_box_count": int(inliers.sum()),
                "outlier_count": int((~inliers).sum()),
                "stable_box": {key: round(float(value), 6) for key, value in zip(("left", "top", "right", "bottom"), stable)},
                "desired_padding_left": desired["left"], "desired_padding_right": desired["right"], "desired_padding_top": desired["top"], "desired_padding_bottom": desired["bottom"],
                "safe_max_left": safe_max["left"], "safe_max_right": safe_max["right"], "safe_max_top": safe_max["top"], "safe_max_bottom": safe_max["bottom"],
                "actual_padding_left": padding["left"], "actual_padding_right": padding["right"], "actual_padding_top": padding["top"], "actual_padding_bottom": padding["bottom"],
                "nearest_blocker_left": blockers["left"], "nearest_blocker_right": blockers["right"], "nearest_blocker_top": blockers["top"], "nearest_blocker_bottom": blockers["bottom"],
                # Retain these aliases for consumers of the immediately prior
                # report schema while exposing the full adaptive audit above.
                "padding_left": padding["left"], "padding_right": padding["right"], "padding_top": padding["top"], "padding_bottom": padding["bottom"],
                "padding": {"side_ratio": RENDER_DESIRED_PADDING_SIDE_RATIO, "vertical_ratio": RENDER_DESIRED_PADDING_VERTICAL_RATIO, "safety_gap_pixels": RENDER_SAFETY_GAP_PIXELS},
                "final_delogo_box": {key: round(value, 6) for key, value in final.items()},
                **{key: round(value, 6) for key, value in final.items()},
                "effect": "ffmpeg_delogo",
            }
            region["line_index" if orientation == "horizontal" else "column_index"] = structure_index
            regions.append(region)
    return regions


def persistence_decision(sample_count: int, hits: int) -> dict[str, Any]:
    ratio = hits / sample_count if sample_count else 0.0
    accepted = sample_count > 0 and ratio >= PERSISTENCE_MIN_RATIO
    return {
        "verification_sample_count": sample_count,
        "verification_hits": hits,
        "persistence_ratio": round(ratio, 4),
        "accepted": accepted,
        "rejected": not accepted,
        "reject_reason": None if accepted else "NOT_PERSISTENT",
    }


def verify_persistence(video: Path, candidate: dict[str, Any], source_start: float, source_end: float, engine: Any) -> dict[str, Any]:
    times = verification_times(source_start, source_end)
    roi = verification_roi(candidate_box(candidate))
    capture = cv2.VideoCapture(str(video))
    hits = 0
    sampled_times: list[float] = []
    for timestamp in times:
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ok, image = capture.read()
        if not ok or image is None:
            continue
        sampled_times.append(timestamp)
        hits += int(verification_hit(candidate, roi, image, engine))
    capture.release()
    sample_count = len(sampled_times)
    return {
        **persistence_decision(sample_count, hits),
        "verification_sample_times_seconds": sampled_times,
        "verification_roi_normalized": roi,
    }


def tight_stable_render_regions(candidate: dict[str, Any], video: Path, source_size: tuple[int, int], engine: Any) -> list[dict[str, Any]]:
    """Measure render-only line boxes after acceptance; never affects Stage 2."""
    capture = cv2.VideoCapture(str(video))
    observations: list[dict[str, Any]] = []
    nearby_boxes: list[dict[str, Any]] = []
    for timestamp in candidate.get("verification_sample_times_seconds", []):
        capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp) * 1000)
        ok, image = capture.read()
        if ok and image is not None:
            # Native full-frame OCR preserves RapidOCR's original text-line
            # geometry.  The verification crop is intentionally not reused:
            # its rescaling was the source of the enlarged render rectangle.
            parts = _full_frame_ocr_parts(image, engine)
            structures = candidate_text_structures(candidate, parts)
            source_boxes = [box for structure in structures for box in structure["source_ocr_boxes"]]
            for structure in structures:
                observations.append({"sample_time_seconds": timestamp, **structure})
            nearby_boxes.extend({"text": part["text"], "confidence": part["confidence"], **part["box"]} for part in parts if not any(_same_box(part["box"], source) for source in source_boxes))
    capture.release()
    return stable_line_regions(observations, source_size, nearby_boxes) if observations else []


def detect(video: Path, report: Path, evidence_dir: Path, source_start: float, source_end: float, sample_seconds: float, sample_fps: float, active_picture: tuple[float, float, float, float] | list[float] = (0.0, 0.0, 1.0, 1.0), vision_model: str | None = DEFAULT_VLM_MODEL) -> dict[str, Any]:
    duration, native_fps = probe(video)
    if not 0 <= source_start < source_end <= duration + 0.05:
        raise RuntimeError("Invalid source range")
    normalized_active_picture = normalize_active_picture(active_picture)
    actual_seconds = min(sample_seconds, source_end - source_start)
    candidate_started = time.monotonic()
    engine = RapidOCR()
    all_detections, sampled = extract_and_ocr(video, source_start, actual_seconds, sample_fps, evidence_dir, engine)
    clusters: list[Cluster] = []
    for detection in all_detections:
        normalized = normalize(detection.text)
        if len(normalized) < 2:
            continue
        existing = next((cluster for cluster in clusters if similar_title(cluster, detection)), None)
        if existing is None:
            existing = Cluster(normalized_text=normalized)
            clusters.append(existing)
        existing.detections.append(detection)
    evaluated: list[dict[str, Any]] = []
    for cluster in clusters:
        valid, score, details = title_like(cluster, sampled)
        initial_hits = len({item.frame_time_seconds for item in cluster.detections})
        candidate = {
            "valid": valid,
            "score": score,
            **details,
            "text": cluster.normalized_text,
            "candidate_text": cluster.normalized_text,
            "candidate_box": details["bounds_normalized"],
            "initial_hits": initial_hits,
            "initial_ratio": round(initial_hits / max(1, sampled), 4),
            "detections": [asdict(item) for item in cluster.detections],
        }
        overlap_ratio = candidate_active_overlap_ratio(candidate_box(candidate), normalized_active_picture)
        candidate["active_picture_overlap_ratio"] = round(overlap_ratio, 6)
        candidate["excluded_by_active_picture"] = valid and overlap_ratio < ACTIVE_PICTURE_MIN_OVERLAP_RATIO
        evaluated.append(candidate)
    candidate_elapsed = time.monotonic() - candidate_started
    candidates = [item for item in evaluated if item["valid"] and not item["excluded_by_active_picture"]]
    verification_started = time.monotonic()
    for candidate in candidates:
        candidate.update(verify_persistence(video, candidate, source_start, source_end, engine))
    verification_elapsed = time.monotonic() - verification_started
    classification_started = time.monotonic()
    for candidate in candidates:
        candidate.update(classify_target(candidate))
    uncertain_candidates = [item for item in candidates if item["rule_class"] == "UNCERTAIN"]
    # One uncertain candidate maps to exactly one local VLM request.  Do not
    # preflight with a model "ping" or retry: an unavailable local model must
    # conservatively keep the overlay rather than create repeated batch cost.
    for candidate in uncertain_candidates:
        if vision_model:
            candidate.update(classify_uncertain_with_vlm(video, candidate, evidence_dir, vision_model))
    classification_elapsed = time.monotonic() - classification_started
    geometry = cv2.VideoCapture(str(video))
    source_size = (int(geometry.get(cv2.CAP_PROP_FRAME_WIDTH)), int(geometry.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    geometry.release()
    render_started = time.monotonic()
    for candidate in candidates:
        candidate["render_regions"] = tight_stable_render_regions(candidate, video, source_size, engine) if candidate["render"] else []
    render_elapsed = time.monotonic() - render_started
    valid_candidates = [item for item in candidates if item["render"] and item["render_regions"]]
    if valid_candidates:
        ordered = sorted(valid_candidates, key=lambda item: (item["score"], item["persistence"], len(item["normalized_text"])), reverse=True)
        winner = ordered[0]
        # A source can carry a title plus one or more persistent labels.  Keep
        # up to four distinct non-subtitle regions so a lower-scoring title is
        # not lost merely because a watermark scored higher.
        regions = []
        for candidate in ordered:
            for region in candidate["render_regions"]:
                region = {**region, "apply_from_seconds": source_start, "apply_to_seconds": source_end}
                duplicate = any(abs(region["left"] - item["left"]) < 0.002 and abs(region["top"] - item["top"]) < 0.002 and abs(region["right"] - item["right"]) < 0.002 and abs(region["bottom"] - item["bottom"]) < 0.002 for item in regions)
                if not duplicate:
                    regions.append(region)
                if len(regions) == MAX_RENDER_REGIONS:
                    break
            if len(regions) == MAX_RENDER_REGIONS:
                break
        decision = {"action": "FULL_DURATION_FIXED_TEXT_DELOGO", "title_text": winner["normalized_text"], "region": regions[0], "regions": regions, "render_regions": regions, "selected": winner}
    else:
        decision = {"action": "NO_PERSISTENT_DRAMA_TITLE", "title_text": None, "region": None, "regions": [], "selected": None}
    with video.open("rb") as source_file:
        digest = hashlib.sha256(source_file.read(1024 * 1024)).hexdigest()
    result = {
        "schema": "drama_title_region_detection_v1",
        "created_unix": int(time.time()),
        "source": {"path": str(video), "size_bytes": video.stat().st_size, "first_megabyte_sha256": digest},
        "input_range": {"start_seconds": source_start, "end_seconds": source_end, "native_duration_seconds": round(duration, 3)},
        "active_picture": normalized_active_picture,
        "sampling": {"sample_seconds": actual_seconds, "sample_fps": sample_fps, "sampled_frames": sampled, "native_fps": native_fps},
        "persistence_verification": {"sample_count_per_candidate": PERSISTENCE_VERIFICATION_SAMPLE_COUNT, "edge_fraction": PERSISTENCE_VERIFICATION_EDGE_FRACTION, "minimum_ratio": PERSISTENCE_MIN_RATIO, "ocr_scope": "candidate_roi_only"},
        "target_classification": {"vlm_model": vision_model or "disabled", "vlm_call_count": sum(1 for item in candidates if item.get("vlm_called")), "vlm_total_seconds": round(sum(float(item.get("vlm_elapsed_seconds", 0.0) or 0.0) for item in candidates), 3)},
        "timing_seconds": {"candidate_detection": round(candidate_elapsed, 3), "persistence_verification": round(verification_elapsed, 3), "target_classification": round(classification_elapsed, 3), "render_roi_measurement": round(render_elapsed, 3), "total": round(candidate_elapsed + verification_elapsed + classification_elapsed + render_elapsed, 3)},
        "decision": decision,
        "candidates": evaluated,
        "evidence_dir": str(evidence_dir),
        "source_was_modified": False,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(dump(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Find persistent drama-title region with local OCR")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--source-start", type=float, default=0.0)
    parser.add_argument("--source-end", type=float)
    parser.add_argument("--sample-seconds", type=float, default=12.0)
    parser.add_argument("--sample-fps", type=float, default=2.0)
    parser.add_argument("--active-picture", type=float, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"), default=(0.0, 0.0, 1.0, 1.0))
    parser.add_argument("--model", default=DEFAULT_VLM_MODEL)
    parser.add_argument("--disable-vlm", action="store_true", help="Use only OCR and fixed rules; never call Ollama")
    args = parser.parse_args()
    if not args.video.is_file() or args.sample_seconds <= 0 or args.sample_seconds > 20 or args.sample_fps < 1 or args.sample_fps > 6:
        raise SystemExit("Invalid arguments")
    duration, _ = probe(args.video)
    source_end = args.source_end if args.source_end is not None else duration
    evidence = args.evidence_dir or (args.report.parent / "剧名检测证据" / hashlib.sha256(str(args.video).encode("utf-8")).hexdigest()[:12])
    result = detect(args.video, args.report, evidence, args.source_start, source_end, args.sample_seconds, args.sample_fps, args.active_picture, None if args.disable_vlm else args.model)
    print(dump({"action": result["decision"]["action"], "title_text": result["decision"]["title_text"], "region": result["decision"]["region"], "report": str(args.report)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(dump({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
