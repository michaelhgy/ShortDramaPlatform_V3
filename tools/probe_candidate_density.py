"""只读诊断：候选密度扫描 —— 要多密的采样才能凑齐 10 张"高正面分"的剧照。

思路：一次性把**很密**的候选池铺出来（48 窗口 × 6 帧 = 288 张），
然后按不同的窗口数"抽样"出 24/36/48 窗口的子集，比较各门槛下的可用帧数。
这样只跑一次抽帧就能看出密度的影响。

用法：
    py -3.12 tools/probe_candidate_density.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.template_engine.jianying59_template import photo_prep  # noqa: E402
from server.template_engine.jianying59_template.photo_prep import (  # noqa: E402
    PHOTO_COUNT,
    account_day_video_sources,
    locate_source_time,
)

ACCOUNT_DAY_DIR = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)
DENSE_WINDOWS = 48
DENSE_OFFSETS = (0.10, 0.28, 0.45, 0.62, 0.80, 0.95)


def main() -> int:
    _, sources = account_day_video_sources(account_day_dir=ACCOUNT_DAY_DIR)
    total = sum(source.duration_seconds for source in sources)
    print(f"素材 {len(sources)} 条 / {total:.0f} 秒")
    print(f"密集池：{DENSE_WINDOWS} 窗口 × {len(DENSE_OFFSETS)} 帧 = {DENSE_WINDOWS * len(DENSE_OFFSETS)} 张\n")

    pool: list[tuple[int, int, photo_prep.FrameCandidate]] = []
    with tempfile.TemporaryDirectory(prefix="density_") as temporary:
        temporary_path = Path(temporary)
        step = total / DENSE_WINDOWS
        for window_index in range(DENSE_WINDOWS):
            start, end = window_index * step, (window_index + 1) * step
            for offset_index, fraction in enumerate(DENSE_OFFSETS):
                moment = start + (end - start) * fraction
                source, local = locate_source_time(sources=sources, global_time=moment)
                seconds = min(max(0.08, local), max(0.08, source.duration_seconds - 0.08))
                frame = temporary_path / f"w{window_index:03d}_{offset_index}.jpg"
                photo_prep._extract_frame(source=source, time_seconds=seconds, target=frame)
                pool.append((window_index, offset_index, photo_prep._measure_frame(
                    source=source, time_seconds=seconds, frame_path=frame,
                )))
    with_face = [item for _w, _o, item in pool if item.face_count]
    print(f"密集池铺完：{len(pool)} 张，含人脸 {len(with_face)} 张")
    print()
    print(f"{'采样密度':>18} {'候选数':>6} {'正面≥0.70':>10} {'正面≥0.75':>10} {'正面≥0.80':>10} {'脸宽≥90':>8} {'可用(≥0.75且脸宽≥90)':>20}")

    for window_count, offsets in ((24, 4), (24, 6), (36, 4), (36, 6), (48, 4), (48, 6)):
        # 从密集池里按比例抽样：窗口间隔 = DENSE_WINDOWS / window_count
        window_stride = max(1, DENSE_WINDOWS // window_count)
        offset_indices = [round(index * (len(DENSE_OFFSETS) - 1) / max(1, offsets - 1)) for index in range(offsets)]
        subset = [
            item for window_index, offset_index, item in pool
            if window_index % window_stride == 0 and offset_index in offset_indices
        ]
        faces = [item for item in subset if item.face_count]
        usable = [item for item in faces if item.frontal_score >= 0.75 and item.face_width >= 90]
        label = f"{window_count}窗×{offsets}帧"
        print(f"{label:>18} {len(subset):>6} "
              f"{sum(1 for item in faces if item.frontal_score >= 0.70):>10} "
              f"{sum(1 for item in faces if item.frontal_score >= 0.75):>10} "
              f"{sum(1 for item in faces if item.frontal_score >= 0.80):>10} "
              f"{sum(1 for item in faces if item.face_width >= 90):>8} {len(usable):>20}")

    print()
    print("结论参考：要凑齐 10 张，'可用'一列至少要有 10 张（考虑每集最多 3 张的限制，最好 ≥12）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
