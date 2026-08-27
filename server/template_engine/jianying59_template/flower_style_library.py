"""Local Jianying 5.9 flower-text catalogue, sourced from cached UI metadata.

This is deliberately a *category-level* library.  It reads the categories the
user approved in Jianying's 花字 panel and automatically records *every*
resource listed in those categories.  ``cached`` is an availability state,
not a membership filter: a resource absent from the current cache remains in
the catalogue so the next sync can accurately show the category's full
contents.  It never asks a user to curate individual styles and never
downloads a resource by itself.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sticker_skin_library import default_user_data_root


SCHEMA_VERSION = 1
ALLOWED_CATEGORY_NAMES = frozenset({"发光", "渐变", "纹理", "红色", "黄色", "黑白", "蓝色", "粉色", "绿色", "紫色"})
REJECTED_NAME_TOKENS = ("电商", "促销", "带货", "节日", "春节", "圣诞", "美食", "游戏", "故障", "综艺", "口播", "水印")


def default_flower_style_catalog_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("未找到 LOCALAPPDATA，无法定位花字视觉库")
    return Path(local_app_data) / "ShortDramaPlatform" / "jianying59" / "flower_style_catalog.json"


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _connect(root: Path) -> sqlite3.Connection:
    database = root / "Cache" / "rp.db"
    if not database.is_file():
        raise FileNotFoundError(f"未找到剪映 5.9 本地资源目录：{database}")
    return sqlite3.connect(database)


def _flower_category_ids(root: Path) -> dict[str, str]:
    connection = _connect(root)
    try:
        rows = connection.execute(
            "select id, response_body from http_cache where url like '%panel/get_panel_info%' order by id desc"
        ).fetchall()
    finally:
        connection.close()
    candidates: list[tuple[int, dict[str, str]]] = []
    for row_id, raw in rows:
        try:
            categories = (json.loads(raw).get("data") or {}).get("categories") or []
        except (TypeError, json.JSONDecodeError):
            continue
        found = {
            _text(item.get("category_name")): _text(item.get("category_id"))
            for item in categories if isinstance(item, dict)
            and _text(item.get("category_name")) in ALLOWED_CATEGORY_NAMES
            and _text(item.get("category_id"))
        }
        if len(found) >= 3:
            candidates.append((int(row_id), found))
    if not candidates:
        raise RuntimeError("当前本机缓存里没有可识别的花字颜色分类；请先在剪映中打开一次 花字 列表")
    return max(candidates, key=lambda item: item[0])[1]


def _color_family(tags: tuple[str, ...]) -> str:
    tag_set = set(tags)
    if tag_set & {"蓝色", "紫色"}:
        return "cool"
    if tag_set & {"粉色", "红色", "黄色"}:
        return "warm"
    if "绿色" in tag_set:
        return "fresh"
    return "neutral"


@dataclass(frozen=True)
class FlowerStyle:
    effect_id: str
    payload_md5: str
    name: str
    category_tags: tuple[str, ...]
    color_family: str
    icon_url: str
    cached: bool


@dataclass(frozen=True)
class FlowerStyleCatalog:
    schema_version: int
    source: str
    synced_at: str
    approved_categories: tuple[str, ...]
    styles: tuple[FlowerStyle, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sync_flower_style_catalog(*, user_data_root: Path | None = None) -> FlowerStyleCatalog:
    """Build a current, no-download catalogue from approved 花字 categories."""
    root = user_data_root or default_user_data_root()
    category_ids = _flower_category_ids(root)
    id_to_name = {identifier: name for name, identifier in category_ids.items()}
    connection = _connect(root)
    try:
        rows = connection.execute(
            "select response_body from http_cache where url like '%get_resources_by_category_id%flower%' order by id desc"
        ).fetchall()
    finally:
        connection.close()
    by_id: dict[str, FlowerStyle] = {}
    for (raw,) in rows:
        try:
            items = (json.loads(raw).get("data") or {}).get("effect_item_list") or []
        except (TypeError, json.JSONDecodeError):
            continue
        for item in items:
            common = item.get("common_attr") if isinstance(item, dict) else None
            if not isinstance(common, dict):
                continue
            effect_id = _text(common.get("effect_id") or common.get("id"))
            payload_md5 = _text(common.get("md5"))
            if not effect_id or not payload_md5:
                continue
            tags = tuple(sorted({id_to_name[str(identifier)] for identifier in common.get("category_ids") or [] if str(identifier) in id_to_name}))
            if not tags:
                continue
            name = _text(common.get("title")) or effect_id
            if any(token in name for token in REJECTED_NAME_TOKENS):
                continue
            cover = common.get("cover_url") if isinstance(common.get("cover_url"), dict) else {}
            cached = (root / "Cache" / "artistEffect" / effect_id / payload_md5).is_dir()
            candidate = FlowerStyle(
                effect_id=effect_id,
                payload_md5=payload_md5,
                name=name,
                category_tags=tags,
                color_family=_color_family(tags),
                icon_url=_text(cover.get("static_img") or cover.get("small")),
                cached=cached,
            )
            # Responses may overlap categories/pages.  Preserve a cached copy
            # in preference to a later metadata-only duplicate.
            existing = by_id.get(effect_id)
            if existing is None or (candidate.cached and not existing.cached):
                by_id[effect_id] = candidate
    # Category membership is the source of truth.  Do not drop a style merely
    # because its payload has not yet been hydrated on this computer.
    styles = tuple(sorted(by_id.values(), key=lambda item: item.effect_id))
    if not styles:
        raise RuntimeError("花字分类已读取，但没有找到符合已批准分类的花字资源")
    return FlowerStyleCatalog(
        schema_version=SCHEMA_VERSION,
        source="jianying59_current_flower_color_categories_full_metadata",
        synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        approved_categories=tuple(sorted(category_ids)),
        styles=styles,
    )


def write_flower_style_catalog(*, catalog: FlowerStyleCatalog, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)


def load_flower_style_catalog(path: Path) -> FlowerStyleCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(f"不支持的花字视觉库版本：{payload.get('schema_version')}")
    styles = tuple(FlowerStyle(
        effect_id=_text(item.get("effect_id")), payload_md5=_text(item.get("payload_md5")),
        name=_text(item.get("name")), category_tags=tuple(_text(tag) for tag in item.get("category_tags") or []),
        color_family=_text(item.get("color_family")) or "neutral", icon_url=_text(item.get("icon_url")),
        cached=bool(item.get("cached")),
    ) for item in payload.get("styles") or [] if _text(item.get("effect_id")) and _text(item.get("payload_md5")))
    if not styles:
        raise RuntimeError("花字视觉库没有可用样式；请在剪映打开已批准花字分类后重新同步")
    return FlowerStyleCatalog(
        schema_version=SCHEMA_VERSION, source=_text(payload.get("source")), synced_at=_text(payload.get("synced_at")),
        approved_categories=tuple(_text(item) for item in payload.get("approved_categories") or []), styles=styles,
    )


def choose_flower_style(
    *, catalog: FlowerStyleCatalog, sticker_color_family: str, seed: int, require_cached: bool = False
) -> FlowerStyle:
    """Use colour family as a soft preference, never a manual per-style list.

    The catalogue always contains all category members.  A 5.9 draft may
    reference an unhydrated flower style: when the user opens that draft,
    Jianying downloads the payload through its own normal hydration path.
    ``cached`` is therefore diagnostic state only, not an eligibility gate.
    """
    available = tuple(style for style in catalog.styles if style.cached) if require_cached else catalog.styles
    if not available:
        availability = "已缓存" if require_cached else "已读取"
        raise RuntimeError(f"花字视觉库没有{availability}样式")
    preferred = tuple(style for style in available if style.color_family == sticker_color_family)
    candidates = preferred or available
    import random
    return random.Random(f"{seed}:flower-style:{sticker_color_family}").choice(candidates)
