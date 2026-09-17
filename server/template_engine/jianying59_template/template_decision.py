"""The one deterministic plan for a native Jianying 5.9 template draft.

Planning is intentionally separate from writing.  A writer receives this
complete object and only serialises already chosen values; it must never choose
another sticker, flower style, position, effect or random parameter midway
through the draft write.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .flower_style_library import FlowerStyleCatalog, load_flower_style_catalog
from .project_base import T00ProjectPlan, VideoProbe
from .sticker_skin_library import StickerSkinCatalog, load_sticker_skin_catalog
from .track01 import Track01Decision, decide_track01
from .track02_03 import PhotoWallDecision, normalize_three_four_photos, decide_photo_walls
from .track09_sticker_skin import StickerSkinDecision, decide_track09_sticker_skin
from .track10_11_flower_text import FlowerTextDecision, decide_flower_text
from .visual_composition import VisualComposition, decide_visual_composition


@dataclass(frozen=True)
class TemplateDecision:
    """All controlled-random choices needed to write one 180-second draft."""

    plan: T00ProjectPlan
    composition: VisualComposition
    track01: Track01Decision
    photo_walls: PhotoWallDecision
    stickers: StickerSkinDecision
    flower_text: FlowerTextDecision

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def build_template_decision(
    *,
    plan: T00ProjectPlan,
    source01: VideoProbe,
    photo_dir: Path,
    photo_cache_root: Path,
    sticker_skin_catalog: Path,
    flower_style_catalog: Path,
    blessing_pool: tuple[str, ...] = (),
    drama_prompt_pool: tuple[str, ...] = (),
) -> TemplateDecision:
    """Resolve every decision before a native draft is created or changed."""
    if plan.duration_seconds != 180:
        raise ValueError("native template contract requires exactly 180 seconds")
    stickers_catalog: StickerSkinCatalog = load_sticker_skin_catalog(sticker_skin_catalog)
    flowers_catalog: FlowerStyleCatalog = load_flower_style_catalog(flower_style_catalog)
    photos = normalize_three_four_photos(photo_dir=photo_dir, cache_root=photo_cache_root)
    track01 = decide_track01(seed=plan.seed, source=source01)
    walls = decide_photo_walls(seed=plan.seed, track01=track01, photos=photos)
    flower_text = decide_flower_text(
        seed=plan.seed,
        duration_seconds=plan.duration_seconds,
        central_window_boundary_ratio=track01.canvas_height_ratio,
        flower_style_catalog=flower_style_catalog,
        blessing_pool=blessing_pool,
        drama_prompt_pool=drama_prompt_pool,
    )
    stickers = decide_track09_sticker_skin(
        seed=plan.seed,
        duration_seconds=plan.duration_seconds,
        catalog=stickers_catalog,
        blessing_anchor=flower_text.blessing_position,
        drama_anchor=flower_text.drama_prompt_position,
        central_window_boundary_ratio=track01.canvas_height_ratio,
    )
    # Loading the catalogue above is deliberate preflight.  The choice helper
    # consumes the same on-disk catalogue and performs no resource sync/network
    # operation.  Keep this local binding so accidental removal is observable.
    if not flowers_catalog.styles:
        raise RuntimeError("flower style catalogue is empty")
    return TemplateDecision(
        plan=plan,
        composition=decide_visual_composition(seed=plan.seed),
        track01=track01,
        photo_walls=walls,
        stickers=stickers,
        flower_text=flower_text,
    )
