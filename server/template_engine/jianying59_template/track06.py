"""T06: full-duration Jianying 5.9 adjustment layer."""

from __future__ import annotations

import json
import os
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import T00ProjectPlan, VideoProbe
from .track01 import Track01Decision
from .track02_03 import PhotoWallDecision
from .track04 import Track04Decision
from .track05 import Track05Decision, create_track05_draft


ADJUST_PARAMETERS: tuple[tuple[str, str, str], ...] = (
    ("色温", "temperature", "v3"),
    ("色调", "tone", "v3"),
    ("饱和度", "saturation", "v1"),
    ("自然饱和度", "natural_saturation", "v1"),
    ("亮度", "brightness", "v2"),
    ("对比度", "contrast", "v3"),
    ("高光", "highlight", "v3"),
    ("阴影", "shadow", "v3"),
    ("白色", "white", ""),
    ("黑色", "black", ""),
    ("光感", "light_sensation", ""),
)
ADJUST_UI_VALUES = (-3, -2, -1, 1, 2, 3)
HSL_COLORS: tuple[tuple[str, int], ...] = (
    ("红色", 1), ("橙色", 2), ("黄色", 3), ("绿色", 4),
    ("青色", 5), ("蓝色", 6), ("紫色", 7), ("洋红", 8),
)
HSL_DIMENSIONS: tuple[tuple[str, str], ...] = (("色相", "hue"), ("饱和度", "saturation"), ("亮度", "lightness"))


def _new_id() -> str:
    return str(uuid.uuid4()).upper()


@dataclass(frozen=True)
class BasicAdjustment:
    label: str
    effect_type: str
    version: str
    ui_value: int
    json_value: float


@dataclass(frozen=True)
class Track06Decision:
    seed: int
    basic_adjustments: tuple[BasicAdjustment, ...]
    hsl_color_name: str
    hsl_color_type: int
    hsl_dimension_label: str
    hsl_dimension: str
    hsl_ui_value: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def decide_track06(*, seed: int) -> Track06Decision:
    """Apply the completed template's deterministic 3-basic-plus-1-HSL rule."""
    rng = random.Random(f"{seed}:track06-adjustment")
    selected = tuple(
        BasicAdjustment(label, effect_type, version, ui_value := rng.choice(ADJUST_UI_VALUES), round(ui_value * 0.02, 2))
        for label, effect_type, version in rng.sample(ADJUST_PARAMETERS, 3)
    )
    color_name, color_type = rng.choice(HSL_COLORS)
    dimension_label, dimension = rng.choice(HSL_DIMENSIONS)
    return Track06Decision(
        seed=seed,
        basic_adjustments=selected,
        hsl_color_name=color_name,
        hsl_color_type=color_type,
        hsl_dimension_label=dimension_label,
        hsl_dimension=dimension,
        hsl_ui_value=rng.choice(ADJUST_UI_VALUES),
    )


def _find_jianying_app_root() -> Path:
    apps_root = Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro" / "Apps"
    candidates = sorted((path for path in apps_root.iterdir() if path.is_dir()), reverse=True) if apps_root.exists() else []
    for candidate in candidates:
        bundle = candidate / "Resources" / "DefaultAdjustBundle"
        if (bundle / "combine_adjust").is_dir() and (bundle / "hsl_v1").is_dir():
            return candidate
    raise RuntimeError("当前剪映安装中未找到 combine_adjust 与 hsl_v1 调节资源")


def _basic_effect(*, adjustment: BasicAdjustment, app_root: Path) -> dict[str, Any]:
    """The exact 5.9 combine_adjust material shape from the verified check."""
    return {
        "adjust_params": [], "algorithm_artifact_path": "", "apply_target_type": 0,
        "bloom_params": None, "category_id": "", "category_name": "", "color_match_info": None,
        "effect_id": "", "enable_skin_tone_correction": False, "exclusion_group": [],
        "face_adjust_params": [], "formula_id": "", "id": _new_id(), "intensity_key": "",
        "multi_language_current": "", "name": "", "panel_id": "",
        "path": (app_root / "Resources" / "DefaultAdjustBundle" / "combine_adjust").as_posix(),
        "platform": "all", "request_id": "", "resource_id": "", "source_platform": 0,
        "sub_type": "none", "time_range": None, "type": adjustment.effect_type,
        "value": adjustment.json_value, "version": adjustment.version,
    }


def _hsl_effect(*, color_type: int, hue: int, saturation: int, lightness: int, interacting: bool, version: str, app_root: Path) -> dict[str, Any]:
    return {
        "hsl_color_type": color_type, "hue": hue, "id": _new_id(), "interacting": interacting,
        "lightness": lightness,
        "path": (app_root / "Resources" / "DefaultAdjustBundle" / ("hsl_v1" if version else "hsl")).as_posix(),
        "type": "hsl", "saturation": saturation, "version": version,
    }


def _append_track06_to_content(*, content_path: Path, plan: T00ProjectPlan, decision: Track06Decision, app_root: Path) -> None:
    with content_path.open("r", encoding="utf-8") as handle:
        document: dict[str, Any] = json.load(handle)
    if any(track.get("name") == "T06_GLOBAL_ADJUST" for track in document.get("tracks", [])):
        raise RuntimeError("目标草稿已经包含 T06，拒绝重复追加")

    materials = document.setdefault("materials", {})
    placeholder_id = _new_id()
    materials.setdefault("placeholders", []).append({
        "id": placeholder_id, "material_resource_id": "", "name": "T06_GLOBAL_ADJUST", "type": "adjust",
    })
    basics = [_basic_effect(adjustment=item, app_root=app_root) for item in decision.basic_adjustments]
    materials.setdefault("effects", []).extend(basics)
    neutral_hsl = _hsl_effect(color_type=1, hue=0, saturation=0, lightness=0, interacting=False, version="", app_root=app_root)
    hsl_values = {"hue": 0, "saturation": 0, "lightness": 0}
    hsl_values[decision.hsl_dimension] = decision.hsl_ui_value
    active_hsl = _hsl_effect(color_type=decision.hsl_color_type, interacting=True, version="1", app_root=app_root, **hsl_values)
    materials.setdefault("hsl", []).extend((neutral_hsl, active_hsl))

    duration_us = plan.duration_seconds * 1_000_000
    document.setdefault("tracks", []).append({
        "attribute": 0, "flag": 0, "id": _new_id(), "is_default_name": False, "name": "T06_GLOBAL_ADJUST",
        "segments": [{
            "caption_info": None, "cartoon": False, "clip": None, "common_keyframes": [],
            "enable_adjust": True, "enable_color_correct_adjust": False, "enable_color_curves": True,
            "enable_color_match_adjust": False, "enable_color_wheels": True,
            "enable_lut": True, "enable_smart_color_adjust": False,
            "extra_material_refs": [*(item["id"] for item in basics), neutral_hsl["id"], active_hsl["id"]],
            "group_id": "", "hdr_settings": None, "id": _new_id(), "intensifies_audio": False,
            "is_placeholder": False, "is_tone_modify": False, "keyframe_refs": [], "last_nonzero_volume": 1.0,
            "material_id": placeholder_id, "render_index": 0,
            "responsive_layout": {"enable": False, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0},
            "reverse": False, "source_timerange": None, "speed": 1.0,
            "target_timerange": {"start": 0, "duration": duration_us}, "template_id": "", "template_scene": "default",
            "track_attribute": 0, "track_render_index": 0, "uniform_scale": None, "visible": True, "volume": 1.0,
        }], "type": "adjust",
    })
    with content_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)


def create_track06_draft(
    *, draft_root: Path, draft_name: str, plan: T00ProjectPlan,
    source01: VideoProbe, source02: VideoProbe, source03: VideoProbe,
    photo_dir: Path, photo_cache_root: Path, user_data_root: Path | None = None,
) -> tuple[Track01Decision, Track04Decision, PhotoWallDecision, Track05Decision, Track06Decision]:
    """Create the cumulative native draft through the full-duration adjustment layer."""
    track01, track04, wall, track05 = create_track05_draft(
        draft_root=draft_root, draft_name=draft_name, plan=plan,
        source01=source01, source02=source02, source03=source03,
        photo_dir=photo_dir, photo_cache_root=photo_cache_root, user_data_root=user_data_root,
    )
    decision = decide_track06(seed=plan.seed)
    _append_track06_to_content(
        content_path=draft_root / draft_name / "draft_content.json", plan=plan,
        decision=decision, app_root=_find_jianying_app_root(),
    )
    return track01, track04, wall, track05, decision
