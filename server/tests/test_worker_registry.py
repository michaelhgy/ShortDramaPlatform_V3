import unittest
from unittest.mock import patch
import importlib

from server.runtime_process import com_initialized
from server.worker_registry import PRODUCTION_WORKERS


class WorkerRegistryTests(unittest.TestCase):
    def test_com_lifecycle_on_windows_worker_boundary(self):
        calls = []
        fake = type("PythonCom", (), {"CoInitialize": lambda self: calls.append("init"), "CoUninitialize": lambda self: calls.append("uninit")})()
        with patch("server.runtime_process.os.name", "nt"), patch.dict("sys.modules", {"pythoncom": fake}):
            with self.assertRaises(RuntimeError):
                with com_initialized():
                    calls.append("work")
                    raise RuntimeError("worker failure")
        self.assertEqual(calls, ["init", "work", "uninit"])

    def test_registry_contains_composition_worker(self):
        self.assertIn("server.final_engine.scripts.run_jianying_composition_batch", PRODUCTION_WORKERS)

    def test_finished_export_preparer_uses_packaged_profile(self):
        module = importlib.import_module("server.final_engine.scripts.prepare_finished_video_export")
        self.assertEqual(module.PROFILE["canvas"], {"width": 1080, "height": 2400})
