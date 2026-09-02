import unittest
from unittest.mock import patch
import importlib
from pathlib import Path

from server.runtime_process import com_initialized
from server.worker_registry import PRODUCTION_WORKERS


class WorkerRegistryTests(unittest.TestCase):
    def test_com_lifecycle_on_windows_worker_boundary(self):
        calls = []
        class FakeInitializer:
            def __enter__(self):
                calls.append("init")
                return self

            def __exit__(self, exception_type, exception, traceback):
                calls.append("uninit")
                return False

        fake = type("UIAutomation", (), {"UIAutomationInitializerInThread": FakeInitializer})()
        with patch("server.runtime_process.os.name", "nt"), patch.dict("sys.modules", {"uiautomation": fake}):
            with self.assertRaises(RuntimeError):
                with com_initialized():
                    calls.append("work")
                    raise RuntimeError("worker failure")
        self.assertEqual(calls, ["init", "work", "uninit"])

    def test_registry_contains_composition_worker(self):
        self.assertIn("server.final_engine.scripts.run_jianying_composition_batch", PRODUCTION_WORKERS)

    def test_composition_worker_uses_only_package_import(self):
        module = importlib.import_module("server.final_engine.scripts.generate_jianying59_composition_draft")
        self.assertEqual(module.build_plan.__module__, "server.final_engine.jianying59_final.composition")
        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from jianying59_final", source)

    def test_finished_export_preparer_uses_packaged_profile(self):
        module = importlib.import_module("server.final_engine.scripts.prepare_finished_video_export")
        self.assertEqual(module.PROFILE["canvas"], {"width": 1080, "height": 2400})
