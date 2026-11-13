"""Extract the four first-version template graphics from flattened previews."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageChops


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "界面设计输入"
OUTPUT_DIR = SOURCE_DIR / "木木短剧第一版纯净模板"


SPECS = {
    "01_原版": {
        "source": "木木短剧模板预览-v1.png",
        "title_box": (235, 70, 820, 175),
        "title_polygon": [(145, 64), (855, 64), (890, 96), (853, 177), (143, 177), (109, 143)],
        "top": {
            "polygons": [
                [(33, 53), (214, 53), (216, 94), (112, 188), (70, 177), (32, 114)],
                [(145, 64), (855, 64), (890, 96), (853, 177), (143, 177), (109, 143)],
                [(69, 20), (344, 20), (337, 60), (82, 60)],
                [(107, 173), (510, 173), (490, 198), (140, 198)],
                [(783, 114), (891, 114), (874, 181), (838, 184)],
            ],
        },
        "bottom": {
            "polygons": [
                [(21, 1507), (116, 1469), (208, 1470), (535, 1530), (513, 1618), (66, 1624), (22, 1586)],
                [(64, 1491), (459, 1491), (535, 1533), (511, 1616), (70, 1618)],
                [(480, 1518), (867, 1518), (895, 1565), (868, 1607), (494, 1607)],
                [(429, 1590), (901, 1590), (874, 1647), (450, 1647)],
            ],
        },
    },
    "02_蓝": {
        "source": "木木短剧模板预览-蓝-v2.png",
        "title_box": (330, 72, 790, 148),
        "title_polygon": [(331, 69), (782, 69), (806, 78), (780, 135), (338, 135)],
        "top": {
            "polygons": [
                [(43, 76), (890, 76), (890, 80), (43, 80)],
                [(109, 49), (325, 49), (314, 83), (105, 83)],
                [(138, 82), (350, 82), (337, 112), (137, 112)],
                [(331, 69), (782, 69), (806, 78), (780, 135), (338, 135)],
                [(765, 72), (804, 72), (785, 143), (762, 143)],
            ],
        },
        "bottom": {
            "polygons": [
                [(174, 1457), (512, 1457), (543, 1482), (510, 1556), (179, 1556)],
                [(489, 1471), (760, 1471), (782, 1502), (759, 1536), (493, 1536)],
            ],
        },
    },
    "03_青": {
        "source": "木木短剧模板预览-青-v2.png",
        "title_box": (220, 78, 760, 158),
        "title_polygon": [(222, 80), (737, 80), (758, 95), (737, 151), (222, 151)],
        "top": {
            "polygons": [
                [(78, 95), (803, 95), (803, 99), (78, 99)],
                [(142, 64), (420, 64), (411, 107), (150, 107)],
                [(113, 83), (226, 83), (207, 119), (112, 119)],
                [(222, 80), (737, 80), (758, 95), (737, 151), (222, 151)],
                [(729, 88), (764, 88), (742, 148), (722, 148)],
            ],
        },
        "bottom": {
            "polygons": [
                [(158, 1452), (537, 1452), (566, 1478), (535, 1554), (159, 1554)],
                [(527, 1470), (775, 1470), (795, 1505), (775, 1534), (527, 1534)],
            ],
        },
    },
    "04_红": {
        "source": "木木短剧模板预览-红-v2.png",
        "title_box": (215, 82, 720, 160),
        "title_polygon": [(216, 84), (700, 84), (720, 97), (700, 160), (216, 160)],
        "top": {
            "polygons": [
                [(92, 76), (257, 76), (218, 133), (139, 133)],
                [(141, 62), (357, 62), (348, 96), (143, 96)],
                [(216, 84), (700, 84), (720, 97), (700, 160), (216, 160)],
                [(693, 119), (773, 119), (748, 146), (694, 146)],
                [(444, 157), (719, 157), (719, 161), (444, 161)],
            ],
        },
        "bottom": {
            "polygons": [
                [(160, 1450), (529, 1450), (556, 1479), (526, 1552), (160, 1552)],
                [(526, 1467), (745, 1467), (768, 1503), (744, 1533), (527, 1533)],
            ],
        },
    },
}


def _mask_for(source: Image.Image, spec: dict[str, object]) -> Image.Image:
    mask = Image.new("L", source.size, 0)
    draw = ImageDraw.Draw(mask)
    for rect in spec.get("rects", []):
        draw.rectangle(rect, fill=255)
    for polygon in spec.get("polygons", []):
        draw.polygon(polygon, fill=255)
    return mask


def _palette_mask(source: Image.Image) -> Image.Image:
    """Keep the template palette while dropping the drama-frame pixels."""
    rgb = source.convert("RGB")
    out = Image.new("L", source.size, 0)
    src = rgb.load()
    dst = out.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b = src[x, y]
            bright = min(r, g, b) >= 168 and max(r, g, b) - min(r, g, b) <= 48
            blue = b >= r * 1.08 and b >= g * 1.01 and b >= 42
            cyan = g >= r * 1.16 and b >= r * 1.16 and g >= 72
            purple = b >= g * 1.12 and r >= g * 1.05 and b >= 72
            red = r >= g * 1.34 and r >= b * 1.24 and r >= 78
            if bright or blue or cyan or purple or red:
                dst[x, y] = 255
    return out


def _clear_title(image: Image.Image, polygon: list[tuple[int, int]]) -> None:
    ImageDraw.Draw(image).polygon(polygon, fill=(255, 255, 255, 255))


def extract(name: str, config: dict[str, object]) -> dict[str, object]:
    source_path = SOURCE_DIR / str(config["source"])
    source = Image.open(source_path).convert("RGBA")
    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    top = _mask_for(source, config["top"])
    bottom = _mask_for(source, config["bottom"])
    geometry = ImageChops.lighter(top, bottom)
    mask = ImageChops.multiply(geometry, _palette_mask(source))
    cropped = Image.composite(source, output, mask)
    _clear_title(cropped, list(config["title_polygon"]))
    out_path = OUTPUT_DIR / f"{name}_空剧名.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path)
    return {"name": name, "source": str(source_path), "output": str(out_path), "size": list(source.size)}


def main() -> None:
    assets = [extract(name, config) for name, config in SPECS.items()]
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps({"assets": assets}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(OUTPUT_DIR), "assets": len(assets)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
