"""只读诊断脚本：实测人脸检测方案在真实素材上的性能与挑人效果。

不写任何生产数据；只在系统临时目录里抽帧。
用法：
    py -3.12 tools/probe_face_detection.py [视频路径] [抽帧数]
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.runtime_process import no_window_kwargs  # noqa: E402
from server.tool_resolver import resolve_ffmpeg, resolve_ffprobe  # noqa: E402

DEFAULT_VIDEO = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材\神农宝库，医武镇九州-1.mp4"
)
MODEL = Path(os.environ.get("TEMP", ".")) / "face_probe" / "yunet.onnx"


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [str(resolve_ffprobe()), "-v", "error", "-show_entries",
         "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window_kwargs(),
    )
    return float(result.stdout.strip())


def extract(path: Path, seconds: float, target: Path) -> bool:
    result = subprocess.run(
        [str(resolve_ffmpeg()), "-hide_banner", "-loglevel", "error", "-ss", f"{seconds:.3f}",
         "-i", str(path), "-frames:v", "1", "-q:v", "2", "-y", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window_kwargs(),
    )
    return result.returncode == 0 and target.is_file() and target.stat().st_size > 0


def main() -> int:
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VIDEO
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    if not video.is_file():
        raise SystemExit(f"视频不存在：{video}")
    if not MODEL.is_file():
        raise SystemExit(f"YuNet 模型不存在：{MODEL}")

    import cv2
    import numpy

    duration = probe_duration(video)
    print(f"视频：{video.name}")
    print(f"时长：{duration:.1f} 秒；抽帧数：{count}")

    detector = cv2.FaceDetectorYN.create(str(MODEL), "", (320, 320), 0.6, 0.3, 5000)
    print(f"OpenCV {cv2.__version__} / FaceDetectorYN 已加载\n")

    timings: list[float] = []
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="face_probe_") as temporary:
        temporary_path = Path(temporary)
        for index in range(1, count + 1):
            seconds = duration * index / (count + 1)
            frame = temporary_path / f"{index:03d}.jpg"
            if not extract(video, seconds, frame):
                continue
            encoded = numpy.fromfile(str(frame), dtype=numpy.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if image is None:
                continue
            height, width = image.shape[:2]
            started = time.perf_counter()
            detector.setInputSize((width, height))
            _retval, faces = detector.detect(image)
            elapsed_ms = (time.perf_counter() - started) * 1000
            timings.append(elapsed_ms)
            rows = [] if faces is None else faces.tolist()
            best = max((row[2] * row[3] for row in rows), default=0.0)
            results.append({
                "second": round(seconds, 2), "size": f"{width}x{height}",
                "faces": len(rows), "biggest_face_px": round(best),
                "ms": round(elapsed_ms, 1),
            })

    with_faces = [item for item in results if int(item["faces"]) > 0]
    print(f"{'时间点':>8}  {'画面':>10}  {'人脸数':>5}  {'最大人脸(像素)':>12}  {'耗时ms':>7}")
    for item in results:
        print(f"{item['second']:>8}  {item['size']:>10}  {item['faces']:>5}  "
              f"{item['biggest_face_px']:>12}  {item['ms']:>7}")
    print()
    print(f"抽到 {len(results)} 帧；其中 {len(with_faces)} 帧检测到人脸 "
          f"（{len(with_faces) / max(1, len(results)) * 100:.0f}%）")
    if timings:
        print(f"单帧耗时：中位 {statistics.median(timings):.1f} ms，"
              f"最快 {min(timings):.1f} ms，最慢 {max(timings):.1f} ms，合计 {sum(timings) / 1000:.1f} 秒")
    summary = {"frames": len(results), "with_faces": len(with_faces),
               "median_ms": round(statistics.median(timings), 1) if timings else 0}
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
