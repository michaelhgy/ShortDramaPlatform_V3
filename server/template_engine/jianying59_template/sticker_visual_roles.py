"""Classify a sticker skin's elements by their visible preview geometry.

The classifier is intentionally modest: it does not claim to understand a
sticker's semantic theme.  It measures transparent bounds, visible area and
aspect ratio so the generator can distinguish likely main elements, support,
small accents and edge-like elements.  Ambiguous packs are excluded from
automatic full-template selection instead of being forced into a bad design.
"""

from __future__ import annotations

import io
import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .sticker_skin_library import StickerSkinCatalog, StickerVisualRoles, load_sticker_skin_catalog


@dataclass(frozen=True)
class StickerPreviewGeometry:
    resource_id: str
    visible_area_ratio: float
    visible_width_ratio: float
    visible_height_ratio: float
    aspect_ratio: float


def _read_geometry(url: str, resource_id: str) -> StickerPreviewGeometry:
    from PIL import Image

    if not url:
        raise RuntimeError(f"贴纸 {resource_id} 缺少预览图地址")
    request = urllib.request.Request(url, headers={"User-Agent": "ShortDramaPlatform/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()
    with Image.open(io.BytesIO(raw)).convert("RGBA") as image:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise RuntimeError(f"贴纸 {resource_id} 预览尺寸无效")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is None:
            return StickerPreviewGeometry(resource_id, 0.0, 0.0, 0.0, 1.0)
        left, top, right, bottom = bbox
        visible_width = max(1, right - left)
        visible_height = max(1, bottom - top)
        # Count actual opaque pixels rather than merely using the bounding box,
        # which keeps hollow lines/rings from masquerading as solid main art.
        nontransparent = sum(1 for value in alpha.getdata() if value >= 24)
        return StickerPreviewGeometry(
            resource_id=resource_id,
            visible_area_ratio=round(nontransparent / (width * height), 6),
            visible_width_ratio=round(visible_width / width, 6),
            visible_height_ratio=round(visible_height / height, 6),
            aspect_ratio=round(visible_width / visible_height, 6),
        )


def _roles(geometry: list[StickerPreviewGeometry]) -> StickerVisualRoles:
    # Main pieces should visibly occupy an area.  Lines/rings are held back as
    # edge candidates even if their bounding rectangle is large.
    solid = sorted((item for item in geometry if item.visible_area_ratio >= 0.12), key=lambda item: item.visible_area_ratio, reverse=True)
    focus = tuple(item.resource_id for item in solid[:4])
    support = tuple(item.resource_id for item in solid[4:12])
    edge = tuple(
        item.resource_id for item in geometry
        if (item.aspect_ratio >= 2.3 or item.aspect_ratio <= 0.43)
        and item.visible_area_ratio >= 0.015
    )
    accent = tuple(
        item.resource_id for item in sorted(geometry, key=lambda item: item.visible_area_ratio)
        if item.visible_area_ratio >= 0.008 and item.resource_id not in focus and item.resource_id not in support
    )
    # An ordinary coherent package does not have to possess a literal line or
    # border item; remaining small symbols may serve as edge connectors.
    if len(edge) < 2:
        edge = tuple(dict.fromkeys((*edge, *accent)))
    return StickerVisualRoles(focus=focus, support=support, accent=accent, edge=edge)


def analyse_sticker_skin_catalog(*, catalog: StickerSkinCatalog) -> dict[str, StickerVisualRoles]:
    results: dict[str, StickerVisualRoles] = {}
    for skin in catalog.skins:
        geometry: list[StickerPreviewGeometry] = []
        failures: list[str] = []
        for resource in skin.resources:
            try:
                geometry.append(_read_geometry(resource.icon_url or resource.preview_cover_url, resource.resource_id))
            except Exception as exc:
                failures.append(f"{resource.resource_id}:{type(exc).__name__}")
        if failures:
            raise RuntimeError(f"贴纸皮肤 {skin.skin_name} 的预览图读取不完整：{', '.join(failures[:3])}")
        results[skin.skin_id] = _roles(geometry)
    return results


def apply_visual_roles(*, catalog: StickerSkinCatalog, roles: dict[str, StickerVisualRoles]) -> StickerSkinCatalog:
    from .sticker_skin_library import StickerSkin

    return StickerSkinCatalog(
        schema_version=catalog.schema_version, source=catalog.source, synced_at=catalog.synced_at,
        skins=tuple(StickerSkin(
            skin_id=skin.skin_id, skin_name=skin.skin_name, resources=skin.resources,
            visual_roles=roles.get(skin.skin_id),
        ) for skin in catalog.skins),
    )


def write_role_report(*, catalog: StickerSkinCatalog, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "kind": "jianying59_sticker_visual_role_report",
        "skin_count": len(catalog.skins),
        "skins": [{
            "skin_id": skin.skin_id, "skin_name": skin.skin_name,
            "visual_roles": None if skin.visual_roles is None else asdict(skin.visual_roles),
            "eligible_for_full_template": bool(skin.visual_roles and skin.visual_roles.usable_for_template()),
        } for skin in catalog.skins],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
