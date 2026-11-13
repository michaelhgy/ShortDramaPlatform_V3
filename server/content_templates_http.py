from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from http import HTTPStatus

from .content_template_renderer import TEMPLATE_SPECS, render_full_preview, render_overlay


BASE = "/api/v3/content-templates"


def _catalog() -> dict[str, object]:
    return {
        "templates": [
            {
                "id": spec.id,
                "name": spec.name,
                "title_box": list(spec.title_box),
                "title_max_size": spec.title_max_size,
                "title_min_size": spec.title_min_size,
            }
            for spec in TEMPLATE_SPECS.values()
        ],
        "title_policy": "单行自动缩小，无法单行容纳时按标点换两行，仍无法容纳则返回错误",
    }


def handle(handler, method: str, path: str, payload: dict | None = None) -> bool:
    if not path.startswith(BASE):
        return False
    try:
        if method == "GET" and path == BASE:
            handler._json(HTTPStatus.OK, _catalog())
            return True
        if method == "POST" and path == BASE + "/render-preview":
            body = payload or {}
            template_id = str(body.get("template_id") or "").strip()
            title = str(body.get("title") or "").strip()
            if not template_id or not title:
                raise ValueError("模板编号和剧名不能为空")
            with tempfile.TemporaryDirectory(prefix="v3-content-template-") as folder:
                preview = render_full_preview(template_id, title, Path(folder) / "preview.png")
                overlay = render_overlay(template_id, title, Path(folder) / "overlay.png")
                image = Path(preview["output"]).read_bytes()
                overlay_image = Path(overlay["output"]).read_bytes()
            result = preview
            result["image_data_url"] = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
            result["overlay_image_data_url"] = "data:image/png;base64," + base64.b64encode(overlay_image).decode("ascii")
            result.pop("output", None)
            handler._json(HTTPStatus.OK, result)
            return True
        handler._json(HTTPStatus.NOT_FOUND, {"error": "内容模板接口不存在"})
    except Exception as exc:
        handler._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    return True
