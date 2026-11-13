import base64
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


LAUNCHER_PATH = Path(__file__).resolve().parents[2] / "tools" / "run_v2_desktop.py"
SPEC = importlib.util.spec_from_file_location("v3_desktop_api_for_test", LAUNCHER_PATH)
assert SPEC and SPEC.loader
desktop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(desktop)


class V3DesktopApiTests(TestCase):
    def test_save_png_uses_native_save_dialog_and_writes_selected_file(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "封面.png"
            window = SimpleNamespace(create_file_dialog=lambda *args, **kwargs: [str(target)])
            webview = SimpleNamespace(SAVE_DIALOG="save", windows=[window])
            with patch.dict(sys.modules, {"webview": webview}):
                result = desktop.DesktopApi().save_png("data:image/png;base64," + base64.b64encode(png).decode(), "封面")
            self.assertTrue(result["saved"])
            self.assertEqual(png, target.read_bytes())

    def test_save_png_cancel_does_not_create_file(self):
        window = SimpleNamespace(create_file_dialog=lambda *args, **kwargs: [])
        webview = SimpleNamespace(SAVE_DIALOG="save", windows=[window])
        with patch.dict(sys.modules, {"webview": webview}):
            result = desktop.DesktopApi().save_png("data:image/png;base64," + base64.b64encode(b"png").decode())
        self.assertEqual({"saved": False, "canceled": True}, result)

    def test_save_png_rejects_non_png_payload(self):
        with self.assertRaisesRegex(ValueError, "格式无效"):
            desktop.DesktopApi().save_png("data:text/plain;base64,QQ==")
