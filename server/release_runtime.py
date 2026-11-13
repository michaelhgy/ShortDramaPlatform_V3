"""Read-only verification for the portable V3 resource closure."""
from __future__ import annotations
import hashlib
import json
from server.tool_resolver import application_resource_root


def probe_v3_resources():
    root = application_resource_root()
    manifest = json.loads((root / "v3-resource-manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("安装包缺少资源：" + item["path"])
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != item["bytes"] or digest != item["sha256"]:
            raise ValueError("安装包资源校验失败：" + item["path"])
    # Exercise the physical-file import and renderer-contract code in frozen mode.
    from tools.ffmpeg_overlay_lab.sticker_library.library import make_batch
    from server.ffmpeg_templates.renderer import STICKERS, EFFECTS, BORDERS, read
    from tools.ffmpeg_overlay_lab.effect_library.library import make_plan as effects
    from tools.ffmpeg_overlay_lab.side_strip_library.library import make_plan as borders
    sticker = make_batch(STICKERS, 1, seed=20261020, seconds=10)["plans"][0]
    effect = effects(read(EFFECTS / "catalog.json"), read(EFFECTS / "rules.json"), 10, 20261020)
    border = borders(read(BORDERS / "catalog.json"), 20261020, width_range=[5, 10])
    return {"counts": manifest["counts"], "verified_files": len(manifest["files"]),
            "resource_root": str(root), "sticker_family": sticker["family"],
            "effect_segments": len(effect["segments"]), "border_plan": border}
