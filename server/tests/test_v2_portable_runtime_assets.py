import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from server.application_resources import application_resource_path, application_resource_root
from server.final_engine.jianying59_final.visual_layers import GLOBAL_EFFECT_POOL, REAL_PHOTO_EFFECT_POOL


class V2PortableRuntimeAssetsTests(unittest.TestCase):
    def test_source_runtime_reads_both_project_resources(self):
        global_effects = json.loads(GLOBAL_EFFECT_POOL.read_text(encoding="utf-8"))
        photo_effects = json.loads(REAL_PHOTO_EFFECT_POOL.read_text(encoding="utf-8"))
        self.assertEqual(len(global_effects["effects"]), 27)
        self.assertEqual(len(photo_effects["effects"]), 13)

    def test_frozen_resource_root_uses_meipass_not_source_checkout(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", r"C:\portable\_internal", create=True):
            self.assertEqual(application_resource_root(), Path(r"C:\portable\_internal"))
            self.assertEqual(
                application_resource_path("server", "resource.json"),
                Path(r"C:\portable\_internal\server\resource.json"),
            )

    def test_formal_ffmpeg_paths_use_no_window_helper(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "v2_file_service.py",
            "final_engine/jianying59_final/composition.py",
            "final_engine/scripts/prepare_clean_viral_proxy.py",
            "final_engine/scripts/detect_black_bars.py",
            "final_engine/scripts/register_ready_bgm.py",
            "template_engine/jianying59_template/project_base.py",
            "template_engine/jianying59_template/photo_prep.py",
        ):
            self.assertIn("no_window_kwargs", (root / relative).read_text(encoding="utf-8"), relative)

    def test_formal_composition_workers_have_no_bare_sibling_fallback(self):
        root = Path(__file__).resolve().parents[1] / "final_engine" / "scripts"
        for name in ("prepare_clean_viral_proxy.py", "run_jianying_composition_batch.py"):
            source = (root / name).read_text(encoding="utf-8")
            self.assertNotIn("from detect_black_bars import", source, name)
            self.assertNotIn("from ollama_local import", source, name)
