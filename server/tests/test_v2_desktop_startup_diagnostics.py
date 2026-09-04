import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


LAUNCHER_PATH = Path(__file__).resolve().parents[2] / "tools" / "run_v2_desktop.py"
SPEC = importlib.util.spec_from_file_location("v2_desktop_launcher_for_test", LAUNCHER_PATH)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class DesktopStartupDiagnosticsTests(unittest.TestCase):
    def test_startup_failure_writes_a_local_log_and_shows_a_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            message_box = Mock()
            fake_windll = SimpleNamespace(user32=SimpleNamespace(MessageBoxW=message_box))
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}, clear=False), patch.object(launcher.ctypes, "windll", fake_windll, create=True):
                launcher.report_startup_failure(RuntimeError("测试启动错误"))
            log_path = Path(directory) / "ShortDramaPlatformV2" / "logs" / "desktop-startup.log"
            self.assertIn("测试启动错误", log_path.read_text(encoding="utf-8"))
            self.assertEqual("V2 启动失败", message_box.call_args.args[2])
            self.assertIn(str(log_path), message_box.call_args.args[1])
