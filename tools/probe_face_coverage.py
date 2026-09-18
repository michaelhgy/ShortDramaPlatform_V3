"""只读诊断：扫描整批素材，统计"含人脸的可用剧照"到底有多少、要花多久。

用于决定新的抽图策略（当前"均匀 10 点采样"命中率不足）。
不改生产数据；只在系统临时目录抽帧。
用法：
    py -3.12 tools/probe_face_coverage.py [采样间隔秒] [每条素材抽多少张]
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.template_engine.jianying59_template import drama_face, photo_prep  # noqa: E402
from server.template_engine.jianying59_template.photo_prep import account_day_video_sources  # noqa: E402

MATERIAL = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)


def main() -> int:
    per_video = int(sys.argv[1]) if len(sys.argv) > 1 else 40

    import cv2
    import numpy

    _, sources = account_day_video_sources(account_day_dir=MATERIAL)
    total_duration = sum(source.duration_seconds for source in sources)
    print(f"素材 {len(sources)} 条，合计 {total_duration:.0f} 秒；每条抽 {per_video} 张\n")

    usable: list[tuple[float, str, float, float]] = []
    extract_seconds = 0.0
    detect_seconds = 0.0
    total_frames = 0
    with tempfile.TemporaryDirectory(prefix="coverage_") as temporary:
        temporary_path = Path(temporary)
        for source in sources:
            for index in range(1, per_video + 1):
                seconds = source.duration_seconds * index / (per_video + 1)
                frame = temporary_path / "f.jpg"
                started = time.monotonic()
                photo_prep._extract_frame(source=source, time_seconds=seconds, target=frame)
                extract_seconds += time.monotonic() - started
                image = cv2.imdecode(numpy.fromfile(str(frame), dtype=numpy.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                total_frames += 1
                height, width = image.shape[:2]
                started = time.monotonic()
                faces = drama_face.detect_faces(image)
                detect_seconds += time.monotonic() - started
                score = drama_face.face_score(faces=faces, image_width=width, image_height=height)
                if score >= 0.5:
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    usable.append((score, source.path.name, seconds, sharpness))
            print(f"  {source.path.name} 完成")

    print()
    print(f"共抽 {total_frames} 张；人脸分 ≥0.5 的可用剧照 {len(usable)} 张 "
          f"（{len(usable) / max(1, total_frames) * 100:.0f}%）")
    print(f"抽帧耗时合计 {extract_seconds:.1f} 秒；人脸检测耗时合计 {detect_seconds:.1f} 秒")
    print(f"平均每张：抽帧 {extract_seconds / max(1, total_frames) * 1000:.0f} ms，"
          f"检测 {detect_seconds / max(1, total_frames) * 1000:.0f} ms")
    if usable:
        scores = [item[0] for item in usable]
        print(f"人脸分：中位 {statistics.median(scores):.3f}，最高 {max(scores):.3f}")
        print()
        print("最好的一批（按人脸分）：")
        for score, name, seconds, sharpness in sorted(usable, reverse=True)[:12]:
            print(f"   {score:.3f}  {name} @ {seconds:.1f}s  清晰度 {sharpness:.0f}")
        print()
        print("可用剧照是否分散在多集（决定照片墙有没有多样性）：")
        by_name: dict[str, int] = {}
        for _score, name, _seconds, _sharpness in usable:
            by_name[name] = by_name.get(name, 0) + 1
        for name, count in sorted(by_name.items()):
            print(f"   {name}: {count} 张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
