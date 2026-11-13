from server.content_templates_http import handle


class Handler:
    def __init__(self):
        self.status = None
        self.payload = None

    def _json(self, status, payload):
        self.status = status
        self.payload = payload


def test_catalog_endpoint_lists_four_templates():
    handler = Handler()
    assert handle(handler, "GET", "/api/v3/content-templates") is True
    assert handler.status == 200
    assert len(handler.payload["templates"]) == 4


def test_preview_endpoint_returns_png_data_url_and_layout():
    handler = Handler()
    assert handle(
        handler,
        "POST",
        "/api/v3/content-templates/render-preview",
        {"template_id": "mumu-blue", "title": "靠一碗福饺，我逆风扭转人生"},
    ) is True
    assert handler.status == 200
    assert handler.payload["image_data_url"].startswith("data:image/png;base64,")
    assert handler.payload["layout"]["lines"]


def test_unknown_path_is_left_for_other_routes():
    assert handle(Handler(), "GET", "/api/v3/other") is False
