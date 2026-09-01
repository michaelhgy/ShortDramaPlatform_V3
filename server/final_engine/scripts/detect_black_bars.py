#!/usr/bin/env python3
"""Detect persistent top/bottom black bars and write a compact production report.

The detection rules in this module are the accepted temporal-row-coverage
rules.  They deliberately use original-video pixel coordinates in the result
and never create diagnostic media.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np


SAMPLE_PERCENTS = (5, 13, 21, 29, 37, 45, 55, 63, 71, 79, 87, 95)
LOW_WIDTH = 224
IGNORE_X_FRACTION = 0.03
SMOOTHING_KERNEL = 5
DARK_THRESHOLD = 58.0
ROW_COVERAGE_THRESHOLD = 0.80
REQUIRED_DARK_COUNT = math.ceil(len(SAMPLE_PERCENTS) * ROW_COVERAGE_THRESHOLD)
MAX_GAP_ROWS = 2
REFINE_WINDOW = 15
SAFETY_MARGIN = 2
MINIMUM_ACTIONABLE_CROP_FRACTION = 0.005


def probe_video(path: Path) -> tuple[float, int, int]:
    if not path.is_file():
        raise FileNotFoundError(f"Video does not exist: {path}")
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path),
    ]
    data = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))
    stream = data["streams"][0]
    duration, width, height = float(data["format"]["duration"]), int(stream["width"]), int(stream["height"])
    if duration <= 0 or width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid video metadata: {path}")
    return duration, width, height


def read_frame(path: Path, sample_time: float) -> np.ndarray:
    capture = cv2.VideoCapture(str(path))
    capture.set(cv2.CAP_PROP_POS_MSEC, sample_time * 1000.0)
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        raise RuntimeError(f"Cannot decode sample at {sample_time:.3f}s: {path}")
    return frame


def row_profile(frame: np.ndarray, width: int = LOW_WIDTH) -> np.ndarray:
    height = round(frame.shape[0] * width / frame.shape[1])
    gray = cv2.cvtColor(cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    ignored = max(1, round(width * IGNORE_X_FRACTION))
    values = np.median(gray[:, ignored:width - ignored], axis=1).astype(np.float64)
    return cv2.medianBlur(values.astype(np.float32).reshape(-1, 1), SMOOTHING_KERNEL).reshape(-1).astype(np.float64)


def edge_extent(dark_rows: np.ndarray, side: Literal["top", "bottom"]) -> int:
    ordered = dark_rows if side == "top" else dark_rows[::-1]
    last_dark = -1
    gap = 0
    for index, is_dark in enumerate(ordered):
        if is_dark:
            last_dark = index
            gap = 0
        else:
            gap += 1
            if gap > MAX_GAP_ROWS:
                break
    return last_dark + 1


def local_refinement(profile: np.ndarray, low_boundary: int, low_height: int, original_height: int, side: Literal["top", "bottom"]) -> int | None:
    expected = round(low_boundary * original_height / low_height)
    ordered = profile <= DARK_THRESHOLD if side == "top" else (profile <= DARK_THRESHOLD)[::-1]
    start = max(0, expected - REFINE_WINDOW)
    end = min(original_height, expected + REFINE_WINDOW + 1)
    local_extent = edge_extent(ordered[start:end], "top")
    return None if local_extent == 0 else start + local_extent


def representative_indices() -> tuple[int, int, int]:
    return (0, len(SAMPLE_PERCENTS) // 2, len(SAMPLE_PERCENTS) - 1)


def safe_refined_boundary(path: Path, sample_times: list[float], low_boundary: int, low_height: int, original_height: int, side: Literal["top", "bottom"]) -> int:
    candidates: list[int | None] = []
    for index in representative_indices():
        frame = read_frame(path, sample_times[index])
        candidates.append(local_refinement(row_profile(frame, width=frame.shape[1]), low_boundary, low_height, original_height, side))
    valid = [value for value in candidates if value is not None]
    fallback = round(low_boundary * original_height / low_height)
    return min([fallback, *valid])


def minimum_actionable_crop(height: int) -> int:
    return math.ceil(height * MINIMUM_ACTIONABLE_CROP_FRACTION)


def apply_minimum_actionable_crop(crop: int, height: int) -> int:
    return crop if crop >= minimum_actionable_crop(height) else 0


def source_identity(path: Path, *, duration: float, width: int, height: int) -> dict[str, Any]:
    with path.open("rb") as source_file:
        digest = hashlib.sha256(source_file.read(1024 * 1024)).hexdigest()
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "first_megabyte_sha256": digest,
        "width": width,
        "height": height,
        "duration_seconds": round(duration, 6),
    }


def detect(video_path: Path, output_report_path: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    duration, width, height = probe_video(video_path)
    sample_times = [duration * percent / 100.0 for percent in SAMPLE_PERCENTS]
    profiles = [row_profile(read_frame(video_path, sample_time)) for sample_time in sample_times]
    matrix = np.stack(profiles)
    dark_counts = np.count_nonzero(matrix <= DARK_THRESHOLD, axis=0)
    common_rows = dark_counts >= REQUIRED_DARK_COUNT
    low_height = int(matrix.shape[1])
    top_low = edge_extent(common_rows, "top")
    bottom_low = edge_extent(common_rows, "bottom")
    top_refined = safe_refined_boundary(video_path, sample_times, top_low, low_height, height, "top") if top_low else 0
    bottom_refined = safe_refined_boundary(video_path, sample_times, bottom_low, low_height, height, "bottom") if bottom_low else 0
    threshold = minimum_actionable_crop(height)
    crop_top = max(0, top_refined - SAFETY_MARGIN) if top_refined else 0
    crop_bottom = max(0, bottom_refined - SAFETY_MARGIN) if bottom_refined else 0
    crop_top = apply_minimum_actionable_crop(crop_top, height)
    crop_bottom = apply_minimum_actionable_crop(crop_bottom, height)
    report = {
        "schema": "black_bar_detection_v1",
        "source": source_identity(video_path, duration=duration, width=width, height=height),
        "decision": {
            "black_bar_detected": bool(crop_top or crop_bottom),
            "crop_top": crop_top,
            "crop_bottom": crop_bottom,
            "crop_left": 0,
            "crop_right": 0,
            "minimum_actionable_crop": threshold,
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
    }
    if output_report_path is not None:
        output_report_path.parent.mkdir(parents=True, exist_ok=True)
        output_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect persistent top/bottom black bars without creating diagnostic media")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = detect(args.video, args.report)
    print(json.dumps({"black_bar_detected": result["decision"]["black_bar_detected"], "report": str(args.report)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
