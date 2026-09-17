"""Entry point for the active native Jianying 5.9 template-generator line."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from server.template_engine.jianying59_template.project_base import build_t00_plan, probe_video
from server.template_engine.jianying59_template.track01 import create_track01_draft
from server.template_engine.jianying59_template.track02_03 import create_track03_draft
from server.template_engine.jianying59_template.track04 import create_track04_only_draft
from server.template_engine.jianying59_template.track05 import create_track05_draft
from server.template_engine.jianying59_template.final_contract import create_final_template_draft
from server.template_engine.jianying59_template.flower_style_library import resolve_flower_style_catalog_path
from server.template_engine.jianying59_template.sticker_skin_library import resolve_sticker_skin_catalog_path
from server.template_engine.jianying59_template.text_visual import create_text_visual_draft
from server.template_engine.jianying59_template.template_copy import load_template_copy


def _trace(path: Path | None, phase: str, message: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "occurred_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "phase": phase,
            "message": message,
        }, ensure_ascii=False) + "\n")


def _trace_path_from_argv() -> Path | None:
    try:
        index = sys.argv.index("--trace-path")
        return Path(sys.argv[index + 1])
    except (ValueError, IndexError):
        return None


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
        "--sticker-skin-catalog", type=Path, default=resolve_sticker_skin_catalog_path(),
        help="优先使用本机更新的贴纸皮肤库；否则使用 V2 内置的已验证基础清单",
    )
    parser.add_argument(
        "--flower-style-catalog", type=Path, default=resolve_flower_style_catalog_path(),
        help="优先使用本机更新的花字库；否则使用 V2 内置的已验证基础清单",
    )
    parser.add_argument("--source-draft-name", help="text-visual 阶段要复制的已验收原生草稿名")
    parser.add_argument(
        "--template-copy", type=Path,
        help="可选：模板文案配置文件（blessing / drama_prompt 字符串数组；空数组=不要该轨道）",
    )
    parser.add_argument("--trace-path", type=Path, help="仅供上层任务诊断读取的过程记录")
    args = parser.parse_args()
    _trace(args.trace_path, "准备模板方案", "正在生成本次模板随机方案")
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
        _trace(args.trace_path, "准备剧照", "正在从真人素材中准备模板剧照")
        prepared = prepare_drama_photos(
            account_day_dir=args.viral_account_day_dir,
            output_dir=args.photo_prep_output_dir,
            seed=args.seed,
            progress=lambda phase, message: _trace(args.trace_path, phase, message),
        )
        photo_dir = Path(prepared.output_directory)
        _trace(args.trace_path, "剧照准备完成", "模板剧照已准备完成")
    if not args.draft_root or not args.name or not args.video:
        parser.error("非 t00 阶段需要 --draft-root、--name 和 --video")
    if args.stage in ("t02-03", "t05"):
        if not args.video_2 or not photo_dir or not args.photo_cache_root:
            parser.error("--stage t02-03 还需要 --video-2、剧照来源（--drama-image-dir 或 --viral-account-day-dir）和 --photo-cache-root")
    if args.stage == "t05":
        if not args.video_3:
            parser.error("--stage t05 还需要 --video-3")
    if args.stage == "final":
        if not photo_dir or not args.photo_cache_root:
            parser.error("--stage final 需要剧照来源（--drama-image-dir 或 --viral-account-day-dir）和 --photo-cache-root")
    if args.stage == "final":
        _trace(args.trace_path, "检查视频素材", "正在读取真人视频的时长和参数")
        source01 = probe_video(args.video)
        blessing_pool, drama_prompt_pool = load_template_copy(path=args.template_copy)
        _trace(args.trace_path, "写入模板草稿", "正在生成剪映模板草稿和轨道内容")
        decision, validation = create_final_template_draft(
            draft_root=args.draft_root, draft_name=args.name, plan=plan,
            source01=source01,
            photo_dir=photo_dir, photo_cache_root=args.photo_cache_root, user_data_root=args.user_data_root,
            sticker_skin_catalog=args.sticker_skin_catalog,
            flower_style_catalog=args.flower_style_catalog,
            blessing_pool=blessing_pool, drama_prompt_pool=drama_prompt_pool,
        )
        _trace(args.trace_path, "模板草稿完成", "剪映模板草稿和结构检查均已完成")
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
    try:
        raise SystemExit(main())
    except Exception as exc:  # Keep frozen worker failures in the task diagnostic instead of a GUI crash dialog.
        _trace(_trace_path_from_argv(), "失败", f"{type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1) from exc
