#!/usr/bin/env python3
"""Run the local detection-to-FFmpeg test flow for the first N viral clips."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
MAX_FINISHED_SECONDS = 900.0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Cannot probe duration: {path}")
    return float(result.stdout.strip())


def natural_index(path: Path) -> int:
    match = re.search(r"\((\d+)\)$", path.stem)
    return int(match.group(1)) if match else 1_000_000


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        detail = result.stderr[-3000:] or result.stdout[-3000:]
        raise RuntimeError(detail.strip() or f"Command failed: {command[1]}")


def report_decision_start(report: Path) -> float:
    data = read_json(report)
    decision = data.get("decision", {})
    return float(decision.get("cut_start_seconds", 0.0)) if decision.get("action") == "AUTO_CUT_LOCAL_VISION" else 0.0


def report_decision_end(report: Path, fallback: float) -> float:
    data = read_json(report)
    decision = data.get("decision", {})
    if decision.get("action") == "AUTO_TRIM_TRAILING_GUIDANCE":
        return float(decision["trim_end_seconds"])
    return float(data.get("input_range", {}).get("end_seconds", fallback))


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch render direct FFmpeg composition tests")
    parser.add_argument("--viral-dir", required=True, type=Path)
    parser.add_argument("--template-video", required=True, type=Path)
    parser.add_argument("--pairing", required=True, type=Path)
    parser.add_argument("--midroll", required=True, type=Path)
    parser.add_argument("--endroll", required=True, type=Path)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.count < 1:
        raise SystemExit("--count must be at least 1")
    for path in (args.viral_dir, args.template_video, args.pairing, args.midroll, args.endroll):
        if not path.exists():
            raise SystemExit(f"Required path missing: {path}")
    sources = sorted((path for path in args.viral_dir.iterdir() if path.suffix.lower() in {".mp4", ".mov", ".mkv"}), key=natural_index)[:args.count]
    if len(sources) < args.count:
        raise SystemExit(f"Only found {len(sources)} source videos; requested {args.count}")
    mid_duration, end_duration = probe_duration(args.midroll), probe_duration(args.endroll)
    source_budget = MAX_FINISHED_SECONDS - mid_duration - end_duration
    if source_budget <= 120:
        raise SystemExit("Mid-roll and end-roll leave no usable viral budget")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for source in sources:
        ordinal = natural_index(source)
        item_dir = args.work_dir / f"{ordinal:02d}"
        evidence = item_dir / "检测证据"
        reports = item_dir / "检测报告"
        item_dir.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        cover_report = reports / "片头封面.json"
        tail_report = reports / "片尾引导.json"
        title_report = reports / "剧名区域.json"
        proxy = item_dir / f"{source.stem}_清理代理.mp4"
        proxy_report = reports / "清理代理.json"
        output = item_dir / f"{source.stem}-FFmpeg成片测试.mp4"
        render_report = reports / "FFmpeg成片.json"
        try:
            if not args.overwrite and any(path.exists() for path in (proxy, output)):
                raise RuntimeError("Existing proxy or output found; rerun only with --overwrite after review")
            run([
                sys.executable, str(SCRIPT_DIR / "detect_opening_cover.py"), "--video", str(source),
                "--report", str(cover_report), "--evidence-dir", str(evidence / "片头"),
            ])
            start = report_decision_start(cover_report)
            original_duration = probe_duration(source)
            capped_end = min(original_duration, start + source_budget)
            run([
                sys.executable, str(SCRIPT_DIR / "detect_tail_guidance.py"), "--video", str(source),
                "--report", str(tail_report), "--evidence-dir", str(evidence / "片尾"),
                "--source-start", f"{start:.6f}", "--source-end", f"{capped_end:.6f}",
            ])
            end = report_decision_end(tail_report, capped_end)
            run([
                sys.executable, str(SCRIPT_DIR / "detect_drama_title_region.py"), "--video", str(source),
                "--report", str(title_report), "--evidence-dir", str(evidence / "剧名"),
                "--source-start", f"{start:.6f}", "--source-end", f"{end:.6f}",
            ])
            clean = [
                sys.executable, str(SCRIPT_DIR / "prepare_clean_viral_proxy.py"), "--source", str(source),
                "--cover-report", str(cover_report), "--tail-report", str(tail_report),
                "--title-report", str(title_report), "--output", str(proxy), "--report", str(proxy_report),
            ]
            if args.overwrite:
                clean.append("--overwrite")
            run(clean)
            render = [
                sys.executable, str(SCRIPT_DIR / "render_finished_video_ffmpeg.py"), "--clean-viral", str(proxy),
                "--template-video", str(args.template_video), "--pairing", str(args.pairing),
                "--midroll", str(args.midroll), "--endroll", str(args.endroll), "--account-id", args.account_id,
                "--output", str(output), "--report", str(render_report),
            ]
            if args.bgm:
                render.extend(["--bgm", str(args.bgm)])
            if args.overwrite:
                render.append("--overwrite")
            run(render)
            results.append({"source": str(source), "status": "RENDERED_TEST_VISUAL_PENDING", "output": str(output), "report": str(render_report)})
        except Exception as exc:
            results.append({"source": str(source), "status": "FAILED", "error": str(exc)})
            break
    summary = {
        "schema": "ffmpeg_composition_batch_v1", "requested_count": args.count,
        "completed_count": sum(item["status"] != "FAILED" for item in results), "source_budget_seconds": round(source_budget, 3),
        "midroll": str(args.midroll), "endroll": str(args.endroll), "template": str(args.template_video),
        "pairing": str(args.pairing), "results": results,
    }
    summary_path = args.work_dir / "批量结果.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["completed_count"] == args.count else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
