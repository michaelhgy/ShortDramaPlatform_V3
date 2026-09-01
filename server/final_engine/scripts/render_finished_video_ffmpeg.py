#!/usr/bin/env python3
"""Render one accepted composition layout directly with FFmpeg/NVENC.

The input viral video must already be a clean proxy created from the local
cover/tail/title reports.  This renderer deliberately never edits sources.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from server.tool_resolver import resolve_ffmpeg, resolve_ffprobe


CANVAS_W, CANVAS_H = 1080, 2400
MIDROLL_SECONDS = 120.0
# FFmpeg's filter parser needs exactly one backslash before the drive colon.
# A raw literal keeps that Windows-specific escape unambiguous.
FONT = r"C\:/Windows/Fonts/msyh.ttc"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [str(resolve_ffprobe()), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Cannot read duration: {path}")
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise RuntimeError(f"Invalid duration: {path}")
    return duration


def escaped_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", r"\'").replace(":", r"\:")


def window_geometry(pairing: dict[str, Any]) -> dict[str, int]:
    bounds = pairing["central_window"]["canvas_pixel_bounds"]
    # Follow the established pairing contract: viral content extends 8 px
    # horizontally and 13 px vertically beneath the template edge feather.
    left = max(0, round(float(bounds["left"]) - 8))
    right = min(CANVAS_W, round(float(bounds["right"]) + 8))
    top = max(0, round(float(bounds["top"]) - 13))
    bottom = min(CANVAS_H, round(float(bounds["bottom"]) + 13))
    width, height = right - left, bottom - top
    if width < 2 or height < 2:
        raise RuntimeError("Invalid central window in pairing JSON")
    return {"left": left, "top": top, "right": right, "bottom": bottom, "width": width, "height": height}


def padded_video(label: str, input_index: int, *, start: float | None = None, end: float | None = None) -> tuple[str, str]:
    trim = ""
    if start is not None and end is not None:
        trim = f"trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,"
    video = (
        f"[{input_index}:v]{trim}fps=30,scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,"
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[{label}v]"
    )
    if start is None:
        audio = f"[{input_index}:a]aresample=44100,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[{label}a]"
    else:
        audio = (
            f"[{input_index}:a]atrim=start={start:.6f}:end={end:.6f},aresample=44100,"
            f"aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[{label}a]"
        )
    return video, audio


def text_filters(window: dict[str, int], account_id: str) -> list[str]:
    warning_x = min(window["right"] - 250, window["left"] + 100)
    warning_y = window["top"] + 22
    filters = [
        f"drawtext=fontfile='{FONT}':text='影视效果请勿模仿':fontcolor=white@0.6:fontsize=24:x={warning_x}:y={warning_y}",
    ]
    # Use one glyph per drawtext filter for a true vertical disclosure label.
    disclosure_x = window["right"] - 42
    disclosure_y = window["bottom"] - 7 * 30 - 24
    for index, glyph in enumerate("内容由AI制作"):
        filters.append(
            f"drawtext=fontfile='{FONT}':text='{glyph}':fontcolor=white@0.6:fontsize=24:x={disclosure_x}:y={disclosure_y + index * 30}"
        )
    # Closed 32-second sinusoidal path: visually moves yet returns to origin.
    account = escaped_text(account_id)
    filters.append(
        f"drawtext=fontfile='{FONT}':text='{account}':fontcolor=white@0.5:fontsize=22:"
        "x=(w-text_w)/2+420*sin(2*PI*t/32):y=(h-text_h)/2+850*sin(2*PI*t/16)"
    )
    return filters


def build_graph(clean_duration: float, mid_duration: float, end_duration: float,
                total: float, window: dict[str, int], account_id: str, use_bgm: bool) -> str:
    if clean_duration <= MIDROLL_SECONDS:
        raise RuntimeError("MIDROLL_POSITION_REVIEW_REQUIRED: cleaned viral content is not longer than 120 seconds")
    pre_v, pre_a = padded_video("pre", 0, start=0.0, end=MIDROLL_SECONDS)
    post_v, post_a = padded_video("post", 0, start=MIDROLL_SECONDS, end=clean_duration)
    mid_v, mid_a = padded_video("mid", 2)
    end_v, end_a = padded_video("end", 3)
    template = f"[1:v]trim=duration={total:.6f},setpts=PTS-STARTPTS,fps=30,setsar=1[template]"
    timeline = (
        f"{pre_v};{pre_a};{mid_v};{mid_a};{post_v};{post_a};{end_v};{end_a};"
        f"[prev][prea][midv][mida][postv][posta][endv][enda]concat=n=4:v=1:a=1[storyv][storya]"
    )
    crop = (
        f"[storyv]crop=w={window['width']}:h={window['height']}:x={window['left']}:y={window['top']}[viralwindow];"
        f"[template][viralwindow]overlay=x={window['left']}:y={window['top']}:eof_action=pass"
    )
    visuals = ",".join(text_filters(window, account_id)) + "[finalv]"
    if use_bgm:
        audio = (
            f"[4:a]atrim=duration={total:.6f},aresample=44100,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[bgm];"
            "[storya][bgm]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[finala]"
        )
    else:
        audio = "[storya]anull[finala]"
    return ";".join([timeline, template, crop + "," + visuals, audio])


def render(args: argparse.Namespace) -> dict[str, Any]:
    for path in (args.clean_viral, args.template_video, args.midroll, args.endroll, args.pairing):
        if not path.is_file():
            raise RuntimeError(f"Required input missing: {path}")
    if args.bgm and not args.bgm.is_file():
        raise RuntimeError(f"BGM missing: {args.bgm}")
    if args.output.exists() and not args.overwrite:
        raise RuntimeError(f"Refusing to overwrite output: {args.output}")
    pairing = read_json(args.pairing)
    window = window_geometry(pairing)
    clean_duration = probe_duration(args.clean_viral)
    mid_duration, end_duration = probe_duration(args.midroll), probe_duration(args.endroll)
    total = clean_duration + mid_duration + end_duration
    graph = build_graph(clean_duration, mid_duration, end_duration, total, window, args.account_id, args.bgm is not None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_suffix(args.output.suffix + ".partial.mp4")
    if partial.exists():
        partial.unlink()
    command = [
        str(resolve_ffmpeg()), "-y", "-i", str(args.clean_viral), "-stream_loop", "-1", "-i", str(args.template_video),
        "-i", str(args.midroll), "-i", str(args.endroll),
    ]
    if args.bgm:
        command.extend(["-stream_loop", "-1", "-i", str(args.bgm)])
    command.extend(["-filter_complex", graph, "-map", "[finalv]", "-map", "[finala]"])
    nvenc = command + ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "-b:v", "0", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(partial)]
    result = subprocess.run(nvenc, capture_output=True, text=True, encoding="utf-8", errors="replace")
    encoder = "h264_nvenc"
    if result.returncode:
        cpu = command + ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(partial)]
        result = subprocess.run(cpu, capture_output=True, text=True, encoding="utf-8", errors="replace")
        encoder = "libx264"
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    partial.replace(args.output)
    output_duration = probe_duration(args.output)
    report = {
        "status": "RENDERED_TEST_VISUAL_PENDING", "schema": "ffmpeg_finished_composition_v1",
        "output": str(args.output), "encoder": encoder, "duration_seconds": round(output_duration, 3),
        "clean_viral_seconds": round(clean_duration, 3), "midroll_seconds": round(mid_duration, 3),
        "endroll_seconds": round(end_duration, 3), "midroll_insert_seconds": MIDROLL_SECONDS,
        "central_window_with_overlap_px": window, "template_pairing": str(args.pairing),
        "account_id": args.account_id, "bgm": str(args.bgm) if args.bgm else None,
        "source_files_modified": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Render one direct FFmpeg finished-video test")
    parser.add_argument("--clean-viral", required=True, type=Path)
    parser.add_argument("--template-video", required=True, type=Path)
    parser.add_argument("--pairing", required=True, type=Path)
    parser.add_argument("--midroll", required=True, type=Path)
    parser.add_argument("--endroll", required=True, type=Path)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    report = render(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
