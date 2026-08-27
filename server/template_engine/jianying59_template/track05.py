"""T05: external video 003 in the mirror band opposite T04."""

from __future__ import annotations

import copy
import json
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import CANVAS_HEIGHT, T00ProjectPlan, VideoProbe
from .track01 import MICROSECONDS, Track01Decision, _default_user_data_root, _latest_payload, calculate_cover_geometry, decide_track01
from .track04 import Track04Decision
from .track02_03 import PhotoWallDecision, create_track03_draft


@dataclass(frozen=True)
class Track05Decision:
    seed: int
    source_path: str
    source_width: int
    source_height: int
    source_duration_seconds: float
    clip_scale: float
    central_half_height_canvas: float
    mirror_size_ui_px: int
    mask_height_material: float
    band_height_canvas: float
    feather: float
    fade_buffer_canvas: float
    side: str
    legal_center_canvas_y_abs: tuple[float, float]
    center_canvas_y: float
    center_material_y: float
    center_source_y_px: float
    opacity: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def decide_track05(
    *,
    seed: int,
    source: VideoProbe,
    track01: Track01Decision,
    track04: Track04Decision,
) -> Track05Decision:
    """Choose T05 geometry independently, while forcing the side opposite T04."""
    geometry = calculate_cover_geometry(source.width, source.height)
    rng = random.Random(f"{seed}:track05-mirror")
    mirror_size_ui_px = rng.randint(40, 50)
    feather = round(rng.uniform(0.05, 0.20), 6)
    side_sign = -1.0 if track04.side == "bottom" else 1.0
    mask_height_material = mirror_size_ui_px / source.height
    band_height_canvas = geometry.display_height * mask_height_material
    fade_buffer_canvas = band_height_canvas * feather / 2
    central_half_height_canvas = CANVAS_HEIGHT * track01.canvas_height_ratio / 2
    min_center_abs = central_half_height_canvas + band_height_canvas / 2 + fade_buffer_canvas
    max_center_abs = CANVAS_HEIGHT / 2 - band_height_canvas / 2 - fade_buffer_canvas
    if min_center_abs > max_center_abs:
        raise ValueError("T05镜面装饰层没有避开中央窗口的安全位置")
    center_canvas_y = side_sign * rng.uniform(min_center_abs, max_center_abs)
    center_material_y = 2 * center_canvas_y / geometry.display_height
    return Track05Decision(
        seed=seed,
        source_path=str(source.path),
        source_width=source.width,
        source_height=source.height,
        source_duration_seconds=source.duration_seconds,
        clip_scale=geometry.cover_scale,
        central_half_height_canvas=round(central_half_height_canvas, 6),
        mirror_size_ui_px=mirror_size_ui_px,
        mask_height_material=round(mask_height_material, 9),
        band_height_canvas=round(band_height_canvas, 6),
        feather=feather,
        fade_buffer_canvas=round(fade_buffer_canvas, 6),
        side="bottom" if side_sign > 0 else "top",
        legal_center_canvas_y_abs=(round(min_center_abs, 6), round(max_center_abs, 6)),
        center_canvas_y=round(center_canvas_y, 6),
        center_material_y=round(center_material_y, 9),
        center_source_y_px=round(center_material_y * source.height / 2, 6),
        opacity=round(rng.uniform(0.40, 0.50), 6),
    )


def _build_native_fragment(*, source: VideoProbe, decision: Track05Decision) -> dict[str, Any]:
    """Ask the current 5.9 library for a native video/mirror material shape."""
    from pyJianYingDraft import ClipSettings, MaskType, ScriptFile, Timerange, TrackType, VideoMaterial, VideoSegment

    scratch = ScriptFile(1080, 2400, 30, False)
    scratch.add_track(TrackType.video, "T05_MIRROR_VIDEO", relative_index=5)
    material = VideoMaterial(str(source.path.resolve()))
    source_us = min(round(source.duration_seconds * MICROSECONDS), material.duration)
    if source_us <= 0:
        raise ValueError("T05外部视频003没有可用时长")
    segment = VideoSegment(
        material,
        Timerange(0, source_us),
        source_timerange=Timerange(0, source_us),
        volume=0.0,
        clip_settings=ClipSettings(
            alpha=decision.opacity,
            scale_x=decision.clip_scale,
            scale_y=decision.clip_scale,
        ),
    )
    segment.add_mask(
        MaskType.镜面,
        center_x=0.0,
        center_y=decision.center_source_y_px,
        size=decision.mask_height_material,
        feather=decision.feather * 100,
    )
    scratch.add_segment(segment, "T05_MIRROR_VIDEO")
    return json.loads(scratch.dumps())


def _append_track05_to_content(
    *,
    content_path: Path,
    plan: T00ProjectPlan,
    source: VideoProbe,
    decision: Track05Decision,
    user_data_root: Path,
) -> None:
    """Append T05 without rewriting the accepted T02/T03 compounds."""
    with content_path.open("r", encoding="utf-8") as handle:
        document: dict[str, Any] = json.load(handle)
    if any(track.get("name") == "T05_MIRROR_VIDEO" for track in document.get("tracks", [])):
        raise RuntimeError("目标草稿已经包含T05，拒绝重复追加")

    fragment = _build_native_fragment(source=source, decision=decision)
    mirror_mask = next((item for item in fragment["materials"].get("masks", []) if item.get("resource_type") == "mirror"), None)
    if mirror_mask is None:
        raise RuntimeError("T05未能生成当前5.9镜面蒙版材料")
    mirror_mask["path"] = _latest_payload(
        user_data_root / "Cache" / "effect" / str(__import__("pyJianYingDraft").MaskType.镜面.value.effect_id),
        label="镜面蒙版",
    ).as_posix()

    native_track = copy.deepcopy(fragment["tracks"][0])
    native_track["id"] = uuid.uuid4().hex
    native_track["name"] = "T05_MIRROR_VIDEO"
    source_segment = native_track["segments"][0]
    source_us = min(round(source.duration_seconds * MICROSECONDS), source_segment["source_timerange"]["duration"])
    total_us = plan.duration_seconds * MICROSECONDS
    repeated_segments: list[dict[str, Any]] = []
    cursor = 0
    while cursor < total_us:
        duration = min(source_us, total_us - cursor)
        segment = copy.deepcopy(source_segment)
        segment["id"] = uuid.uuid4().hex
        segment["target_timerange"] = {"start": cursor, "duration": duration}
        segment["source_timerange"] = {"start": 0, "duration": duration}
        segment["render_index"] = 5
        segment["track_render_index"] = 5
        repeated_segments.append(segment)
        cursor += duration
    native_track["segments"] = repeated_segments

    for name, values in fragment["materials"].items():
        if not values:
            continue
        document.setdefault("materials", {}).setdefault(name, []).extend(copy.deepcopy(values))
    document.setdefault("tracks", []).append(native_track)
    document["render_index_track_mode_on"] = True
    _set_top_level_track_indices(document)
    with content_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)


def _set_top_level_track_indices(document: dict[str, Any]) -> None:
    """Make the five visible template layers explicit in the 5.9 root draft.

    Nested photo-wall documents keep their own render indexes.  This only
    assigns the root timeline, so Jianying does not need to infer the intended
    T01 → T05 stack when it first opens the generated draft.
    """
    expected = {
        "T01_OUTER_VIDEO": 1,
        "T02_BOTTOM_PHOTO_WALL": 2,
        "T03_TOP_PHOTO_WALL": 3,
        "T04_MIRROR_VIDEO": 4,
        "T05_MIRROR_VIDEO": 5,
    }
    seen: set[str] = set()
    for track in document.get("tracks", []):
        index = expected.get(track.get("name"))
        if index is None:
            continue
        seen.add(track["name"])
        for segment in track.get("segments", []):
            segment["render_index"] = index
            segment["track_render_index"] = index
    missing = set(expected) - seen
    if missing:
        raise RuntimeError(f"5.9根时间线缺少轨道：{', '.join(sorted(missing))}")


def create_track05_draft(
    *,
    draft_root: Path,
    draft_name: str,
    plan: T00ProjectPlan,
    source01: VideoProbe,
    source02: VideoProbe,
    source03: VideoProbe,
    photo_dir: Path,
    photo_cache_root: Path,
    user_data_root: Path | None = None,
) -> tuple[Track01Decision, Track04Decision, PhotoWallDecision, Track05Decision]:
    """Create the cumulative native draft through T05."""
    if source03.height <= source03.width:
        raise ValueError("T05只能使用竖屏外部视频003")
    track01, track04, wall = create_track03_draft(
        draft_root=draft_root,
        draft_name=draft_name,
        plan=plan,
        source01=source01,
        source02=source02,
        photo_dir=photo_dir,
        photo_cache_root=photo_cache_root,
        user_data_root=user_data_root,
    )
    decision = decide_track05(seed=plan.seed, source=source03, track01=track01, track04=track04)
    _append_track05_to_content(
        content_path=draft_root / draft_name / "draft_content.json",
        plan=plan,
        source=source03,
        decision=decision,
        user_data_root=user_data_root or _default_user_data_root(),
    )
    return track01, track04, wall, decision
