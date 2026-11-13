"""Collect exactly the portable V3 runtime libraries; no business or lab output."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

LAB = Path("tools/ffmpeg_overlay_lab")


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def collect(root):
    root = Path(root).resolve()
    paths = {}

    def add(relative, expected=None):
        p = (root / relative).resolve()
        if not p.is_relative_to(root) or not p.is_file():
            raise ValueError(f"Missing or unsafe runtime resource: {relative}")
        name = p.relative_to(root).as_posix()
        if name not in paths:
            paths[name] = {"path": name, "bytes": p.stat().st_size, "sha256": digest(p)}
        if expected and paths[name]["sha256"].lower() != expected.lower():
            raise ValueError(f"Runtime resource changed: {relative}")

    def read(relative):
        add(relative)
        return json.loads((root / relative).read_text(encoding="utf-8"))

    st = LAB / "sticker_library/v1_20261018"
    inventory = read(st / "inventory.json")
    read(st / "sources/usable_catalog.json")
    read(st / "sources/motion_reference.json")
    for item in inventory["resources"].values():
        add(st / item["normalized_poster"], item["poster_sha256"])
        if item.get("native_cache"):
            add(st / item["native_cache"], item["native_cache_sha256"])
    fx = LAB / "effect_library/v1_20261018"
    full = LAB / "fullscreen_stickers/v1_20261025"
    overlay = read(full / "catalog.json")
    add(full / '素材总览.html')
    add(full / 'selection.json')
    for item in overlay['assets']:
        add(full / item['file'], item['id'])
    effects = read(fx / "catalog.json")
    read(fx / "rules.json")
    for item in effects["assets"]:
        for layer in item["layers"]:
            add(fx / layer["file"], layer.get("sha256"))
        bg = item.get("background") or {}
        if bg.get("layer"):
            add(fx / bg["layer"]["file"], bg["layer"].get("sha256"))
        if bg.get("lut"):
            add(fx / bg["lut"])
    edge = LAB / "side_strip_library/v1_20261019"
    borders = read(edge / "catalog.json")
    for item in borders["assets"]:
        add(edge / item["file"], item["sha256"])
    # template_cache reads these physical sources for its saved renderer contract;
    # library.py also dynamically imports template_cache.py by path.
    for name in ("sticker_layer.py", "sticker_library/library.py",
                 "sticker_library/template_cache.py", "effect_library/library.py",
                 "side_strip_library/library.py"):
        add(LAB / name)
    return {
        "schema_version": 1,
        "counts": {"sticker_families": len(inventory["families"]),
                   "stickers": len(inventory["resources"]),
                   "fullscreen_stickers": len(overlay['assets']),
                   "effect_types": len(effects["effects"]),
                   "effect_variants": len(effects["assets"]),
                   "borders": len(borders["assets"])},
        "files": sorted(paths.values(), key=lambda x: x["path"]),
        "total_bytes": sum(x["bytes"] for x in paths.values()),
    }


def verify(root, manifest):
    root = Path(root).resolve()
    for item in manifest["files"]:
        p = (root / item["path"]).resolve()
        if (not p.is_relative_to(root) or not p.is_file()
                or p.stat().st_size != item["bytes"] or digest(p) != item["sha256"]):
            raise ValueError(f"Bundled runtime resource failed verification: {item['path']}")
    return manifest["counts"]
