"""Render the Mumu short-drama title and brand overlay from a drama title."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from .application_resources import application_resource_path


FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\NotoSerifSC-VF.ttf"),
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
)


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    name: str
    panel_color: tuple[int, int, int, int]
    accent_color: tuple[int, int, int, int]
    accent_secondary: tuple[int, int, int, int]
    title_color: tuple[int, int, int, int]
    title_box: tuple[int, int, int, int]
    title_max_size: int
    title_min_size: int
    font_weight: bytes = b"SemiBold"
    letter_spacing: int = 0


TEMPLATE_SPECS = {
    "mumu-original": TemplateSpec(
        id="mumu-original",
        name="木木短剧·原版配色",
        panel_color=(255, 255, 255, 255),
        accent_color=(13, 207, 237, 255),
        accent_secondary=(143, 70, 237, 255),
        title_color=(22, 43, 73, 255),
        title_box=(235, 90, 915, 187),
        title_max_size=72,
        title_min_size=24,
        font_weight=b"SemiBold",
    ),
    "mumu-blue": TemplateSpec(
        id="mumu-blue",
        name="木木短剧·蓝色版",
        panel_color=(249, 250, 255, 255),
        accent_color=(45, 156, 244, 255),
        accent_secondary=(126, 104, 255, 255),
        title_color=(25, 53, 102, 255),
        title_box=(385, 92, 900, 166),
        title_max_size=60,
        title_min_size=22,
        font_weight=b"SemiBold",
    ),
    "mumu-cyan": TemplateSpec(
        id="mumu-cyan",
        name="木木短剧·青色版",
        panel_color=(249, 255, 255, 255),
        accent_color=(47, 214, 205, 255),
        accent_secondary=(132, 244, 232, 255),
        title_color=(22, 43, 73, 255),
        title_box=(270, 140, 920, 220),
        title_max_size=66,
        title_min_size=22,
        font_weight=b"SemiBold",
    ),
    "mumu-red": TemplateSpec(
        id="mumu-red",
        name="木木短剧·红色版",
        panel_color=(255, 252, 252, 255),
        accent_color=(244, 65, 88, 255),
        accent_secondary=(255, 176, 78, 255),
        title_color=(145, 25, 36, 255),
        title_box=(245, 135, 890, 220),
        title_max_size=62,
        title_min_size=22,
        font_weight=b"SemiBold",
    ),
}


REFERENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "界面设计输入"
ASSET_DIR = application_resource_path("server", "content_template_assets")
TEMPLATE_ASSETS = {
    "mumu-original": ASSET_DIR / "mumu-original.png",
    "mumu-blue": ASSET_DIR / "mumu-blue.png",
    "mumu-cyan": ASSET_DIR / "mumu-cyan.png",
    "mumu-red": ASSET_DIR / "mumu-red.png",
}

REFERENCE_IMAGES = {
    "mumu-original": REFERENCE_DIR / "木木短剧模板预览-v1.png",
    "mumu-blue": REFERENCE_DIR / "木木短剧模板预览-蓝-v2.png",
    "mumu-cyan": REFERENCE_DIR / "木木短剧模板预览-青-v2.png",
    "mumu-red": REFERENCE_DIR / "木木短剧模板预览-红-v2.png",
}



class TitleTooLongError(ValueError):
    pass


def available_template_ids() -> tuple[str, ...]:
    return tuple(TEMPLATE_SPECS)


def normalize_title(title: str) -> str:
    value = re.sub(r"\s+", " ", str(title or "")).strip()
    value = value.strip("《》〈〉<>\"“”‘’")
    if not value:
        raise ValueError("剧名不能为空")
    return value


def _font(size: int, weight: bytes = b"SemiBold") -> ImageFont.FreeTypeFont:
    path = next((candidate for candidate in FONT_CANDIDATES if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError("未找到可用的中文模板字体")
    font = ImageFont.truetype(str(path), size)
    if path.name == "NotoSerifSC-VF.ttf" and hasattr(font, "set_variation_by_name"):
        try:
            font.set_variation_by_name(weight)
        except OSError:
            pass
    return font


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    return box[2] - box[0], box[3] - box[1]


def _split_title(title: str) -> tuple[str, str] | None:
    for mark in ("，", ",", "：", ":", "·", "—", "-"):
        if mark in title:
            left, right = title.split(mark, 1)
            if left.strip() and right.strip():
                return left.strip() + mark, right.strip()
    midpoint = len(title) // 2
    if midpoint >= 2 and len(title) - midpoint >= 2:
        return title[:midpoint], title[midpoint:]
    return None


def fit_title(title: str, template_id: str) -> dict[str, object]:
    normalized = normalize_title(title)
    spec = TEMPLATE_SPECS[template_id]
    left, top, right, bottom = spec.title_box
    max_width = right - left - 38
    max_height = bottom - top - 18
    probe = Image.new("RGBA", (8, 8))
    draw = ImageDraw.Draw(probe)

    for size in range(spec.title_max_size, spec.title_min_size - 1, -1):
        font = _font(size, spec.font_weight)
        width, height = _text_size(draw, normalized, font)
        if width <= max_width and height <= max_height:
            return {"text": normalized, "lines": [normalized], "font_size": size, "box": spec.title_box}

    split = _split_title(normalized)
    if split:
        for size in range(spec.title_max_size, spec.title_min_size - 1, -1):
            font = _font(size, spec.font_weight)
            measurements = [_text_size(draw, line, font) for line in split]
            if max(width for width, _ in measurements) <= max_width and sum(height for _, height in measurements) + 8 <= max_height:
                return {"text": normalized, "lines": list(split), "font_size": size, "box": spec.title_box}

    raise TitleTooLongError(f"剧名过长，无法放入模板标题区域：{normalized}")


def _render_title_overlay(template_id: str, title: str, canvas: tuple[int, int]) -> tuple[Image.Image, dict[str, object]]:
    spec = TEMPLATE_SPECS[template_id]
    layout = fit_title(title, template_id)
    width, height = canvas
    scale_x = width / 1080
    scale_y = height / 1920
    asset_path = TEMPLATE_ASSETS[template_id]
    if not asset_path.is_file():
        raise FileNotFoundError(f"未找到透明模板素材：{asset_path}")
    overlay = Image.open(asset_path).convert("RGBA").resize(canvas, Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(overlay, "RGBA")

    def sx(value: int) -> int:
        return round(value * scale_x)

    def sy(value: int) -> int:
        return round(value * scale_y)

    box_left = sx(spec.title_box[0])
    box_top = sy(spec.title_box[1])
    box_right = sx(spec.title_box[2])
    box_bottom = sy(spec.title_box[3])
    lines = list(layout["lines"])
    font_size = round(int(layout["font_size"]) * scale_x)
    font = _font(font_size, spec.font_weight)
    stroke_width = max(1, round(1 * scale_x))
    line_boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width) for line in lines]
    line_sizes = [(box[2] - box[0], box[3] - box[1]) for box in line_boxes]
    line_gap = round(8 * scale_y)
    total_height = sum(size[1] for size in line_sizes) + line_gap * (len(lines) - 1)
    cursor_y = (box_top + box_bottom - total_height) // 2
    for line, (line_box, (line_width, line_height)) in zip(lines, zip(line_boxes, line_sizes)):
        cursor_x = (box_left + box_right - line_width) // 2 - line_box[0]
        draw.text(
            (cursor_x, cursor_y - line_box[1]),
            line,
            font=font,
            fill=spec.title_color,
            stroke_width=stroke_width,
            stroke_fill=(255, 255, 255, 170),
        )
        cursor_y += line_height + line_gap
    return overlay, layout


def render_full_preview(
    template_id: str,
    title: str,
    output_path: str | Path,
    canvas: tuple[int, int] = (1080, 1920),
) -> dict[str, object]:
    """Composite the transparent template asset over the reference frame for UI preview."""
    if template_id not in TEMPLATE_SPECS:
        raise ValueError(f"未知木木短剧模板：{template_id}")
    reference_path = REFERENCE_IMAGES[template_id]
    if not reference_path.is_file():
        raise FileNotFoundError(f"未找到模板预览底图：{reference_path}")
    background = Image.open(reference_path).convert("RGBA")
    background = ImageOps.fit(background, canvas, method=Image.Resampling.LANCZOS)
    # The reference images are flattened examples and contain their own title
    # and brand graphics. Use only the clean middle of the frame as a blurred
    # preview background so those old graphics cannot show through the new
    # transparent template.
    middle = background.crop((0, 260, canvas[0], 1480))
    background = middle.resize(canvas, Image.Resampling.BICUBIC)
    background = background.filter(ImageFilter.GaussianBlur(18))
    title_overlay, layout = _render_title_overlay(template_id, title, canvas)
    background.alpha_composite(title_overlay)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    background.convert("RGB").save(output, format="PNG")
    return {
        "template_id": template_id,
        "title": normalize_title(title),
        "layout": layout,
        "output": str(output),
        "canvas": list(canvas),
        "preview_kind": "full_frame",
        "reference_image": str(reference_path),
    }


def render_overlay(template_id: str, title: str, output_path: str | Path, canvas: tuple[int, int] = (1080, 1920)) -> dict[str, object]:
    if template_id not in TEMPLATE_SPECS:
        raise ValueError(f"未知木木短剧模板：{template_id}")
    overlay, layout = _render_title_overlay(template_id, title, canvas)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output)
    return {"template_id": template_id, "title": normalize_title(title), "layout": layout, "output": str(output), "canvas": list(canvas)}
