"""只读诊断：人脸识别（InsightFace）能否可靠判断"这两个是同一个演员"。

在独立虚拟环境里跑：
    & "$env:TEMP\mp_venv\Scripts\python.exe" tools\probe_face_identity.py [每集抽帧数]

输出：把候选帧的人脸两两算相似度，看"同一演员"与"不同演员"的分数是否能分开。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.runtime_process import no_window_kwargs  # noqa: E402
from server.tool_resolver import resolve_ffmpeg  # noqa: E402

MATERIAL = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)


def _extract(video: Path, seconds: float, target: Path) -> None:
    subprocess.run(
        [str(resolve_ffmpeg()), "-hide_banner", "-loglevel", "error", "-ss", f"{seconds:.3f}",
         "-i", str(video), "-frames:v", "1", "-q:v", "2", "-y", str(target)],
        capture_output=True, **no_window_kwargs(),
    )


def main() -> int:
    per_video = int(sys.argv[1]) if len(sys.argv) > 1 else 6

    import cv2
    import numpy
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    started = time.monotonic()
    app.prepare(ctx_id=-1, det_size=(640, 640))
    print(f"模型加载耗时 {time.monotonic() - started:.1f} 秒（首次会自动下载模型）\n")

    videos = sorted(MATERIAL.glob("*.mp4"))
    samples: list[tuple[str, float, numpy.ndarray]] = []
    timings: list[float] = []
    with tempfile.TemporaryDirectory(prefix="identity_") as temporary:
        temporary_path = Path(temporary)
        for video in videos:
            for index in range(1, per_video + 1):
                seconds = 90.0 + index * 57.0
                frame = temporary_path / "f.jpg"
                _extract(video, seconds, frame)
                if not frame.is_file():
                    continue
                image = cv2.imdecode(numpy.fromfile(str(frame), dtype=numpy.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                started = time.monotonic()
                faces = app.get(image)
                timings.append(time.monotonic() - started)
                if not faces:
                    continue
                biggest = max(faces, key=lambda item: (item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1]))
                samples.append((video.name, seconds, biggest.normed_embedding))

    print(f"抽帧 {len(videos) * per_video} 张，得到带特征的人脸 {len(samples)} 个")
    if timings:
        timings.sort()
        print(f"单帧识别耗时：中位 {timings[len(timings) // 2] * 1000:.0f} ms")
        print(f"若对 144 张候选做人脸识别：约 {sum(timings) / len(timings) * 144:.1f} 秒")

    if len(samples) < 2:
        print("样本太少，无法比较相似度")
        return 1

    print(f"\n{'样本A':>16} {'样本B':>16} {'相似度':>8}")
    pairs: list[tuple[float, str, str]] = []
    for left in range(len(samples)):
        for right in range(left + 1, len(samples)):
            name_a, sec_a, emb_a = samples[left]
            name_b, sec_b, emb_b = samples[right]
            score = float(numpy.dot(emb_a, emb_b))
            pairs.append((score, f"{name_a[-7:]}@{sec_a:.0f}", f"{name_b[-7:]}@{sec_b:.0f}"))
    pairs.sort(reverse=True)
    for score, label_a, label_b in pairs[:12]:
        print(f"{label_a:>16} {label_b:>16} {score:>8.3f}")
    print("   ...")
    for score, label_a, label_b in pairs[-5:]:
        print(f"{label_a:>16} {label_b:>16} {score:>8.3f}")
    print("\n判读：同一演员的两张通常 >0.5；不同演员通常 <0.3。看中间是否有明显分界。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
