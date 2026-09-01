from __future__ import annotations

"""Create one durable finished-video export job without touching Jianying.

The composition builder has already fixed the timeline, duration, and output
identity. This script validates those facts, writes an independent controller
job next to the composition task, then optionally enqueues it in the shared
serial Jianying export queue. It never opens a draft, starts a render, or
overwrites a finished video.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_SCRIPTS = SCRIPT_DIR.parents[2] / "template_factory" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from export_template_video import PROFILE  # noqa: E402
from jianying_export_queue import READY, enqueue_job  # noqa: E402


JOB_NAME = "成片导出任务.json"
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,127}$")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def expected_duration(report: dict[str, Any]) -> float:
    duration_us = report.get("composition", {}).get("duration_microseconds")
    if not isinstance(duration_us, int) or duration_us <= 0:
        raise ValueError("composition report has no positive composition.duration_microseconds")
    return round(duration_us / 1_000_000, 6)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a no-GUI finished-video Jianying export job")
    parser.add_argument("--composition-report", type=Path)
    parser.add_argument("--draft-dir", type=Path, help="Use a known draft directly for recovery/testing.")
    parser.add_argument("--draft-name", help="Required with --draft-dir when the folder name differs from Jianying's display name.")
    parser.add_argument("--expected-duration-seconds", type=float, help="Required with --draft-dir.")
    parser.add_argument("--task-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--queue-job-id")
    parser.add_argument("--replace-pending", action="store_true")
    args = parser.parse_args()

    if bool(args.composition_report) == bool(args.draft_dir):
        raise ValueError("provide exactly one of --composition-report or --draft-dir")
    report_path: Path | None = None
    report: dict[str, Any] | None = None
    if args.composition_report:
        report_path = args.composition_report.resolve()
        report = read_json(report_path)
        if report.get("status") != "STRUCTURAL_PASS_VISUAL_PENDING":
            raise ValueError(f"composition report is not structurally ready: {report.get('status')!r}")
        draft_path = Path(str(report.get("draft_path", ""))).resolve()
        draft_name = str(report["draft_name"])
        duration = expected_duration(report)
    else:
        draft_path = args.draft_dir.resolve()
        if not args.expected_duration_seconds or args.expected_duration_seconds <= 0:
            raise ValueError("--draft-dir requires a positive --expected-duration-seconds")
        draft_name = args.draft_name or draft_path.name
        duration = round(args.expected_duration_seconds, 6)
    if not draft_path.is_dir():
        raise FileNotFoundError(f"composition draft does not exist: {draft_path}")
    output = args.output.resolve()
    if output.suffix.casefold() != ".mp4":
        raise ValueError("--output must end in .mp4")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite finished video: {output}")
    task_root = args.task_root.resolve()
    job_path = task_root / JOB_NAME
    if job_path.exists() and not args.replace_pending:
        existing = read_json(job_path)
        if existing.get("status") not in {"EXPORT_VERIFIED", "FAILED", "PAUSED_BY_DOUBLE_ESC", "PAUSED_EXTERNAL_MODAL", "PAUSED_NEEDS_DRAFT_OPEN"}:
            raise FileExistsError(f"unfinished export job already exists: {job_path}")
    job = {
        "schema_version": 1,
        "kind": "finished_video",
        "status": "PENDING_USER_START",
        "created_at": now(),
        "draft_name": draft_name,
        "draft_path": str(draft_path),
        "output_path": str(output),
        "expected_duration_seconds": duration,
        "profile": PROFILE,
        "composition_report_path": str(report_path) if report_path else None,
        "human_input_policy": "double_esc_only_within_1_second_during_foreground_control",
        "foreground_contract": "The fixed controller releases keyboard and mouse immediately after Jianying accepts export.",
        "events": [{"at": now(), "status": "PENDING_USER_START", "detail": "finished-video export prepared"}],
    }
    write_json(job_path, job)
    if args.queue:
        queue = args.queue.resolve()
        job_id = args.queue_job_id or "finished-" + hashlib.sha256(f"{draft_path}|{output}".encode("utf-8")).hexdigest()[:20]
        if not JOB_ID_RE.fullmatch(job_id):
            raise ValueError("queue job id must contain only ASCII letters, digits, dot, dash, underscore")
        queue_job = {
            "job_id": job_id,
            "kind": "finished_video",
            "status": READY,
            "created_at": now(),
            "updated_at": now(),
            "draft_path": str(draft_path),
            "draft_name": draft_name,
            "output_path": str(output),
            "expected_duration_seconds": duration,
            "profile": PROFILE,
            "source_task_path": str(task_root),
            "controller_job_path": str(job_path),
            "foreground_policy": "double_esc_only_within_1_second",
            "events": [{"at": now(), "status": READY, "detail": "finished-video export prepared"}],
        }
        enqueue_job(queue, queue_job)
        job["shared_queue"] = {"path": str(queue), "job_id": job_id, "status": READY}
        write_json(job_path, job)
    print(json.dumps({"status": "PENDING_USER_START", "job": str(job_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
