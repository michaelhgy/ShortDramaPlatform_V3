"""Confirmed visual layers for native Jianying 5.9 finished-video drafts."""

from __future__ import annotations

import copy
import json
import os
import random
import uuid
from pathlib import Path
from typing import Any

from PIL import Image


CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 2400
PHOTO_COUNT = 6
REAL_PHOTO_ALPHA = 0.02
REAL_PHOTO_RULE_VERSION = "cell-cover-local-mask-v2"
# Leave a small cover margin so rounding at a cell boundary cannot expose a
# one-pixel transparent seam in Jianying 5.9.
COVER_SAFETY_MARGIN = 1.005
GLOBAL_EFFECT_POOL = Path(__file__).resolve().parents[2] / "template_engine" / "jianying59_template" / "resources" / "track07_08_effect_pool_5_9.json"
REAL_PHOTO_EFFECT_POOL = Path(__file__).with_name("resources") / "real_photo_effect_pool_5_9.json"
ADJUST_PARAMETERS = (
    ("色温", "temperature", "v3"), ("色调", "tone", "v3"), ("饱和度", "saturation", "v1"),
    ("自然饱和度", "natural_saturation", "v1"), ("亮度", "brightness", "v2"),
    ("对比度", "contrast", "v3"), ("高光", "highlight", "v3"), ("阴影", "shadow", "v3"),
    ("白色", "white", ""), ("黑色", "black", ""), ("光感", "light_sensation", ""),
)
HSL_COLORS = (("红色", 1), ("橙色", 2), ("黄色", 3), ("绿色", 4), ("青色", 5), ("蓝色", 6), ("紫色", 7), ("洋红", 8))
HSL_DIMENSIONS = (("色相", "hue"), ("饱和度", "saturation"), ("亮度", "lightness"))
ADJUST_UI_VALUES = (-3, -2, -1, 1, 2, 3)


def new_id() -> str:
    return str(uuid.uuid4()).upper()


def _natural_key(path: Path) -> tuple[Any, ...]:
    import re
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.stem))


def _read_photo_pool(photo_dir: Path, photo_files: list[Path] | None = None) -> list[dict[str, Any]]:
    if not photo_dir.is_dir():
        raise FileNotFoundError(f"真人图片素材库不存在：{photo_dir}")
    result: list[dict[str, Any]] = []
    source_paths = photo_files if photo_files is not None else sorted(photo_dir.iterdir(), key=_natural_key)
    for path in source_paths:
        if not path.is_file() or path.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        try:
            with Image.open(path) as image:
                width, height = image.size
            if width > 0 and height > 0:
                result.append({"path": str(path.resolve()), "name": path.name, "width": width, "height": height})
        except (OSError, ValueError):
            continue
    if len(result) < PHOTO_COUNT:
        raise RuntimeError(f"真人图片素材库至少需要{PHOTO_COUNT}张可读图片，当前只有{len(result)}张")
    return result


def _real_photo_effects() -> list[dict[str, Any]]:
    """Load the 13 verified Jianying 5.9 effects without a donor draft."""
    payload = json.loads(REAL_PHOTO_EFFECT_POOL.read_text(encoding="utf-8"))
    candidates = list(payload.get("effects") or [])
    if payload.get("schema") != "jianying59_real_photo_effect_pool_v1" or len(candidates) != 13:
        raise RuntimeError("真人组合特效清单必须包含13个已验证候选")
    required = ("name", "resource_id", "effect_id", "payload_md5", "category_id", "category_name")
    if any(not all(str(item.get(field) or "") for field in required) for item in candidates):
        raise RuntimeError("真人组合特效清单包含无效资源身份")
    return [
        {
            "adjust_params": copy.deepcopy(item.get("adjust_params") or []),
            "algorithm_artifact_path": "", "apply_target_type": 0, "apply_time_range": None,
            "category_id": item["category_id"], "category_name": item["category_name"],
            "common_keyframes": [], "disable_effect_faces": [], "effect_id": item["effect_id"],
            "formula_id": "", "name": item["name"], "platform": "all", "render_index": 11000,
            "request_id": "", "resource_id": item["resource_id"], "source_platform": 0,
            "time_range": None, "track_render_index": 0, "type": "video_effect", "value": 1.0,
            "version": "", "payload_md5": item["payload_md5"],
        }
        for item in candidates
    ]


def _grid(seed: int) -> list[dict[str, float]]:
    """Return a 2 x 3 partition with modest, gap-free variation."""
    rng = random.Random(f"{seed}:real-photo-grid")
    left_ratio = rng.uniform(0.46, 0.54)
    deviations = [rng.uniform(-0.025, 0.025) for _ in range(3)]
    average = sum(deviations) / 3
    row_ratios = [(1 / 3) + value - average for value in deviations]
    cells: list[dict[str, float]] = []
    top = 0.0
    for row_height in row_ratios:
        left = 0.0
        for column_width in (left_ratio, 1.0 - left_ratio):
            width = CANVAS_WIDTH * column_width
            height = CANVAS_HEIGHT * row_height
            cells.append({
                "x": left * CANVAS_WIDTH,
                "y": top * CANVAS_HEIGHT,
                "width": width,
                "height": height,
                "center_x": (left + column_width / 2) * 2 - 1,
                "center_y": (top + row_height / 2) * 2 - 1,
            })
            left += column_width
        top += row_height
    return cells


def _cover_scale(image: dict[str, Any], cell: dict[str, float]) -> float:
    natural_height = CANVAS_WIDTH * int(image["height"]) / int(image["width"])
    return round(max(float(cell["width"]) / CANVAS_WIDTH, float(cell["height"]) / natural_height) * COVER_SAFETY_MARGIN, 9)


def _local_mask_size(image: dict[str, Any], cell: dict[str, float], scale: float) -> dict[str, float]:
    """Map a canvas cell to the image-local mask dimensions used by Jianying."""
    display_width = CANVAS_WIDTH * scale
    display_height = display_width * int(image["height"]) / int(image["width"])
    return {
        "width": round(min(1.0, float(cell["width"]) / display_width), 9),
        "height": round(min(1.0, float(cell["height"]) / display_height), 9),
    }


def _validate_photo_cover(item: dict[str, Any]) -> None:
    """Fail before writing a draft if a local mask cannot cover its cell."""
    image_width = int(item["width"])
    image_height = int(item["height"])
    scale = float(item["scale"])
    cell = item["cell"]
    mask = item["mask"]
    display_width = CANVAS_WIDTH * scale
    display_height = display_width * image_height / image_width
    if display_width * float(mask["width"]) + 1e-5 < float(cell["width"]):
        raise ValueError("真人图片局部蒙版宽度不足以覆盖所属格子")
    if display_height * float(mask["height"]) + 1e-5 < float(cell["height"]):
        raise ValueError("真人图片局部蒙版高度不足以覆盖所属格子")


def plan_visual_layers(*, photo_dir: Path, duration_us: int, seed: int, photo_files: list[Path] | None = None) -> dict[str, Any]:
    if duration_us <= 0:
        raise ValueError("真人组合片段时长无效")
    # The lifecycle service has already selected and moved the six photos for
    # this account/day.  Keep that natural order; only layout/effect choices
    # remain randomized per finished draft.
    photos = _read_photo_pool(photo_dir, photo_files)[:PHOTO_COUNT]
    cells = _grid(seed)
    selected_effect = random.Random(f"{seed}:real-photo-effect").choice(_real_photo_effects())
    selections = []
    for index, (photo, cell) in enumerate(zip(photos, cells), start=1):
        scale = _cover_scale(photo, cell)
        selection = {
            "index": index, **photo, "cell": cell, "scale": scale,
            "mask": _local_mask_size(photo, cell, scale),
        }
        _validate_photo_cover(selection)
        selections.append(selection)
    return {
        "seed": seed,
        "duration_us": duration_us,
        "rule_version": REAL_PHOTO_RULE_VERSION,
        "grid": {"columns": 2, "rows": 3, "layout": "bounded_random_gap_free"},
        "photos": selections,
        "effect": selected_effect,
        "alpha": REAL_PHOTO_ALPHA,
    }


def plan_global_layers(*, seed: int) -> dict[str, Any]:
    pool_payload = json.loads(GLOBAL_EFFECT_POOL.read_text(encoding="utf-8"))
    effects = list(pool_payload.get("effects") or [])
    if len(effects) != 27:
        raise RuntimeError("成片全局特效池必须是27个已验证候选")
    effect_rng = random.Random(f"{seed}:final-global-effects")
    chosen = effect_rng.sample(effects, 2)
    adjustment_rng = random.Random(f"{seed}:final-global-adjustment")
    basic = []
    for label, effect_type, version in adjustment_rng.sample(ADJUST_PARAMETERS, 3):
        ui_value = adjustment_rng.choice(ADJUST_UI_VALUES)
        basic.append({"label": label, "type": effect_type, "version": version, "ui_value": ui_value, "value": round(ui_value * 0.02, 2)})
    color_name, color_type = adjustment_rng.choice(HSL_COLORS)
    dimension_label, dimension = adjustment_rng.choice(HSL_DIMENSIONS)
    return {
        "seed": seed,
        "effects": [
            {"name": item["name"], "resource_id": item["resource_id"], "effect_id": item["effect_id"], "payload_md5": item["payload_md5"], "opacity_ui_value": effect_rng.randint(2, 8)}
            for item in chosen
        ],
        "adjustment": {
            "basic": basic, "hsl_color_name": color_name, "hsl_color_type": color_type,
            "hsl_dimension_label": dimension_label, "hsl_dimension": dimension,
            "hsl_ui_value": adjustment_rng.choice(ADJUST_UI_VALUES),
        },
    }


def _effect_material(item: dict[str, Any], user_data_root: Path) -> dict[str, Any]:
    opacity = round(int(item["opacity_ui_value"]) / 100, 2)
    return {
        "adjust_params": [
            {"name": "effects_adjust_background_animation", "value": opacity, "default_value": 1.0},
            {"name": "effects_adjust_speed", "value": 0.33, "default_value": 0.33},
        ], "algorithm_artifact_path": "", "apply_target_type": 2, "apply_time_range": None,
        "category_id": "", "category_name": "", "common_keyframes": [], "disable_effect_faces": [],
        "effect_id": item["effect_id"], "formula_id": "", "id": new_id(), "name": item["name"],
        "path": (user_data_root / "Cache" / "effect" / item["effect_id"] / item["payload_md5"]).as_posix(),
        "platform": "all", "render_index": 0, "request_id": "", "resource_id": item["resource_id"],
        "source_platform": 0, "time_range": None, "track_render_index": 0, "type": "video_effect", "value": 1.0, "version": "",
    }


def _track_segment(material_id: str, duration_us: int, index: int) -> dict[str, Any]:
    return {"caption_info": None, "cartoon": False, "clip": None, "common_keyframes": [], "enable_adjust": False,
        "enable_color_correct_adjust": False, "enable_color_curves": True, "enable_color_match_adjust": False,
        "enable_color_wheels": True, "enable_lut": False, "enable_smart_color_adjust": False, "extra_material_refs": [],
        "group_id": "", "hdr_settings": None, "id": new_id(), "intensifies_audio": False, "is_placeholder": False,
        "is_tone_modify": False, "keyframe_refs": [], "last_nonzero_volume": 1.0, "material_id": material_id,
        "render_index": 11012 + index, "responsive_layout": {"enable": False, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0},
        "reverse": False, "source_timerange": None, "speed": 1.0, "target_timerange": {"start": 0, "duration": duration_us},
        "template_id": "", "template_scene": "default", "track_attribute": 0, "track_render_index": 7 + index,
        "uniform_scale": None, "visible": True, "volume": 1.0}


def _find_app_root() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro" / "Apps"
    for candidate in sorted(root.iterdir(), reverse=True) if root.is_dir() else []:
        bundle = candidate / "Resources" / "DefaultAdjustBundle"
        if (bundle / "combine_adjust").is_dir() and (bundle / "hsl_v1").is_dir():
            return candidate
    raise RuntimeError("当前剪映安装中未找到5.9调节资源")


def _append_adjustment(document: dict[str, Any], decision: dict[str, Any], duration_us: int) -> None:
    app_root = _find_app_root()
    materials = document.setdefault("materials", {})
    placeholder_id = new_id()
    materials.setdefault("placeholders", []).append({"id": placeholder_id, "material_resource_id": "", "name": "F05_GLOBAL_ADJUST", "type": "adjust"})
    basics = [{"adjust_params": [], "algorithm_artifact_path": "", "apply_target_type": 0, "bloom_params": None, "category_id": "", "category_name": "", "color_match_info": None, "effect_id": "", "enable_skin_tone_correction": False, "exclusion_group": [], "face_adjust_params": [], "formula_id": "", "id": new_id(), "intensity_key": "", "multi_language_current": "", "name": "", "panel_id": "", "path": (app_root / "Resources" / "DefaultAdjustBundle" / "combine_adjust").as_posix(), "platform": "all", "request_id": "", "resource_id": "", "source_platform": 0, "sub_type": "none", "time_range": None, "type": item["type"], "value": item["value"], "version": item["version"]} for item in decision["basic"]]
    materials.setdefault("effects", []).extend(basics)
    hsl_values = {"hue": 0, "saturation": 0, "lightness": 0}
    hsl_values[decision["hsl_dimension"]] = decision["hsl_ui_value"]
    neutral = {"hsl_color_type": 1, "hue": 0, "id": new_id(), "interacting": False, "lightness": 0, "path": (app_root / "Resources" / "DefaultAdjustBundle" / "hsl").as_posix(), "type": "hsl", "saturation": 0, "version": ""}
    active = {"hsl_color_type": decision["hsl_color_type"], "id": new_id(), "interacting": True, "path": (app_root / "Resources" / "DefaultAdjustBundle" / "hsl_v1").as_posix(), "type": "hsl", "version": "1", **hsl_values}
    materials.setdefault("hsl", []).extend((neutral, active))
    segment = _track_segment(placeholder_id, duration_us, 2)
    segment.update({"enable_adjust": True, "enable_lut": True, "extra_material_refs": [*(item["id"] for item in basics), neutral["id"], active["id"]]})
    document.setdefault("tracks", []).append({"attribute": 0, "flag": 0, "id": new_id(), "is_default_name": False, "name": "F05_GLOBAL_ADJUST", "segments": [segment], "type": "adjust"})


def _nested_draft(layer: dict[str, Any], rectangle_payload: Path) -> dict[str, Any]:
    from pyJianYingDraft import ClipSettings, MaskType, ScriptFile, Timerange, TrackType, VideoMaterial, VideoSegment
    nested = ScriptFile(CANVAS_WIDTH, CANVAS_HEIGHT, 30, False)
    for index, item in enumerate(layer["photos"], start=1):
        track_name = f"REAL_PHOTO_{index:02d}"
        nested.add_track(TrackType.video, track_name, relative_index=index)
        cell = item["cell"]
        segment = VideoSegment(VideoMaterial(item["path"]), Timerange(0, layer["duration_us"]), source_timerange=Timerange(0, layer["duration_us"]), volume=0.0, clip_settings=ClipSettings(scale_x=item["scale"], scale_y=item["scale"], transform_x=cell["center_x"], transform_y=cell["center_y"]))
        # The transform uses the nested canvas. Jianying 5.9 stores this
        # combination mask in the child image's local coordinate system, so
        # the canvas cell must be converted through the scaled image display
        # size. Passing the canvas ratio here produces the old black gaps.
        mask = item["mask"]
        _validate_photo_cover(item)
        segment.add_mask(MaskType.矩形, center_x=0.0, center_y=0.0, size=mask["height"], rect_width=mask["width"], feather=0.0, invert=False)
        nested.add_segment(segment, track_name)
    document = json.loads(nested.dumps())
    document["duration"] = layer["duration_us"]
    document["canvas_config"] = {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT, "ratio": "custom"}
    document["render_index_track_mode_on"] = True
    for index, track in enumerate(document.get("tracks", []), start=1):
        for segment in track.get("segments", []):
            segment["track_render_index"] = index
    for material in document.get("materials", {}).get("videos", []):
        material["material_id"] = ""
        material["local_material_id"] = ""
        material["crop"] = {}
        material["crop_ratio"] = "free"
        material["has_audio"] = False
    for mask in document.get("materials", {}).get("masks", []):
        mask["path"] = rectangle_payload.as_posix()
    return document


def _append_real_photo_compound(document: dict[str, Any], layer: dict[str, Any], duration_us: int, rectangle_payload: Path, user_data_root: Path) -> None:
    materials = document.setdefault("materials", {})
    prototype = next((item for item in materials.get("videos", []) if item.get("path")), None)
    if prototype is None:
        raise RuntimeError("成片缺少可复用视频材料，无法创建真人组合片段")
    draft_ref_id = new_id()
    materials.setdefault("drafts", []).append({"category_id": "", "category_name": "", "combination_id": new_id(), "draft": _nested_draft(layer, rectangle_payload), "formula_id": "", "id": draft_ref_id, "name": "F06_REAL_PHOTO_COMPOUND", "precompile_combination": False, "type": "combination"})
    compound = copy.deepcopy(prototype)
    compound.update({"id": new_id(), "material_id": "", "local_material_id": "", "material_name": "真人六宫格组合片段", "path": "", "media_path": "", "duration": duration_us, "width": CANVAS_WIDTH, "height": CANVAS_HEIGHT, "type": "video", "has_audio": False, "extra_type_option": 2, "is_copyright": True, "category_id": "", "category_name": ""})
    materials.setdefault("videos", []).append(compound)
    effect = copy.deepcopy(layer["effect"])
    effect["id"] = new_id()
    payload_name = str(effect.pop("payload_md5", "") or Path(str(effect.get("path") or "")).name)
    if payload_name:
        effect["path"] = (Path(user_data_root) / "Cache" / "effect" / str(effect.get("effect_id") or "") / payload_name).as_posix()
    materials.setdefault("video_effects", []).append(effect)
    speed_id, canvas_id, mapping_id, vocal_id = new_id(), new_id(), new_id(), new_id()
    materials.setdefault("speeds", []).append({"curve_speed": None, "id": speed_id, "mode": 0, "speed": 1.0, "type": "speed"})
    materials.setdefault("canvases", []).append({"album_image": "", "blur": 0.0, "color": "", "id": canvas_id, "image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": "", "type": "canvas_color"})
    materials.setdefault("sound_channel_mappings", []).append({"audio_channel_mapping": 0, "id": mapping_id, "is_config_open": False, "type": ""})
    materials.setdefault("vocal_separations", []).append({"choice": 0, "id": vocal_id, "production_path": "", "time_range": None, "type": "vocal_separation"})
    parent = _track_segment(compound["id"], duration_us, 3)
    parent.update({"source_timerange": {"start": 0, "duration": duration_us}, "extra_material_refs": [draft_ref_id, speed_id, effect["id"], canvas_id, mapping_id, vocal_id], "clip": {"alpha": layer["alpha"], "flip": {"horizontal": False, "vertical": False}, "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}}, "volume": 0.0, "uniform_scale": {"on": True, "value": 1.0}})
    document.setdefault("tracks", []).append({"attribute": 0, "flag": 0, "id": new_id(), "is_default_name": False, "name": "F06_REAL_PHOTO_COMPOUND", "segments": [parent], "type": "video"})


def append_visual_layers(*, content_path: Path, plan: dict[str, Any], user_data_root: Path, rectangle_payload: Path) -> None:
    document = json.loads(content_path.read_text(encoding="utf-8"))
    duration_us = int(plan["duration_us"])
    materials = document.setdefault("materials", {})
    for index, item in enumerate(plan["tracks"]["global_layers"]["effects"]):
        material = _effect_material(item, user_data_root)
        materials.setdefault("video_effects", []).append(material)
        document.setdefault("tracks", []).append({"attribute": 0, "flag": 0, "id": new_id(), "is_default_name": False, "name": f"F0{3 + index}_GLOBAL_EFFECT", "segments": [_track_segment(material["id"], duration_us, index)], "type": "effect"})
    _append_adjustment(document, plan["tracks"]["global_layers"]["adjustment"], duration_us)
    _append_real_photo_compound(document, plan["tracks"]["real_photo"], duration_us, rectangle_payload, user_data_root)
    order = {
        "F01_VIRAL_MAIN": 1, "F02_TEMPLATE_LOOP": 2, "F03_GLOBAL_EFFECT": 3,
        "F04_GLOBAL_EFFECT": 4, "F05_GLOBAL_ADJUST": 5, "F06_REAL_PHOTO_COMPOUND": 6,
        "F07_ACCOUNT_ID": 7, "F08_WARNING": 8, "F09_AI_DISCLOSURE": 9, "F10_BGM": 10,
    }
    document["tracks"].sort(key=lambda track: order.get(str(track.get("name")), 99))
    document["render_index_track_mode_on"] = True
    content_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
