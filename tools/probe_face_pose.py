"""只读诊断：YuNet 返回的 5 个面部关键点能否用来判断"正面对镜头"。

YuNet 输出每行 15 个数：框(x,y,w,h) + 5 个关键点(各 x,y) + 5 个分数。
只要关键点可信，就能**不装任何新库**算出头部朝向（左右偏转 / 俯仰）。

用法：
    py -3.12 tools/probe_face_pose.py [每集抽帧数]
"""

from __future__ import annotations

import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.template_engine.jianying59_template import drama_face, photo_prep  # noqa: E402
from server.template_engine.jianying59_template.photo_prep import account_day_video_sources  # noqa: E402

ACCOUNT_DAY_DIR = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)

# YuNet 关键点顺序：右眼、左眼、鼻尖、右嘴角、左嘴角（相对于图像坐标）
RIGHT_EYE, LEFT_EYE, NOSE, RIGHT_MOUTH, LEFT_MOUTH = range(5)


def landmarks(image) -> list[list[float]]:
    """返回每张脸的完整原始输出（含 5 个关键点），坐标已换算回原图尺度。

    YuNet 每行 15 个数：``x, y, w, h`` + 5 个关键点 ``(x, y)`` 共 10 个 + 1 个总分。
    """
    import cv2

    detector = drama_face._detector()
    if detector is None:
        return []
    height, width = image.shape[:2]
    scale = 1.0
    working = image
    if width > drama_face.DETECTION_WIDTH:
        scale = drama_face.DETECTION_WIDTH / width
        working = cv2.resize(image, (drama_face.DETECTION_WIDTH, round(height * scale)), interpolation=cv2.INTER_AREA)
    working_height, working_width = working.shape[:2]
    detector.setInputSize((working_width, working_height))
    _retval, faces = detector.detect(working)
    if faces is None:
        return []
    rows: list[list[float]] = []
    for row in faces:
        values = [float(value) for value in row[:15]]
        detections = values[:4] + [values[14]]              # 框 4 个 + 总分
        points = [value / scale for value in values[4:14]]  # 10 个关键点坐标
        rows.append(detections[:4] + points + [detections[4]])
    return rows


def yaw_ratio(row: list[float]) -> float:
    """鼻尖在两眼之间的相对位置：0.5 = 正对镜头，偏离越远 = 侧脸越明显。"""
    right_eye_x, left_eye_x, nose_x = row[4], row[6], row[8]
    span = left_eye_x - right_eye_x
    if abs(span) < 1e-6:
        return 0.5
    return (nose_x - right_eye_x) / span


def pitch_ratio(row: list[float]) -> float:
    """鼻尖相对"眼-嘴"垂直中线的位置：0.5 附近 = 平视。"""
    eye_y = (row[5] + row[7]) / 2
    mouth_y = (row[11] + row[13]) / 2
    span = mouth_y - eye_y
    if abs(span) < 1e-6:
        return 0.5
    return (row[9] - eye_y) / span


def main() -> int:
    per_video = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    import cv2
    import numpy

    _, sources = account_day_video_sources(account_day_dir=ACCOUNT_DAY_DIR)
    print(f"素材 {len(sources)} 条，每条抽 {per_video} 帧\n")

    yaws: list[float] = []
    pitches: list[float] = []
    frontal: list[tuple[float, float, str, float]] = []
    with tempfile.TemporaryDirectory(prefix="pose_") as temporary:
        temporary_path = Path(temporary)
        for source in sources:
            for index in range(1, per_video + 1):
                seconds = source.duration_seconds * index / (per_video + 1)
                frame = temporary_path / "f.jpg"
                photo_prep._extract_frame(source=source, time_seconds=seconds, target=frame)
                image = cv2.imdecode(numpy.fromfile(str(frame), dtype=numpy.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                rows = landmarks(image)
                if not rows:
                    continue
                # 取框最大的一张脸
                row = max(rows, key=lambda item: item[2] * item[3])
                yaw = yaw_ratio(row)
                pitch = pitch_ratio(row)
                yaws.append(yaw)
                pitches.append(pitch)
                if 0.42 <= yaw <= 0.58 and 0.30 <= pitch <= 0.62:
                    frontal.append((yaw, pitch, source.path.name, row[2]))

    if not yaws:
        print("没有检测到任何人脸")
        return 1
    print(f"含人脸的帧：{len(yaws)}")
    print(f"左右偏转 yaw  ：中位 {statistics.median(yaws):.3f}，"
          f"0.45~0.55 占 {sum(1 for v in yaws if 0.45 <= v <= 0.55) / len(yaws) * 100:.0f}%")
    print(f"俯仰   pitch ：中位 {statistics.median(pitches):.3f}，"
          f"0.35~0.60 占 {sum(1 for v in pitches if 0.35 <= v <= 0.60) / len(pitches) * 100:.0f}%")
    print(f"\n同时满足\"接近正面\"的帧：{len(frontal)}（占含脸帧的 {len(frontal) / len(yaws) * 100:.0f}%）")
    print("\n几个例子（yaw 越接近 0.5 越正对镜头）：")
    for yaw, pitch, name, face_w in sorted(frontal, key=lambda item: abs(item[0] - 0.5))[:10]:
        print(f"   yaw={yaw:.3f} pitch={pitch:.3f} 脸宽={face_w:.0f}px  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
