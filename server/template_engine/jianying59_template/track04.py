"""T04: external video 002 with the safe mirror-mask band."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import CANVAS_HEIGHT, T00ProjectPlan, VideoProbe, create_native_t00_draft
from .track01 import (
    MICROSECONDS,
    Track01Decision,
    _attach_native_paths_and_filter,
    _default_user_data_root,
    add_track01_to_draft,
    calculate_cover_geometry,
    decide_track01,
)
from server.jianying_resource_paths import attach_cached_path_if_present


@dataclass(frozen=True)
class Track04Decision:
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


def decide_track04(*, seed: int, source: VideoProbe, track01: Track01Decision) -> Track04Decision:
    """Keep the mirror band and its feather completely outside T01's window."""
    geometry = calculate_cover_geometry(source.width, source.height)
    rng = random.Random(f"{seed}:track04-mirror")
    mirror_size_ui_px = rng.randint(40, 50)
    feather = round(rng.uniform(0.05, 0.20), 6)
    side_sign = rng.choice((-1.0, 1.0))
    mask_height_material = mirror_size_ui_px / source.height
    band_height_canvas = geometry.display_height * mask_height_material
    fade_buffer_canvas = band_height_canvas * feather / 2
    central_half_height_canvas = CANVAS_HEIGHT * track01.canvas_height_ratio / 2
    min_center_abs = central_half_height_canvas + band_height_canvas / 2 + fade_buffer_canvas
    max_center_abs = CANVAS_HEIGHT / 2 - band_height_canvas / 2 - fade_buffer_canvas
    if min_center_abs > max_center_abs:
        raise ValueError("T04 mirror band has no safe position outside the central window")
    center_canvas_y = side_sign * rng.uniform(min_center_abs, max_center_abs)
    center_material_y = 2 * center_canvas_y / geometry.display_height
    return Track04Decision(
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


def _attach_native_mirror_path(*, content_path: Path, user_data_root: Path) -> None:
    """Attach the current 5.9 mirror bundle and share it across repeated segments."""
    from pyJianYingDraft import MaskType

    with content_path.open("r", encoding="utf-8") as handle:
        document: dict[str, Any] = json.load(handle)
    materials = document.setdefault("materials", {})
    masks = materials.setdefault("masks", [])
    mirror_masks = [item for item in masks if item.get("resource_type") == "mirror"]
    if not mirror_masks:
        raise RuntimeError("T04 write produced no mirror-mask material")

    shared_mask = mirror_masks[0]
    attach_cached_path_if_present(shared_mask, user_data_root / "Cache" / "effect" / str(MaskType.镜面.value.effect_id))
    shared_mask_id = shared_mask["id"]
    obsolete_mask_ids = {item["id"] for item in mirror_masks[1:]}
    materials["masks"] = [item for item in masks if item.get("id") not in obsolete_mask_ids]

    track = next((item for item in document.get("tracks", []) if item.get("name") == "T04_MIRROR_VIDEO"), None)
    if track is None:
        raise RuntimeError("T04 write produced no video track")
    for segment in track.get("segments", []):
        refs = [shared_mask_id if ref in obsolete_mask_ids else ref for ref in segment.get("extra_material_refs", [])]
        if shared_mask_id not in refs:
            refs.append(shared_mask_id)
        segment["extra_material_refs"] = refs

    with content_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)


def add_track04_to_draft(*, draft: Any, plan: T00ProjectPlan, source: VideoProbe, decision: Track04Decision) -> None:
    """Append the pathless T04 video and mirror material to an open native draft."""
    from pyJianYingDraft import ClipSettings, MaskType, Timerange, TrackType, VideoMaterial, VideoSegment

    draft.add_track(TrackType.video, "T04_MIRROR_VIDEO", relative_index=4)
    material = VideoMaterial(str(source.path.resolve()))
    total_us = plan.duration_seconds * MICROSECONDS
    source_us = min(round(source.duration_seconds * MICROSECONDS), material.duration)
    if source_us <= 0:
        raise ValueError("T02 source video has no usable duration")
    cursor = 0
    while cursor < total_us:
        segment_us = min(source_us, total_us - cursor)
        segment = VideoSegment(
            material,
            Timerange(cursor, segment_us),
            source_timerange=Timerange(0, segment_us),
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
        draft.add_segment(segment, "T04_MIRROR_VIDEO")
        cursor += segment_us


def create_track04_only_draft(
    *,
    draft_root: Path,
    draft_name: str,
    plan: T00ProjectPlan,
    source01: VideoProbe,
    source02: VideoProbe,
    user_data_root: Path | None = None,
) -> tuple[Track01Decision, Track04Decision]:
    """Create a focused T01+T04 native draft, without using a donor."""
    if source01.height <= source01.width or source02.height <= source02.width:
        raise ValueError("T01 and T02 must both use portrait videos")
    track01 = decide_track01(seed=plan.seed, source=source01)
    track04 = decide_track04(seed=plan.seed, source=source02, track01=track01)
    active_user_data_root = user_data_root or _default_user_data_root()

    from pyJianYingDraft import TrackType

    draft = create_native_t00_draft(draft_root=draft_root, draft_name=draft_name, plan=plan)
    draft.add_track(TrackType.video)
    add_track01_to_draft(draft=draft, plan=plan, source=source01, decision=track01)
    add_track04_to_draft(draft=draft, plan=plan, source=source02, decision=track04)
    draft.save()
    content_path = draft_root / draft_name / "draft_content.json"
    _attach_native_paths_and_filter(
        content_path=content_path,
        decision=track01,
        user_data_root=active_user_data_root,
    )
    _attach_native_mirror_path(content_path=content_path, user_data_root=active_user_data_root)
    return track01, track04
