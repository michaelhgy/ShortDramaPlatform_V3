"""T01: external video 001 with the legacy central inverse rectangle window."""

from __future__ import annotations

import json
import os
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import CANVAS_HEIGHT, CANVAS_WIDTH, T00ProjectPlan, VideoProbe, create_native_t00_draft


MICROSECONDS = 1_000_000
RECTANGLE_MASK_CACHE_CATEGORY = "636077"


@dataclass(frozen=True)
class FilterCandidate:
    resource_id: str
    name: str
    category_id: str
    category_name: str


# These are current 5.9 materials observed in a saved native draft, not names
# guessed by the generator.  The payload directory is always resolved at runtime.
TRACK01_FILTER_CANDIDATES = (
    FilterCandidate("7486736825369840907", "日光肤", "5914475", "🍉夏日"),
    FilterCandidate("7532869399326313728", "晴朗自然", "5914475", "🍉夏日"),
)


@dataclass(frozen=True)
class CoverGeometry:
    scale1_height: float
    cover_scale: float
    display_width: float
    display_height: float


@dataclass(frozen=True)
class Track01Decision:
    seed: int
    source_path: str
    source_width: int
    source_height: int
    source_duration_seconds: float
    canvas_width_ratio: float
    canvas_height_ratio: float
    feather: float
    geometry: CoverGeometry
    mask_width_material: float
    mask_height_material: float
    filter_resource_id: str
    filter_name: str
    filter_strength: float = 0.01

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def calculate_cover_geometry(source_width: int, source_height: int) -> CoverGeometry:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("视频宽高必须为正数")
    scale1_height = CANVAS_WIDTH * source_height / source_width
    cover_scale = max(1.0, CANVAS_HEIGHT / scale1_height)
    return CoverGeometry(
        scale1_height=scale1_height,
        cover_scale=cover_scale,
        display_width=CANVAS_WIDTH * cover_scale,
        display_height=scale1_height * cover_scale,
    )


def decide_track01(*, seed: int, source: VideoProbe) -> Track01Decision:
    geometry = calculate_cover_geometry(source.width, source.height)
    rng = random.Random(f"{seed}:track01")
    width_ratio = round(rng.uniform(0.90, 0.97), 6)
    # The photo walls are decorative frames, not the dominant image area.
    # Keep each wall within roughly 276–312 px so sticker groups have room to
    # form the visual frame without competing with the central drama window.
    height_ratio = round(rng.uniform(0.74, 0.77), 6)
    # 产品负责人确认：T01 的剪映界面羽化值暂时固定为 1。
    # pyJianYingDraft 接收百分比前的归一化数值，写入时统一乘以 100。
    feather = 0.01
    filter_candidate = random.Random(f"{seed}:track01-filter").choice(TRACK01_FILTER_CANDIDATES)
    return Track01Decision(
        seed=seed,
        source_path=str(source.path),
        source_width=source.width,
        source_height=source.height,
        source_duration_seconds=source.duration_seconds,
        canvas_width_ratio=width_ratio,
        canvas_height_ratio=height_ratio,
        feather=feather,
        geometry=geometry,
        mask_width_material=round(CANVAS_WIDTH * width_ratio / geometry.display_width, 6),
        mask_height_material=round(CANVAS_HEIGHT * height_ratio / geometry.display_height, 6),
        filter_resource_id=filter_candidate.resource_id,
        filter_name=filter_candidate.name,
    )


def _default_user_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        raise RuntimeError("未设置LOCALAPPDATA；请传入 --user-data-root")
    return Path(local_app_data) / "JianyingPro" / "User Data"


def _latest_payload(root: Path, *, label: str) -> Path:
    payloads = sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.stat().st_mtime, reverse=True) if root.is_dir() else []
    if not payloads:
        raise RuntimeError(f"当前剪映5.9未找到{label}本地资源，不能生成T01")
    return payloads[0]


def _attach_native_paths_and_filter(*, content_path: Path, decision: Track01Decision, user_data_root: Path) -> None:
    """Complete the fields that pyJianYingDraft intentionally leaves pathless.

    All paths are discovered from the current machine's 5.9 cache at runtime.
    """
    with content_path.open("r", encoding="utf-8") as handle:
        document: dict[str, Any] = json.load(handle)
    materials = document.setdefault("materials", {})
    masks = materials.setdefault("masks", [])
    rectangle_masks = [item for item in masks if item.get("resource_type") == "rectangle"]
    if not rectangle_masks:
        raise RuntimeError("T01写入后未找到矩形蒙版材料")

    shared_mask = rectangle_masks[0]
    shared_mask["path"] = _latest_payload(
        user_data_root / "Cache" / "effect" / RECTANGLE_MASK_CACHE_CATEGORY,
        label="矩形蒙版",
    ).as_posix()
    shared_mask_id = shared_mask["id"]
    obsolete_mask_ids = {item["id"] for item in rectangle_masks[1:]}
    materials["masks"] = [item for item in masks if item.get("id") not in obsolete_mask_ids]

    candidate = next(item for item in TRACK01_FILTER_CANDIDATES if item.resource_id == decision.filter_resource_id)
    filter_payload = _latest_payload(
        user_data_root / "Cache" / "artistEffect" / candidate.resource_id,
        label=f"滤镜“{candidate.name}”",
    )
    filter_id = uuid.uuid4().hex.upper()
    filter_material = {
        "adjust_params": [],
        "algorithm_artifact_path": "",
        "apply_target_type": 0,
        "bloom_params": None,
        "category_id": candidate.category_id,
        "category_name": candidate.category_name,
        "color_match_info": {"source_feature_path": "", "target_feature_path": "", "target_image_path": ""},
        "effect_id": candidate.resource_id,
        "enable_skin_tone_correction": False,
        "exclusion_group": [],
        "face_adjust_params": [],
        "formula_id": "",
        "id": filter_id,
        "intensity_key": "",
        "multi_language_current": "",
        "name": candidate.name,
        "panel_id": "",
        "path": filter_payload.as_posix(),
        "platform": "all",
        "request_id": "",
        "resource_id": candidate.resource_id,
        "source_platform": 1,
        "sub_type": "none",
        "time_range": None,
        "type": "filter",
        "value": decision.filter_strength,
        "version": "",
    }
    materials.setdefault("effects", []).append(filter_material)

    track = next((item for item in document.get("tracks", []) if item.get("name") == "T01_OUTER_VIDEO"), None)
    if track is None:
        raise RuntimeError("T01写入后未找到视频轨")
    for segment in track.get("segments", []):
        refs = [shared_mask_id if ref in obsolete_mask_ids else ref for ref in segment.get("extra_material_refs", [])]
        if shared_mask_id not in refs:
            refs.append(shared_mask_id)
        refs.append(filter_id)
        segment["extra_material_refs"] = refs

    with content_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)


def add_track01_to_draft(*, draft: Any, plan: T00ProjectPlan, source: VideoProbe, decision: Track01Decision) -> None:
    """Append the T01 video and its pathless native materials to an open draft."""
    from pyJianYingDraft import ClipSettings, MaskType, Timerange, TrackType, VideoMaterial, VideoSegment

    draft.add_track(TrackType.video, "T01_OUTER_VIDEO", relative_index=1)
    material = VideoMaterial(str(source.path.resolve()))
    total_us = plan.duration_seconds * MICROSECONDS
    source_us = min(round(source.duration_seconds * MICROSECONDS), material.duration)
    if source_us <= 0:
        raise ValueError("T01 source video has no usable duration")
    cursor = 0
    while cursor < total_us:
        segment_us = min(source_us, total_us - cursor)
        segment = VideoSegment(
            material,
            Timerange(cursor, segment_us),
            source_timerange=Timerange(0, segment_us),
            volume=0.0,
            clip_settings=ClipSettings(scale_x=decision.geometry.cover_scale, scale_y=decision.geometry.cover_scale),
        )
        segment.add_mask(
            MaskType.矩形,
            center_x=0.0,
            center_y=0.0,
            size=decision.mask_height_material,
            rect_width=decision.mask_width_material,
            feather=decision.feather * 100,
            invert=True,
        )
        draft.add_segment(segment, "T01_OUTER_VIDEO")
        cursor += segment_us


def create_track01_draft(
    *,
    draft_root: Path,
    draft_name: str,
    plan: T00ProjectPlan,
    source: VideoProbe,
    user_data_root: Path | None = None,
) -> Track01Decision:
    """Create the cumulative native draft through T01."""
    if source.height <= source.width:
        raise ValueError("T01只能使用竖屏视频")
    decision = decide_track01(seed=plan.seed, source=source)
    active_user_data_root = user_data_root or _default_user_data_root()

    from pyJianYingDraft import TrackType

    draft = create_native_t00_draft(draft_root=draft_root, draft_name=draft_name, plan=plan)
    # Jianying marks the lowest video track as the main track regardless of its
    # display name.  The legacy donor kept that main track empty, so preserve
    # the same ordering and put T01 on the first ordinary video track.
    draft.add_track(TrackType.video)
    add_track01_to_draft(draft=draft, plan=plan, source=source, decision=decision)
    draft.save()
    _attach_native_paths_and_filter(
        content_path=draft_root / draft_name / "draft_content.json",
        decision=decision,
        user_data_root=active_user_data_root,
    )
    return decision
