"""只读对比脚本：**老选图逻辑 vs 新选图逻辑**，同一批候选帧并排出图。

纪律（2026-09-18 踩过坑）：候选帧必须用**真实流程的函数**取，不能自己复刻一遍取数逻辑，
否则诊断结论会和真实运行相反。本脚本调用：
``account_day_video_sources`` / ``planned_windows`` / ``locate_source_time`` / ``_extract_frame`` / ``_measure_frame``。

不改生产数据；输出写到指定目录（默认系统临时目录）。
用法：
    py -3.12 tools/compare_photo_wall_crop.py [输出目录]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.template_engine.jianying59_template import drama_face, photo_prep  # noqa: E402

ACCOUNT_DAY_DIR = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)
TILE = (270, 360)  # 每个对比格子的尺寸，3:4


def _old_crop(image):
    """2026-09-18 之前的裁切写法：四舍五入 + 画面居中（会差 1 像素）。"""
    width, height = image.size
    if width / height > 3 / 4:
        crop_width = round(height * 3 / 4)
        left = (width - crop_width) // 2
        return (left, 0, left + crop_width, height)
    crop_height = round(width / (3 / 4))
    top = (height - crop_height) // 2
    return (0, top, width, top + crop_height)


def _old_pick(candidates):
    """2026-09-18 之前的挑图写法：只看清晰度与明暗，**完全不看人**。"""
    return max(candidates, key=lambda item: (item.sharpness, -item.exposure_penalty))


def _best_face_of(frame_path: Path, image):
    import cv2
    import numpy

    faces = drama_face.detect_faces(
        cv2.imdecode(numpy.fromfile(str(frame_path), dtype=numpy.uint8), cv2.IMREAD_COLOR)
    )
    return max(faces, key=lambda item: item.area) if faces else None


def main() -> int:
    from PIL import Image, ImageDraw

    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "photo_wall_compare"
    output.mkdir(parents=True, exist_ok=True)

    dramas, sources = photo_prep.account_day_video_sources(account_day_dir=ACCOUNT_DAY_DIR)
    total = sum(source.duration_seconds for source in sources)
    print(f"剧集目录 {len(dramas)} 个，视频 {len(sources)} 条，合计 {total:.0f} 秒")
    windows = photo_prep.planned_windows(total_duration=total, count=photo_prep.WINDOW_COUNT)
    print(f"窗口 {len(windows)} 个，每窗 {len(photo_prep.FRAME_OFFSET_FRACTIONS)} 帧\n")

    tiles = []
    with tempfile.TemporaryDirectory(prefix="photo_compare_") as temporary:
        temporary_path = Path(temporary)
        for window_index, (start, end) in enumerate(windows, start=1):
            candidates: list[tuple[object, Path]] = []
            for offset_index, fraction in enumerate(photo_prep.FRAME_OFFSET_FRACTIONS, start=1):
                moment = start + (end - start) * fraction
                source, local = photo_prep.locate_source_time(sources=sources, global_time=moment)
                seconds = min(max(0.08, local), max(0.08, source.duration_seconds - 0.08))
                frame = temporary_path / f"w{window_index:02d}_{offset_index:02d}.jpg"
                photo_prep._extract_frame(source=source, time_seconds=seconds, target=frame)
                candidates.append((photo_prep._measure_frame(source=source, time_seconds=seconds, frame_path=frame), frame))
            if not candidates:
                continue

            old_choice = _old_pick([measured for measured, _path in candidates])
            new_choice = max(candidates, key=lambda item: (item[0].face_score, item[0].sharpness))[0]
            old_path = next(path for measured, path in candidates if measured is old_choice)
            new_path = next(path for measured, path in candidates if measured is new_choice)

            with Image.open(old_path) as raw:
                raw = raw.convert("RGB")
                old_tile = raw.crop(_old_crop(raw)).resize(TILE, Image.LANCZOS)
            with Image.open(new_path) as raw:
                raw = raw.convert("RGB")
                width, height = raw.size
                face = _best_face_of(new_path, raw)
                box = (
                    drama_face.face_centered_crop_box(image_width=width, image_height=height, face=face)
                    if face is not None else drama_face.center_crop_box(image_width=width, image_height=height)
                )
                new_tile = raw.crop(box).resize(TILE, Image.LANCZOS)

            cell = Image.new("RGB", (TILE[0] * 2 + 6, TILE[1]), (30, 30, 36))
            cell.paste(old_tile, (0, 0))
            cell.paste(new_tile, (TILE[0] + 6, 0))
            draw = ImageDraw.Draw(cell)
            draw.text((6, 6), f"OLD win{window_index} face={old_choice.face_count}", fill=(255, 90, 90))
            draw.text((TILE[0] + 12, 6), f"NEW face={new_choice.face_count}", fill=(120, 255, 120))
            tiles.append(cell)
            print(f"  窗口 {window_index:>2}: 老选 face={old_choice.face_count} 清晰度={old_choice.sharpness:.0f}"
                  f"  |  新选 face={new_choice.face_count} 人脸分={new_choice.face_score:.3f}")

    if not tiles:
        raise SystemExit("没有生成任何对比图")
    columns = 2
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * (TILE[0] * 2 + 6) + 8, rows * (TILE[1] + 8)), (16, 16, 20))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * (TILE[0] * 2 + 14) + 4, (index // columns) * (TILE[1] + 8) + 4))
    target = output / "对比_老选图_vs_人脸选图.png"
    sheet.save(target)
    print(f"\n对比图：{target}")
    print("左 = 老逻辑（只看清晰度、画面居中裁切）；右 = 新逻辑（优先挑人脸、以人脸为中心裁切）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
