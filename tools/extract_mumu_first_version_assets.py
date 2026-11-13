"""Extract the four first-version Mumu template strips without the baked title."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "界面设计输入"
OUTPUT_DIR = SOURCE_DIR / "木木短剧第一版纯素材"

SOURCES = (
    ("01_原版", SOURCE_DIR / "木木短剧模板预览-v1.png", (0, 0, 941, 220), (235, 64, 820, 177)),
    ("02_蓝", SOURCE_DIR / "木木短剧模板预览-蓝-v2.png", (55, 35, 890, 205), (300, 66, 790, 153)),
    ("03_青", SOURCE_DIR / "木木短剧模板预览-青-v2.png", (65, 35, 850, 210), (205, 78, 770, 160)),
    ("04_红", SOURCE_DIR / "木木短剧模板预览-红-v2.png", (65, 35, 850, 210), (205, 75, 735, 160)),
)


def _is_title_pixel(r: int, g: int, b: int) -> bool:
    # The title is dark navy or red. The surrounding panel is near white.
    return max(r, g, b) < 205 or (r > g * 1.25 and r > b * 1.25 and r < 235)


def extract(name: str, source_path: Path, crop_box: tuple[int, int, int, int], title_box: tuple[int, int, int, int]) -> dict[str, object]:
    source = Image.open(source_path).convert("RGBA")
    cropped = source.crop(crop_box)
    left, top, right, bottom = title_box
    left -= crop_box[0]
    right -= crop_box[0]
    top -= crop_box[1]
    bottom -= crop_box[1]

    pixels = cropped.load()
    # Clear only the original title glyphs. The title panel and its borders stay untouched.
    for y in range(max(0, top), min(cropped.height, bottom)):
        for x in range(max(0, left), min(cropped.width, right)):
            r, g, b, a = pixels[x, y]
            if a and _is_title_pixel(r, g, b):
                pixels[x, y] = (255, 255, 255, 255)

    out_path = OUTPUT_DIR / f"{name}_空剧名.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path)
    return {
        "name": name,
        "source": str(source_path),
        "output": str(out_path),
        "source_size": list(source.size),
        "crop_box": list(crop_box),
        "title_box_in_source": list(title_box),
        "output_size": list(cropped.size),
    }


def main() -> None:
    records = [extract(*item) for item in SOURCES]
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps({"assets": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(OUTPUT_DIR), "assets": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
