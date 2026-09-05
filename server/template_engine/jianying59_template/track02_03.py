"""T02/T03: native 5.9 compound photo walls.

The visible photo walls are not a collection of ordinary main-timeline image
tracks.  Each wall is a small native Jianying draft kept in ``materials.drafts``
and replayed by one parent compound segment.  This is the same native mechanism
used by the earlier 5.9 track tests; only the finished legacy photo-wall rules
are carried forward here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .project_base import CANVAS_HEIGHT, CANVAS_WIDTH, T00ProjectPlan, VideoProbe, create_native_t00_draft
from .track01 import (
    MICROSECONDS,
    Track01Decision,
    _attach_native_paths_and_filter,
    _default_user_data_root,
    add_track01_to_draft,
    decide_track01,
)
from server.jianying_resource_paths import attach_cached_path_if_present
from .track04 import Track04Decision, _attach_native_mirror_path, add_track04_to_draft, decide_track04


PHOTO_COUNT = 10
PHOTO_DURATION_US = 5 * MICROSECONDS
NESTED_CANVAS_WIDTH = 3806
# These three values are the visual 019A calibration anchor from the completed
# generator.  They define the actual rendered card width; clip.scale means
# motion extent, not card size.
PHOTO_ANCHOR_NESTED_HEIGHT = 983
PHOTO_ANCHOR_SCALE = 0.6424
PHOTO_ANCHOR_INTERVAL_FRAMES = 19
PHOTO_ANCHOR_GAP_PX = 15.0
PHOTO_ANCHOR_WIDTH_PX = (
    CANVAS_WIDTH * (1.0 + PHOTO_ANCHOR_SCALE) * PHOTO_ANCHOR_INTERVAL_FRAMES / (5 * 30)
    - PHOTO_ANCHOR_GAP_PX
)


@dataclass(frozen=True)
class PhotoInput:
    source_path: str
    normalized_path: str
    sha256: str
    width: int
    height: int


@dataclass(frozen=True)
class PhotoWallDecision:
    seed: int
    direction: str
    central_height_ratio: float
    central_half_height_canvas: float
    wall_height_canvas: float
    nested_canvas_width: int
    nested_canvas_height: int
    vertical_scale_correction: float
    position_y_normalized_abs: float
    target_gap_canvas_px: float
    preferred_motion_extent: float
    motion_extent: float
    interval_frames: int
    interval_us: int
    movement_duration_us: int
    photo_width_canvas_px: float
    movement_per_frame_canvas_px: float
    actual_gap_canvas_px: float
    loop_duplicate_count: int
    cycle_duration_us: int
    pre_roll_us: int
    target_duration_us: int
    nested_entry_count: int
    nested_duration_us: int
    feather: float
    source_photos: tuple[PhotoInput, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def _natural_key(path: Path) -> tuple[Any, ...]:
    return tuple(int(piece) if piece.isdigit() else piece.casefold() for piece in re.split(r"(\d+)", path.name))


def normalize_three_four_photos(*, photo_dir: Path, cache_root: Path) -> tuple[PhotoInput, ...]:
    """Use the old center-crop policy and retain the normalized image by hash.

    The former generator first made reusable 3:4 files, then explicitly cleared
    crop on the Jianying material.  Keeping that sequence avoids both stretching
    and accidental inheritance of a second crop from a prior draft.
    """
    from PIL import Image

    # The active photo-preparation step stores its small source manifest beside
    # the ten JPEGs.  Treat only image files as wall inputs; a metadata JSON
    # must not become an accidental eleventh "photo".
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    sources = sorted(
        (path for path in photo_dir.iterdir() if path.is_file() and path.suffix.casefold() in image_extensions),
        key=_natural_key,
    )
    if len(sources) != PHOTO_COUNT:
        raise ValueError(f"T03/T04必须恰好提供10张短剧人物图，当前为{len(sources)}张")
    if len({path.resolve() for path in sources}) != PHOTO_COUNT:
        raise ValueError("T03/T04短剧人物图不能重复")

    cache_root.mkdir(parents=True, exist_ok=True)
    results: list[PhotoInput] = []
    for index, source in enumerate(sources, start=1):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        target = cache_root / f"照片墙_3x4_{index:02d}_{digest[:12]}.jpg"
        with Image.open(source) as image:
            image = image.convert("RGB")
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError(f"人物图尺寸无效：{source.name}")
            if width / height > 3 / 4:
                crop_width = round(height * 3 / 4)
                left = (width - crop_width) // 2
                box = (left, 0, left + crop_width, height)
            else:
                crop_height = round(width / (3 / 4))
                top = (height - crop_height) // 2
                box = (0, top, width, top + crop_height)
            if not target.is_file():
                image.crop(box).save(target, format="JPEG", quality=95, subsampling=0)
        with Image.open(target) as normalized:
            normalized_width, normalized_height = normalized.size
        if normalized_width * 4 != normalized_height * 3:
            raise RuntimeError(f"T03/T04标准化后不是3:4：{target.name}")
        results.append(
            PhotoInput(
                source_path=str(source.resolve()),
                normalized_path=str(target.resolve()),
                sha256=digest,
                width=normalized_width,
                height=normalized_height,
            )
        )
    return tuple(results)


def _aligned_start(*, index: int, interval_frames: int) -> int:
    """Convert each accumulated frame count independently, never accumulated us."""
    return round(index * interval_frames * MICROSECONDS / 30)


def _phase_adjusted_entry(*, index: int, decision: PhotoWallDecision) -> tuple[int, int, float]:
    """Place legacy pre-roll inside the nested timeline instead of trimming it.

    Jianying 5.9 combinations persist correctly when their parent starts at
    source time zero.  For the first cycle, cards that had already entered
    during the legacy pre-roll begin at nested time zero at their in-flight X
    position and only keep their remaining visible duration.
    """
    shifted_start = _aligned_start(index=index, interval_frames=decision.interval_frames) - decision.pre_roll_us
    if shifted_start >= 0:
        return shifted_start, decision.movement_duration_us, 0.0
    remaining = decision.movement_duration_us + shifted_start
    if remaining <= 0:
        raise RuntimeError("照片墙预滚超过单张照片运动时长")
    return 0, remaining, -shifted_start / decision.movement_duration_us


def decide_photo_walls(
    *,
    seed: int,
    track01: Track01Decision,
    photos: Iterable[PhotoInput],
    target_duration_us: int = 180 * MICROSECONDS,
) -> PhotoWallDecision:
    selected = tuple(photos)
    if len(selected) != PHOTO_COUNT:
        raise ValueError("照片墙决策必须接收10张人物图")
    if len({item.sha256 for item in selected}) != PHOTO_COUNT:
        raise ValueError("照片墙决策不能使用重复人物图")
    if any(item.width * 4 != item.height * 3 for item in selected):
        raise ValueError("照片墙必须使用已经标准化的3:4人物图")
    if target_duration_us <= 0:
        raise ValueError("照片墙目标时长必须大于零")

    central_half = CANVAS_HEIGHT * track01.canvas_height_ratio / 2
    wall_height = (CANVAS_HEIGHT - CANVAS_HEIGHT * track01.canvas_height_ratio) / 2
    nested_height = round(wall_height * NESTED_CANVAS_WIDTH / CANVAS_WIDTH)
    raw_wall_height = nested_height * CANVAS_WIDTH / NESTED_CANVAS_WIDTH
    vertical_scale = wall_height / raw_wall_height
    position_y_abs = 2 * (central_half + wall_height / 2) / CANVAS_HEIGHT

    rng = random.Random(f"{seed}:photo-gap")
    target_gap = round(rng.uniform(12.0, 18.0), 6)
    preferred_extent = round(rng.uniform(0.55, 0.70), 6)
    direction = random.Random(f"{seed}:photo-direction").choice(("left_to_right", "right_to_left"))
    feather = round(random.Random(f"{seed}:photo-wall-feather").uniform(0.30, 0.40), 6)
    photo_width = PHOTO_ANCHOR_WIDTH_PX * nested_height / PHOTO_ANCHOR_NESTED_HEIGHT
    minimum_extent = max(0.45, preferred_extent - 0.08)
    maximum_extent = min(0.75, preferred_extent + 0.08)
    candidates: list[tuple[float, float, int, float, float]] = []
    for extent_step in range(math.ceil(minimum_extent * 10_000), math.floor(maximum_extent * 10_000) + 1):
        extent = extent_step / 10_000
        per_frame = CANVAS_WIDTH * (1 + extent) / (5 * 30)
        for frames in range(15, 36):
            gap = per_frame * frames - photo_width
            if 10.0 <= gap <= 20.0:
                score = abs(gap - target_gap) * 1000 + abs(extent - preferred_extent) * 20
                candidates.append((score, extent, frames, per_frame, gap))
    if not candidates:
        raise RuntimeError("本种子没有满足10–20像素间隙的照片墙合法解")
    _, extent, interval_frames, per_frame, actual_gap = min(candidates)
    interval_us = round(interval_frames * MICROSECONDS / 30)
    duplicates = math.ceil(PHOTO_DURATION_US / interval_us)
    cycle_duration = _aligned_start(index=PHOTO_COUNT, interval_frames=interval_frames)
    pre_roll = _aligned_start(index=duplicates - 1, interval_frames=interval_frames)
    # Preserve the original outer-repeat contract: the nested composition is
    # one short cycle with its tail copies, while the main photo-wall track
    # places that cycle continuously across the full 180-second template.
    nested_entry_count = PHOTO_COUNT + duplicates
    nested_duration = _aligned_start(index=nested_entry_count, interval_frames=interval_frames) + PHOTO_DURATION_US
    return PhotoWallDecision(
        seed=seed,
        direction=direction,
        central_height_ratio=track01.canvas_height_ratio,
        central_half_height_canvas=round(central_half, 6),
        wall_height_canvas=round(wall_height, 6),
        nested_canvas_width=NESTED_CANVAS_WIDTH,
        nested_canvas_height=nested_height,
        vertical_scale_correction=round(vertical_scale, 9),
        position_y_normalized_abs=round(position_y_abs, 9),
        target_gap_canvas_px=target_gap,
        preferred_motion_extent=preferred_extent,
        motion_extent=round(extent, 9),
        interval_frames=interval_frames,
        interval_us=interval_us,
        movement_duration_us=PHOTO_DURATION_US,
        photo_width_canvas_px=round(photo_width, 6),
        movement_per_frame_canvas_px=round(per_frame, 9),
        actual_gap_canvas_px=round(actual_gap, 6),
        loop_duplicate_count=duplicates,
        cycle_duration_us=cycle_duration,
        pre_roll_us=pre_roll,
        target_duration_us=target_duration_us,
        nested_entry_count=nested_entry_count,
        nested_duration_us=nested_duration,
        feather=feather,
        source_photos=selected,
    )


def _build_nested_photo_wall(*, decision: PhotoWallDecision) -> dict[str, Any]:
    """Build one short native photo-wall cycle with its overlap tail."""
    from pyJianYingDraft import ClipSettings, KeyframeProperty, ScriptFile, Timerange, TrackType, VideoMaterial, VideoSegment

    nested = ScriptFile(
        decision.nested_canvas_width,
        decision.nested_canvas_height,
        30,
        False,
    )
    for index in range(decision.nested_entry_count):
        photo = decision.source_photos[index % PHOTO_COUNT]
        # A saved 5.9 compound creates a fresh child track and material object
        # for every repeated placement of the same physical image.  The path is
        # intentionally repeated, while the native material object id stays
        # unique for that occurrence.
        track_name = f"PHOTO_{index + 1:03d}"
        nested.add_track(TrackType.video, track_name, relative_index=index)
        start, visible_duration, initial_progress = _phase_adjusted_entry(index=index, decision=decision)
        segment = VideoSegment(
            VideoMaterial(photo.normalized_path),
            Timerange(start, visible_duration),
            source_timerange=Timerange(0, visible_duration),
            volume=0.0,
            # The normalized 3:4 material is already the correct wall height
            # at 100% in Jianying 5.9.  The old extra fit displayed as 130%.
            # X remains the legacy motion-range carrier.
            clip_settings=ClipSettings(
                scale_x=decision.motion_extent,
                scale_y=1.0,
            ),
        )
        if decision.direction == "right_to_left":
            x_start, x_end = 1 + decision.motion_extent, -1 - decision.motion_extent
        else:
            x_start, x_end = -1 - decision.motion_extent, 1 + decision.motion_extent
        x_at_entry = x_start + (x_end - x_start) * initial_progress
        segment.add_keyframe(KeyframeProperty.scale_x, 0, 1.0)
        segment.add_keyframe(KeyframeProperty.position_x, 0, x_at_entry)
        segment.add_keyframe(KeyframeProperty.position_x, visible_duration, x_end)
        nested.add_segment(segment, track_name)
    document = json.loads(nested.dumps())
    document["duration"] = decision.nested_duration_us
    document["canvas_config"] = {
        "width": decision.nested_canvas_width,
        "height": decision.nested_canvas_height,
        "ratio": f"{round(decision.nested_canvas_width / decision.nested_canvas_height, 4)}:1",
    }
    # These are physically normalized 3:4 files.  Clear the library's default
    # crop so Jianying never applies a second crop to a completed source.
    for material in document.get("materials", {}).get("videos", []):
        # A native 5.9 compound stores local child media by their own ``id``;
        # ``material_id`` must stay empty.  The manually created, reopenable
        # ``测试`` compound has this exact contract.  Setting it to the media
        # ID makes Jianying rewrite the parent as a missing-material placeholder
        # after the project is reopened.
        material["material_id"] = ""
        material["local_material_id"] = ""
        material["crop"] = {}
        material["crop_ratio"] = "3:4"
        material["has_audio"] = False
    # A native 5.9 compound uses track-render-index mode for overlapping
    # internal picture tracks.  Without it every generated child segment has
    # track_render_index=0, and the compositor renders only the last layer.
    document["render_index_track_mode_on"] = True
    for track_render_index, track in enumerate(document.get("tracks", []), start=1):
        for segment in track.get("segments", []):
            segment["track_render_index"] = track_render_index
    return document


def _new_line_mask(*, first_photo: PhotoInput, feather: float, region: str, user_data_root: Path) -> dict[str, Any]:
    """Ask pyJianYingDraft for the current 5.9 line-mask shape, then configure it."""
    from pyJianYingDraft import MaskType, ScriptFile, Timerange, TrackType, VideoMaterial, VideoSegment

    scratch = ScriptFile(1080, 2400, 30, False)
    scratch.add_track(TrackType.video, "MASK_TEMPLATE")
    segment = VideoSegment(VideoMaterial(first_photo.normalized_path), Timerange(0, MICROSECONDS), volume=0.0)
    segment.add_mask(list(MaskType)[0], center_x=0.0, center_y=0.0, size=0.5, feather=30.0)
    scratch.add_segment(segment, "MASK_TEMPLATE")
    payload = json.loads(scratch.dumps())
    material = next(item for item in payload["materials"]["masks"] if item.get("resource_type") == "line")
    material = copy.deepcopy(material)
    material["id"] = uuid.uuid4().hex
    attach_cached_path_if_present(material, user_data_root / "Cache" / "effect" / str(list(MaskType)[0].value.effect_id))
    material["config"] = {
        "aspectRatio": 1.0,
        "centerX": 0.0,
        "centerY": 0.78 if region == "top" else -0.78,
        "feather": feather,
        "height": 0.0,
        "invert": region == "top",
        "rotation": 0.0,
        "roundCorner": 0.0,
        "width": 0.28,
    }
    return material


def _append_component_materials(*, document: dict[str, Any], draft_ref_id: str) -> list[str]:
    materials = document.setdefault("materials", {})
    speed_id = uuid.uuid4().hex
    canvas_id = uuid.uuid4().hex
    mapping_id = uuid.uuid4().hex
    vocal_id = uuid.uuid4().hex
    materials.setdefault("speeds", []).append({"curve_speed": None, "id": speed_id, "mode": 0, "speed": 1.0, "type": "speed"})
    materials.setdefault("canvases", []).append({"album_image": "", "blur": 0.0, "color": "", "id": canvas_id, "image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": "", "type": "canvas_color"})
    materials.setdefault("sound_channel_mappings", []).append({"audio_channel_mapping": 0, "id": mapping_id, "is_config_open": False, "type": ""})
    materials.setdefault("vocal_separations", []).append({"choice": 0, "id": vocal_id, "production_path": "", "time_range": None, "type": "vocal_separation"})
    return [speed_id, draft_ref_id, canvas_id, mapping_id, vocal_id]


def _append_parent_compound(
    *,
    document: dict[str, Any],
    decision: PhotoWallDecision,
    region: str,
    track_name: str,
    relative_index: int,
    user_data_root: Path,
) -> None:
    """Attach independent native compound cycles across the photo-wall track."""
    materials = document.setdefault("materials", {})
    videos = materials.setdefault("videos", [])
    direct_material = next((item for item in videos if item.get("path")), None)
    if direct_material is None:
        raise RuntimeError("T03/T04需要T01或T02提供一个当前5.9视频材料模板")
    mask = _new_line_mask(first_photo=decision.source_photos[0], feather=decision.feather, region=region, user_data_root=user_data_root)
    materials.setdefault("masks", []).append(mask)

    track = next((item for item in document.get("tracks", []) if item.get("name") == track_name), None)
    if track is None:
        raise RuntimeError(f"T03/T04草稿没有预留轨道：{track_name}")
    prototype = next(
        segment
        for candidate in document.get("tracks", [])
        for segment in candidate.get("segments", [])
        if candidate.get("name") == "T01_OUTER_VIDEO"
    )
    sign = 1.0 if region == "bottom" else -1.0
    parent_segments: list[dict[str, Any]] = []
    cursor = 0
    while cursor < decision.target_duration_us:
        placement_duration = min(decision.cycle_duration_us, decision.target_duration_us - cursor)
        nested = _build_nested_photo_wall(decision=decision)
        nested["id"] = str(uuid.uuid4()).upper()
        draft_ref_id = uuid.uuid4().hex
        compound_id = uuid.uuid4().hex
        materials.setdefault("drafts", []).append(
            {
                "category_id": "",
                "category_name": "",
                "combination_id": uuid.uuid4().hex,
                "draft": nested,
                "formula_id": "",
                "id": draft_ref_id,
                "name": f"{track_name}_CYCLE_{len(parent_segments) + 1:02d}",
                "precompile_combination": False,
                "type": "combination",
            }
        )
        compound_material = copy.deepcopy(direct_material)
        compound_material.update(
            {
                "id": compound_id,
                "material_id": "",
                "local_material_id": "",
                "material_name": "底部短剧人物照片墙" if region == "bottom" else "顶部短剧人物照片墙",
                "path": "",
                "media_path": "",
                "duration": decision.nested_duration_us,
                "width": decision.nested_canvas_width,
                "height": decision.nested_canvas_height,
                "type": "video",
                "has_audio": False,
                "extra_type_option": 2,
                "is_copyright": True,
                "category_id": "",
                "category_name": "",
            }
        )
        videos.append(compound_material)
        component_refs = _append_component_materials(document=document, draft_ref_id=draft_ref_id)
        component_refs.append(mask["id"])
        parent = copy.deepcopy(prototype)
        parent.update(
            {
                "id": uuid.uuid4().hex,
                "material_id": compound_id,
                "target_timerange": {"start": cursor, "duration": placement_duration},
                # The pre-roll is already encoded inside the nested timeline.
                # A 5.9 combination parent must always begin at source zero.
                "source_timerange": {"start": 0, "duration": placement_duration},
                "render_index": relative_index,
                "track_render_index": 0,
                "extra_material_refs": list(component_refs),
                "common_keyframes": [],
                "keyframe_refs": [],
                "volume": 0.0,
                "last_nonzero_volume": 1.0,
                "clip": {
                    "alpha": 1.0,
                    "flip": {"horizontal": False, "vertical": False},
                    "rotation": 0.0,
                    "scale": {"x": 1.0, "y": decision.vertical_scale_correction},
                    "transform": {"x": 0.0, "y": round(sign * decision.position_y_normalized_abs, 9)},
                },
                "uniform_scale": {"on": True, "value": 1.0},
            }
        )
        parent_segments.append(parent)
        cursor += placement_duration
    track["segments"] = parent_segments
    # The real 5.9 compound sample stores combination tracks in explicit
    # render-index mode.  Preserve that document-level contract for both walls.
    document["render_index_track_mode_on"] = True
    document.setdefault("config", {})["combination_max_index"] = max(
        int(document.get("config", {}).get("combination_max_index", 1)),
        len(materials.get("drafts", [])) + 1,
    )


def _attach_photo_walls(
    *,
    content_path: Path,
    decision: PhotoWallDecision,
    user_data_root: Path,
) -> None:
    with content_path.open("r", encoding="utf-8") as handle:
        document: dict[str, Any] = json.load(handle)
    _append_parent_compound(
        document=document,
        decision=decision,
        region="bottom",
        track_name="T02_BOTTOM_PHOTO_WALL",
        relative_index=2,
        user_data_root=user_data_root,
    )
    _append_parent_compound(
        document=document,
        decision=decision,
        region="top",
        track_name="T03_TOP_PHOTO_WALL",
        relative_index=3,
        user_data_root=user_data_root,
    )
    with content_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)


def create_track03_draft(
    *,
    draft_root: Path,
    draft_name: str,
    plan: T00ProjectPlan,
    source01: VideoProbe,
    source02: VideoProbe,
    photo_dir: Path,
    photo_cache_root: Path,
    user_data_root: Path | None = None,
) -> tuple[Track01Decision, Track04Decision, PhotoWallDecision]:
    """Create the cumulative native draft through the two confirmed photo walls."""
    if source01.height <= source01.width or source02.height <= source02.width:
        raise ValueError("T01/T04必须使用竖屏视频")
    photos = normalize_three_four_photos(photo_dir=photo_dir, cache_root=photo_cache_root)
    track01 = decide_track01(seed=plan.seed, source=source01)
    track04 = decide_track04(seed=plan.seed, source=source02, track01=track01)
    wall = decide_photo_walls(
        seed=plan.seed,
        track01=track01,
        photos=photos,
        target_duration_us=plan.duration_seconds * MICROSECONDS,
    )
    active_user_data_root = user_data_root or _default_user_data_root()

    from pyJianYingDraft import TrackType

    draft = create_native_t00_draft(draft_root=draft_root, draft_name=draft_name, plan=plan)
    draft.add_track(TrackType.video)
    add_track01_to_draft(draft=draft, plan=plan, source=source01, decision=track01)
    draft.add_track(TrackType.video, "T02_BOTTOM_PHOTO_WALL", relative_index=2)
    draft.add_track(TrackType.video, "T03_TOP_PHOTO_WALL", relative_index=3)
    add_track04_to_draft(draft=draft, plan=plan, source=source02, decision=track04)
    draft.save()
    content_path = draft_root / draft_name / "draft_content.json"
    _attach_native_paths_and_filter(content_path=content_path, decision=track01, user_data_root=active_user_data_root)
    _attach_native_mirror_path(content_path=content_path, user_data_root=active_user_data_root)
    _attach_photo_walls(content_path=content_path, decision=wall, user_data_root=active_user_data_root)
    return track01, track04, wall
