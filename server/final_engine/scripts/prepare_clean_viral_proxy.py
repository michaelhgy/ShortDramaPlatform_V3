#!/usr/bin/env python3
"""Render a non-destructive, trimmed and tightly de-logoed viral proxy via FFmpeg."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from server.tool_resolver import resolve_ffmpeg, resolve_ffprobe

try:
    from .detect_black_bars import probe_video as probe_black_bar_video
    from .detect_black_bars import source_identity as black_bar_source_identity
except ImportError:  # Direct script execution from the batch runner.
    from detect_black_bars import probe_video as probe_black_bar_video
    from detect_black_bars import source_identity as black_bar_source_identity


DELOGO_EDGE_PIXELS = 2
BLACK_BAR_REPORT_SCHEMA = "black_bar_detection_v1"
IDENTITY_DURATION_TOLERANCE_SECONDS = 0.05


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [str(resolve_ffprobe()), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Cannot probe {path}")
    return float(result.stdout.strip())


def probe_geometry(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            str(resolve_ffprobe()), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Cannot probe video geometry: {path}")
    values = result.stdout.strip().split(",")
    if len(values) != 2:
        raise RuntimeError(f"Unexpected video geometry: {result.stdout!r}")
    width, height = (int(value) for value in values)
    if width < 2 or height < 2:
        raise RuntimeError(f"Invalid video geometry: {width}x{height}")
    return width, height


def decision_start(report: dict[str, Any]) -> float:
    decision = report.get("decision", {})
    if decision.get("action") == "AUTO_CUT_LOCAL_VISION":
        return float(decision["cut_start_seconds"])
    return 0.0


def decision_end(report: dict[str, Any], fallback: float) -> float:
    decision = report.get("decision", {})
    if decision.get("action") in {"AUTO_TRIM_TRAILING_GUIDANCE", "AUTO_TRIM_FINAL_NON_PLOT", "AUTO_TRIM_FINAL_VISUAL_ENDCARD", "AUTO_TRIM_FINAL_OCR_ENDCARD"}:
        return float(decision["trim_end_seconds"])
    # The tail detector is deliberately run only on the already budget-capped
    # source range.  "No trailing guidance" therefore means "keep that cap",
    # never "restore the original full source".
    input_range = report.get("input_range", {})
    capped_end = input_range.get("end_seconds")
    if capped_end is not None:
        return float(capped_end)
    return fallback


def title_regions(report: dict[str, Any]) -> list[dict[str, float]]:
    decision = report.get("decision", {})
    if decision.get("action") not in {"FULL_DURATION_TITLE_MOSAIC", "FULL_DURATION_FIXED_TEXT_BLUR", "FULL_DURATION_FIXED_TEXT_DELOGO"}:
        return []
    raw_regions = decision.get("regions")
    if not isinstance(raw_regions, list):
        raw_regions = [decision.get("region")]
    result = []
    for region in raw_regions:
        if isinstance(region, dict) and all(key in region for key in ("left", "top", "right", "bottom")):
            result.append({key: float(region[key]) for key in ("left", "top", "right", "bottom")})
    return result[:4]


def validate_black_bar_report(report: dict[str, Any], source: Path) -> dict[str, int]:
    """Return the accepted source-pixel crop, refusing a stale report."""
    if report.get("schema") != BLACK_BAR_REPORT_SCHEMA:
        raise RuntimeError("Black-bar report has an unexpected schema")
    duration, width, height = probe_black_bar_video(source)
    expected = black_bar_source_identity(source, duration=duration, width=width, height=height)
    reported = report.get("source")
    if not isinstance(reported, dict):
        raise RuntimeError("Black-bar report has no source identity")
    for key in ("path", "size_bytes", "first_megabyte_sha256", "width", "height"):
        if reported.get(key) != expected[key]:
            raise RuntimeError(f"Black-bar report source identity mismatch: {key}")
    try:
        reported_duration = float(reported["duration_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Black-bar report has an invalid source duration") from exc
    if abs(reported_duration - float(expected["duration_seconds"])) > IDENTITY_DURATION_TOLERANCE_SECONDS:
        raise RuntimeError("Black-bar report source identity mismatch: duration_seconds")

    decision = report.get("decision")
    if not isinstance(decision, dict) or not isinstance(decision.get("black_bar_detected"), bool):
        raise RuntimeError("Black-bar report has no valid decision")
    crop: dict[str, int] = {}
    for key in ("crop_top", "crop_bottom", "crop_left", "crop_right"):
        value = decision.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeError(f"Black-bar report has an invalid {key}")
        crop[key.removeprefix("crop_")] = value
    if crop["left"] + crop["right"] >= width or crop["top"] + crop["bottom"] >= height:
        raise RuntimeError("Black-bar report crop removes the whole picture")
    has_crop = any(crop.values())
    if decision["black_bar_detected"] != has_crop:
        raise RuntimeError("Black-bar report detection flag does not match its crop")
    return crop


def applied_encoder_safe_crop(detected_crop: dict[str, int], source_size: tuple[int, int]) -> dict[str, int]:
    """Keep an even H.264 geometry by retaining at most one extra edge pixel."""
    applied = dict(detected_crop)
    if not any(applied.values()):
        return applied
    width, height = source_size
    for dimension, first_edge, second_edge in ((width, "right", "left"), (height, "bottom", "top")):
        output_size = dimension - applied[first_edge] - applied[second_edge]
        if output_size <= 0:
            raise RuntimeError("Black-bar crop leaves no encodable picture")
        if output_size % 2:
            # Never remove an additional picture pixel: retain one pixel from a
            # detected black edge, deterministically preferring right/bottom.
            if applied[first_edge] > 0:
                applied[first_edge] -= 1
            elif applied[second_edge] > 0:
                applied[second_edge] -= 1
            else:
                raise RuntimeError("Cannot make cropped geometry even without extra picture crop")
    return applied


def expected_geometry(source_size: tuple[int, int], crop: dict[str, int]) -> tuple[int, int]:
    width, height = source_size
    result = (width - crop["left"] - crop["right"], height - crop["top"] - crop["bottom"])
    if result[0] < 2 or result[1] < 2 or result[0] % 2 or result[1] % 2:
        raise RuntimeError(f"Invalid encoder geometry after black-bar crop: {result[0]}x{result[1]}")
    return result


def filter_graph(start: float, end: float, regions: list[dict[str, float]], source_size: tuple[int, int], crop: dict[str, int] | None = None) -> str:
    trimmed = f"trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS"
    crop = crop or {"left": 0, "top": 0, "right": 0, "bottom": 0}
    needs_crop = any(crop.values())
    if not regions:
        if not needs_crop:
            return f"[0:v]{trimmed}[v]"
        width, height = expected_geometry(source_size, crop)
        return f"[0:v]{trimmed},crop=w={width}:h={height}:x={crop['left']}:y={crop['top']}[v]"
    # Render regions are already tight stable text-line boxes.  Clamp only for
    # FFmpeg safety; do not expand them into a cross-frame envelope here.
    source_width, source_height = source_size
    graph = f"[0:v]{trimmed}[base0]"
    for index, region in enumerate(regions):
        left, top, right, bottom = (region[key] for key in ("left", "top", "right", "bottom"))
        x = min(max(DELOGO_EDGE_PIXELS, round(source_width * left)), source_width - DELOGO_EDGE_PIXELS - 2)
        y = min(max(DELOGO_EDGE_PIXELS, round(source_height * top)), source_height - DELOGO_EDGE_PIXELS - 2)
        right_px = min(source_width - DELOGO_EDGE_PIXELS, max(x + 2, round(source_width * right)))
        bottom_px = min(source_height - DELOGO_EDGE_PIXELS, max(y + 2, round(source_height * bottom)))
        width, height = max(2, right_px - x), max(2, bottom_px - y)
        graph += f";[base{index}]delogo=x={x}:y={y}:w={width}:h={height}:show=0[base{index + 1}]"
    if not needs_crop:
        return graph + f";[base{len(regions)}]null[v]"
    width, height = expected_geometry(source_size, crop)
    return graph + f";[base{len(regions)}]crop=w={width}:h={height}:x={crop['left']}:y={crop['top']}[v]"


def run_ffmpeg(source: Path, output: Path, start: float, end: float, regions: list[dict[str, float]], crop: dict[str, int]) -> tuple[int, int]:
    partial = output.with_suffix(output.suffix + ".partial.mp4")
    if partial.exists():
        partial.unlink()
    source_size = probe_geometry(source)
    expected = expected_geometry(source_size, crop)
    graph = filter_graph(start, end, regions, source_size, crop)
    common = [
        str(resolve_ffmpeg()), "-y", "-i", str(source), "-filter_complex", graph,
        "-map", "[v]", "-map", "0:a?", "-af", f"atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(partial),
    ]
    # RTX machines use NVENC; fall back to a portable CPU encode on another PC.
    nvenc = common[:-1] + ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-b:v", "0"] + common[-1:]
    result = subprocess.run(nvenc, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        cpu = common[:-1] + ["-c:v", "libx264", "-preset", "medium", "-crf", "18"] + common[-1:]
        result = subprocess.run(cpu, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    if not partial.is_file() or probe_duration(partial) <= 0:
        raise RuntimeError("FFmpeg did not produce a readable proxy")
    actual = probe_geometry(partial)
    if actual != expected:
        raise RuntimeError(f"FFmpeg proxy geometry mismatch: expected {expected[0]}x{expected[1]}, got {actual[0]}x{actual[1]}")
    partial.replace(output)
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Create clean viral proxy without modifying source")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--cover-report", required=True, type=Path)
    parser.add_argument("--tail-report", required=True, type=Path)
    parser.add_argument("--title-report", required=True, type=Path)
    parser.add_argument("--black-bar-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit(f"Source does not exist: {args.source}")
    if args.output.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite: {args.output}")
    cover, tail, title, black_bar = (read_json(path) for path in (args.cover_report, args.tail_report, args.title_report, args.black_bar_report))
    source_duration = probe_duration(args.source)
    start = decision_start(cover)
    end = decision_end(tail, source_duration)
    if not 0 <= start < end <= source_duration + 0.05:
        raise SystemExit(f"Invalid cleaned range: {start}..{end}, source={source_duration}")
    regions = title_regions(title)
    detected_crop = validate_black_bar_report(black_bar, args.source)
    applied_crop = applied_encoder_safe_crop(detected_crop, probe_geometry(args.source))
    expected_output_width, expected_output_height = expected_geometry(probe_geometry(args.source), applied_crop)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    actual_output_width, actual_output_height = run_ffmpeg(args.source, args.output, start, end, regions, applied_crop)
    result = {
        "schema": "clean_viral_proxy_v1",
        "source": str(args.source),
        "output": str(args.output),
        "source_duration_seconds": round(source_duration, 3),
        "source_range_seconds": {"start": start, "end": end},
        "output_duration_seconds": round(probe_duration(args.output), 3),
        "black_bar_report": str(args.black_bar_report),
        "detected_crop": detected_crop,
        "applied_crop": applied_crop,
        "expected_output_geometry": {"width": expected_output_width, "height": expected_output_height},
        "actual_output_geometry": {"width": actual_output_width, "height": actual_output_height},
        "title_region_normalized": regions[0] if regions else None,
        "title_regions_normalized": regions,
        "overlay_redaction_effect": "ffmpeg_delogo_tight_stable_roi",
        "source_was_modified": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
