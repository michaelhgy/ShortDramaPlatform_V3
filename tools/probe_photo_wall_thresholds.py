"""只读参数扫描：人脸尺寸下限 / 正面分门槛 定多少才合适。

把候选池铺一次（与真实流程同样的窗口与帧数），然后在内存里用不同参数反复挑选，
比较"选出 10 张"的质量分布，避免为每个参数组合都重跑一遍抽帧。

用法：
    py -3.12 tools/probe_photo_wall_thresholds.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.template_engine.jianying59_template import drama_face, photo_prep  # noqa: E402
from server.template_engine.jianying59_template.photo_prep import (  # noqa: E402
    FRAME_OFFSET_FRACTIONS,
    PHOTO_COUNT,
    account_day_video_sources,
    locate_source_time,
    planned_windows,
)

ACCOUNT_DAY_DIR = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)


def main() -> int:
    _, sources = account_day_video_sources(account_day_dir=ACCOUNT_DAY_DIR)
    total = sum(source.duration_seconds for source in sources)
    windows = planned_windows(total_duration=total, count=photo_prep.WINDOW_COUNT)
    print(f"素材 {len(sources)} 条 / {total:.0f} 秒；窗口 {len(windows)} × 每窗 {len(FRAME_OFFSET_FRACTIONS)} 帧\n")

    candidates: list[photo_prep.FrameCandidate] = []
    with tempfile.TemporaryDirectory(prefix="sweep_") as temporary:
        temporary_path = Path(temporary)
        for window_index, (start, end) in enumerate(windows, start=1):
            for offset_index, fraction in enumerate(FRAME_OFFSET_FRACTIONS, start=1):
                moment = start + (end - start) * fraction
                source, local = locate_source_time(sources=sources, global_time=moment)
                seconds = min(max(0.08, local), max(0.08, source.duration_seconds - 0.08))
                frame = temporary_path / f"w{window_index:02d}_{offset_index:02d}.jpg"
                photo_prep._extract_frame(source=source, time_seconds=seconds, target=frame)
                candidates.append(photo_prep._measure_frame(source=source, time_seconds=seconds, frame_path=frame))

    with_face = [item for item in candidates if item.face_count]
    print(f"候选 {len(candidates)} 张，含人脸 {len(with_face)} 张")
    print(f"  正面分 ≥0.70 : {sum(1 for item in with_face if item.frontal_score >= 0.70)}")
    print(f"  正面分 ≥0.80 : {sum(1 for item in with_face if item.frontal_score >= 0.80)}")
    print(f"  脸宽 ≥90px   : {sum(1 for item in with_face if item.face_width >= 90)}")
    print(f"  脸占画面 ≥1.5%: {sum(1 for item in with_face if (item.face_width * item.face_width * 1.33) / (item.width * item.height) >= 0.015)}")
    print()

    print(f"{'最小脸宽':>8} {'正面门槛':>8} {'选中':>4} {'正面分中位':>10} {'正面分最低':>10} {'脸宽中位':>8} {'最多同集':>8}")
    for min_face_width in (56.0, 90.0, 120.0, 150.0):
        for frontal_gate in (0.0, 0.70, 0.80, 0.88):
            pool = [item for item in candidates if item.frontal_score >= frontal_gate]
            selection = photo_prep.choose_photo_set(
                candidates=pool, count=PHOTO_COUNT, min_face_width=min_face_width, max_per_video=3,
            )
            if not selection:
                print(f"{min_face_width:>8.0f} {frontal_gate:>8.2f} {0:>4}  —")
                continue
            frontals = sorted(item.frontal_score for item in selection)
            widths = sorted(item.face_width for item in selection)
            per_video: dict[str, int] = {}
            for item in selection:
                per_video[item.source.path.name] = per_video.get(item.source.path.name, 0) + 1
            print(f"{min_face_width:>8.0f} {frontal_gate:>8.2f} {len(selection):>4} "
                  f"{frontals[len(frontals) // 2]:>10.2f} {frontals[0]:>10.2f} "
                  f"{widths[len(widths) // 2]:>8.0f} {max(per_video.values()):>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
