"""T07/T08: the two full-duration decoration-effect tracks for Jianying 5.9."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import T00ProjectPlan, VideoProbe
from .track01 import Track01Decision, _default_user_data_root
from .track02_03 import PhotoWallDecision
from .track04 import Track04Decision
from .track05 import Track05Decision
from .track06 import Track06Decision, create_track06_draft


POOL_PATH = Path(__file__).with_name("resources") / "track07_08_effect_pool_5_9.json"
OPACITY_PARAMETER = "effects_adjust_background_animation"
SPEED_PARAMETER = "effects_adjust_speed"
SPEED_DEFAULT = 0.33


def _new_id() -> str:
    return str(uuid.uuid4()).upper()


@dataclass(frozen=True)
class EffectCandidate:
    name: str
    resource_id: str
    effect_id: str
    payload_md5: str


@dataclass(frozen=True)
class SelectedEffect:
    track_name: str
    candidate: EffectCandidate
    opacity_ui_value: int
    opacity_json_value: float


@dataclass(frozen=True)
class Track07_08Decision:
    seed: int
    effects: tuple[SelectedEffect, SelectedEffect]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def load_effect_pool(path: Path = POOL_PATH) -> tuple[EffectCandidate, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("opacity_parameter") != OPACITY_PARAMETER or payload.get("speed_parameter") != SPEED_PARAMETER:
        raise ValueError("T07/T08特效池参数合同不正确")
    if payload.get("speed_default") != SPEED_DEFAULT:
        raise ValueError("T07/T08特效池速度默认值不正确")
    rows = payload.get("effects")
    if not isinstance(rows, list) or len(rows) != 27:
        raise ValueError("T07/T08特效池必须恰好是27个已验收候选")
    pool = tuple(EffectCandidate(**{key: str(row.get(key) or "") for key in ("name", "resource_id", "effect_id", "payload_md5")}) for row in rows)
    if any(not all(asdict(item).values()) for item in pool):
        raise ValueError("T07/T08特效池存在空字段")
    if len({item.name for item in pool}) != 27 or len({item.resource_id for item in pool}) != 27 or len({item.effect_id for item in pool}) != 27:
        raise ValueError("T07/T08特效池存在重复候选")
    return pool


def decide_track07_08(*, seed: int, pool: tuple[EffectCandidate, ...] | None = None) -> Track07_08Decision:
    """Preserve the old reference-effect stream: choose two distinct items, 2–8%."""
    candidates = pool or load_effect_pool()
    rng = random.Random(f"{seed}:track13-reference-effects")
    chosen = rng.sample(candidates, 2)
    selected = tuple(SelectedEffect(
        track_name=f"T0{7 + index}_DECORATIVE_EFFECT",
        candidate=candidate,
        opacity_ui_value=(ui_value := rng.randint(2, 8)),
        opacity_json_value=round(ui_value / 100, 2),
    ) for index, candidate in enumerate(chosen))
    return Track07_08Decision(seed=seed, effects=selected)  # type: ignore[arg-type]


def _material(effect: SelectedEffect, user_data_root: Path) -> dict[str, Any]:
    item = effect.candidate
    return {
        "adjust_params": [
            {"name": OPACITY_PARAMETER, "value": effect.opacity_json_value, "default_value": 1.0},
            {"name": SPEED_PARAMETER, "value": SPEED_DEFAULT, "default_value": SPEED_DEFAULT},
        ],
        "algorithm_artifact_path": "", "apply_target_type": 2, "apply_time_range": None,
        "category_id": "", "category_name": "", "common_keyframes": [], "disable_effect_faces": [],
        "effect_id": item.effect_id, "formula_id": "", "id": _new_id(), "name": item.name,
        "path": (user_data_root / "Cache" / "effect" / item.effect_id / item.payload_md5).as_posix(),
        "platform": "all", "render_index": 0, "request_id": "", "resource_id": item.resource_id,
        "source_platform": 0, "time_range": None, "track_render_index": 0,
        "type": "video_effect", "value": 1.0, "version": "",
    }


def _segment(material_id: str, duration_us: int, ordinal: int) -> dict[str, Any]:
    return {
        "caption_info": None, "cartoon": False, "clip": None, "common_keyframes": [],
        "enable_adjust": False, "enable_color_correct_adjust": False, "enable_color_curves": True,
        "enable_color_match_adjust": False, "enable_color_wheels": True, "enable_lut": False,
        "enable_smart_color_adjust": False, "extra_material_refs": [], "group_id": "", "hdr_settings": None,
        "id": _new_id(), "intensifies_audio": False, "is_placeholder": False, "is_tone_modify": False,
        "keyframe_refs": [], "last_nonzero_volume": 1.0, "material_id": material_id,
        "render_index": 11012 + ordinal,
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0},
        "reverse": False, "source_timerange": None, "speed": 1.0,
        "target_timerange": {"start": 0, "duration": duration_us}, "template_id": "", "template_scene": "default",
        "track_attribute": 0, "track_render_index": 7 + ordinal, "uniform_scale": None, "visible": True, "volume": 1.0,
    }


def _append_track07_08(*, content_path: Path, plan: T00ProjectPlan, decision: Track07_08Decision, user_data_root: Path) -> None:
    document: dict[str, Any] = json.loads(content_path.read_text(encoding="utf-8"))
    if any(str(track.get("name", "")).startswith(("T07_", "T08_")) for track in document.get("tracks", [])):
        raise RuntimeError("目标草稿已经包含T07/T08，拒绝重复追加")
    materials = document.setdefault("materials", {}).setdefault("video_effects", [])
    for ordinal, selected in enumerate(decision.effects):
        material = _material(selected, user_data_root)
        materials.append(material)
        document.setdefault("tracks", []).append({
            "attribute": 0, "flag": 0, "id": _new_id(), "is_default_name": False,
            "name": selected.track_name,
            "segments": [_segment(material["id"], plan.duration_seconds * 1_000_000, ordinal)], "type": "effect",
        })
    document["render_index_track_mode_on"] = True
    content_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def create_track07_08_draft(
    *, draft_root: Path, draft_name: str, plan: T00ProjectPlan,
    source01: VideoProbe, source02: VideoProbe, source03: VideoProbe,
    photo_dir: Path, photo_cache_root: Path, user_data_root: Path | None = None,
) -> tuple[Track01Decision, Track04Decision, PhotoWallDecision, Track05Decision, Track06Decision, Track07_08Decision]:
    track01, track04, wall, track05, track06 = create_track06_draft(
        draft_root=draft_root, draft_name=draft_name, plan=plan, source01=source01, source02=source02,
        source03=source03, photo_dir=photo_dir, photo_cache_root=photo_cache_root, user_data_root=user_data_root,
    )
    decision = decide_track07_08(seed=plan.seed)
    _append_track07_08(
        content_path=draft_root / draft_name / "draft_content.json", plan=plan, decision=decision,
        user_data_root=user_data_root or _default_user_data_root(),
    )
    return track01, track04, wall, track05, track06, decision
