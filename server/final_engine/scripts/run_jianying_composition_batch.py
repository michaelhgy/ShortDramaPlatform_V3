#!/usr/bin/env python3
"""Create first-N real composition drafts using Jianying masks and effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from server.runtime_process import no_window_kwargs, worker_command
from typing import Any

from server.tool_resolver import resolve_ffprobe

from server.final_engine.scripts.ollama_local import ensure_local_ollama
from server.final_engine.scripts.detect_black_bars import probe_video as probe_black_bar_video, source_identity as black_bar_source_identity


SCRIPT_DIR = Path(__file__).resolve().parent
MAX_FINISHED_SECONDS = 900.0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_trace(path: Path | None, phase: str, message: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "occurred_at": datetime.now().isoformat(timespec="milliseconds"),
            "phase": phase,
            "message": message,
        }, ensure_ascii=False) + "\n")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [str(resolve_ffprobe()), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window_kwargs(),
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Cannot probe duration: {path}")
    return float(result.stdout.strip())


def natural_index(path: Path) -> int:
    match = re.search(r"(?:\s*\((\d+)\)|-(\d+))$", path.stem)
    return int(match.group(1) or match.group(2)) if match else 1_000_000


def ready_bgm_items(manifest_path: Path) -> list[dict[str, Any]]:
    """Load only local, normalized BGM assets eligible for Jianying use."""
    manifest = read_json(manifest_path)
    root = manifest_path.parent.parent
    items: list[dict[str, Any]] = []
    for raw in manifest.get("items", []):
        if not isinstance(raw, dict) or raw.get("status") != "ready" or not raw.get("music_id"):
            continue
        relative = raw.get("relative_audio_path")
        if not isinstance(relative, str) or not relative:
            continue
        path = (root / relative).resolve()
        if not path.is_file():
            continue
        item = dict(raw)
        item["path"] = str(path)
        items.append(item)
    return sorted(items, key=lambda item: str(item["music_id"]))


def recent_bgm_ids(usage_log: Path, limit: int = 50) -> set[str]:
    if not usage_log.is_file():
        return set()
    values: list[str] = []
    for line in usage_log.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("music_id"):
            values.append(str(row["music_id"]))
    return set(values[-limit:])


def select_ready_bgm(manifest_path: Path, usage_log: Path, *, seed: int, task_key: str) -> dict[str, Any]:
    candidates = ready_bgm_items(manifest_path)
    if not candidates:
        raise RuntimeError("NO_READY_BGM: ready manifest has no usable normalized local audio asset")
    fresh = [item for item in candidates if str(item["music_id"]) not in recent_bgm_ids(usage_log)]
    pool = fresh or candidates
    token = f"{seed}|{task_key}|{'|'.join(str(item['music_id']) for item in pool)}"
    index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % len(pool)
    chosen = dict(pool[index])
    chosen.update({"selection_seed": seed, "task_key": task_key, "pool_size": len(pool), "reused_due_to_pool_size": len(candidates) == 1})
    return chosen


def record_bgm_usage(usage_log: Path, item: dict[str, Any]) -> None:
    usage_log.parent.mkdir(parents=True, exist_ok=True)
    event = {"used_at_utc": datetime.now(UTC).isoformat(), "music_id": str(item["music_id"]), "title": str(item.get("title", item["music_id"])), "task_key": item["task_key"], "selection_seed": item["selection_seed"]}
    with usage_log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def replenish_ready_bgm(args: argparse.Namespace) -> dict[str, Any] | None:
    """Ensure the local BGM pool is usable before assigning any batch tracks.

    This is deliberately a local, no-GUI maintenance action.  It downloads a
    cached Jianying candidate only once, normalises it, and registers the
    resulting local audio file.  The preview URL is never passed to a draft.
    """
    if not args.bgm_ready_manifest or not args.bgm_auto_replenish:
        return None
    before = len(ready_bgm_items(args.bgm_ready_manifest))
    if before >= args.bgm_target_ready:
        return {"status": "NOT_NEEDED", "before": before, "after": before, "target": args.bgm_target_ready}
    catalogue = args.bgm_catalogue or (args.bgm_ready_manifest.parent / "剪映音乐目录V1.json")
    if not catalogue.is_file():
        raise RuntimeError(f"BGM_CATALOGUE_MISSING: {catalogue}")
    report = args.bgm_replenish_report or (args.work_dir / "BGM补库结果.json")
    command = worker_command("server.final_engine.scripts.replenish_jianying_bgm", SCRIPT_DIR / "replenish_jianying_bgm.py", [
        "--catalogue", str(catalogue),
        "--library-root", str(args.bgm_ready_manifest.parent.parent),
        "--ready-manifest", str(args.bgm_ready_manifest),
        "--target-count", str(args.bgm_target_ready),
        "--attempt-limit", str(args.bgm_replenish_attempt_limit),
        "--report", str(report),
    ])
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window_kwargs())
    after = len(ready_bgm_items(args.bgm_ready_manifest))
    status = "READY" if after >= args.bgm_target_ready else "SHORTFALL"
    # A partial pool is still usable and should not stop a composition batch.
    # The explicit summary makes the shortage visible instead of pretending
    # that repeat avoidance is possible with too few local tracks.
    return {
        "status": status, "before": before, "after": after,
        "target": args.bgm_target_ready, "report": str(report),
        "replenisher_exit_code": completed.returncode,
        "detail": (completed.stderr[-800:] or completed.stdout[-800:]).strip(),
    }


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window_kwargs())
    if result.returncode:
        detail = result.stderr[-3000:] or result.stdout[-3000:]
        text = detail.strip()
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and payload.get("error") and payload.get("message"):
                text = f"{payload['error']}: {payload['message']}"
        except json.JSONDecodeError:
            pass
        raise RuntimeError(text or f"Command failed: {command[1]}")


def opening_start(report: Path) -> float:
    decision = read_json(report).get("decision", {})
    return float(decision["cut_start_seconds"]) if decision.get("action") == "AUTO_CUT_LOCAL_VISION" else 0.0


def tail_end(report: Path, fallback: float) -> float:
    payload = read_json(report)
    decision = payload.get("decision", {})
    if decision.get("action") in {"AUTO_TRIM_TRAILING_GUIDANCE", "AUTO_TRIM_FINAL_NON_PLOT", "AUTO_TRIM_FINAL_VISUAL_ENDCARD", "AUTO_TRIM_FINAL_OCR_ENDCARD"}:
        return float(decision["trim_end_seconds"])
    return float(payload.get("input_range", {}).get("end_seconds", fallback))


def active_picture_from_crop_decision(decision: dict[str, Any], *, width: int, height: int) -> dict[str, float]:
    try:
        detected = bool(decision["black_bar_detected"])
        crop_top, crop_bottom = int(decision["crop_top"]), int(decision["crop_bottom"])
        crop_left, crop_right = int(decision["crop_left"]), int(decision["crop_right"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Black bar report decision is incomplete") from exc
    if min(crop_top, crop_bottom, crop_left, crop_right) < 0 or crop_top + crop_bottom >= height or crop_left + crop_right >= width:
        raise RuntimeError("Black bar report crop geometry is invalid")
    if detected != bool(crop_top or crop_bottom):
        raise RuntimeError("Black bar report detection flag does not match crop geometry")
    if not detected:
        return {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
    return {"left": crop_left / width, "top": crop_top / height, "right": 1.0 - crop_right / width, "bottom": 1.0 - crop_bottom / height}


def active_picture_from_black_bar_report(report: Path, source: Path) -> dict[str, float]:
    payload = read_json(report)
    if payload.get("schema") != "black_bar_detection_v1":
        raise RuntimeError("Black bar report schema is invalid")
    reported = payload.get("source")
    if not isinstance(reported, dict):
        raise RuntimeError("Black bar report source identity is missing")
    if Path(str(reported.get("path", ""))).resolve() != source.resolve():
        raise RuntimeError("Black bar report source path does not match current video")
    duration, width, height = probe_black_bar_video(source)
    expected = black_bar_source_identity(source, duration=duration, width=width, height=height)
    for key in ("size_bytes", "first_megabyte_sha256", "width", "height"):
        if reported.get(key) != expected[key]:
            raise RuntimeError(f"Black bar report source identity mismatch: {key}")
    try:
        reported_duration = float(reported["duration_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Black bar report source duration is invalid") from exc
    if abs(reported_duration - float(expected["duration_seconds"])) > 0.05:
        raise RuntimeError("Black bar report source identity mismatch: duration_seconds")
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        raise RuntimeError("Black bar report decision is missing")
    return active_picture_from_crop_decision(decision, width=width, height=height)


def finished_output_name(source: Path) -> str:
    """Map current `剧名-n` and legacy `剧名 (n)` clips to `剧名-n.mp4`."""
    match = re.search(r"(?:\s*\((\d+)\)|-(\d+))$", source.stem)
    if match:
        return f"{source.stem[:match.start()].rstrip()}-{match.group(1) or match.group(2)}.mp4"
    return f"{source.stem}-1.mp4"


def exact_source_file(path: Path | None) -> Path:
    """Validate the production-owned source before any detector can run."""
    if path is None or not str(path).strip():
        raise ValueError("Requested viral_source_path is empty")
    if not path.is_file():
        raise ValueError(f"Requested viral_source_path is not a file: {path}")
    try:
        with path.open("rb") as source:
            source.read(1)
    except OSError as exc:
        raise ValueError(f"Requested viral_source_path is not readable: {path}: {exc}") from exc
    return path


def selected_sources(*, viral_dir: Path | None, start_index: int, count: int, source_file: Path | None) -> list[Path]:
    """Keep explicit production selection separate from legacy folder batches."""
    if source_file is not None:
        return [exact_source_file(source_file)]
    if viral_dir is None:
        raise ValueError("Folder batch mode requires --viral-dir")
    sources = sorted(
        (item for item in viral_dir.iterdir()
         if item.suffix.lower() in {".mp4", ".mov", ".mkv"} and natural_index(item) >= start_index),
        key=natural_index,
    )[:count]
    if len(sources) != count:
        raise ValueError(f"Only found {len(sources)} clips from index {start_index}; requested {count}")
    return sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch create Jianying composition drafts from real viral inputs")
    parser.add_argument("--viral-dir", type=Path, help="Folder batch mode input")
    parser.add_argument("--source-file", type=Path, help="Exact production source; never falls back to folder selection")
    parser.add_argument("--template-video", required=True, type=Path)
    parser.add_argument("--pairing", required=True, type=Path)
    parser.add_argument("--draft-root", required=True, type=Path)
    parser.add_argument("--user-data-root", required=True, type=Path)
    parser.add_argument("--real-photo-dir", required=True, type=Path)
    parser.add_argument("--real-photo-files", default="", help="JSON array of six task-reserved real-photo paths")
    parser.add_argument("--draft-prefix", required=True)
    parser.add_argument("--draft-suffix", default="_成片草稿", help="Suffix after the source ordinal; use a unique test suffix only for disposable drafts")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--midroll", required=True, type=Path)
    parser.add_argument("--endroll", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--trace-path", type=Path, help="仅供上层任务诊断读取的过程记录")
    parser.add_argument("--local-vision-ai-mode", choices=("compatibility", "quality", "disabled"), default="compatibility")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--start-index", type=int, default=1, help="Natural clip number to begin from, inclusive")
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--bgm-id", default="")
    parser.add_argument("--bgm-title", default="")
    parser.add_argument("--bgm-ready-manifest", type=Path, help="Per-video local-ready BGM selection manifest")
    parser.add_argument("--bgm-usage-log", type=Path, help="Write only after the individual draft succeeds")
    parser.add_argument("--bgm-seed", type=int, default=0, help="Deterministic base seed for per-video BGM selection")
    parser.add_argument("--bgm-catalogue", type=Path, help="Jianying cached catalogue used only to replenish the local ready pool")
    parser.add_argument("--bgm-target-ready", type=int, default=20, help="Automatically replenish the local ready pool to this count")
    parser.add_argument("--bgm-replenish-attempt-limit", type=int, default=50)
    parser.add_argument("--bgm-replenish-report", type=Path)
    parser.add_argument("--no-bgm-auto-replenish", dest="bgm_auto_replenish", action="store_false", help="Do not replenish the local ready BGM pool before this batch")
    parser.add_argument("--export-queue", type=Path, help="Optional shared Jianying queue; creates one finished-video job after each draft")
    parser.add_argument("--finished-output-dir", type=Path, help="Required with --export-queue; final directory for this drama")
    parser.set_defaults(bgm_auto_replenish=True)
    args = parser.parse_args()
    write_trace(args.trace_path, "检查成片条件", "正在检查成片草稿所需的素材和路径")
    if args.count < 1:
        raise SystemExit("--count must be at least 1")
    if args.start_index < 1:
        raise SystemExit("--start-index must be at least 1")
    if not args.draft_suffix or any(character in args.draft_suffix for character in '<>:"/\\|?*'):
        raise SystemExit("--draft-suffix is empty or contains an illegal Windows path character")
    if args.source_file is None and args.viral_dir is None:
        raise SystemExit("Specify --source-file or --viral-dir")
    for path in (args.template_video, args.pairing, args.draft_root, args.user_data_root, args.real_photo_dir, args.midroll, args.endroll):
        if not path.exists():
            raise SystemExit(f"Required path missing: {path}")
    if args.bgm and not args.bgm.is_file():
        raise SystemExit(f"BGM missing: {args.bgm}")
    if args.bgm and args.bgm_ready_manifest:
        raise SystemExit("Use either fixed --bgm or per-video --bgm-ready-manifest, not both")
    if args.bgm_ready_manifest and not args.bgm_ready_manifest.is_file():
        raise SystemExit(f"BGM ready manifest missing: {args.bgm_ready_manifest}")
    if args.bgm_ready_manifest and args.bgm_usage_log is None:
        raise SystemExit("--bgm-usage-log is required with --bgm-ready-manifest")
    if args.bgm_target_ready < 1 or args.bgm_replenish_attempt_limit < 1:
        raise SystemExit("BGM replenishment counts must be positive")
    if (args.export_queue is None) != (args.finished_output_dir is None):
        raise SystemExit("--export-queue and --finished-output-dir must be supplied together")
    if args.finished_output_dir and not args.finished_output_dir.is_dir():
        raise SystemExit(f"Finished output directory does not exist: {args.finished_output_dir}")
    try:
        sources = selected_sources(
            viral_dir=args.viral_dir, start_index=args.start_index, count=args.count, source_file=args.source_file,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    source_budget = MAX_FINISHED_SECONDS - probe_duration(args.midroll) - probe_duration(args.endroll)
    if source_budget <= 120:
        raise SystemExit("Insertion media leave no usable viral budget")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    # The batch is also a supported manual entry point, so it cannot rely on
    # the V1 worker being the only caller that starts Ollama.
    vision_model = {"compatibility": "qwen2.5vl:3b", "quality": "qwen2.5vl:7b"}.get(args.local_vision_ai_mode)
    if vision_model:
        write_trace(args.trace_path, "启动本地视觉服务", "正在确认本地视觉分析服务可用")
        ensure_local_ollama(vision_model)
    write_trace(args.trace_path, "准备背景音乐", "正在准备本次成片草稿需要的背景音乐")
    bgm_pool = replenish_ready_bgm(args)
    results: list[dict[str, Any]] = []
    for source in sources:
        ordinal = natural_index(source)
        draft_name = f"{args.draft_prefix}-{ordinal}{args.draft_suffix}"
        if (args.draft_root / draft_name).exists():
            results.append({"source": str(source), "status": "SKIPPED_EXISTING", "draft_name": draft_name})
            continue
        item_dir = args.work_dir / f"{ordinal:02d}"
        reports = item_dir / "检测报告"
        evidence = item_dir / "检测证据"
        reports.mkdir(parents=True, exist_ok=True)
        cover_report = reports / "片头封面.json"
        tail_report = reports / "片尾引导.json"
        black_bar_report = reports / "黑边检测.json"
        title_report = reports / "剧名区域.json"
        proxy = item_dir / f"{source.stem}_清理代理.mp4"
        proxy_report = reports / "清理代理.json"
        draft_report = reports / "剪映成片草稿.json"
        try:
            write_trace(args.trace_path, "分析片头", f"正在分析素材 {source.name} 的片头")
            selected_bgm = None
            if args.bgm_ready_manifest:
                selected_bgm = select_ready_bgm(
                    args.bgm_ready_manifest, args.bgm_usage_log,
                    seed=args.bgm_seed, task_key=f"{args.draft_prefix}:{ordinal}",
                )
            opening_command = worker_command("server.final_engine.scripts.detect_opening_cover", SCRIPT_DIR / "detect_opening_cover.py", ["--video", str(source), "--report", str(cover_report), "--evidence-dir", str(evidence / "片头")])
            if vision_model:
                opening_command.extend(["--model", vision_model])
            else:
                opening_command.append("--disable-vlm")
            run(opening_command)
            start = opening_start(cover_report)
            capped_end = min(probe_duration(source), start + source_budget)
            write_trace(args.trace_path, "分析片尾", f"正在分析素材 {source.name} 的片尾")
            run(worker_command("server.final_engine.scripts.detect_tail_guidance", SCRIPT_DIR / "detect_tail_guidance.py", ["--video", str(source), "--report", str(tail_report),
                "--evidence-dir", str(evidence / "片尾"), "--source-start", f"{start:.6f}", "--source-end", f"{capped_end:.6f}",
            ]))
            end = tail_end(tail_report, capped_end)
            write_trace(args.trace_path, "检测画面边缘", f"正在检查素材 {source.name} 的黑边")
            run(worker_command("server.final_engine.scripts.detect_black_bars", SCRIPT_DIR / "detect_black_bars.py", ["--video", str(source), "--report", str(black_bar_report)]))
            active_picture = active_picture_from_black_bar_report(black_bar_report, source)
            title_command = worker_command("server.final_engine.scripts.detect_drama_title_region", SCRIPT_DIR / "detect_drama_title_region.py", ["--video", str(source), "--report", str(title_report),
                "--evidence-dir", str(evidence / "剧名"), "--source-start", f"{start:.6f}", "--source-end", f"{end:.6f}",
                "--active-picture", f"{active_picture['left']:.9f}", f"{active_picture['top']:.9f}", f"{active_picture['right']:.9f}", f"{active_picture['bottom']:.9f}",
            ])
            if vision_model:
                title_command.extend(["--model", vision_model])
            else:
                title_command.append("--disable-vlm")
            write_trace(args.trace_path, "识别剧名区域", f"正在识别素材 {source.name} 的剧名区域")
            run(title_command)
            command = worker_command("server.final_engine.scripts.generate_composition_from_detection_reports", SCRIPT_DIR / "generate_composition_from_detection_reports.py", [
                "--viral-source", str(source), "--cover-report", str(cover_report), "--tail-report", str(tail_report), "--title-report", str(title_report), "--black-bar-report", str(black_bar_report),
                "--clean-proxy", str(proxy), "--clean-proxy-report", str(proxy_report),
                "--template-video", str(args.template_video), "--pairing", str(args.pairing),
                "--draft-root", str(args.draft_root), "--draft-name", draft_name, "--account-id", args.account_id,
                "--user-data-root", str(args.user_data_root),
                "--real-photo-dir", str(args.real_photo_dir),
                "--real-photo-files", args.real_photo_files,
                "--midroll", str(args.midroll), "--endroll", str(args.endroll), "--report", str(draft_report),
            ])
            if args.bgm:
                command.extend(["--bgm", str(args.bgm), "--bgm-id", args.bgm_id, "--bgm-title", args.bgm_title])
            elif selected_bgm:
                command.extend([
                    "--bgm", str(selected_bgm["path"]), "--bgm-id", str(selected_bgm["music_id"]),
                    "--bgm-title", str(selected_bgm.get("title", selected_bgm["music_id"])),
                ])
            write_trace(args.trace_path, "写入成片草稿", f"正在生成素材 {source.name} 的剪映成片草稿")
            run(command)
            export_job = None
            if args.export_queue and args.finished_output_dir:
                output = args.finished_output_dir / finished_output_name(source)
                export_task = item_dir / "导出任务"
                run(worker_command("server.final_engine.scripts.prepare_finished_video_export", SCRIPT_DIR / "prepare_finished_video_export.py", [
                    "--composition-report", str(draft_report), "--task-root", str(export_task),
                    "--output", str(output), "--queue", str(args.export_queue),
                    "--queue-job-id", f"finished-{hashlib.sha256(str(output).encode('utf-8')).hexdigest()[:20]}",
                ]))
                export_job = str(export_task / "成片导出任务.json")
            if selected_bgm:
                record_bgm_usage(args.bgm_usage_log, selected_bgm)
            results.append({
                "source": str(source), "status": "STRUCTURAL_PASS_VISUAL_PENDING", "draft_name": draft_name,
                "draft_path": str(args.draft_root / draft_name), "report": str(draft_report),
                "export_job": export_job,
                "bgm": ({"music_id": selected_bgm["music_id"], "title": selected_bgm.get("title"), "pool_size": selected_bgm["pool_size"], "reused_due_to_pool_size": selected_bgm["reused_due_to_pool_size"]} if selected_bgm else None),
            })
            write_trace(args.trace_path, "成片草稿完成", f"素材 {source.name} 的剪映成片草稿已完成")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            write_trace(args.trace_path, "成片草稿失败", f"素材 {source.name}：{detail}")
            results.append({"source": str(source), "status": "FAILED", "error": detail})
    summary = {
        "schema": "jianying_composition_batch_v1", "requested_count": len(sources),
        "completed_count": sum(row["status"] == "STRUCTURAL_PASS_VISUAL_PENDING" for row in results), "source_budget_seconds": round(source_budget, 3),
        "template": str(args.template_video), "pairing": str(args.pairing), "bgm_pool": bgm_pool, "results": results,
    }
    (args.work_dir / "批量结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # The report itself remains UTF-8.  Console output must stay ASCII-safe so
    # a GBK Windows host cannot turn a completed batch into a false failure.
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0 if not any(row["status"] == "FAILED" for row in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
