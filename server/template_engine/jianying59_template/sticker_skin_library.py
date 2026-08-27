"""Current Jianying 5.9 sticker-skin catalogue and controlled layout rules.

The product definition is deliberately simple: a sticker skin is one category
under Jianying's ``贴纸 -> 贴纸素材`` panel.  Synchronisation is *A = B*: every
eligible category currently present in that panel becomes one skin, and a
removed category disappears on the next sync.  The generated catalogue is a
local runtime file, never a hand-maintained project asset.

Only collection categories whose children are ordinary sticker resources are
eligible.  Built-in navigation entries such as 收藏 / 热门 / AI贴纸 do not enter
the library.  A skin is one coherent source collection; a generated template
never mixes resources from different skins.
"""

from __future__ import annotations

import json
import os
import random
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MGET_ITEM_URL = "https://lv-api-sinfonlinea.ulikecam.com/artist/v1/effect/mget_item"
SYSTEM_CATEGORY_NAMES = frozenset({"收藏", "热门", "AI贴纸", "最新"})
CATALOG_SCHEMA_VERSION = 1


def default_user_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("未找到 LOCALAPPDATA，无法定位剪映 5.9 本地目录")
    return Path(local_app_data) / "JianyingPro" / "User Data"


def default_sticker_skin_catalog_path() -> Path:
    """Return the user-local runtime catalogue location, never a project path."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("未找到 LOCALAPPDATA，无法定位贴纸皮肤库")
    return Path(local_app_data) / "ShortDramaPlatform" / "jianying59" / "sticker_skin_catalog.json"


def _catalog_params() -> dict[str, str]:
    """Parameters observed from the installed 5.9 client metadata path."""
    return {
        "effect_sdk_version": "16.4.0", "channel": "jianyingpro_0", "aid": "3704",
        "opengl_version": "3.3", "device_id": "1", "cpu": "windows", "version_name": "5.9.0",
        "language": "zh-Hans", "region": "CN", "version_code": "5.9.0", "device_platform": "windows",
        "biz_id": "2", "subdivision_id": "", "gpu": "windows", "version_code_num": "329984", "device_type": "x86_64",
    }


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _mget(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read only 5.9 collection/resource metadata; never download a payload."""
    request = urllib.request.Request(
        f"{MGET_ITEM_URL}?{urllib.parse.urlencode(_catalog_params())}",
        data=json.dumps({"items": items}, ensure_ascii=False).encode("utf-8"),
        headers={
            "User-Agent": "JianyingPro/5.9.0.11632 (Windows)",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("ret") != "0":
        raise RuntimeError(f"剪映 5.9 贴纸目录读取失败：{payload.get('ret')} {payload.get('errmsg')}")
    rows = payload.get("data", {}).get("effect_item_list")
    if not isinstance(rows, list):
        raise RuntimeError("剪映 5.9 未返回贴纸目录")
    return rows


def _load_sticker_panel_categories(user_data_root: Path) -> list[dict[str, Any]]:
    """Read the latest locally cached *sticker* panel, with no GUI operation."""
    import sqlite3

    database = user_data_root / "Cache" / "rp.db"
    if not database.is_file():
        raise FileNotFoundError(f"未找到剪映 5.9 本地资源目录：{database}")
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            "select id, response_body from http_cache where url like '%panel/get_panel_info%' order by id desc"
        ).fetchall()
    finally:
        connection.close()
    candidates: list[tuple[int, list[dict[str, Any]]]] = []
    for row_id, raw in rows:
        try:
            payload = json.loads(raw)
            data = payload.get("data") or {}
            categories = data.get("categories")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(categories, list):
            continue
        visible = [item for item in categories if isinstance(item, dict)]
        # A manually-added sticker collection is a very large numeric ID and
        # has category_source=2.  This separates the real sticker panel from
        # flower/filter/text pages without embedding an opaque panel token.
        collection_count = sum(1 for item in visible if len(_text(item.get("category_id"))) >= 16)
        if collection_count >= 3:
            candidates.append((int(row_id), visible))
    if candidates:
        # The most recently cached valid **sticker** panel is the UI truth.
        # Generic text-template panels can also contain big category IDs, but
        # their names expose textual categories (片头标题 / 水印 / 长文本 etc.).
        sticker_like = [
            candidate for candidate in candidates
            if not {"片头标题", "时间地点", "水印", "手写字", "长文本"}.intersection(
                {_text(item.get("category_name")) for item in candidate[1]}
            )
        ]
        chosen = sticker_like or candidates
        return max(chosen, key=lambda item: item[0])[1]
    raise RuntimeError("当前本机缓存里没有可识别的剪映 5.9 贴纸素材分类；请先在剪映中打开一次贴纸素材列表")


@dataclass(frozen=True)
class StickerResource:
    resource_id: str
    payload_md5: str
    name: str
    request_id: str
    icon_url: str
    preview_cover_url: str


@dataclass(frozen=True)
class StickerVisualRoles:
    """Image-derived roles for one skin; resource metadata alone is not enough."""

    focus: tuple[str, ...]
    support: tuple[str, ...]
    accent: tuple[str, ...]
    edge: tuple[str, ...]

    def usable_for_template(self) -> bool:
        """A skin needs a readable anchor, support and detail.

        The old 2/2/2 threshold existed only because the probe always wrote ten
        stickers.  The product rule is now two non-empty visual groups, whose
        final instance count is decided by the composition plan.
        """
        return bool(self.focus) and bool(self.support) and bool(self.accent or self.edge)


@dataclass(frozen=True)
class StickerSkin:
    skin_id: str
    skin_name: str
    resources: tuple[StickerResource, ...]
    visual_roles: StickerVisualRoles | None = None


@dataclass(frozen=True)
class StickerSkinCatalog:
    schema_version: int
    source: str
    synced_at: str
    skins: tuple[StickerSkin, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resource_from_detail(detail: dict[str, Any]) -> StickerResource | None:
    common = detail.get("common_attr") if isinstance(detail, dict) else None
    if not isinstance(common, dict):
        return None
    resource_id = _text(common.get("id") or common.get("resource_id") or common.get("effect_id"))
    payload_md5 = _text(common.get("md5"))
    if not resource_id or not payload_md5:
        return None
    cover = common.get("cover_url") if isinstance(common.get("cover_url"), dict) else {}
    return StickerResource(
        resource_id=resource_id,
        payload_md5=payload_md5,
        name=_text(common.get("title")) or resource_id,
        request_id=_text(common.get("request_id")),
        icon_url=_text(cover.get("static_img") or cover.get("small")),
        preview_cover_url=_text(cover.get("static_img") or cover.get("small")),
    )


def _skin_from_category(category: dict[str, Any]) -> StickerSkin | None:
    skin_id = _text(category.get("category_id"))
    skin_name = _text(category.get("category_name"))
    if not skin_id or not skin_name or skin_name in SYSTEM_CATEGORY_NAMES:
        return None
    parents = _mget([{"id": skin_id, "effect_type": 102, "source": 1}])
    if not parents:
        return None
    collection = parents[0].get("collection") if isinstance(parents[0], dict) else None
    children = collection.get("resources") if isinstance(collection, dict) else None
    if not isinstance(children, list) or not children:
        return None
    # Sticker collection children are type 2.  Other panel concepts (for
    # example text-template groups) use other types and must not leak in.
    sticker_children = [
        {"id": _text(child.get("id")), "effect_type": int(child.get("effect_type") or 0), "source": int(child.get("source") or 1)}
        for child in children if isinstance(child, dict) and _text(child.get("id")) and int(child.get("effect_type") or 0) == 2
    ]
    if not sticker_children:
        return None
    details = _mget(sticker_children)
    resources = tuple(sorted(
        (resource for resource in (_resource_from_detail(item) for item in details) if resource is not None),
        key=lambda item: item.resource_id,
    ))
    if not resources:
        return None
    return StickerSkin(skin_id=skin_id, skin_name=skin_name, resources=resources)


def sync_sticker_skin_catalog(*, user_data_root: Path | None = None) -> StickerSkinCatalog:
    """Build A=B from the current local sticker categories and their children."""
    root = user_data_root or default_user_data_root()
    skins = [skin for skin in (_skin_from_category(category) for category in _load_sticker_panel_categories(root)) if skin]
    if not skins:
        raise RuntimeError("没有同步到可用贴纸皮肤；当前贴纸素材分类可能尚未加载完成")
    return StickerSkinCatalog(
        schema_version=CATALOG_SCHEMA_VERSION,
        source="jianying59_current_sticker_material_categories_A_equals_B",
        synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        skins=tuple(sorted(skins, key=lambda item: item.skin_id)),
    )


def write_sticker_skin_catalog(*, catalog: StickerSkinCatalog, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)


def load_sticker_skin_catalog(path: Path) -> StickerSkinCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise RuntimeError(f"不支持的贴纸皮肤库版本：{payload.get('schema_version')}")
    skins = []
    for item in payload.get("skins") or []:
        resources = tuple(StickerResource(**resource) for resource in item.get("resources") or [])
        if len(resources) < 4:
            continue
        raw_roles = item.get("visual_roles") if isinstance(item.get("visual_roles"), dict) else None
        roles = None if raw_roles is None else StickerVisualRoles(
            focus=tuple(_text(value) for value in raw_roles.get("focus") or []),
            support=tuple(_text(value) for value in raw_roles.get("support") or []),
            accent=tuple(_text(value) for value in raw_roles.get("accent") or []),
            edge=tuple(_text(value) for value in raw_roles.get("edge") or []),
        )
        skins.append(StickerSkin(skin_id=_text(item.get("skin_id")), skin_name=_text(item.get("skin_name")), resources=resources, visual_roles=roles))
    if not skins:
        raise RuntimeError("贴纸皮肤库中没有至少含 8 个资源的皮肤；请重新同步")
    return StickerSkinCatalog(
        schema_version=CATALOG_SCHEMA_VERSION,
        source=_text(payload.get("source")), synced_at=_text(payload.get("synced_at")),
        skins=tuple(skins),
    )


@dataclass(frozen=True)
class StickerPlacement:
    role: str
    transform_x: float
    transform_y: float
    scale: float
    rotation: float
    alpha: float = 1.0


def _role_resources(skin: StickerSkin) -> dict[str, list[StickerResource]]:
    by_id = {resource.resource_id: resource for resource in skin.resources}
    roles = skin.visual_roles
    if roles is None:
        ordered = list(skin.resources)
        third = max(1, len(ordered) // 3)
        return {
            "main": ordered[:third],
            "support": ordered[third:third * 2] or ordered[:third],
            "accent": ordered[third * 2:] or ordered,
            "edge": ordered[third * 2:] or ordered,
        }
    return {
        "main": [by_id[item] for item in roles.focus if item in by_id],
        "support": [by_id[item] for item in roles.support if item in by_id],
        "accent": [by_id[item] for item in roles.accent if item in by_id],
        "edge": [by_id[item] for item in roles.edge if item in by_id],
    }


def _bounded(value: float, low: float, high: float) -> float:
    return round(max(low, min(high, value)), 6)


_LEGACY_LEFT_HEAVY_ANCHORS: tuple[tuple[str, float, float], ...] = (
    ("main", -0.82, 0.86),
    ("support", -0.58, 0.96),
    ("accent", -0.97, 0.74),
    ("accent", -0.34, 0.88),
    ("accent", -0.12, 0.98),
    ("support", 0.78, 0.89),
    ("accent", 0.52, 0.99),
    ("accent", 0.98, 0.77),
)

_LEGACY_ROLE_SCALE = {
    "main": (0.70, 0.86),
    "support": (0.42, 0.60),
    "accent": (0.18, 0.36),
}

_LEGACY_ROLE_ALPHA = {
    "main": (0.90, 1.00),
    "support": (0.82, 0.96),
    "accent": (0.62, 0.86),
}


def _legacy_region_placements(*, prefix: str, heavy_side: str, upper: bool, central_window_boundary_ratio: float, rng: random.Random) -> tuple[StickerPlacement, ...]:
    """Port completed legacy T15-T30 placement to native 5.9 materials.

    Source: ``scripts/add_portrait_frame_stickers_test.py`` and the frozen
    T15-T30 action rule.  Each wall has eight slots, arranged as a five-item
    heavy side plus a three-item light side.  Only the resource source changed
    for 5.9; scale, alpha, rotation and anchor ranges are retained.
    """
    if not 0.0 < central_window_boundary_ratio < 1.0:
        raise ValueError("central_window_boundary_ratio must be within (0, 1)")
    result = []
    for ordinal, (role, x, y) in enumerate(_LEGACY_LEFT_HEAVY_ANCHORS, start=1):
        if heavy_side == "right":
            x = -x
        if not upper:
            y = -y
        x = _bounded(x + rng.uniform(-0.019, 0.019), -1.0, 1.0)
        y = _bounded(y + rng.uniform(-0.005, 0.005), -1.0, 1.0)
        result.append(StickerPlacement(
            role=f"{prefix}_{ordinal:02d}_{role}",
            transform_x=x,
            transform_y=y,
            scale=round(rng.uniform(*_LEGACY_ROLE_SCALE[role]), 6),
            rotation=round(rng.uniform(-8.0, 8.0), 3),
            alpha=round(rng.uniform(*_LEGACY_ROLE_ALPHA[role]), 6),
        ))
    return tuple(result)


def choose_skin_and_layout(*, catalog: StickerSkinCatalog, seed: int, count: int | None = None, blessing_anchor: tuple[float, float] | None = None, drama_anchor: tuple[float, float] | None = None, central_window_boundary_ratio: float = 0.70) -> tuple[StickerSkin, tuple[tuple[StickerResource, StickerPlacement], ...]]:
    """Choose one 5.9 skin and apply the original sixteen-slot T15-T30 plan."""
    eligible = tuple(
        skin for skin in catalog.skins
        if len(skin.resources) >= 16 and (skin.visual_roles is None or skin.visual_roles.usable_for_template())
    )
    if not eligible:
        raise RuntimeError("没有可组成两个视觉小组的贴纸皮肤；请同步或分析贴纸素材分类")
    rng = random.Random(f"{seed}:sticker-skin")
    skin = rng.choice(eligible)
    resources = list(skin.resources)
    rng.shuffle(resources)
    top_heavy_side = "left" if rng.randrange(2) == 0 else "right"
    placements = _legacy_region_placements(
        prefix="top", heavy_side=top_heavy_side, upper=True,
        central_window_boundary_ratio=central_window_boundary_ratio, rng=rng,
    )
    placements += _legacy_region_placements(
        prefix="bottom", heavy_side="right" if top_heavy_side == "left" else "left", upper=False,
        central_window_boundary_ratio=central_window_boundary_ratio, rng=rng,
    )
    chosen = list(zip(resources[:16], placements, strict=True))
    if count is not None:
        if count <= 0:
            raise ValueError("count must be positive")
        chosen = chosen[:count]
    return skin, tuple(chosen)

    # Kept below only until the next cleanup pass so dirty-worktree history is
    # easy to review.  The return above is the active legacy T15-T30 planner.
    pools = _role_resources(skin)
    if not pools["main"] or not pools["support"]:
        raise RuntimeError(f"贴纸皮肤 {skin.skin_name} 没有足以形成主体和辅体的元素")
    composition = decide_visual_composition(seed=seed)
    placements = _cluster_placements(prefix="top", side=composition.top_focus_side, upper=True, weight=composition.top_weight, text_anchor=blessing_anchor, central_window_boundary_ratio=central_window_boundary_ratio, rng=rng)
    placements += _cluster_placements(prefix="bottom", side=composition.bottom_focus_side, upper=False, weight=composition.bottom_weight, text_anchor=drama_anchor, central_window_boundary_ratio=central_window_boundary_ratio, rng=rng)
    chosen: list[tuple[StickerResource, StickerPlacement]] = []
    used: set[str] = set()
    for placement in placements:
        role = placement.role.rsplit("_", 1)[-1]
        # ``spread`` is a placement role, not a new asset taxonomy: it uses
        # the skin's small accent elements to extend the focal pair across a
        # photo wall.
        pool = pools.get(role) or pools["accent"] or pools["support"]
        unique = [item for item in pool if item.resource_id not in used]
        resource = rng.choice(unique or pool)
        if resource.resource_id in used and role in {"main", "support"}:
            alternatives = [item for item in skin.resources if item.resource_id not in used]
            if not alternatives:
                raise RuntimeError(f"贴纸皮肤 {skin.skin_name} 缺少不重复的主/辅元素")
            resource = rng.choice(alternatives)
        used.add(resource.resource_id)
        chosen.append((resource, placement))
    if count is not None:
        if count <= 0:
            raise ValueError("count must be positive")
        chosen = chosen[:count]
    return skin, tuple(chosen)
