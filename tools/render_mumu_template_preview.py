"""Render the four runtime Mumu title overlays for a supplied drama title."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.content_template_renderer import available_template_ids, render_overlay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True, help="剧名")
    parser.add_argument("--output-dir", type=Path, required=True, help="透明叠层输出目录")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for template_id in available_template_ids():
        output = args.output_dir / f"{template_id}.png"
        manifest.append(render_overlay(template_id, args.title, output))
    (args.output_dir / "manifest.json").write_text(
        __import__("json").dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已生成 {len(manifest)} 个木木短剧标题叠层")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
