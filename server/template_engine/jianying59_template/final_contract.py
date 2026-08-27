"""Final writer and structural validator for the active Jianying 5.9 template.

The final route is deliberately linear.  It consumes one :class:`TemplateDecision`
and appends each already-decided layer to a new native draft.  Stage helpers
remain available for narrow diagnostics, but the production-facing CLI never
lets those helpers choose their own random values.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import T00ProjectPlan, VideoProbe, create_native_t00_draft
from .template_decision import TemplateDecision, build_template_decision
from .track01 import _attach_native_paths_and_filter, _default_user_data_root, add_track01_to_draft
from .track02_03 import _attach_photo_walls
from .track04 import _attach_native_mirror_path, add_track04_to_draft
from .track05 import _append_track05_to_content
from .track09_sticker_skin import _append_track09
from .track10_11_flower_text import (
    BLESSING_TRACK_NAME,
    DRAMA_PROMPT_TRACK_NAME,
    FULL_DURATION_US,
    _append_flower_text,
)


STICKER_PREFIX = "T09_STICKER_SKIN_"
CORE_TRACK_TYPES = {
    "T01_OUTER_VIDEO": "video",
    "T02_BOTTOM_PHOTO_WALL": "video",
    "T03_TOP_PHOTO_WALL": "video",
    "T04_MIRROR_VIDEO": "video",
    "T05_MIRROR_VIDEO": "video",
    BLESSING_TRACK_NAME: "text",
    DRAMA_PROMPT_TRACK_NAME: "text",
}


@dataclass(frozen=True)
class FinalTemplateValidation:
    duration_us: int
    core_track_count: int
    sticker_track_count: int
    sticker_skin_id: str
    blessing_flower_effect_id: str
    drama_flower_effect_id: str
    no_audio_tracks: bool
    no_real_person_compound_track: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def _continuous_full_coverage_segments(track: dict[str, Any], duration_us: int) -> list[dict[str, Any]]:
    segments = list(track.get("segments") or [])
    if not segments:
        raise RuntimeError(f"track {track.get('name')} has no segments")
    expected_start = 0
    for segment in sorted(segments, key=lambda item: int((item.get("target_timerange") or {}).get("start") or 0)):
        timerange = segment.get("target_timerange") or {}
        start = timerange.get("start")
        duration = timerange.get("duration")
        if start != expected_start or not isinstance(duration, int) or duration <= 0:
            raise RuntimeError(f"track {track.get('name')} does not continuously cover {duration_us}us")
        expected_start += duration
    if expected_start != duration_us:
        raise RuntimeError(f"track {track.get('name')} does not continuously cover {duration_us}us")
    return segments


def _flower_effect_id(text: dict[str, Any], label: str) -> str:
    try:
        content = json.loads(str(text.get("content") or "{}"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label} text material contains invalid content JSON") from error
    styles = list(content.get("styles") or [])
    effect_style = (styles[0].get("effectStyle") if styles else None) or {}
    result = str(effect_style.get("id") or "")
    if not result:
        raise RuntimeError(f"{label} text material has no flower effectStyle")
    return result


def validate_final_template_draft(*, content_path: Path, duration_seconds: int, decision: TemplateDecision | None = None) -> FinalTemplateValidation:
    """Validate structure and the decision-to-draft binding; never claim visual pass."""
    duration_us = duration_seconds * 1_000_000
    if duration_us != FULL_DURATION_US:
        raise ValueError("final native template contract requires exactly 180 seconds")
    document: dict[str, Any] = json.loads(content_path.read_text(encoding="utf-8"))
    tracks = list(document.get("tracks") or [])
    named = {str(track.get("name")): track for track in tracks if track.get("name")}
    for name, expected_type in CORE_TRACK_TYPES.items():
        track = named.get(name)
        if track is None or track.get("type") != expected_type:
            raise RuntimeError(f"missing or drifted core track: {name}")
        _continuous_full_coverage_segments(track, duration_us)

    sticker_tracks = [track for track in tracks if str(track.get("name", "")).startswith(STICKER_PREFIX)]
    if len(sticker_tracks) != 16:
        raise RuntimeError("template needs the completed legacy T15-T30 layout: eight stickers per wall")
    if decision is not None and len(sticker_tracks) != len(decision.stickers.items):
        raise RuntimeError("written sticker count does not match TemplateDecision")
    materials = document.get("materials") or {}
    stickers = {str(item.get("id")): item for item in (materials.get("stickers") or [])}
    sticker_material_ids: set[str] = set()
    sticker_skin_ids: set[str] = set()
    for track in sticker_tracks:
        if track.get("type") != "sticker":
            raise RuntimeError(f"sticker track {track.get('name')} has wrong type")
        segments = _continuous_full_coverage_segments(track, duration_us)
        if len(segments) != 1:
            raise RuntimeError("each static sticker needs one full-duration segment")
        material_id = str(segments[0].get("material_id") or "")
        material = stickers.get(material_id)
        if not material:
            raise RuntimeError("sticker segment references no native sticker material")
        sticker_material_ids.add(material_id)
        sticker_skin_ids.add(str(material.get("category_id") or ""))
    if "" in sticker_skin_ids or len(sticker_skin_ids) != 1:
        raise RuntimeError("all template stickers must come from one skin category")
    if decision is not None:
        planned_ids = [item.resource_id for item in decision.stickers.items]
        written_ids = [str(stickers[str(track["segments"][0]["material_id"])].get("resource_id") or "") for track in sticker_tracks]
        if planned_ids != written_ids:
            raise RuntimeError("written sticker order does not match TemplateDecision")

    texts = {str(item.get("id")): item for item in (materials.get("texts") or [])}
    flower_ids: dict[str, str] = {}
    for name in (BLESSING_TRACK_NAME, DRAMA_PROMPT_TRACK_NAME):
        segments = _continuous_full_coverage_segments(named[name], duration_us)
        if len(segments) != 1:
            raise RuntimeError(f"{name} needs one full-duration text segment")
        text = texts.get(str(segments[0].get("material_id") or ""))
        if text is None:
            raise RuntimeError(f"{name} text material is missing")
        if float(text.get("font_size", 0.0)) != 15.0 or int(text.get("text_size", 0)) != 30:
            raise RuntimeError(f"{name} must keep the completed legacy 15px/30px text material")
        flower_ids[name] = _flower_effect_id(text, name)
    if flower_ids[BLESSING_TRACK_NAME] == flower_ids[DRAMA_PROMPT_TRACK_NAME]:
        raise RuntimeError("blessing and drama-guide text must use two different flower styles")
    if decision is not None:
        if flower_ids[BLESSING_TRACK_NAME] != decision.flower_text.blessing_style.effect_id:
            raise RuntimeError("blessing flower style differs from TemplateDecision")
        if flower_ids[DRAMA_PROMPT_TRACK_NAME] != decision.flower_text.drama_prompt_style.effect_id:
            raise RuntimeError("drama-guide flower style differs from TemplateDecision")
        expected_text_tracks = {
            BLESSING_TRACK_NAME: (
                decision.flower_text.blessing_position,
                decision.flower_text.blessing_scale,
                decision.flower_text.blessing_rotation,
            ),
            DRAMA_PROMPT_TRACK_NAME: (
                decision.flower_text.drama_prompt_position,
                decision.flower_text.drama_prompt_scale,
                decision.flower_text.drama_prompt_rotation,
            ),
        }
        for name, (position, scale, rotation) in expected_text_tracks.items():
            clip = named[name]["segments"][0].get("clip") or {}
            transform = clip.get("transform") or {}
            written_scale = clip.get("scale") or {}
            if (
                transform.get("x") != position[0]
                or transform.get("y") != position[1]
                or written_scale.get("x") != scale
                or written_scale.get("y") != scale
                or clip.get("rotation") != rotation
            ):
                raise RuntimeError(f"{name} differs from the completed legacy text decision")

    no_audio = not any(track.get("type") == "audio" for track in tracks)
    if not no_audio:
        raise RuntimeError("template stage must not contain BGM or audio tracks")
    no_real_person = not any("REAL_PERSON" in str(track.get("name", "")) or "TRACK31" in str(track.get("name", "")) for track in tracks)
    if not no_real_person:
        raise RuntimeError("real-person composition belongs to the finished-video stage")
    return FinalTemplateValidation(
        duration_us=duration_us,
        core_track_count=len(CORE_TRACK_TYPES),
        sticker_track_count=len(sticker_tracks),
        sticker_skin_id=next(iter(sticker_skin_ids)),
        blessing_flower_effect_id=flower_ids[BLESSING_TRACK_NAME],
        drama_flower_effect_id=flower_ids[DRAMA_PROMPT_TRACK_NAME],
        no_audio_tracks=no_audio,
        no_real_person_compound_track=no_real_person,
    )


def write_template_draft(
    *, draft_root: Path, draft_name: str, decision: TemplateDecision,
    source01: VideoProbe, source02: VideoProbe, source03: VideoProbe,
    user_data_root: Path | None = None,
) -> None:
    """Write a new draft exactly once from an already complete decision."""
    root = user_data_root or _default_user_data_root()
    plan = decision.plan
    from pyJianYingDraft import TrackType

    draft = create_native_t00_draft(draft_root=draft_root, draft_name=draft_name, plan=plan)
    draft.add_track(TrackType.video)
    add_track01_to_draft(draft=draft, plan=plan, source=source01, decision=decision.track01)
    draft.add_track(TrackType.video, "T02_BOTTOM_PHOTO_WALL", relative_index=2)
    draft.add_track(TrackType.video, "T03_TOP_PHOTO_WALL", relative_index=3)
    add_track04_to_draft(draft=draft, plan=plan, source=source02, decision=decision.track04)
    draft.save()
    content_path = draft_root / draft_name / "draft_content.json"
    _attach_native_paths_and_filter(content_path=content_path, decision=decision.track01, user_data_root=root)
    _attach_native_mirror_path(content_path=content_path, user_data_root=root)
    _attach_photo_walls(content_path=content_path, decision=decision.photo_walls, user_data_root=root)
    _append_track05_to_content(content_path=content_path, plan=plan, source=source03, decision=decision.track05, user_data_root=root)
    _append_track09(content_path=content_path, decision=decision.stickers, user_data_root=root)
    _append_flower_text(content_path=content_path, decision=decision.flower_text, user_data_root=root)


def create_final_template_draft(
    *, draft_root: Path, draft_name: str, plan: T00ProjectPlan, source01: VideoProbe, source02: VideoProbe,
    source03: VideoProbe, photo_dir: Path, photo_cache_root: Path, user_data_root: Path | None = None,
    sticker_skin_catalog: Path, flower_style_catalog: Path,
) -> tuple[TemplateDecision, FinalTemplateValidation]:
    """Plan, write and structurally validate one native template draft."""
    decision = build_template_decision(
        plan=plan, source01=source01, source02=source02, source03=source03,
        photo_dir=photo_dir, photo_cache_root=photo_cache_root,
        sticker_skin_catalog=sticker_skin_catalog, flower_style_catalog=flower_style_catalog,
    )
    write_template_draft(
        draft_root=draft_root, draft_name=draft_name, decision=decision,
        source01=source01, source02=source02, source03=source03, user_data_root=user_data_root,
    )
    validation = validate_final_template_draft(
        content_path=draft_root / draft_name / "draft_content.json", duration_seconds=plan.duration_seconds, decision=decision,
    )
    return decision, validation
