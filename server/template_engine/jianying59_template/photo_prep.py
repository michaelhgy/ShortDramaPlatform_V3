"""Deterministic, non-destructive drama-photo preparation for template drafts.

The template generator owns this preparation step because the T02/T03 photo
walls need exactly ten reusable 3:4 drama stills.  Source videos are only
read.  The caller supplies a fresh output directory; generation is staged in
an adjacent temporary directory and published only after all ten images pass
the local checks.

Frame selection deliberately prefers technically usable, varied images.  A
local face detector can be plugged in later, but it is not a hard dependency:
short dramas may centre animals or other creatures, and a missing detector
must never make the generator invent an AI judgement or reject all material.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from server.tool_resolver import resolve_ffmpeg, resolve_ffprobe
from server.runtime_process import no_window_kwargs
from server.template_engine.jianying59_template import drama_expression, drama_face, drama_identity


PHOTO_COUNT = 10
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".m4v"})
ProgressReporter = Callable[[str, str], None]

# 候选铺法：把**整批素材的总时长**切成若干个窗口，每个窗口取几帧。
# 老做法只有一个"每 1/(count+1) 处取一帧"的网格（10 点 × 5 帧 = 50 张），实测在 12 集
# 5066 秒的素材上会连续错过人物镜头。
#
# 候选数量是精度与耗时的旋钮（实测每张约 109ms 抽帧 + 31ms 人脸检测）。
# 2026-09-18 用真实素材做过密度扫描，以"正面分≥0.75 且脸宽≥90px"为可用标准：
#   24窗×4帧 =  96 张 → 可用  7 张（凑不齐 10 张）
#   24窗×6帧 = 144 张 → 可用 14 张  ← 选定
#   36窗×6帧 = 288 张 → 可用 34 张（更宽裕，但候选取帧要 288×0.14 ≈ 40 秒，收益递减）
WINDOW_COUNT = 24
FRAME_OFFSET_FRACTIONS = (0.08, 0.25, 0.42, 0.58, 0.75, 0.92)
# 同一集里挑出的两张照片至少间隔这么远，避免照片墙上出现"同一场戏的两个画面"。
MIN_SOURCE_GAP_SECONDS = 8.0
# 单张照片里的人脸至少要这么宽（像素）。照片墙卡片按 540px 宽出图，
# 比这更小的脸贴上去就是一团糊（实测会挑到 50~60px 的脸）。
MIN_FACE_WIDTH_PX = 90.0
# 同一集最多贡献几张，保证 10 张不至于全是同一集/同一个人的连拍。
MAX_PHOTOS_PER_VIDEO = 3
# 正面分门槛：低于此值的候选不参与挑选。0.75 对应"基本正脸"；
# 实测 96 张候选只有 10 张过线，144 张候选有 18 张过线，所以门槛与候选数是配套的。
MIN_FRONTAL_SCORE = 0.75
# 同一位演员最多占几张（人脸识别判定）。实测不加这条会 10 张里 3 张是同一人。
MAX_PHOTOS_PER_PERSON = 2
# 表情门槛：闭眼、以及"嘴张得极大"（喊叫）的帧不进入严格档。
MAX_EYES_CLOSED = drama_expression.EYES_CLOSED
MAX_MOUTH_OPEN = drama_expression.MOUTH_SHOUTING

# 用户 2026-09-18 确认：照片墙要抽"人物剧照"，不是随机画面。
FACE_PREFERENCE = "yunet_local_face_detection_prefer_single_clear_face_then_crop_centered_on_face"

# 降级阶梯：**必须凑满 10 张**（用户 2026-09-18 明确："宁可 10 张里有些质量差，也不能少数量"）。
# 模板对剧照有三道硬校验（恰好 10 个文件 / 路径不重复 / SHA256 不重复），少给一张就直接失败，
# 所以这里一级一级放宽，直到凑满。
#   strict          正面分≥0.75、脸宽≥90px、睁眼、不喊叫、同演员≤2、同集≤3
#   relaxed_frontal 正面分≥0.55（其余同上）
#   relaxed_size    脸宽≥60px
#   relaxed_all     只要求有人脸、画面各不相同
#   duplicates      允许同演员/同集重复，只保证画面不同
#   variants        画面都不够时，用极轻微二次裁切做出不同字节（肉眼几乎不可分辨）
SELECTION_LADDER: tuple[tuple[str, dict[str, Any]], ...] = (
    ("strict", {"frontal": MIN_FRONTAL_SCORE, "face_width": MIN_FACE_WIDTH_PX,
                "expression": True, "per_person": MAX_PHOTOS_PER_PERSON, "per_video": MAX_PHOTOS_PER_VIDEO}),
    ("relaxed_frontal", {"frontal": 0.55, "face_width": MIN_FACE_WIDTH_PX,
                         "expression": True, "per_person": MAX_PHOTOS_PER_PERSON, "per_video": MAX_PHOTOS_PER_VIDEO}),
    ("relaxed_size", {"frontal": 0.55, "face_width": 60.0,
                      "expression": False, "per_person": MAX_PHOTOS_PER_PERSON, "per_video": MAX_PHOTOS_PER_VIDEO}),
    ("relaxed_all", {"frontal": 0.0, "face_width": 0.0,
                     "expression": False, "per_person": MAX_PHOTOS_PER_PERSON, "per_video": PHOTO_COUNT}),
    # 最后一级：允许同一个人多出现几次，但仍然限制"同一集别刷屏"。
    # 人数上限设成 PHOTO_COUNT 等于不限制——那是"保数量优先"的明确取舍，
    # 由调用方在学习记录里写明（stage=duplicates）。
    ("duplicates", {"frontal": 0.0, "face_width": 0.0,
                    "expression": False, "per_person": PHOTO_COUNT, "per_video": PHOTO_COUNT,
                    "allow_repeat_frames": True}),
)


def _report(progress: ProgressReporter | None, phase: str, message: str) -> None:
    if progress is not None:
        progress(phase, message)


def _natural_key(path: Path) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name))


@dataclass(frozen=True)
class VideoSource:
    path: Path
    duration_seconds: float


@dataclass(frozen=True)
class DramaPhotoSource:
    """One eligible drama below an account-day viral-material directory."""

    drama_name: str
    directory: Path
    videos: tuple[VideoSource, ...]


@dataclass(frozen=True)
class FrameCandidate:
    source: VideoSource
    time_seconds: float
    width: int
    height: int
    sharpness: float
    exposure_penalty: float
    perceptual_key: tuple[int, ...]
    face_count: int = 0
    face_score: float = 0.0
    frontal_score: float = 0.0
    face_width: float = 0.0
    # 表情（MediaPipe；不可用时全为 None 语义的 0）
    eyes_closed: float = 0.0
    mouth_open: float = 0.0
    smile: float = 0.0
    expression_measured: bool = False
    # 人脸身份（ArcFace；不可用时 None）
    identity: Any | None = None

    @property
    def face_blurred(self) -> bool:
        """眼睛闭着或夸张张嘴（喊叫）——严格档会剔除这两种。"""
        if not self.expression_measured:
            return False
        return self.eyes_closed >= MAX_EYES_CLOSED or self.mouth_open >= MAX_MOUTH_OPEN


@dataclass(frozen=True)
class PreparedPhoto:
    index: int
    source_video: str
    source_time_seconds: float
    output: str
    sha256: str
    sharpness: float
    exposure_penalty: float
    face_preference: str
    subtitle_blur_count: int
    face_count: int = 0
    face_score: float = 0.0
    crop_mode: str = "center"
    frontal_score: float = 0.0
    face_width: float = 0.0
    eyes_closed: float = 0.0
    mouth_open: float = 0.0
    smile: float = 0.0
    # 同一演员的第几张（1 = 这个人的第一张）；None = 没能判定身份
    person_ordinal: int | None = None
    # 是否为"保底凑数"的产物（极轻微二次裁切）
    variant_of: str = ""


@dataclass(frozen=True)
class PhotoPrepDecision:
    count: int
    output_directory: str
    source_scope: str
    source_drama_names: tuple[str, ...]
    source_drama_directories: tuple[str, ...]
    source_videos: tuple[str, ...]
    face_preference: str
    ocr_subtitle_blur: str
    items: tuple[PreparedPhoto, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def discover_drama_videos(video_dir: Path, *, progress: ProgressReporter | None = None) -> tuple[VideoSource, ...]:
    """Return readable videos in deterministic order; do not recurse or mutate."""
    if not video_dir.is_dir():
        raise FileNotFoundError(f"剧集视频目录不存在：{video_dir}")
    sources: list[VideoSource] = []
    for path in sorted((item for item in video_dir.iterdir() if item.is_file() and item.suffix.casefold() in VIDEO_EXTENSIONS), key=_natural_key):
        started = time.monotonic()
        _report(progress, "读取剧集视频", f"正在读取视频：{path.name}")
        duration = _probe_duration(path)
        _report(progress, "读取剧集视频", f"视频读取完成：{path.name}，耗时 {time.monotonic() - started:.1f} 秒")
        if duration > 0:
            sources.append(VideoSource(path=path.resolve(), duration_seconds=duration))
    if not sources:
        raise RuntimeError(f"剧集视频目录内没有可读取的视频：{video_dir}")
    return tuple(sources)


def discover_account_day_drama_sources(account_day_dir: Path, *, progress: ProgressReporter | None = None) -> tuple[DramaPhotoSource, ...]:
    """Discover candidate dramas under ``爆款/账号日`` without changing sources.

    Production batches normally contain one subdirectory per drama.  Direct
    video files are supported only for a small one-drama development batch.
    The generator never reaches into another account/day directory.
    """
    if not account_day_dir.is_dir():
        raise FileNotFoundError(f"爆款账号日目录不存在：{account_day_dir}")
    direct_videos = tuple(
        item for item in account_day_dir.iterdir()
        if item.is_file() and item.suffix.casefold() in VIDEO_EXTENSIONS
    )
    if direct_videos:
        return (DramaPhotoSource(
            drama_name=account_day_dir.name,
            directory=account_day_dir.resolve(),
            videos=discover_drama_videos(account_day_dir, progress=progress),
        ),)
    sources: list[DramaPhotoSource] = []
    for directory in sorted((item for item in account_day_dir.iterdir() if item.is_dir()), key=_natural_key):
        try:
            _report(progress, "扫描剧集目录", f"正在扫描剧集目录：{directory.name}")
            videos = discover_drama_videos(directory, progress=progress)
        except RuntimeError:
            continue
        sources.append(DramaPhotoSource(drama_name=directory.name, directory=directory.resolve(), videos=videos))
    if not sources:
        raise RuntimeError(f"爆款账号日目录下没有可读取的剧集视频：{account_day_dir}")
    return tuple(sources)


def choose_account_day_drama_source(*, account_day_dir: Path, seed: int) -> DramaPhotoSource:
    """Legacy helper kept for diagnostics; final photo preparation uses all dramas."""
    candidates = discover_account_day_drama_sources(account_day_dir)
    return random.Random(f"{seed}:drama-photo-source").choice(candidates)


def account_day_video_sources(*, account_day_dir: Path, progress: ProgressReporter | None = None) -> tuple[DramaPhotoSource, tuple[VideoSource, ...]]:
    """Aggregate every readable viral video in this account/day, never another day."""
    dramas = discover_account_day_drama_sources(account_day_dir, progress=progress)
    videos = tuple(video for drama in dramas for video in drama.videos)
    if not videos:
        raise RuntimeError("current account/day has no readable viral videos")
    return dramas, videos


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [str(resolve_ffprobe()), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=20, **no_window_kwargs(),
    )
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def planned_global_times(*, total_duration: float, count: int = PHOTO_COUNT) -> tuple[float, ...]:
    if total_duration <= 0 or count <= 0:
        raise ValueError("总时长和剧照数量必须大于零")
    return tuple(total_duration * (index + 1) / (count + 1) for index in range(count))


def planned_windows(*, total_duration: float, count: int = WINDOW_COUNT) -> tuple[tuple[float, float], ...]:
    """把整批素材的总时长切成 ``count`` 个等长窗口。

    候选帧在**每个窗口内**取，所以选出来的 10 张天然分散在整段时间轴上，
    不会全部挤在同一集或同一分钟里。
    """
    if total_duration <= 0 or count <= 0:
        raise ValueError("总时长和窗口数量必须大于零")
    step = total_duration / count
    return tuple((index * step, (index + 1) * step) for index in range(count))


def locate_source_time(*, sources: Iterable[VideoSource], global_time: float) -> tuple[VideoSource, float]:
    source_list = tuple(sources)
    if not source_list:
        raise ValueError("至少需要一个剧集视频")
    cursor = 0.0
    for source in source_list:
        if global_time <= cursor + source.duration_seconds:
            return source, min(max(0.08, global_time - cursor), max(0.08, source.duration_seconds - 0.08))
        cursor += source.duration_seconds
    final = source_list[-1]
    return final, max(0.08, final.duration_seconds - 0.08)


def _extract_frame(*, source: VideoSource, time_seconds: float, target: Path) -> None:
    result = subprocess.run(
        [str(resolve_ffmpeg()), "-hide_banner", "-loglevel", "error", "-ss", f"{time_seconds:.3f}", "-i", str(source.path), "-frames:v", "1", "-q:v", "2", "-y", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=40, **no_window_kwargs(),
    )
    if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError(result.stderr.strip() or f"无法读取剧照帧：{source.path.name}@{time_seconds:.3f}s")


def _measure_frame(*, source: VideoSource, time_seconds: float, frame_path: Path) -> FrameCandidate:
    import cv2
    import numpy

    # OpenCV's imread does not reliably support a Unicode Windows path.  Input
    # directories in this product normally contain Chinese names, so decode the
    # bytes ourselves instead of falling back to an ASCII-only temp location.
    encoded = numpy.fromfile(str(frame_path), dtype=numpy.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RuntimeError(f"抽取帧不可读取：{frame_path.name}")
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mean = float(gray.mean())
    # Very dark/bright frames are usually transitions, captions, or exposure
    # failures.  The quality check is a soft score, never content censorship.
    exposure_penalty = max(0.0, 48.0 - mean) + max(0.0, mean - 210.0)
    tiny = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
    perceptual_key = tuple(int(value) for value in tiny.flatten())
    # Human presence is measured here so the same decoded frame is reused; a
    # missing model simply yields no faces and falls back to the old scoring.
    faces = drama_face.detect_faces(image)
    biggest = max(faces, key=lambda item: item.area) if faces else None
    # 表情与身份只在"这张有脸"时才值得算：没脸的帧既不会入选，也算不出东西。
    expression = drama_expression.measure(image) if biggest is not None else None
    identity = drama_identity.identity_of(image, biggest) if biggest is not None else None
    return FrameCandidate(
        source=source, time_seconds=time_seconds, width=width, height=height,
        sharpness=sharpness, exposure_penalty=exposure_penalty, perceptual_key=perceptual_key,
        face_count=len(faces), face_score=drama_face.face_score(faces=faces, image_width=width, image_height=height),
        frontal_score=drama_face.frontal_score(biggest) if biggest is not None else 0.0,
        face_width=biggest.width if biggest is not None else 0.0,
        eyes_closed=expression.eyes_closed if expression else 0.0,
        mouth_open=expression.mouth_open if expression else 0.0,
        smile=expression.smile if expression else 0.0,
        expression_measured=expression is not None,
        identity=identity,
    )


def _difference(first: FrameCandidate, second: FrameCandidate) -> float:
    return sum(abs(left - right) for left, right in zip(first.perceptual_key, second.perceptual_key, strict=True)) / len(first.perceptual_key)


def choose_photo_set(
    *, candidates: Iterable[FrameCandidate], count: int = PHOTO_COUNT, min_gap_seconds: float = MIN_SOURCE_GAP_SECONDS,
    min_face_width: float = MIN_FACE_WIDTH_PX, max_per_video: int = MAX_PHOTOS_PER_VIDEO,
    min_frontal_score: float = MIN_FRONTAL_SCORE, require_expression: bool = False,
    max_per_person: int = MAX_PHOTOS_PER_PERSON, allow_repeat_frames: bool = False,
) -> tuple[FrameCandidate, ...]:
    """Pick the ``count`` best candidates for the wall under one set of gates.

    Ranking (user 2026-09-18: "图片当然是人物正面对镜头的那种比较好"):
    1. **looking at the camera** — measured from face landmarks; only ~14% of
       face-bearing frames in the real material qualify, so this dominates;
    2. **a pleasant expression** — a smile helps, shouting does not;
    3. **face quality** — detection confidence, how alone the person is, framing;
    4. **sharpness**, then exposure.

    Gates (each added because a real defect was observed):
    - ``min_frontal_score`` / ``min_face_width`` — 50px faces were picked and looked
      like smudges;
    - ``require_expression`` — drops closed eyes and shouting (MediaPipe);
    - ``max_per_person`` — the same actor was taking 3 of the 10 slots;
    - perceptual-key de-duplication, plus ``max_per_video`` photos per episode with
      at least ``min_gap_seconds`` between two picks from one episode.

    ``allow_repeat_frames`` is the last-resort rung: it still refuses *identical*
    frames, but no longer refuses a second photo of the same person.
    """
    options = tuple(candidates)
    if count <= 0:
        raise ValueError("需要的剧照数量必须大于零")

    def rank(candidate: FrameCandidate) -> tuple[float, float, float, float, float]:
        return (
            candidate.frontal_score,
            candidate.smile if candidate.expression_measured else 0.0,
            candidate.face_score,
            candidate.sharpness,
            -candidate.exposure_penalty,
        )

    picked: list[FrameCandidate] = []
    per_video: dict[Path, int] = {}
    for candidate in sorted(options, key=rank, reverse=True):
        if candidate.face_count and candidate.frontal_score < min_frontal_score:
            continue
        if candidate.face_count and candidate.face_width < min_face_width:
            continue
        if require_expression and candidate.face_blurred:
            continue
        if not allow_repeat_frames and any(_difference(candidate, prior) < 8.0 for prior in picked):
            continue
        if allow_repeat_frames and any(
            candidate.source.path == prior.source.path
            and abs(candidate.time_seconds - prior.time_seconds) < 1e-6
            for prior in picked
        ):
            # 同一帧不能重复用（模板会按 SHA256 校验重复）
            continue
        if per_video.get(candidate.source.path, 0) >= max_per_video:
            continue
        if any(
            candidate.source.path == prior.source.path
            and abs(candidate.time_seconds - prior.time_seconds) < min_gap_seconds
            for prior in picked
        ):
            continue
        if candidate.identity is not None and max_per_person < count:
            # 直接数"已选中的人里有几个和这张是同一个人"。
            # 早先按 identity 对象的 id 计数是错的：同一演员每张都是新对象，
            # 计数永远从 1 开始，上限就形同虚设（实测 3 张同一人就是这样漏过去的）。
            same_person = sum(
                1 for prior in picked
                if prior.identity is not None and candidate.identity.is_same_person(prior.identity)
            )
            if same_person >= max_per_person:
                continue
        picked.append(candidate)
        per_video[candidate.source.path] = per_video.get(candidate.source.path, 0) + 1
        if len(picked) == count:
            break
    return tuple(picked)


def select_photo_set(
    *, candidates: Iterable[FrameCandidate], count: int = PHOTO_COUNT,
) -> tuple[tuple[FrameCandidate, ...], str]:
    """走完整个降级阶梯，**保证凑满 ``count`` 张**，并返回用了哪一级。

    用户 2026-09-18 明确："宁可 10 张里有些质量差，也不能少数量。"
    模板对剧照有三道硬校验（恰好 10 个文件 / 路径不重复 / SHA256 不重复），
    所以这里的最后手段是"把最好的画面做极轻微二次裁切"凑数，
    由调用方在写盘时执行（见 ``prepare_drama_photos``）。
    """
    options = tuple(candidates)
    if not options:
        raise RuntimeError("没有可用的候选画面")
    for stage, gates in SELECTION_LADDER:
        selection = choose_photo_set(
            candidates=options, count=count,
            min_frontal_score=float(gates["frontal"]),
            min_face_width=float(gates["face_width"]),
            require_expression=bool(gates["expression"]),
            max_per_person=int(gates["per_person"]),
            max_per_video=int(gates["per_video"]),
            allow_repeat_frames=bool(gates.get("allow_repeat_frames", False)),
        )
        if len(selection) == count:
            return selection, stage
    # 阶梯走完仍不够：把最好的画面重复使用，靠"二次裁切"凑成不同字节。
    ranked = sorted(
        options,
        key=lambda item: (item.frontal_score, item.face_score, item.sharpness),
        reverse=True,
    )
    filled: list[FrameCandidate] = list(ranked[:count])
    while len(filled) < count:
        filled.append(ranked[len(filled) % len(ranked)])
    return tuple(filled), "variants"


def _crop_three_four(source: Path, target: Path, *, face: Any | None = None, variant: bool = False) -> None:
    """Crop one frame to an **exact** 3:4 image, centred on the face when known.

    The exactness matters: the previous implementation derived the short side
    with ``round(<float>)``, which lands one pixel off for roughly two thirds of
    possible frame sizes and then trips the strict 3:4 check in
    ``track02_03.normalize_three_four_photos`` ("标准化后不是3:4").
    Here the long side is derived by integer maths, so the ratio is exact by
    construction.

    ``variant=True`` shifts the crop by a sub-percent offset.  It exists only for
    the last-resort rung of the selection ladder: when the material cannot supply
    ten distinct frames, the template still requires ten *different* files
    (SHA256 checked), so the same scene is re-cropped by a hair.  The difference
    is invisible at photo-wall size.
    """
    from PIL import Image

    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            raise RuntimeError(f"剧照尺寸无效：{source.name}")
        if face is not None:
            box = drama_face.face_centered_crop_box(image_width=width, image_height=height, face=face)
        else:
            box = drama_face.center_crop_box(image_width=width, image_height=height)
        if variant:
            shift = max(1, round((box[2] - box[0]) * 0.012))
            left = max(0, min(box[0] + shift, width - (box[2] - box[0])))
            top = max(0, min(box[1] + shift, height - (box[3] - box[1])))
            box = (left, top, left + (box[2] - box[0]), top + (box[3] - box[1]))
        cropped = image.crop(box)
        output_width, output_height = cropped.size
        if output_width * 4 != output_height * 3:
            # Integer maths above makes this unreachable; keep it as a guard so a
            # future edit cannot silently reintroduce a rounded crop.
            raise RuntimeError(
                f"剧照裁切后不是精确3:4：源 {width}x{height}，结果 {output_width}x{output_height}"
            )
        # 统一输出尺寸：源素材是 1080 宽，直接落盘会白白占空间；缩到 720x960 仍然清晰，
        # 并且尺寸固定后照片墙的取景比例才是可预期的。
        if output_width > drama_face.OUTPUT_WIDTH:
            target_width, target_height = drama_face.exact_three_four_size(
                width=output_width, height=output_height, max_width=drama_face.OUTPUT_WIDTH,
            )
            cropped = cropped.resize((target_width, target_height), Image.LANCZOS)
        cropped.save(target, format="JPEG", quality=95, subsampling=0)


_OCR_ENGINE: Any | None = None


def _local_ocr_boxes(image_path: Path) -> tuple[tuple[float, float, float, float], ...]:
    """Return all locally recognised text bounds from a prepared 3:4 image."""
    global _OCR_ENGINE
    import cv2
    import numpy
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        # 缺 OCR 只意味着"字幕不会被柔化"，不该让整个模板任务失败
        # （换一台没装这个库的电脑时会走到这里）。调用方会记录"本次未做字幕处理"。
        return ()
    if _OCR_ENGINE is None:
        try:
            _OCR_ENGINE = RapidOCR()
        except Exception:
            return ()
    encoded = numpy.fromfile(str(image_path), dtype=numpy.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RuntimeError(f"裁切后的剧照无法供 OCR 读取：{image_path.name}")
    try:
        result, _elapsed = _OCR_ENGINE(image)
    except Exception:
        return ()
    boxes: list[tuple[float, float, float, float]] = []
    for item in result or []:
        box, _text, score = item
        if float(score) < 0.35:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return tuple(boxes)


def soften_detected_text(*, image_path: Path) -> int:
    """Gaussian-blur all detected text after the final 3:4 crop.

    False positives are acceptable for this product: the goal is to avoid
    retaining hard subtitles in a decorative photo wall, never to preserve a
    watermark because an OCR model was uncertain.
    """
    from PIL import Image, ImageDraw, ImageFilter

    boxes = _local_ocr_boxes(image_path)
    if not boxes:
        return 0
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        width, height = image.size
        applied = 0
        for left, top, right, bottom in boxes:
            padding = max(6, round(min(width, height) * 0.012))
            x1 = max(0, int(math.floor(left)) - padding)
            y1 = max(0, int(math.floor(top)) - padding)
            x2 = min(width, int(math.ceil(right)) + padding)
            y2 = min(height, int(math.ceil(bottom)) + padding)
            if x2 <= x1 or y2 <= y1:
                continue
            region = image.crop((x1, y1, x2, y2))
            blurred = region.filter(ImageFilter.GaussianBlur(radius=max(5, round(min(region.size) * 0.12))))
            # Keep the edge soft so this looks like a local subtitle softening
            # treatment rather than a sharp rectangular patch.
            mask = Image.new("L", region.size, 0)
            draw = ImageDraw.Draw(mask)
            inset = min(padding, max(1, min(region.size) // 4))
            draw.rectangle((inset, inset, region.size[0] - inset, region.size[1] - inset), fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(radius=max(2, inset / 2)))
            image.paste(blurred, (x1, y1), mask)
            applied += 1
        image.save(image_path, format="JPEG", quality=95, subsampling=0)
    return applied


def _best_face(frame_path: Path) -> Any | None:
    """Return the face to centre the crop on, or None when the frame has none."""
    try:
        import cv2
        import numpy
        encoded = numpy.fromfile(str(frame_path), dtype=numpy.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    except Exception:
        return None
    if image is None or image.size == 0:
        return None
    faces = drama_face.detect_faces(image)
    if not faces:
        return None
    return max(faces, key=lambda item: item.area)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 剧照缓存（2026-09-18）
#
# 为什么要做：同一个"账号+剧集"会**重复建任务**（实测 桃桃冰叭|家养恶犬终为祸 出现过 3 次），
# 而剧照准备要抽 144 帧、跑人脸/表情/身份三层判断，约 20 秒。同一批素材的结果是确定的，
# 重复跑纯属白烧时间。失败重试也会走同一条路（失败时模板缓存被清掉，重试等于重做）。
#
# 单位 = **账号 + 剧集**（用户 2026-09-18 明确："账号a+剧集a是一个模板，账号b+剧集a不能共用同一个"）。
# 因此缓存目录按 账号|剧集 再分一层，绝不跨账号复用。
#
# 位置放在 `<系统数据>/剧照缓存/`：它是**派生数据**，不属于生产文件，也不属于用户放置的生成资源。
# 素材变了（文件增删改）指纹就变，自动重做，不会用错图。
# ---------------------------------------------------------------------------

CACHE_FOLDER_NAME = "剧照缓存"
# 每个"账号+剧集"最多保留几份指纹缓存（换素材会产生新指纹，旧的迟早要清）。
CACHE_KEEP_FINGERPRINTS = 3


def material_fingerprint(sources: Iterable[VideoSource]) -> str:
    """素材指纹：路径 + 大小 + 修改时间。素材一变，指纹就变。"""
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda item: str(item.path)):
        try:
            stat = source.path.stat()
            stamp = f"{source.path}|{stat.st_size}|{stat.st_mtime_ns}"
        except OSError:
            stamp = f"{source.path}|missing"
        digest.update(stamp.encode("utf-8"))
    return digest.hexdigest()[:16]


def photo_cache_root(data_root: Path, *, account: str, drama: str) -> Path:
    """缓存目录：`<系统数据>/剧照缓存/<账号__剧集>/`（按账号+剧集隔离）。"""
    safe = re.sub(r'[<>:"/\\|?*]', "_", f"{account}__{drama}").strip() or "未命名"
    return Path(data_root) / CACHE_FOLDER_NAME / safe[:120]


def _cache_is_usable(directory: Path, *, count: int) -> bool:
    if not directory.is_dir():
        return False
    images = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg", ".png"}
    )
    return len(images) >= count


def prune_photo_cache(unit_root: Path, *, keep: int = CACHE_KEEP_FINGERPRINTS) -> int:
    """只保留最近 ``keep`` 份指纹缓存，避免换素材后旧缓存无限堆积。

    指纹会随素材变化（重新上传、换一版片子），每变一次就多一个目录；
    不清的话缓存会一直变大。删除时只动指纹目录本身，不碰生产文件。
    """
    if not unit_root.is_dir():
        return 0
    entries = [path for path in unit_root.iterdir() if path.is_dir() and not path.name.startswith(".")]
    if len(entries) <= keep:
        return 0
    entries.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    removed = 0
    for stale in entries[keep:]:
        shutil.rmtree(stale, ignore_errors=True)
        removed += 1
    return removed


def _publish_from_cache(*, cache_directory: Path, output_dir: Path, count: int) -> dict[str, Any]:
    """把缓存里的剧照复制成一次新的产出（不改缓存本身）。"""
    import shutil

    manifest_path = cache_directory / "剧照准备清单.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}
    images = sorted(
        path for path in cache_directory.iterdir()
        if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg", ".png"}
    )[:count]
    if len(images) < count:
        raise RuntimeError(f"剧照缓存不完整：{cache_directory} 只有 {len(images)} 张")

    staging = output_dir.parent / f".{output_dir.name}.cache"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    items: list[PreparedPhoto] = []
    source_items = manifest.get("items") or []
    for index, image in enumerate(images):
        target = staging / f"剧集人物_{index + 1:03d}.jpg"
        shutil.copyfile(image, target)
        original = source_items[index] if index < len(source_items) else {}
        items.append(PreparedPhoto(
            index=index + 1,
            source_video=str(original.get("source_video", "")),
            source_time_seconds=float(original.get("source_time_seconds", 0.0)),
            output=str(output_dir / target.name),
            sha256=_sha256(target),
            sharpness=float(original.get("sharpness", 0.0)),
            exposure_penalty=float(original.get("exposure_penalty", 0.0)),
            face_preference=FACE_PREFERENCE,
            subtitle_blur_count=int(original.get("subtitle_blur_count", 0)),
            face_count=int(original.get("face_count", 0)),
            face_score=float(original.get("face_score", 0.0)),
            crop_mode=str(original.get("crop_mode", "center")),
            frontal_score=float(original.get("frontal_score", 0.0)),
            face_width=float(original.get("face_width", 0.0)),
            eyes_closed=float(original.get("eyes_closed", 0.0)),
            mouth_open=float(original.get("mouth_open", 0.0)),
            smile=float(original.get("smile", 0.0)),
            person_ordinal=original.get("person_ordinal"),
            variant_of=str(original.get("variant_of", "")),
        ))
    cached_manifest = dict(manifest)
    cached_manifest.update({
        "count": count,
        "source_scope": "reused_from_cache",
        "cache_reused_from": str(cache_directory),
        "items": [asdict(item) for item in items],
    })
    (staging / "剧照准备清单.json").write_text(
        json.dumps(cached_manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    os.replace(staging, output_dir)
    return {
        "items": items,
        "drama_names": cached_manifest.get("source_drama_names") or [],
        "source_videos": cached_manifest.get("source_videos") or [],
    }


def prepare_drama_photos(*, account_day_dir: Path, output_dir: Path, seed: int, count: int = PHOTO_COUNT,
                         progress: ProgressReporter | None = None,
                         cache_directory: Path | None = None) -> PhotoPrepDecision:
    """Create exactly ten varied 3:4 stills without modifying source videos.

    All readable viral videos under the current account/day participate.  The
    planner keeps deterministic source order, then uses local quality and
    de-duplication; every final 3:4 image is OCR-checked and its detected text
    is softly blurred.  Source videos are never modified.

    ``cache_directory`` enables reuse: when it already holds a complete set from
    the same material, the prepared photos are copied out instead of re-running
    the whole extraction.  The caller passes a cache path scoped to
    account+drama (see ``photo_cache_root``); the cache is never shared across
    accounts.
    """
    if count != PHOTO_COUNT:
        raise ValueError("当前照片墙合同固定需要10张剧照")
    if output_dir.exists():
        raise FileExistsError(f"剧照输出目录必须尚不存在，避免覆盖：{output_dir}")
    parent = output_dir.parent
    if not parent.is_dir():
        parent.mkdir(parents=True, exist_ok=True)

    if cache_directory is not None and _cache_is_usable(cache_directory, count=count):
        _report(progress, "复用剧照缓存", f"该账号+剧集已有剧照缓存，直接复用：{cache_directory}")
        copied = _publish_from_cache(cache_directory=cache_directory, output_dir=output_dir, count=count)
        prepared = tuple(copied["items"])
        return PhotoPrepDecision(
            count=count, output_directory=str(output_dir), source_scope="reused_from_cache",
            source_drama_names=tuple(copied["drama_names"]), source_drama_directories=(),
            source_videos=tuple(copied["source_videos"]), face_preference=FACE_PREFERENCE,
            ocr_subtitle_blur="rapidocr_all_detected_text_gaussian_softening_after_three_four_crop",
            items=prepared,
        )

    _report(progress, "扫描剧集素材", "正在查找可用于剧照的剧集视频")
    dramas, sources = account_day_video_sources(account_day_dir=account_day_dir, progress=progress)
    _report(progress, "剧集素材已就绪", f"已找到 {len(dramas)} 个剧集目录、{len(sources)} 条可读视频；开始准备 10 张剧照")
    chosen: list[FrameCandidate] = []
    prepared: list[PreparedPhoto] = []
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.", dir=parent) as temporary_name:
        temporary = Path(temporary_name)
        raw = temporary / "raw"
        raw.mkdir()
        final = temporary / "prepared"
        final.mkdir()
        total_duration = sum(source.duration_seconds for source in sources)
        # ---- 第一步：在整批素材上铺候选帧 --------------------------------------
        # 老做法是"按总时长均匀取 10 个时间点，每点看 ±2.4 秒"。在 2026-09-18 的真实素材上
        # （12 集、5066 秒）它会在第 8、10 集恰好抓到没有人的片段，10 张里有 2 张是空镜/车内视角。
        # 实测扫描 480 张有 39% 是可用人物剧照，所以改成"多铺候选、再全局挑最好的"。
        windows = planned_windows(total_duration=total_duration, count=WINDOW_COUNT)
        candidates: list[tuple[FrameCandidate, Path]] = []
        extraction_seconds = 0.0
        analysis_seconds = 0.0
        for window_index, (window_start, window_end) in enumerate(windows, start=1):
            for offset_index, fraction in enumerate(FRAME_OFFSET_FRACTIONS, start=1):
                moment = window_start + (window_end - window_start) * fraction
                source, local_time = locate_source_time(sources=sources, global_time=moment)
                candidate_time = min(max(0.08, local_time), max(0.08, source.duration_seconds - 0.08))
                frame = raw / f"w{window_index:02d}_{offset_index:02d}.jpg"
                _report(
                    progress, "抽取候选画面",
                    f"候选 {window_index}/{len(windows)}：正在从 {source.path.name} 抽取画面 {offset_index}/{len(FRAME_OFFSET_FRACTIONS)}",
                )
                started = time.monotonic()
                _extract_frame(source=source, time_seconds=candidate_time, target=frame)
                extraction_seconds += time.monotonic() - started
                _report(progress, "分析候选画面", f"候选 {window_index}/{len(windows)}：正在识别人脸与质量")
                started = time.monotonic()
                candidates.append((_measure_frame(source=source, time_seconds=candidate_time, frame_path=frame), frame))
                analysis_seconds += time.monotonic() - started
        _report(
            progress, "候选画面已就绪",
            f"共 {len(candidates)} 张候选（含人脸 {sum(1 for item, _ in candidates if item.face_count)} 张，"
            f"其中正对镜头 {sum(1 for item, _ in candidates if item.frontal_score >= 0.7)} 张、"
            f"闭眼或喊叫 {sum(1 for item, _ in candidates if item.face_blurred)} 张），"
            f"正在挑出 {count} 张",
        )

        # ---- 第二步：按降级阶梯挑满 10 张 -------------------------------------
        # 用户 2026-09-18 明确："宁可 10 张里有些质量差，也不能少数量。"
        # 模板对剧照有三道硬校验（恰好 10 个文件 / 路径不重复 / SHA256 不重复），
        # 少一张整个模板任务就失败，所以这里保证凑满，代价是质量可能下降。
        selection, used_stage = select_photo_set(
            candidates=(item[0] for item in candidates), count=count,
        )
        if used_stage == "strict":
            _report(progress, "挑选完成", f"10 张剧照全部达到严格标准（正脸、睁眼、大小合适、无重复演员）")
        else:
            _report(
                progress, "已降低挑选标准",
                f"正面镜头不足，本次使用了「{used_stage}」级别凑满 10 张；照片墙上可能出现质量一般的画面",
            )

        path_for = {id(candidate): path for candidate, path in candidates}
        used_variants: set[int] = set()
        seen_persons: list[Any] = []
        for index, candidate in enumerate(selection, start=1):
            photo_started = time.monotonic()
            # 这位演员在本次照片墙里是第几张（用于事后核对"同一个人占了几张"）
            person_ordinal: int | None = None
            if candidate.identity is not None:
                same = [prior for prior in seen_persons if candidate.identity.is_same_person(prior)]
                if same:
                    person_ordinal = len(same) + 1
                else:
                    seen_persons.append(candidate.identity)
                    person_ordinal = 1
            source_frame = path_for[id(candidate)]
            target = final / f"剧集人物_{index:03d}.jpg"
            variant_of = ""
            if used_stage == "variants" and id(candidate) in used_variants:
                # 最后手段：同一画面做极轻微二次裁切，做出不同字节以通过 SHA256 重复校验。
                # 肉眼几乎不可分辨，但能保证"数量永远够 10 张"。
                variant_of = source_frame.name
            used_variants.add(id(candidate))
            # 只在**被选中的那一帧**上找人脸，不要为了画面差异改用同槽位的另一帧：
            # 换了帧，脸就可能换成另一个人，身份去重（对候选帧做的）就白做了。
            # 实测教训：交付的 10 张里曾出现 3 对同一演员（相似度 0.87），而清单却记着 10 个不同的人。
            face = _best_face(source_frame)
            crop_mode = "face_centered" if face is not None else "center"
            _report(
                progress, "裁切剧照",
                f"剧照 {index}/{count}：正在裁切成 3:4 画面"
                + (
                    f"（以人脸为中心；正面分 {candidate.frontal_score:.2f}，人脸 {candidate.face_count} 个，"
                    f"脸宽 {candidate.face_width:.0f}px，人脸分 {candidate.face_score:.3f}"
                    + (f"，闭眼 {candidate.eyes_closed:.2f}" if candidate.expression_measured else "")
                    + "）"
                    if face is not None
                    else f"（本张没检测到人脸，按画面中心裁切；人脸 {candidate.face_count} 个，"
                         f"人脸分 {candidate.face_score:.3f}）"
                )
                + f"；来源 {candidate.source.path.name} @ {candidate.time_seconds:.1f}s"
                + ("；**保底凑数**" if variant_of else ""),
            )
            started = time.monotonic()
            _crop_three_four(source_frame, target, face=face, variant=bool(variant_of))
            crop_seconds = time.monotonic() - started
            _report(progress, "OCR 字幕处理", f"剧照 {index}/{count}：正在识别并柔化字幕")
            started = time.monotonic()
            subtitle_blur_count = soften_detected_text(image_path=target)
            ocr_seconds = time.monotonic() - started
            prepared.append(PreparedPhoto(
                index=index, source_video=str(candidate.source.path), source_time_seconds=round(candidate.time_seconds, 3),
                output=str(output_dir / target.name), sha256=_sha256(target), sharpness=round(candidate.sharpness, 3),
                exposure_penalty=round(candidate.exposure_penalty, 3), face_preference=FACE_PREFERENCE,
                subtitle_blur_count=subtitle_blur_count,
                face_count=candidate.face_count, face_score=candidate.face_score, crop_mode=crop_mode,
                frontal_score=candidate.frontal_score, face_width=round(candidate.face_width, 1),
                eyes_closed=candidate.eyes_closed, mouth_open=candidate.mouth_open, smile=candidate.smile,
                person_ordinal=person_ordinal, variant_of=variant_of,
            ))
            _report(
                progress,
                "剧照处理完成",
                f"剧照 {index}/{count} 已完成：裁切 {crop_seconds:.2f} 秒，"
                f"OCR {ocr_seconds:.2f} 秒，本张合计 {time.monotonic() - photo_started:.2f} 秒"
                f"（全部候选抽帧累计 {extraction_seconds:.2f} 秒、分析累计 {analysis_seconds:.2f} 秒）",
            )
        if len({item.sha256 for item in prepared}) != count:
            raise RuntimeError("剧照候选仍出现完全重复，拒绝生成重复照片墙")
        manifest = {
            "kind": "jianying59_template_photo_prep",
            "count": count,
            "source_scope": "all_readable_viral_videos_in_current_account_day",
            "source_drama_names": [drama.drama_name for drama in dramas],
            "source_drama_directories": [str(drama.directory) for drama in dramas],
            "source_videos": [str(source.path) for source in sources],
            "face_preference": FACE_PREFERENCE,
            "face_detector_available": drama_face.detector_available(),
            "expression_detector_available": drama_expression.available(),
            "identity_model_available": drama_identity.available(),
            "selection_stage": used_stage,
            "selection_rules": {
                "window_count": WINDOW_COUNT,
                "frames_per_window": len(FRAME_OFFSET_FRACTIONS),
                "min_frontal_score": MIN_FRONTAL_SCORE,
                "min_face_width_px": MIN_FACE_WIDTH_PX,
                "max_photos_per_video": MAX_PHOTOS_PER_VIDEO,
                "max_photos_per_person": MAX_PHOTOS_PER_PERSON,
                "min_source_gap_seconds": MIN_SOURCE_GAP_SECONDS,
                "max_eyes_closed": MAX_EYES_CLOSED,
                "max_mouth_open": MAX_MOUTH_OPEN,
            },
            "quality": {
                "avg_frontal_score": round(
                    sum(item.frontal_score for item in prepared) / max(1, len(prepared)), 4
                ),
                "min_face_width_px": round(min((item.face_width for item in prepared), default=0.0), 1),
                "eyes_closed_photos": sum(1 for item in prepared if item.eyes_closed >= MAX_EYES_CLOSED),
                "shouting_photos": sum(1 for item in prepared if item.mouth_open >= MAX_MOUTH_OPEN),
                "smiling_photos": sum(1 for item in prepared if item.smile >= drama_expression.SMILE_THRESHOLD),
                "distinct_people": len(seen_persons),
                "duplicate_fill_photos": sum(1 for item in prepared if item.variant_of),
            },
            "ocr_subtitle_blur": "rapidocr_all_detected_text_gaussian_softening_after_three_four_crop",
            "items": [asdict(item) for item in prepared],
        }
        (final / "剧照准备清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        _report(progress, "发布剧照", "10 张剧照已完成，正在写入任务缓存")
        os.replace(final, output_dir)

    # 写一份到"账号+剧集"缓存，供同一单位的后续任务/重试直接复用（素材变了会自动重做）。
    if cache_directory is not None:
        try:
            import shutil

            staging = cache_directory.parent / f".{cache_directory.name}.staging"
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            for item in prepared:
                shutil.copyfile(item.output, staging / Path(item.output).name)
            manifest_path = output_dir / "剧照准备清单.json"
            if manifest_path.is_file():
                shutil.copyfile(manifest_path, staging / manifest_path.name)
            shutil.rmtree(cache_directory, ignore_errors=True)
            os.replace(staging, cache_directory)
            removed = prune_photo_cache(cache_directory.parent)
            _report(
                progress, "已写入剧照缓存",
                f"下次同一账号+剧集的任务可直接复用：{cache_directory}"
                + (f"（顺带清理了 {removed} 份旧素材的缓存）" if removed else ""),
            )
        except OSError as exc:
            # 缓存失败绝不能影响本次任务：照片已经交付了。
            _report(progress, "剧照缓存跳过", f"本次剧照已生成，但缓存写入失败（不影响使用）：{exc}")

    return PhotoPrepDecision(
        count=count, output_directory=str(output_dir), source_scope="all_readable_viral_videos_in_current_account_day",
        source_drama_names=tuple(drama.drama_name for drama in dramas),
        source_drama_directories=tuple(str(drama.directory) for drama in dramas),
        source_videos=tuple(str(source.path) for source in sources),
        face_preference=FACE_PREFERENCE,
        ocr_subtitle_blur="rapidocr_all_detected_text_gaussian_softening_after_three_four_crop", items=tuple(prepared),
    )
