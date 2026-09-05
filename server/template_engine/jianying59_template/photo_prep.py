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


PHOTO_COUNT = 10
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".m4v"})
FRAME_OFFSETS = (-2.4, -1.2, 0.0, 1.2, 2.4)
ProgressReporter = Callable[[str, str], None]


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
    return FrameCandidate(
        source=source, time_seconds=time_seconds, width=width, height=height,
        sharpness=sharpness, exposure_penalty=exposure_penalty, perceptual_key=perceptual_key,
    )


def _difference(first: FrameCandidate, second: FrameCandidate) -> float:
    return sum(abs(left - right) for left, right in zip(first.perceptual_key, second.perceptual_key, strict=True)) / len(first.perceptual_key)


def choose_frame_candidate(*, candidates: Iterable[FrameCandidate], already_selected: Iterable[FrameCandidate]) -> FrameCandidate:
    """Pick a sharp, exposed and non-duplicate option around one timeline slot."""
    options = tuple(candidates)
    if not options:
        raise ValueError("候选剧照不能为空")
    selected = tuple(already_selected)

    def score(candidate: FrameCandidate) -> tuple[float, float, float]:
        duplicate_distance = min((_difference(candidate, prior) for prior in selected), default=255.0)
        # First prefer meaningful visual difference, then quality.  This keeps
        # ten wall cards from becoming near-identical even inside one episode.
        quality = math.log1p(max(candidate.sharpness, 0.0)) * 8.0 - candidate.exposure_penalty * 1.4
        return (duplicate_distance, quality, -abs(candidate.time_seconds))

    return max(options, key=score)


def _crop_three_four(source: Path, target: Path) -> None:
    from PIL import Image

    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            raise RuntimeError(f"剧照尺寸无效：{source.name}")
        if width / height > 3 / 4:
            crop_width = round(height * 3 / 4)
            left = (width - crop_width) // 2
            box = (left, 0, left + crop_width, height)
        else:
            crop_height = round(width * 4 / 3)
            top = (height - crop_height) // 2
            box = (0, top, width, top + crop_height)
        image.crop(box).save(target, format="JPEG", quality=95, subsampling=0)


_OCR_ENGINE: Any | None = None


def _local_ocr_boxes(image_path: Path) -> tuple[tuple[float, float, float, float], ...]:
    """Return all locally recognised text bounds from a prepared 3:4 image."""
    global _OCR_ENGINE
    import cv2
    import numpy
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:  # Do not pretend that subtitle processing ran.
        raise RuntimeError("本机缺少 RapidOCR，无法执行剧照字幕柔化") from exc
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    encoded = numpy.fromfile(str(image_path), dtype=numpy.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RuntimeError(f"裁切后的剧照无法供 OCR 读取：{image_path.name}")
    result, _elapsed = _OCR_ENGINE(image)
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_drama_photos(*, account_day_dir: Path, output_dir: Path, seed: int, count: int = PHOTO_COUNT,
                         progress: ProgressReporter | None = None) -> PhotoPrepDecision:
    """Create exactly ten varied 3:4 stills without modifying source videos.

    All readable viral videos under the current account/day participate.  The
    planner keeps deterministic source order, then uses local quality and
    de-duplication; every final 3:4 image is OCR-checked and its detected text
    is softly blurred.  Source videos are never modified.
    """
    if count != PHOTO_COUNT:
        raise ValueError("当前照片墙合同固定需要10张剧照")
    if output_dir.exists():
        raise FileExistsError(f"剧照输出目录必须尚不存在，避免覆盖：{output_dir}")
    _report(progress, "扫描剧集素材", "正在查找可用于剧照的剧集视频")
    dramas, sources = account_day_video_sources(account_day_dir=account_day_dir, progress=progress)
    _report(progress, "剧集素材已就绪", f"已找到 {len(dramas)} 个剧集目录、{len(sources)} 条可读视频；开始准备 10 张剧照")
    parent = output_dir.parent
    if not parent.is_dir():
        parent.mkdir(parents=True, exist_ok=True)
    chosen: list[FrameCandidate] = []
    prepared: list[PreparedPhoto] = []
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.", dir=parent) as temporary_name:
        temporary = Path(temporary_name)
        raw = temporary / "raw"
        raw.mkdir()
        final = temporary / "prepared"
        final.mkdir()
        total_duration = sum(source.duration_seconds for source in sources)
        for index, global_time in enumerate(planned_global_times(total_duration=total_duration, count=count), start=1):
            source, local_time = locate_source_time(sources=sources, global_time=global_time)
            candidate_paths: list[tuple[FrameCandidate, Path]] = []
            for offset_index, offset in enumerate(FRAME_OFFSETS, start=1):
                candidate_time = min(max(0.08, local_time + offset), max(0.08, source.duration_seconds - 0.08))
                frame = raw / f"{index:02d}_{offset_index:02d}.jpg"
                _report(progress, "抽取候选画面", f"剧照 {index}/{count}：正在从 {source.path.name} 抽取候选画面 {offset_index}/{len(FRAME_OFFSETS)}")
                _extract_frame(source=source, time_seconds=candidate_time, target=frame)
                _report(progress, "分析候选画面", f"剧照 {index}/{count}：正在分析候选画面 {offset_index}/{len(FRAME_OFFSETS)}")
                candidate_paths.append((_measure_frame(source=source, time_seconds=candidate_time, frame_path=frame), frame))
            candidate = choose_frame_candidate(candidates=(item[0] for item in candidate_paths), already_selected=chosen)
            source_frame = next(path for measured, path in candidate_paths if measured == candidate)
            target = final / f"剧集人物_{index:03d}.jpg"
            _report(progress, "裁切剧照", f"剧照 {index}/{count}：正在裁切为 3:4 画面")
            _crop_three_four(source_frame, target)
            _report(progress, "OCR 字幕处理", f"剧照 {index}/{count}：正在识别并柔化字幕")
            subtitle_blur_count = soften_detected_text(image_path=target)
            prepared.append(PreparedPhoto(
                index=index, source_video=str(candidate.source.path), source_time_seconds=round(candidate.time_seconds, 3),
                output=str(output_dir / target.name), sha256=_sha256(target), sharpness=round(candidate.sharpness, 3),
                exposure_penalty=round(candidate.exposure_penalty, 3), face_preference="not_enabled_no_reliable_local_human_and_animal_detector",
                subtitle_blur_count=subtitle_blur_count,
            ))
            chosen.append(candidate)
            _report(progress, "剧照处理完成", f"剧照 {index}/{count} 已完成")
        if len({item.sha256 for item in prepared}) != count:
            raise RuntimeError("剧照候选仍出现完全重复，拒绝生成重复照片墙")
        manifest = {
            "kind": "jianying59_template_photo_prep",
            "count": count,
            "source_scope": "all_readable_viral_videos_in_current_account_day",
            "source_drama_names": [drama.drama_name for drama in dramas],
            "source_drama_directories": [str(drama.directory) for drama in dramas],
            "source_videos": [str(source.path) for source in sources],
            "face_preference": "not_enabled_no_reliable_local_human_and_animal_detector",
            "ocr_subtitle_blur": "rapidocr_all_detected_text_gaussian_softening_after_three_four_crop",
            "items": [asdict(item) for item in prepared],
        }
        (final / "剧照准备清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        _report(progress, "发布剧照", "10 张剧照已完成，正在写入任务缓存")
        os.replace(final, output_dir)
    return PhotoPrepDecision(
        count=count, output_directory=str(output_dir), source_scope="all_readable_viral_videos_in_current_account_day",
        source_drama_names=tuple(drama.drama_name for drama in dramas),
        source_drama_directories=tuple(str(drama.directory) for drama in dramas),
        source_videos=tuple(str(source.path) for source in sources),
        face_preference="not_enabled_no_reliable_local_human_and_animal_detector",
        ocr_subtitle_blur="rapidocr_all_detected_text_gaussian_softening_after_three_four_crop", items=tuple(prepared),
    )
