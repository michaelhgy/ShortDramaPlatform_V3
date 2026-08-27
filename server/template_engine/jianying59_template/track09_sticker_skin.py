"""T09: native Jianying 5.9 sticker skins and their fixed-picture layout.

The runtime catalogue is synchronised from the user's current ``贴纸素材``
categories.  Each generated draft uses exactly one of those collections.  The
legacy dream-gem sample remains only as an explicit fallback for regression
tests and for already-created drafts; normal generation receives a catalogue.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_base import T00ProjectPlan, VideoProbe
from .track01 import Track01Decision, _default_user_data_root
from .track02_03 import PhotoWallDecision
from .track04 import Track04Decision
from .track05 import Track05Decision
from .track06 import Track06Decision
from .track07_08 import Track07_08Decision, create_track07_08_draft
from .sticker_skin_library import StickerSkinCatalog, choose_skin_and_layout, load_sticker_skin_catalog


SKIN_ID = "dream_gem_test_skin_v1"
SKIN_NAME = "梦幻宝石测试皮肤"
FULL_DURATION_US = 180_000_000


def _new_id() -> str:
    return str(uuid.uuid4()).upper()


@dataclass(frozen=True)
class StickerSkinItem:
    resource_id: str
    payload_md5: str
    name: str
    transform_x: float
    transform_y: float
    scale: float
    rotation: float
    alpha: float = 1.0
    request_id: str = ""
    icon_url: str = ""


@dataclass(frozen=True)
class StickerSkinDecision:
    seed: int
    skin_id: str
    skin_name: str
    items: tuple[StickerSkinItem, ...]
    duration_seconds: int
    animation: str = "none_static_full_duration"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


# Each item and its native material shape were observed in a manually opened
# Jianying 5.9 draft.  This fixed set remains a regression fixture only; the
# final route uses the current A=B skin catalogue and a dynamic instance plan.
DREAM_GEM_ITEMS: tuple[StickerSkinItem, ...] = (
    StickerSkinItem("7131647143491767587", "d7df5526fac1151fe4226414261112f3", "梦幻宝石蝴蝶", -0.76, -0.83, 0.320988, -7.0),
    StickerSkinItem("7131652712336313634", "be1b879638be2c5df944a1559d4212c4", "梦幻宝石下左装饰", -0.58, -0.76, 0.182716, 13.0),
    StickerSkinItem("7131647835606420777", "e18f4b0dc803e44462f3270700bacf01", "梦幻宝石下左点缀", -0.87, -0.68, 0.120988, -22.0),
    StickerSkinItem("7131694680202333474", "55fded48133448cc874ee499e4203cd6", "梦幻宝石蝴蝶结", 0.75, -0.83, 0.308642, 7.0),
    StickerSkinItem("7131752419213446434", "651eb227db2e7f3a9d8b585d833de36d", "梦幻宝石下右装饰", 0.60, -0.76, 0.162963, -14.0),
    StickerSkinItem("7131692674406452495", "db6f9acd00b581ee474a749f0945959f", "梦幻宝石下右点缀", 0.87, -0.68, 0.130864, 22.0),
    StickerSkinItem("7131688856939777314", "69b841f15e2d5ad0949050d9c69d3392", "梦幻宝石灯球", -0.75, 0.82, 0.253086, 8.0),
    StickerSkinItem("7131691324939521280", "dfa3520e4a5bfb0a14a137595660739f", "梦幻宝石上左装饰", -0.59, 0.73, 0.209877, 24.0),
    StickerSkinItem("7131689816940416256", "8d4b5d55cd1683c0acf4d7c6d4a24096", "梦幻宝石上右装饰", 0.75, 0.82, 0.271605, -6.0),
    StickerSkinItem("7131680575018044713", "4c15718f27f038a46bee622566a63ce8", "梦幻爱心", 0.60, 0.73, 0.179012, 15.0),
)


def _catalog_decision(*, catalog: StickerSkinCatalog, seed: int, duration_seconds: int, blessing_anchor: tuple[float, float] | None = None, drama_anchor: tuple[float, float] | None = None, central_window_boundary_ratio: float = 0.70) -> StickerSkinDecision:
    skin, selected = choose_skin_and_layout(
        catalog=catalog, seed=seed, blessing_anchor=blessing_anchor, drama_anchor=drama_anchor,
        central_window_boundary_ratio=central_window_boundary_ratio,
    )
    return StickerSkinDecision(
        seed=seed,
        skin_id=skin.skin_id,
        skin_name=skin.skin_name,
        items=tuple(
            StickerSkinItem(
                resource_id=resource.resource_id,
                payload_md5=resource.payload_md5,
                name=resource.name,
                transform_x=placement.transform_x,
                transform_y=placement.transform_y,
                scale=placement.scale,
                rotation=placement.rotation,
                alpha=placement.alpha,
                request_id=resource.request_id,
                icon_url=resource.icon_url,
            )
            for resource, placement in selected
        ),
        duration_seconds=duration_seconds,
    )


def decide_track09_sticker_skin(*, seed: int, duration_seconds: int, catalog: StickerSkinCatalog | None = None, blessing_anchor: tuple[float, float] | None = None, drama_anchor: tuple[float, float] | None = None, central_window_boundary_ratio: float = 0.70) -> StickerSkinDecision:
    if duration_seconds != 180:
        raise ValueError("贴纸皮肤测试只适用于已确认的 180 秒模板")
    if catalog is not None:
        return _catalog_decision(
            catalog=catalog, seed=seed, duration_seconds=duration_seconds,
            blessing_anchor=blessing_anchor, drama_anchor=drama_anchor,
            central_window_boundary_ratio=central_window_boundary_ratio,
        )
    if len(DREAM_GEM_ITEMS) != 10:
        raise AssertionError("梦幻宝石测试皮肤必须恰好有十个元素")
    if len({item.resource_id for item in DREAM_GEM_ITEMS}) != len(DREAM_GEM_ITEMS):
        raise AssertionError("同一贴纸皮肤不能含重复资源 ID")
    return StickerSkinDecision(
        seed=seed,
        skin_id=SKIN_ID,
        skin_name=SKIN_NAME,
        items=DREAM_GEM_ITEMS,
        duration_seconds=duration_seconds,
    )


def _asset_path(user_data_root: Path, item: StickerSkinItem) -> Path:
    return user_data_root / "Cache" / "artistEffect" / item.resource_id / item.payload_md5


def _material(item: StickerSkinItem, decision: StickerSkinDecision, user_data_root: Path) -> dict[str, Any]:
    """The native 5.9 sticker material contract validated by the probe."""
    return {
        "aigc_type": "none", "background_alpha": 1.0, "background_color": "",
        "border_color": "", "border_line_style": 0, "border_width": 0.0,
        "category_id": decision.skin_id, "category_name": decision.skin_name, "check_flag": 1,
        "combo_info": {"text_templates": []}, "cycle_setting": True,
        "formula_id": "", "global_alpha": 1.0, "has_shadow": False,
        "icon_url": item.icon_url, "id": _new_id(), "multi_language_current": "none",
        "name": item.name, "original_size": [],
        "path": _asset_path(user_data_root, item).as_posix(), "platform": "all",
        "preview_cover_url": item.icon_url,
        "radius": {"bottom_left": 0.0, "bottom_right": 0.0, "top_left": 0.0, "top_right": 0.0},
        "request_id": item.request_id, "resource_id": item.resource_id, "sequence_type": False,
        "shadow_alpha": 0.8, "shadow_angle": 0.0, "shadow_color": "",
        "shadow_distance": 0.0, "shadow_point": {"x": 0.0, "y": 0.0},
        "shadow_smoothing": 0.0,
        "shape_param": {"custom_points": [], "roundness": [], "shape_size": [], "shape_type": 0},
        "source_platform": 1, "sticker_id": item.resource_id, "sub_type": 0,
        "team_id": "", "type": "sticker", "unicode": "",
    }


def _segment(material_id: str, item: StickerSkinItem, ordinal: int) -> dict[str, Any]:
    return {
        "caption_info": None, "cartoon": False,
        "clip": {
            "alpha": item.alpha, "flip": {"horizontal": False, "vertical": False},
            "rotation": item.rotation,
            "scale": {"x": item.scale, "y": item.scale},
            "transform": {"x": item.transform_x, "y": item.transform_y},
        },
        "common_keyframes": [], "enable_adjust": False,
        "enable_color_correct_adjust": False, "enable_color_curves": True,
        "enable_color_match_adjust": False, "enable_color_wheels": True,
        "enable_lut": False, "enable_smart_color_adjust": False,
        "extra_material_refs": [], "group_id": "", "hdr_settings": None,
        "id": _new_id(), "intensifies_audio": False, "is_placeholder": False,
        "is_tone_modify": False, "keyframe_refs": [], "last_nonzero_volume": 1.0,
        "material_id": material_id, "render_index": 14_100 + ordinal,
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0, "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0},
        "reverse": False, "source_timerange": None, "speed": 1.0,
        "target_timerange": {"start": 0, "duration": FULL_DURATION_US},
        "template_id": "", "template_scene": "default", "track_attribute": 0,
        "track_render_index": 100 + ordinal,
        "uniform_scale": {"on": True, "value": item.scale}, "visible": True,
        "volume": 0.0,
    }


def _append_track09(*, content_path: Path, decision: StickerSkinDecision, user_data_root: Path) -> None:
    document: dict[str, Any] = json.loads(content_path.read_text(encoding="utf-8"))
    if any(str(track.get("name", "")).startswith("T09_STICKER_SKIN_") for track in document.get("tracks", [])):
        raise RuntimeError("目标草稿已包含 T09 贴纸皮肤，拒绝重复写入")
    # The user verified that a category item referenced this way is hydrated by
    # Jianying when first opened.  We therefore keep the exact expected cache
    # path but do not require it to be present before the native draft exists.
    materials = document.setdefault("materials", {}).setdefault("stickers", [])
    for ordinal, item in enumerate(decision.items, start=1):
        material = _material(item, decision, user_data_root)
        materials.append(material)
        document.setdefault("tracks", []).append({
            "attribute": 0, "flag": 0, "id": _new_id(), "is_default_name": False,
            "name": f"T09_STICKER_SKIN_{ordinal:02d}", "type": "sticker",
            "segments": [_segment(material["id"], item, ordinal)],
        })
    document["render_index_track_mode_on"] = True
    content_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def create_track09_sticker_skin_draft(
    *, draft_root: Path, draft_name: str, plan: T00ProjectPlan,
    source01: VideoProbe, source02: VideoProbe, source03: VideoProbe,
    photo_dir: Path, photo_cache_root: Path, user_data_root: Path | None = None,
    sticker_skin_catalog: Path | None = None,
) -> tuple[Track01Decision, Track04Decision, PhotoWallDecision, Track05Decision, Track06Decision, Track07_08Decision, StickerSkinDecision]:
    """Build a fresh native draft, then add the full-duration same-pack skin."""
    track01, track04, walls, track05, track06, effects = create_track07_08_draft(
        draft_root=draft_root, draft_name=draft_name, plan=plan, source01=source01,
        source02=source02, source03=source03, photo_dir=photo_dir,
        photo_cache_root=photo_cache_root, user_data_root=user_data_root,
    )
    catalog = load_sticker_skin_catalog(sticker_skin_catalog) if sticker_skin_catalog else None
    decision = decide_track09_sticker_skin(seed=plan.seed, duration_seconds=plan.duration_seconds, catalog=catalog)
    _append_track09(
        content_path=draft_root / draft_name / "draft_content.json", decision=decision,
        user_data_root=user_data_root or _default_user_data_root(),
    )
    return track01, track04, walls, track05, track06, effects, decision
