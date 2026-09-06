#!/usr/bin/env python3
"""Compose a Jianying draft from local detection reports without touching source media.

The cleaned proxy is the only viral input passed to the existing draft builder,
so trims and the source-relative title mosaic cannot be accidentally omitted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from server.runtime_process import no_window_kwargs, worker_command


SCRIPT_DIR = Path(__file__).resolve().parent


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window_kwargs())
    if result.returncode:
        detail = result.stderr[-2500:] or result.stdout[-2500:]
        raise RuntimeError(detail.strip() or f"Command failed: {command[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a composition draft from cover/tail/title local reports")
    parser.add_argument("--viral-source", required=True, type=Path)
    parser.add_argument("--cover-report", required=True, type=Path)
    parser.add_argument("--tail-report", required=True, type=Path)
    parser.add_argument("--title-report", required=True, type=Path)
    parser.add_argument("--black-bar-report", required=True, type=Path)
    parser.add_argument("--clean-proxy", required=True, type=Path)
    parser.add_argument("--clean-proxy-report", required=True, type=Path)
    parser.add_argument("--template-video", required=True, type=Path)
    parser.add_argument("--pairing", required=True, type=Path)
    parser.add_argument("--draft-root", required=True, type=Path)
    parser.add_argument("--user-data-root", required=True, type=Path)
    parser.add_argument("--jianying-app-root", required=True, type=Path)
    parser.add_argument("--real-photo-dir", required=True, type=Path)
    parser.add_argument("--real-photo-files", default="", help="JSON array of six task-reserved real-photo paths")
    parser.add_argument("--draft-name", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--midroll", type=Path, help="Insert after 120 seconds of cleaned viral content")
    parser.add_argument("--endroll", type=Path, help="Append after cleaned viral content")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--bgm-id", default="")
    parser.add_argument("--bgm-title", default="")
    parser.add_argument("--overwrite-clean-proxy", action="store_true")
    args = parser.parse_args()

    required = [
        args.viral_source, args.cover_report, args.tail_report, args.title_report, args.black_bar_report,
        args.template_video, args.pairing,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Missing required input(s): " + "; ".join(missing))
    if args.bgm and not args.bgm.is_file():
        raise SystemExit(f"BGM does not exist: {args.bgm}")
    if (args.midroll is None) != (args.endroll is None):
        raise SystemExit("--midroll and --endroll must be supplied together")
    for path in (args.midroll, args.endroll):
        if path is not None and not path.is_file():
            raise SystemExit(f"Insertion media does not exist: {path}")
    if args.clean_proxy.exists() and not args.overwrite_clean_proxy:
        raise SystemExit(f"Refusing to overwrite existing clean proxy: {args.clean_proxy}")

    clean_command = worker_command("server.final_engine.scripts.prepare_clean_viral_proxy", SCRIPT_DIR / "prepare_clean_viral_proxy.py", [
        "--source", str(args.viral_source),
        "--cover-report", str(args.cover_report),
        "--tail-report", str(args.tail_report),
        "--title-report", str(args.title_report),
        "--black-bar-report", str(args.black_bar_report),
        "--output", str(args.clean_proxy),
        "--report", str(args.clean_proxy_report),
    ])
    if args.overwrite_clean_proxy:
        clean_command.append("--overwrite")
    run(clean_command)

    base_report = args.report.with_suffix(args.report.suffix + ".native59.json")
    compose_command = worker_command("server.final_engine.scripts.generate_jianying59_composition_draft", SCRIPT_DIR / "generate_jianying59_composition_draft.py", [
        "--viral", str(args.clean_proxy),
        "--template-video", str(args.template_video),
        "--pairing", str(args.pairing),
        "--draft-root", str(args.draft_root),
        "--user-data-root", str(args.user_data_root),
        "--jianying-app-root", str(args.jianying_app_root),
        "--real-photo-dir", str(args.real_photo_dir),
        "--real-photo-files", args.real_photo_files,
        "--draft-name", args.draft_name,
        "--account-id", args.account_id,
        "--report", str(base_report),
    ])
    if args.bgm:
        compose_command.extend(["--bgm", str(args.bgm), "--bgm-id", args.bgm_id, "--bgm-title", args.bgm_title])
    if args.midroll:
        compose_command.extend(["--midroll", str(args.midroll), "--endroll", str(args.endroll)])
    run(compose_command)

    clean = read_json(args.clean_proxy_report)
    base = read_json(base_report)
    result = {
        "status": base["status"],
        "schema": "composition_from_detection_reports_v1",
        "draft_path": base["draft_path"],
        "draft_name": args.draft_name,
        "source_unchanged": True,
        "source": str(args.viral_source),
        "clean_proxy": clean,
        "detection_reports": {
            "cover": str(args.cover_report), "tail": str(args.tail_report), "title": str(args.title_report), "black_bar": str(args.black_bar_report),
        },
        "composition": base["composition"],
        "next_actions": [] if args.midroll else ["insert_midroll", "append_endroll"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
