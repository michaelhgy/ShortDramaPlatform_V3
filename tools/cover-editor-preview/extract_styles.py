"""Read local Jianying TextStyle assets; never writes to Jianying or business data."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


def content_types(value):
    if isinstance(value, dict):
        if "render_type" in value:
            yield value["render_type"]
        for child in value.values():
            yield from content_types(child)
    elif isinstance(value, list):
        for child in value:
            yield from content_types(child)


def main():
    cache = Path(os.environ["LOCALAPPDATA"]) / "JianyingPro/User Data/Cache/artistEffect"
    catalog_path = PROJECT / "server/template_engine/jianying59_template/resources/flower_style_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    styles = []
    for item in catalog["styles"]:
        folder = cache / item["effect_id"] / item["payload_md5"]
        source = folder / "effectStyle.json"
        if not source.is_file():
            continue
        raw = source.read_bytes()
        style = json.loads(raw)
        if set(content_types(style)) - {"solid", "gradient"}:
            continue
        # Seasonal copy is unsuitable for this first, general-purpose cover palette.
        if any(word in item["name"] for word in ("元旦", "冬至", "新年")):
            continue
        icon = folder / "cover_icon.png"
        styles.append({
            "id": item["effect_id"], "name": item["name"],
            "tags": item["category_tags"], "source": "Jianying local TextStyle",
            "sourceSha256": hashlib.sha256(raw).hexdigest(),
            "icon": "data:image/png;base64," + base64.b64encode(icon.read_bytes()).decode() if icon.is_file() else "",
            "style": style,
        })
    destination = PROJECT / "src/coverEditor/simpleFlowerStyles.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(styles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"styles": len(styles), "destination": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
