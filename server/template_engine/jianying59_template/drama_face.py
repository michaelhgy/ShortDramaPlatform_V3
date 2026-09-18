"""Local human-face detection used to choose and frame the template photo wall.

Why this exists
---------------
The first version of the photo wall picked ten frames by timeline position alone
and scored them on sharpness and exposure.  That produced pictures of
backgrounds, props and empty rooms: nothing in the pipeline ever asked "is there
a person in this frame, and is the face inside the frame?".  This module adds
exactly that question, using OpenCV's own YuNet detector so no new third-party
runtime is required.

Design rules
------------
- **Model file, not a new dependency.**  ``opencv-contrib``/``opencv`` 4.5.4+ and
  5.x already ship ``cv2.FaceDetectorYN``; only the 232 KB model file is needed.
  It is vendored under ``resources/`` so a machine without network still works.
- **Never a hard failure.**  If the model is missing or the detector cannot run,
  detection returns "no faces" and callers fall back to the previous behaviour.
  A photo wall is not worth failing a production task over.
- **Advisory, never censorship.**  A frame with no detected face is *deprioritised*,
  not forbidden: short dramas legitimately feature animals, crowds and scenery,
  and an over-confident detector must not be able to empty the photo pool.

License: the bundled model is YuNet by Shiqi Yu (MIT).  See
``resources/YuNet-LICENSE.txt``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Detection runs on a downscaled copy: it is roughly twice as fast and found the
# same faces in measurement (see docs/V2模板草稿轨道规则.md).
DETECTION_WIDTH = 640
SCORE_THRESHOLD = 0.7
NMS_THRESHOLD = 0.3
TOP_K = 50

MODEL_RESOURCE_NAME = "face_detection_yunet_2023mar.onnx"

# 照片墙卡片最多需要这么宽的画面。以人脸为中心裁切时，如果只按"脸加一点边"裁，
# 1080x1920 的素材会裁出 200x270 这样的小图，贴到照片墙上会糊。
# 所以取景范围有一个下限，保证输出至少够清晰。
MIN_CROP_WIDTH = 540
# 最终写盘的宽度上限：够清楚，又不至于让模板草稿里的图片过大。
OUTPUT_WIDTH = 720

_DETECTOR_LOCK = threading.Lock()
_DETECTOR: Any | None = None
_DETECTOR_FAILED = False


def model_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / MODEL_RESOURCE_NAME


@dataclass(frozen=True)
class FaceBox:
    """One detected face in original-image pixel coordinates.

    ``yaw_ratio`` / ``pitch_ratio`` are derived from YuNet's five landmarks and
    describe head orientation relative to the camera: ``yaw_ratio`` is where the
    nose sits between the eyes (0.5 = looking straight at the camera), and
    ``pitch_ratio`` is where the nose sits between the eye line and the mouth
    line (0.5 = level).  Both are ``0.5`` when the landmarks are unusable.
    """

    x: float
    y: float
    width: float
    height: float
    score: float
    yaw_ratio: float = 0.5
    pitch_ratio: float = 0.5
    mouth_openness: float = 0.0
    # 原始关键点（原图像素坐标）：右眼、左眼、鼻尖、右嘴角、左嘴角。
    # 保留它们，是为了让人脸对齐（ArcFace 身份比对）不必再检测一遍。
    landmarks: tuple[tuple[float, float], ...] = ()

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def right_eye(self) -> tuple[float, float] | None:
        return self.landmarks[0] if len(self.landmarks) > 0 else None

    @property
    def left_eye(self) -> tuple[float, float] | None:
        return self.landmarks[1] if len(self.landmarks) > 1 else None


def _detector() -> Any | None:
    """Create the YuNet detector once per process; return None when unavailable."""
    global _DETECTOR, _DETECTOR_FAILED
    if _DETECTOR is not None or _DETECTOR_FAILED:
        return _DETECTOR
    with _DETECTOR_LOCK:
        if _DETECTOR is not None or _DETECTOR_FAILED:
            return _DETECTOR
        path = model_path()
        if not path.is_file():
            # Missing model is a normal, recoverable state (for example a slim
            # install): callers fall back to the pre-existing quality scoring.
            _DETECTOR_FAILED = True
            return None
        try:
            import cv2
            # OpenCV 5 logs "Targets are not supported by the new graph engine"
            # while building the detector.  It is harmless, but workers relay
            # stdout into the task log and the report, so keep it out.
            try:
                cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
            except Exception:
                pass
            _DETECTOR = cv2.FaceDetectorYN.create(str(path), "", (320, 320), SCORE_THRESHOLD, NMS_THRESHOLD, TOP_K)
        except Exception:
            _DETECTOR_FAILED = True
            return None
    return _DETECTOR


def detector_available() -> bool:
    return _detector() is not None


def _landmark_orientation(values: list[float]) -> tuple[float, float, float]:
    """从 YuNet 的 5 个关键点推出 (左右偏转, 俯仰, 张嘴程度)。

    关键点顺序：右眼、左眼、鼻尖、右嘴角、左嘴角，各 (x, y)。
    全部换算成"相对脸自身的比例"，所以与画面尺寸无关。

    实测核对（2026-09-18，把关键点画在真实帧上肉眼比对）：
    - ``yaw`` 接近 0.5 的是正脸，4.0 以上的是明显侧脸/低头 → 可作为"正对镜头"的主判据；
    - ``pitch`` 0.3~0.6 为平视；
    - ``mouth`` 越大嘴越张（0.12 左右是闭嘴说话，0.19 以上通常在喊）。
    """
    right_eye_x, right_eye_y = values[4], values[5]
    left_eye_x, left_eye_y = values[6], values[7]
    nose_x, nose_y = values[8], values[9]
    right_mouth_x, right_mouth_y = values[10], values[11]
    left_mouth_x, left_mouth_y = values[12], values[13]

    eye_span = left_eye_x - right_eye_x
    yaw = (nose_x - right_eye_x) / eye_span if abs(eye_span) > 1e-6 else 0.5

    eye_y = (right_eye_y + left_eye_y) / 2
    mouth_y = (right_mouth_y + left_mouth_y) / 2
    vertical_span = mouth_y - eye_y
    pitch = (nose_y - eye_y) / vertical_span if abs(vertical_span) > 1e-6 else 0.5

    face_width = max(abs(values[2]), 1.0)
    mouth_width = abs(left_mouth_x - right_mouth_x)
    mouth = ((right_mouth_y + left_mouth_y) / 2 - nose_y - mouth_width * 0.30) / face_width
    return (round(yaw, 5), round(pitch, 5), round(mouth, 5))


def frontal_score(face: FaceBox) -> float:
    """0..1 —— 这张脸有多"正对镜头"。

    用户 2026-09-18 明确要求："图片当然是人物正面对镜头的那种比较好。"
    实测素材里只有约 14% 的含脸帧算得上接近正面，所以这是挑图最重要的一个维度。
    """
    # 左右偏转：0.5 最佳；偏离 0.05 开始扣分，偏离 0.35 归零。
    yaw_penalty = min(1.0, abs(face.yaw_ratio - 0.5) / 0.35)
    yaw = 1.0 - yaw_penalty
    # 俯仰：0.45 最佳（略微俯视比仰视好看）；偏离 0.30 归零。
    pitch_penalty = min(1.0, abs(face.pitch_ratio - 0.45) / 0.30)
    pitch = 1.0 - pitch_penalty
    return round(max(0.0, yaw) * 0.65 + max(0.0, pitch) * 0.35, 6)


def expression_penalty(face: FaceBox) -> float:
    """0..1 —— 表情扣分，**只惩罚极端情况**。

    诚实说明：本机能拿到的人脸关键点**分不出"大喊"和"正常说话/微笑"**
    （2026-09-18 实测：张嘴分最高的那批里，既有夸张喊叫也有正常对话）。
    所以这里只把"嘴张得极大"的帧降权，不做任何表情喜好判断——
    真正要挑"好看的表情"需要额外的表情识别模型，用户尚未确认要装。
    """
    if face.mouth_openness <= 0.22:
        return 0.0
    return min(1.0, (face.mouth_openness - 0.22) / 0.10)


def detect_faces(image: Any) -> tuple[FaceBox, ...]:
    """Return every face found in a BGR image, in original coordinates.

    ``image`` is an OpenCV BGR array.  Returns an empty tuple when the detector
    is unavailable or finds nothing.
    """
    detector = _detector()
    if detector is None or image is None or getattr(image, "size", 0) == 0:
        return ()
    import cv2

    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        return ()
    scale = 1.0
    working = image
    if width > DETECTION_WIDTH:
        scale = DETECTION_WIDTH / width
        working = cv2.resize(image, (DETECTION_WIDTH, max(1, round(height * scale))), interpolation=cv2.INTER_AREA)
    working_height, working_width = working.shape[:2]
    try:
        with _DETECTOR_LOCK:
            detector.setInputSize((working_width, working_height))
            _retval, faces = detector.detect(working)
    except Exception:
        return ()
    if faces is None:
        return ()
    boxes: list[FaceBox] = []
    for row in faces:
        values = [float(item) for item in row[:15]]
        x, y, box_width, box_height, score = values[0], values[1], values[2], values[3], values[14]
        if box_width <= 0 or box_height <= 0:
            continue
        yaw, pitch, mouth = _landmark_orientation(values)
        points = tuple(
            (values[4 + index * 2] / scale, values[5 + index * 2] / scale) for index in range(5)
        )
        boxes.append(FaceBox(
            x=x / scale, y=y / scale, width=box_width / scale, height=box_height / scale, score=score,
            yaw_ratio=yaw, pitch_ratio=pitch, mouth_openness=mouth, landmarks=points,
        ))
    return tuple(boxes)


def face_score(*, faces: Iterable[FaceBox], image_width: int, image_height: int) -> float:
    """Score how well a frame works as a single-person photo-wall card.

    Higher is better; ``0.0`` means "no usable face".  The scoring encodes four
    product judgements, in this order of importance:

    1. **Looking at the camera** (user 2026-09-18: "人物正面对镜头的那种比较好").
       Only about 14% of face-bearing frames in the real material are close to
       frontal, so this term decides most of the outcome.
    2. **One clear person beats a crowd.**  Group shots scale down quickly.
    3. **The face must be comfortably inside the frame**, because the 3:4 crop
       keeps the face centred.
    4. **Bigger faces are better**, up to a limit.  A detected face is still
       evidence of a person even when small (wide shots, someone seen through a
       windscreen), so the penalty is floored rather than taken to zero.
    """
    boxes = tuple(faces)
    if not boxes:
        return 0.0
    frame_area = float(max(1, image_width) * max(1, image_height))
    best = max(boxes, key=lambda item: item.area)
    area_ratio = best.area / frame_area
    if area_ratio <= 0:
        return 0.0

    # Crowding: the largest face competes with everything else in the frame.
    other_area = sum(box.area for box in boxes if box is not best) / frame_area
    crowding = 1.0 / (1.0 + 6.0 * min(1.0, other_area / max(area_ratio, 1e-6)))

    # Distance from the nearest edge, in units of the face's own size.
    margin = min(
        best.x, best.y, image_width - (best.x + best.width), image_height - (best.y + best.height),
    ) / max(best.width, best.height, 1.0)
    edge = 0.0 if margin <= 0 else min(1.0, margin / 0.6)

    # Face size: the sweet spot is roughly 0.5%-25% of the frame.
    if area_ratio < 0.005:
        size = 0.35 + (area_ratio / 0.005) * 0.65
    elif area_ratio <= 0.25:
        size = 1.0
    else:
        size = max(0.4, 1.0 - (area_ratio - 0.25))

    frontal = frontal_score(best)
    expression = 1.0 - expression_penalty(best)
    return round(best.score * frontal * crowding * edge * size * expression, 6)


def _exact_three_four_from_width(width: int, height: int) -> tuple[int, int]:
    """Largest exact 3:4 size that fits in ``width`` x ``height``.

    Integer-only: stepping the width down until ``width * 4`` is divisible by 3
    guarantees ``height = width * 4 // 3`` is exact.  Raises when the frame is too
    small to hold any 3:4 image rather than silently returning a 0-pixel box.
    """
    target = min(int(width), int(height) * 3 // 4)
    while target > 1 and (target * 4) % 3 != 0:
        target -= 1
    if target < 3:
        raise ValueError(f"画面太小，放不下 3:4 画面：{width}x{height}")
    return target, target * 4 // 3


def face_centered_crop_box(
    *, image_width: int, image_height: int, face: FaceBox, aspect: float = 3 / 4,
    min_width: int = MIN_CROP_WIDTH,
) -> tuple[int, int, int, int]:
    """Return an exact 3:4 crop box that keeps ``face`` centred.

    The returned box always satisfies ``width * 4 == height * 3`` for the default
    3:4 aspect, because the height is derived from the width by integer maths
    (``width * 4 // 3``).  That exactness is required downstream: a rounded
    floating-point crop is what produced "标准化后不是3:4" failures.

    ``min_width`` keeps enough of the scene for the result to look like a photo
    rather than a passport crop, and to stay sharp at photo-wall size.
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError("画面尺寸无效")

    # Framing: roughly the face plus a little context, but never smaller than
    # ``min_width`` (or than what the source can actually provide).
    desired = max(
        int(round(face.width * 2.2)),
        int(round(face.height * 2.2 * aspect)),
        int(min_width),
    )
    crop_width, crop_height = _exact_three_four_from_width(min(desired, image_width), image_height)

    left = int(round(face.center_x - crop_width / 2))
    top = int(round(face.center_y - crop_height * 0.42))  # slightly above centre: headroom
    left = max(0, min(left, image_width - crop_width))
    top = max(0, min(top, image_height - crop_height))
    return left, top, left + crop_width, top + crop_height


def center_crop_box(*, image_width: int, image_height: int, aspect: float = 3 / 4) -> tuple[int, int, int, int]:
    """Exact-aspect fallback crop used when no face was detected."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("画面尺寸无效")
    crop_width, crop_height = _exact_three_four_from_width(image_width, image_height)
    left = (image_width - crop_width) // 2
    top = (image_height - crop_height) // 2
    return left, top, left + crop_width, top + crop_height


def exact_three_four_size(*, width: int, height: int, max_width: int = 720) -> tuple[int, int]:
    """Return an exact 3:4 output size not larger than ``max_width``.

    Integer-only maths: ``height = width * 4 // 3`` only when that is exact,
    otherwise step down until the ratio is exact.
    """
    target = min(int(width), int(max_width))
    while target > 1 and (target * 4) % 3 != 0:
        target -= 1
    if target <= 1:
        raise ValueError("无法得到精确的 3:4 输出尺寸")
    return target, target * 4 // 3
