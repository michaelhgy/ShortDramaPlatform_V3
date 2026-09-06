"""Create one project-owned native Jianying 5.9 finished-video draft."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


from server.final_engine.jianying59_final.composition import build_plan, probe_media, report_payload, write_native_draft


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one native Jianying 5.9 finished-video draft")
    parser.add_argument("--viral", required=True, type=Path)
    parser.add_argument("--template-video", required=True, type=Path)
    parser.add_argument("--pairing", required=True, type=Path)
    parser.add_argument("--draft-root", required=True, type=Path)
    parser.add_argument("--user-data-root", required=True, type=Path)
    parser.add_argument("--jianying-app-root", required=True, type=Path)
    parser.add_argument("--real-photo-dir", required=True, type=Path)
    parser.add_argument("--real-photo-files", default="", help="JSON array of the six reserved image paths")
    parser.add_argument("--draft-name", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--midroll", required=True, type=Path)
    parser.add_argument("--endroll", required=True, type=Path)
    parser.add_argument("--bgm", required=True, type=Path)
    parser.add_argument("--bgm-id", default="")
    parser.add_argument("--bgm-title", default="")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if not args.draft_name or any(character in args.draft_name for character in '<>:"/\\|?*'):
        raise ValueError("成片草稿名称为空或含非法Windows路径字符")
    for path in (args.viral, args.template_video, args.pairing, args.midroll, args.endroll, args.bgm):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not args.user_data_root.is_dir():
        raise NotADirectoryError(f"剪映User Data目录不存在：{args.user_data_root}")
    if not args.jianying_app_root.is_dir():
        raise NotADirectoryError(f"剪映程序资源目录不存在：{args.jianying_app_root}")
    if not args.real_photo_dir.is_dir():
        raise NotADirectoryError(f"真人图片素材库不存在：{args.real_photo_dir}")
    pairing = json.loads(args.pairing.read_text(encoding="utf-8-sig"))
    real_photo_files = [Path(str(item)) for item in json.loads(args.real_photo_files or "[]")]
    plan = build_plan(
        viral=probe_media(args.viral), template=probe_media(args.template_video), pairing=pairing,
        account_id=args.account_id, midroll=probe_media(args.midroll), endroll=probe_media(args.endroll),
        bgm=probe_media(args.bgm, audio_only=True), bgm_id=args.bgm_id, bgm_title=args.bgm_title,
        real_photo_dir=args.real_photo_dir, real_photo_files=real_photo_files or None,
    )
    draft_path = write_native_draft(plan=plan, draft_root=args.draft_root, draft_name=args.draft_name,
                                    user_data_root=args.user_data_root,
                                    jianying_app_root=args.jianying_app_root)
    report = report_payload(plan=plan, draft_path=draft_path, draft_name=args.draft_name)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Frozen workers have no console for Python's default traceback.  Send
        # the real cause back to the parent process instead of only exit code 1.
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
