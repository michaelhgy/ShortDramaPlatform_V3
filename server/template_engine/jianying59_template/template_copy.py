"""User-editable copy pools for the two native template text tracks.

The two pools replace the previously hard-coded blessing and drama-guide copy.
An empty pool means "do not write that text track at all".  When the user has
not created a copy file yet (or a field is absent), the bundled defaults below
keep the completed 180-second template's behaviour unchanged.

The copy file lives in the V2 system data directory so it survives code updates
and can later be read/written by a settings screen:

    <系统数据>/模板文案.json

Example content::

    {
      "blessing": ["愿您身体健康", "愿您平安喜乐"],
      "drama_prompt": ["左下角免费看全集"]
    }

An absent field falls back to the default pool; an empty array omits the track.
"""

from __future__ import annotations

import json
from pathlib import Path


SCHEMA_VERSION = 1

DEFAULT_BLESSING_COPY = (
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
DEFAULT_DRAMA_PROMPT_COPY = (
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


def clean_copy_items(value: object, field: str) -> list[str]:
    """把界面或配置文件里的一条文案池整理成字符串列表。

    空白项被丢弃（用户多敲的空行不该变成一条空文案）。**非数组必须明确报错**，
    不能静默当成空池——否则用户会以为"改了没生效"，实际是"填错了被吞掉"。
    """
    if not isinstance(value, list):
        raise ValueError(f"模板文案配置的 {field} 必须是字符串数组")
    return [str(item).strip() for item in value if str(item).strip()]


def _pool(payload: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Return the configured pool, the default, or () when explicitly emptied."""
    value = payload.get(key)
    if value is None:
        return default
    return tuple(clean_copy_items(value, key))


def load_template_copy(*, path: Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(blessing_pool, drama_prompt_pool)``.

    ``path`` may be missing: the bundled defaults are used unchanged.  A present
    file must be a JSON object with ``blessing`` and ``drama_prompt`` string
    arrays; an empty array means "omit that text track".
    """
    if path is None or not path.is_file():
        return DEFAULT_BLESSING_COPY, DEFAULT_DRAMA_PROMPT_COPY
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"模板文案配置无法解析：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("模板文案配置必须是 JSON 对象，形如 {\"blessing\": [...], \"drama_prompt\": [...]}")
    return _pool(payload, "blessing", DEFAULT_BLESSING_COPY), _pool(payload, "drama_prompt", DEFAULT_DRAMA_PROMPT_COPY)
