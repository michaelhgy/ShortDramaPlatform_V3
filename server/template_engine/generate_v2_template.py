"""Entry point for the active native Jianying 5.9 template-generator line."""

from __future__ import annotations

import argparse
from pathlib import Path

from server.template_engine.jianying59_template.project_base import build_t00_plan, probe_video
from server.template_engine.jianying59_template.track01 import create_track01_draft
from server.template_engine.jianying59_template.track02_03 import create_track03_draft
from server.template_engine.jianying59_template.track04 import create_track04_only_draft
from server.template_engine.jianying59_template.track05 import create_track05_draft
from server.template_engine.jianying59_template.final_contract import create_final_template_draft
from server.template_engine.jianying59_template.flower_style_library import default_flower_style_catalog_path
from server.template_engine.jianying59_template.sticker_skin_library import default_sticker_skin_catalog_path
from server.template_engine.jianying59_template.text_visual import create_text_visual_draft


def main() -> int:
    parser = argparse.ArgumentParser(description="剪映5.9原生模板生成器")
    parser.add_argument("--seed", type=int, required=True)
    # T06/T07/T08 are finished-video responsibilities in V2.  Keep their
    # modules as historical references, but do not expose them as production
    # stages that a task can accidentally invoke.
    parser.add_argument("--stage", choices=("final", "t00", "t01", "t02-03", "t04", "t05", "text-visual"), default="final")
    parser.add_argument("--draft-root", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--video-2", type=Path)
    parser.add_argument("--video-3", type=Path)
    parser.add_argument("--drama-image-dir", type=Path)
    parser.add_argument("--viral-account-day-dir", type=Path, help="可选：从 爆款/账号日 下按种子选一部剧，准备10张照片墙剧照")
    parser.add_argument("--photo-prep-output-dir", type=Path, help="使用 --viral-account-day-dir 时，写入新的10张剧照目录")
    parser.add_argument("--photo-cache-root", type=Path)
    parser.add_argument("--user-data-root", type=Path)
    parser.add_argument(
        "--sticker-skin-catalog", type=Path, default=default_sticker_skin_catalog_path(),
        help="由 sync_jianying59_sticker_skins.py 同步的本机贴纸皮肤库（默认用户本机运行时目录）",
    )
    parser.add_argument(
        "--flower-style-catalog", type=Path, default=default_flower_style_catalog_path(),
        help="由 sync_jianying59_flower_styles.py 同步的本机花字完整名录（默认用户本机运行时目录）",
    )
    parser.add_argument("--source-draft-name", help="text-visual 阶段要复制的已验收原生草稿名")
    args = parser.parse_args()
    plan = build_t00_plan(args.seed)
    if args.stage == "t00":
        print(plan.to_json())
        return 0
    if args.stage == "text-visual":
        if not args.draft_root or not args.name or not args.source_draft_name:
            parser.error("--stage text-visual 需要 --draft-root、--name 和 --source-draft-name")
        decision = create_text_visual_draft(
            draft_root=args.draft_root,
            source_draft_name=args.source_draft_name,
            output_draft_name=args.name,
            plan=plan,
        )
        print(decision.to_json())
        return 0
    if args.drama_image_dir and args.viral_account_day_dir:
        parser.error("--drama-image-dir 和 --viral-account-day-dir 只能提供一种剧照来源")
    photo_dir = args.drama_image_dir
    if args.viral_account_day_dir:
        if not args.photo_prep_output_dir:
            parser.error("使用 --viral-account-day-dir 还需要 --photo-prep-output-dir（必须是一个尚不存在的新目录）")
        from server.template_engine.jianying59_template.photo_prep import prepare_drama_photos
        prepared = prepare_drama_photos(
            account_day_dir=args.viral_account_day_dir,
            output_dir=args.photo_prep_output_dir,
            seed=args.seed,
        )
        photo_dir = Path(prepared.output_directory)
    if not args.draft_root or not args.name or not args.video:
        parser.error("非 t00 阶段需要 --draft-root、--name 和 --video")
    if args.stage in ("final", "t02-03", "t05"):
        if not args.video_2 or not photo_dir or not args.photo_cache_root:
            parser.error("--stage t02-03 还需要 --video-2、剧照来源（--drama-image-dir 或 --viral-account-day-dir）和 --photo-cache-root")
    if args.stage in ("final", "t05"):
        if not args.video_3:
            parser.error("--stage t05/t06 还需要 --video-3")
    if args.stage == "final":
        decision, validation = create_final_template_draft(
            draft_root=args.draft_root, draft_name=args.name, plan=plan,
            source01=probe_video(args.video), source02=probe_video(args.video_2), source03=probe_video(args.video_3),
            photo_dir=photo_dir, photo_cache_root=args.photo_cache_root, user_data_root=args.user_data_root,
            sticker_skin_catalog=args.sticker_skin_catalog,
            flower_style_catalog=args.flower_style_catalog,
        )
        print("{" + f'"templateDecision":{decision.to_json()},"structuralValidation":{validation.to_json()}' + "}")
        return 0
    if args.stage == "t05":
        track01, track04, wall, track05 = create_track05_draft(
            draft_root=args.draft_root,
            draft_name=args.name,
            plan=plan,
            source01=probe_video(args.video),
            source02=probe_video(args.video_2),
            source03=probe_video(args.video_3),
            photo_dir=photo_dir,
            photo_cache_root=args.photo_cache_root,
            user_data_root=args.user_data_root,
        )
        print("{" + f'"track01":{track01.to_json()},"photoWall":{wall.to_json()},"track04":{track04.to_json()},"track05":{track05.to_json()}' + "}")
        return 0
    if args.stage == "t02-03":
        track01, track04, wall = create_track03_draft(
            draft_root=args.draft_root,
            draft_name=args.name,
            plan=plan,
            source01=probe_video(args.video),
            source02=probe_video(args.video_2),
            photo_dir=photo_dir,
            photo_cache_root=args.photo_cache_root,
            user_data_root=args.user_data_root,
        )
        print("{" + f'"track01":{track01.to_json()},"photoWall":{wall.to_json()},"track04":{track04.to_json()}' + "}")
        return 0
    if args.stage == "t04":
        if not args.video_2:
            parser.error("--stage t04 还需要 --video-2")
        track01, track04 = create_track04_only_draft(
            draft_root=args.draft_root,
            draft_name=args.name,
            plan=plan,
            source01=probe_video(args.video),
            source02=probe_video(args.video_2),
            user_data_root=args.user_data_root,
        )
        print("{" + f'"track01":{track01.to_json()},"track04":{track04.to_json()}' + "}")
        return 0
    decision = create_track01_draft(
        draft_root=args.draft_root,
        draft_name=args.name,
        plan=plan,
        source=probe_video(args.video),
        user_data_root=args.user_data_root,
    )
    print(decision.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
