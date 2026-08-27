"""T10/T11: full-duration, two-style Jianying 5.9 flower text.

The writer keeps the native 5.9 material shape observed in a saved draft.  It
does not invent text-effect JSON from catalogue metadata.  The planner chooses
two distinct styles from the same or a neighbouring colour family so upper
blessing and lower drama-guide text feel related without becoming identical.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import T00ProjectPlan, VideoProbe
from .flower_style_library import (
    FlowerStyleCatalog,
    choose_flower_style,
    load_flower_style_catalog,
)
from .track09_sticker_skin import (
    StickerSkinDecision,
    _default_user_data_root,
    create_track09_sticker_skin_draft,
)


FULL_DURATION_US = 180_000_000
BLESSING_TRACK_NAME = "T10_TEXT_BLESSING"
DRAMA_PROMPT_TRACK_NAME = "T11_TEXT_DRAMA_PROMPT"

# Legacy completed-template text rules.  These are canvas-normalized positions,
# not screen pixels: H is the actual upper boundary of the central window.
# The two tracks deliberately live in their own photo-wall bands instead of
# being forced to the centre of the canvas.
BLESSING_X_RANGE = (-0.45, 0.35)
BLESSING_BAND_FRACTION_RANGE = (0.22, 0.55)
BLESSING_ROTATION_RANGE = (-5.0, 5.0)
BLESSING_VISIBLE_WIDTH_RANGE_PX = (430, 620)

DRAMA_PROMPT_X_RANGE = (0.12, 0.30)
DRAMA_PROMPT_BAND_FRACTION_RANGE = (0.20, 0.42)
DRAMA_PROMPT_ROTATION_RANGE = (-3.0, 3.0)
DRAMA_PROMPT_VISIBLE_WIDTH_BY_CHAR_COUNT = {
    7: (460, 560),
    8: (480, 580),
    9: (480, 580),
}

# The old completed generator had two independently curated pools.  Keep those
# IDs in the new writer instead of treating every style in a current 5.9
# category as interchangeable.  The current catalogue only supplies the live
# 5.9 material path/metadata for these IDs.
LEGACY_BLESSING_EFFECT_IDS = frozenset({
    "7406678794901130534", "7598123215231405337", "7599552680914242840",
    "7127667758245940510", "7351431205692181786", "7400213633055198503",
    "7507132514088062233", "7479056232117062937", "7403960732490157364",
    "6927160139359341828", "7430448068283206950", "7265622933702184232",
    "7391015553818692927", "7360986749046213928", "7612124928858443070",
    "7266696486363106616", "7406683118108806437", "7127681015732112654",
    "7236638821901733175", "7247314937222024480", "7401444618681847103",
    "7580794667453844798", "7583314481644604697", "7160595759375666446",
    "7399826245703175487", "7434413789652536588", "6927160139359227140",
    "7166472064356912387", "7263028102610144575", "7476028091077430552",
    "7404359079063244067", "7614497944833854745", "7404388775264030003",
    "7407010177842482459", "7667160942656015640", "7332635756839718179",
})
LEGACY_DRAMA_PROMPT_EFFECT_IDS = frozenset({
    "7406678794901130534", "7598123215231405337", "7599552680914242840",
    "7127667758245940510", "7351431205692181786", "7400213633055198503",
    "7507132514088062233", "7479056232117062937", "7403960732490157364",
    "6927160139359341828", "7430448068283206950", "7265622933702184232",
    "7391015553818692927", "7360986749046213928", "7612124928858443070",
    "7266696486363106616", "7406683118108806437", "7127681015732112654",
    "7236638821901733175", "7247314937222024480", "7401444618681847103",
    "7580794667453844798", "7127676763148143885", "6896137924853648648",
    "6896144074487729422", "6896137661153676552", "6896137727012654343",
    "6927160144421784832", "7268912246900772135", "7273018315025550628",
    "7343160086795242788", "7343449320475151627", "7166472183814950183",
    "7160601239800040712",
})

# Old 15px material text uses these calibrated transform ranges.  A single
# random fraction keeps the two visible heights linked: drama 124–138px,
# blessing exactly 10px smaller.
BLESSING_SCALE_BY_CHAR_COUNT = {
    6: (0.58, 0.66),
    7: (0.55, 0.63),
    8: (0.52, 0.60),
}
DRAMA_PROMPT_SCALE_BY_CHAR_COUNT = {
    7: (0.60, 0.68),
    8: (0.56, 0.64),
    9: (0.56, 0.64),
}

BLESSING_COPY = (
    "愿您身体健康",
    "愿您平安喜乐",
    "愿您福气常伴",
    "愿您万事顺心",
    "愿您幸福安康",
    "祝您笑口常开",
    "愿您每天都开心",
    "愿您日子越过越好",
    "愿您一家幸福美满",
    "祝您日子红红火火",
)
DRAMA_PROMPT_COPY = (
    "左下角免费看全集",
    "左下角免费看后续",
    "左下角免费看结局",
    "左下角免费继续看",
    "左下角免费接着看",
    "点免费剧集看全集",
    "点免费剧集看后续",
    "免费剧集接着看",
    "后续请点免费剧集",
    "结局请点免费剧集",
)


def _new_id() -> str:
    return str(uuid.uuid4()).upper()


@dataclass(frozen=True)
class FlowerStyleCandidate:
    """A real 5.9 material sample eligible for the current sticker skin."""

    effect_id: str
    payload_md5: str
    name: str
    category_tags: tuple[str, ...]


@dataclass(frozen=True)
class FlowerTextDecision:
    seed: int
    blessing_style: FlowerStyleCandidate
    drama_prompt_style: FlowerStyleCandidate
    blessing_text: str
    drama_prompt_text: str
    duration_seconds: int
    drama_target_visible_size_px: int
    blessing_target_visible_size_px: int
    blessing_target_visible_width_px: int
    drama_prompt_target_visible_width_px: int
    # These are the observed, usable 5.9 native flower-text sizes.  The
    # catalogue's target pixels are planning labels only until a per-style
    # visible-bounds calibration table exists; do not write those pixels as a
    # Jianying font-size value.
    blessing_size: float = 15.0
    drama_prompt_size: float = 15.0
    blessing_scale: float = 0.60
    drama_prompt_scale: float = 0.62
    blessing_position: tuple[float, float] = (-0.08, 0.82)
    drama_prompt_position: tuple[float, float] = (0.22, -0.81)
    blessing_rotation: float = 0.0
    drama_prompt_rotation: float = 0.0
    composition_pattern: str = "legacy_dynamic_photo_wall_bands"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


# This material was saved by Jianying 5.9 in the user's "8月12日" draft.
# It is a purple/cool outline title style and fits the currently active
# 梦幻宝石 sticker skin.  More candidates are appended only after they have
# an equally real saved-material sample and a locally reachable payload.
FLOWER_STYLE_CANDIDATES: tuple[FlowerStyleCandidate, ...] = (
    FlowerStyleCandidate(
        effect_id="7259922491185958203",
        payload_md5="6bc9faabfd6fcf23871bf062df3b69a1",
        name="蓝紫色粗体描边花字",
        category_tags=("purple",),
    ),
)

_DREAM_GEM_ALLOWED_TAGS = frozenset({"blue", "pink", "purple", "light", "gradient", "blackwhite"})
_REJECTED_NAME_TOKENS = (
    "电商", "促销", "带货", "节日", "春节", "圣诞", "美食", "游戏", "故障", "综艺", "口播",
)


def _eligible_styles() -> tuple[FlowerStyleCandidate, ...]:
    """Return only styles that pass the current skin's deterministic filter."""
    eligible = tuple(
        item for item in FLOWER_STYLE_CANDIDATES
        if set(item.category_tags) & _DREAM_GEM_ALLOWED_TAGS
        and not any(token in item.name for token in _REJECTED_NAME_TOKENS)
    )
    if not eligible:
        raise RuntimeError("当前贴纸皮肤没有可用的花字样式")
    return eligible


def _candidate(style: Any) -> FlowerStyleCandidate:
    return FlowerStyleCandidate(
        effect_id=style.effect_id,
        payload_md5=style.payload_md5,
        name=style.name,
        category_tags=style.category_tags,
    )


def _catalog_style_pair(*, catalog: FlowerStyleCatalog, seed: int) -> tuple[FlowerStyleCandidate, FlowerStyleCandidate]:
    """Use the two old curated pools, with current 5.9 catalogue metadata."""
    blessing_pool = tuple(
        style for style in catalog.styles if style.effect_id in LEGACY_BLESSING_EFFECT_IDS
    )
    if not blessing_pool:
        raise RuntimeError("当前花字目录没有旧版祝福文字可用花字")
    rng = random.Random(f"{seed}:legacy-flower-style-pair")
    blessing = rng.choice(blessing_pool)
    drama_pool = tuple(
        style
        for style in catalog.styles
        if style.effect_id in LEGACY_DRAMA_PROMPT_EFFECT_IDS
        and style.effect_id != blessing.effect_id
    )
    if not drama_pool:
        raise RuntimeError("当前花字目录没有与祝福文字不同的旧版剧集引导花字")
    return _candidate(blessing), _candidate(rng.choice(drama_pool))


def decide_flower_text(
    *, seed: int, duration_seconds: int, central_window_boundary_ratio: float, flower_style_catalog: Path | None = None
) -> FlowerTextDecision:
    if duration_seconds != 180:
        raise ValueError("花字双轨当前只适用于已确认的 180 秒模板")
    rng = random.Random(f"{seed}:flower-text")
    if not 0.0 < central_window_boundary_ratio < 1.0:
        raise ValueError("central_window_boundary_ratio must be within (0, 1)")
    if flower_style_catalog is None:
        styles = _eligible_styles()
        if len(styles) < 2:
            raise RuntimeError("正式模板必须传入当前花字目录，不能用单一样式回退")
        blessing_style, drama_style = rng.sample(list(styles), 2)
    else:
        blessing_style, drama_style = _catalog_style_pair(
            catalog=load_flower_style_catalog(flower_style_catalog), seed=seed,
        )
    drama_size = rng.randint(124, 138)
    linked_size_fraction = (drama_size - 124) / (138 - 124)
    wall_band = 1.0 - central_window_boundary_ratio
    blessing_fraction = rng.uniform(*BLESSING_BAND_FRACTION_RANGE)
    drama_fraction = rng.uniform(*DRAMA_PROMPT_BAND_FRACTION_RANGE)
    blessing_position = (
        round(rng.uniform(*BLESSING_X_RANGE), 6),
        round(1.0 - blessing_fraction * wall_band, 6),
    )
    drama_position = (
        round(rng.uniform(*DRAMA_PROMPT_X_RANGE), 6),
        round(-central_window_boundary_ratio - drama_fraction * wall_band, 6),
    )
    blessing_text = rng.choice(BLESSING_COPY)
    drama_text = rng.choice(DRAMA_PROMPT_COPY)
    drama_width_range = DRAMA_PROMPT_VISIBLE_WIDTH_BY_CHAR_COUNT[len(drama_text)]
    blessing_scale_range = BLESSING_SCALE_BY_CHAR_COUNT[len(blessing_text)]
    drama_scale_range = DRAMA_PROMPT_SCALE_BY_CHAR_COUNT[len(drama_text)]
    return FlowerTextDecision(
        seed=seed,
        blessing_style=blessing_style,
        drama_prompt_style=drama_style,
        blessing_text=blessing_text,
        drama_prompt_text=drama_text,
        duration_seconds=duration_seconds,
        drama_target_visible_size_px=drama_size,
        blessing_target_visible_size_px=drama_size - 10,
        blessing_target_visible_width_px=rng.randint(*BLESSING_VISIBLE_WIDTH_RANGE_PX),
        drama_prompt_target_visible_width_px=rng.randint(*drama_width_range),
        blessing_size=15.0,
        drama_prompt_size=15.0,
        blessing_scale=round(
            blessing_scale_range[0]
            + linked_size_fraction * (blessing_scale_range[1] - blessing_scale_range[0]),
            6,
        ),
        drama_prompt_scale=round(
            drama_scale_range[0]
            + linked_size_fraction * (drama_scale_range[1] - drama_scale_range[0]),
            6,
        ),
        blessing_position=blessing_position,
        drama_prompt_position=drama_position,
        blessing_rotation=round(rng.uniform(*BLESSING_ROTATION_RANGE), 3),
        drama_prompt_rotation=round(rng.uniform(*DRAMA_PROMPT_ROTATION_RANGE), 3),
    )


def _asset_path(user_data_root: Path, style: FlowerStyleCandidate) -> Path:
    return user_data_root / "Cache" / "artistEffect" / style.effect_id / style.payload_md5


def _system_font_path(user_data_root: Path) -> str:
    apps_root = user_data_root.parent / "Apps"
    candidates = sorted(apps_root.glob("*/Resources/Font/SystemFont/zh-hans.ttf"))
    if not candidates:
        raise FileNotFoundError("当前剪映安装目录中缺少系统中文字体 zh-hans.ttf")
    return candidates[-1].as_posix()


def _text_material(*, text: str, size: float, style: FlowerStyleCandidate, user_data_root: Path) -> dict[str, Any]:
    """Native text material cloned from the observed 5.9 flower-text shape."""
    font_path = _system_font_path(user_data_root)
    content = {
        "styles": [{
            "effectStyle": {"id": style.effect_id, "path": _asset_path(user_data_root, style).as_posix()},
            "fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": [1.0, 1.0, 1.0]}}},
            "font": {"id": "", "path": font_path},
            "range": [0, len(text)],
            "size": size,
        }],
        "text": text,
    }
    return {
        "add_type": 0, "alignment": 1, "background_alpha": 1.0, "background_color": "",
        "background_height": 0.14, "background_horizontal_offset": 0.0, "background_round_radius": 0.0,
        "background_style": 0, "background_vertical_offset": 0.0, "background_width": 0.14,
        "base_content": "", "bold_width": 0.0, "border_alpha": 1.0, "border_color": "", "border_width": 0.08,
        "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "is_new": False, "path": "", "request_id": "", "resource_id": "", "resource_name": "", "source_platform": 0},
        "check_flag": 7, "combo_info": {"text_templates": []}, "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
        "fixed_height": -1.0, "fixed_width": -1.0, "font_category_id": "", "font_category_name": "", "font_id": "",
        "font_name": "", "font_path": font_path, "font_resource_id": "", "font_size": size, "font_source_platform": 0,
        "font_team_id": "", "font_title": "none", "font_url": "", "fonts": [], "force_apply_line_max_width": False,
        "global_alpha": 1.0, "group_id": "", "has_shadow": False, "id": _new_id(), "initial_scale": 1.0,
        "inner_padding": -1.0, "is_rich_text": False, "italic_degree": 0, "ktv_color": "", "language": "", "layer_weight": 1,
        "letter_spacing": 0.0, "line_feed": 1, "line_max_width": 0.82, "line_spacing": 0.02,
        "multi_language_current": "none", "name": style.name, "original_size": [], "preset_category": "", "preset_category_id": "",
        "preset_has_set_alignment": False, "preset_id": "", "preset_index": 0, "preset_name": "", "recognize_task_id": "",
        "recognize_type": 0, "relevance_segment": [], "shadow_alpha": 0.9, "shadow_angle": -45.0, "shadow_color": "",
        "shadow_distance": 5.0, "shadow_point": {"x": 0.6363961030678928, "y": -0.6363961030678928},
        "shadow_smoothing": 0.45, "shape_clip_x": False, "shape_clip_y": False, "source_from": "", "style_name": "",
        "sub_type": 0, "subtitle_keywords": None, "subtitle_template_original_fontsize": 0.0, "text_alpha": 1.0,
        "text_color": "#FFFFFF", "text_curve": None, "text_preset_resource_id": "", "text_size": int(size * 2),
        "text_to_audio_ids": [], "tts_auto_update": False, "type": "text", "typesetting": 0, "underline": False,
        "underline_offset": 0.22, "underline_width": 0.05, "use_effect_default_color": True,
        "words": {"end_time": [], "start_time": [], "text": []},
    }


def _effect_material(style: FlowerStyleCandidate, user_data_root: Path) -> dict[str, Any]:
    return {
        "adjust_params": [], "algorithm_artifact_path": "", "apply_target_type": 0, "bloom_params": None,
        "category_id": "11886", "category_name": "11886", "color_match_info": {"source_feature_path": "", "target_feature_path": "", "target_image_path": ""},
        "effect_id": style.effect_id, "enable_skin_tone_correction": False, "exclusion_group": [], "face_adjust_params": [],
        "formula_id": "", "id": _new_id(), "intensity_key": "", "multi_language_current": "", "name": style.name,
        "panel_id": "", "path": _asset_path(user_data_root, style).as_posix(), "platform": "all", "request_id": "",
        "resource_id": style.effect_id, "source_platform": 1, "sub_type": "none", "time_range": None,
        "type": "text_effect", "value": 1.0, "version": "",
    }


def _segment(*, material_id: str, refs: list[str], transform_x: float, transform_y: float, scale: float, rotation: float, ordinal: int) -> dict[str, Any]:
    return {
        "caption_info": None, "cartoon": False,
        "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False}, "rotation": rotation, "scale": {"x": scale, "y": scale}, "transform": {"x": transform_x, "y": transform_y}},
        "common_keyframes": [], "enable_adjust": False, "enable_color_correct_adjust": False, "enable_color_curves": True,
        "enable_color_match_adjust": False, "enable_color_wheels": True, "enable_lut": False, "enable_smart_color_adjust": False,
        "extra_material_refs": refs, "group_id": "", "hdr_settings": None, "id": _new_id(), "intensifies_audio": False,
        "is_placeholder": False, "is_tone_modify": False, "keyframe_refs": [], "last_nonzero_volume": 1.0,
        "material_id": material_id, "render_index": 15_000 + ordinal,
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0},
        "reverse": False, "source_timerange": None, "speed": 1.0,
        "target_timerange": {"start": 0, "duration": FULL_DURATION_US}, "template_id": "", "template_scene": "default",
        "track_attribute": 0, "track_render_index": 200 + ordinal, "uniform_scale": {"on": True, "value": 1.0},
        "visible": True, "volume": 1.0,
    }


def _append_flower_text(*, content_path: Path, decision: FlowerTextDecision, user_data_root: Path) -> None:
    document: dict[str, Any] = json.loads(content_path.read_text(encoding="utf-8"))
    if any(track.get("name") in {BLESSING_TRACK_NAME, DRAMA_PROMPT_TRACK_NAME} for track in document.get("tracks", [])):
        raise RuntimeError("目标草稿已经有花字双轨，拒绝重复写入")
    materials = document.setdefault("materials", {})
    blessing_effect = _effect_material(decision.blessing_style, user_data_root)
    drama_effect = _effect_material(decision.drama_prompt_style, user_data_root)
    animation = {"animations": [], "id": _new_id(), "multi_language_current": "none", "type": "sticker_animation"}
    blessing = _text_material(text=decision.blessing_text, size=decision.blessing_size, style=decision.blessing_style, user_data_root=user_data_root)
    drama = _text_material(text=decision.drama_prompt_text, size=decision.drama_prompt_size, style=decision.drama_prompt_style, user_data_root=user_data_root)
    materials.setdefault("effects", []).extend((blessing_effect, drama_effect))
    materials.setdefault("material_animations", []).append(animation)
    materials.setdefault("texts", []).extend((blessing, drama))
    blessing_refs = [animation["id"], blessing_effect["id"], blessing_effect["id"]]
    drama_refs = [animation["id"], drama_effect["id"], drama_effect["id"]]
    document.setdefault("tracks", []).extend((
        {"attribute": 0, "flag": 0, "id": _new_id(), "is_default_name": False, "name": BLESSING_TRACK_NAME, "type": "text", "segments": [_segment(material_id=blessing["id"], refs=blessing_refs, transform_x=decision.blessing_position[0], transform_y=decision.blessing_position[1], scale=decision.blessing_scale, rotation=decision.blessing_rotation, ordinal=1)]},
        {"attribute": 0, "flag": 0, "id": _new_id(), "is_default_name": False, "name": DRAMA_PROMPT_TRACK_NAME, "type": "text", "segments": [_segment(material_id=drama["id"], refs=drama_refs, transform_x=decision.drama_prompt_position[0], transform_y=decision.drama_prompt_position[1], scale=decision.drama_prompt_scale, rotation=decision.drama_prompt_rotation, ordinal=2)]},
    ))
    document["render_index_track_mode_on"] = True
    content_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def create_track10_11_flower_text_draft(
    *, draft_root: Path, draft_name: str, plan: T00ProjectPlan, source01: VideoProbe, source02: VideoProbe,
    source03: VideoProbe, photo_dir: Path, photo_cache_root: Path, user_data_root: Path | None = None,
    sticker_skin_catalog: Path | None = None,
    flower_style_catalog: Path | None = None,
) -> tuple[Any, Any, Any, Any, Any, Any, StickerSkinDecision, FlowerTextDecision]:
    """Build a fresh T00–T09 draft, then append two same-style flower tracks."""
    root = user_data_root or _default_user_data_root()
    track01, track04, walls, track05, track06, effects, stickers = create_track09_sticker_skin_draft(
        draft_root=draft_root, draft_name=draft_name, plan=plan, source01=source01, source02=source02,
        source03=source03, photo_dir=photo_dir, photo_cache_root=photo_cache_root, user_data_root=root,
        sticker_skin_catalog=sticker_skin_catalog,
    )
    decision = decide_flower_text(
        seed=plan.seed,
        duration_seconds=plan.duration_seconds,
        central_window_boundary_ratio=track01.canvas_height_ratio,
        flower_style_catalog=flower_style_catalog,
    )
    _append_flower_text(content_path=draft_root / draft_name / "draft_content.json", decision=decision, user_data_root=root)
    return track01, track04, walls, track05, track06, effects, stickers, decision
