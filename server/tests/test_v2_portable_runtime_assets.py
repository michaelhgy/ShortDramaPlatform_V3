import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from server.application_resources import application_resource_path, application_resource_root
from server.final_engine.jianying59_final.visual_layers import GLOBAL_EFFECT_POOL, REAL_PHOTO_EFFECT_POOL
from server.template_engine.jianying59_template.flower_style_library import (
    bundled_flower_style_catalog_path,
    load_flower_style_catalog,
    resolve_flower_style_catalog_path,
)
from server.template_engine.jianying59_template.sticker_skin_library import (
    bundled_sticker_skin_catalog_path,
    load_sticker_skin_catalog,
    resolve_sticker_skin_catalog_path,
)


class V2PortableRuntimeAssetsTests(unittest.TestCase):
    def test_source_runtime_reads_both_project_resources(self):
        global_effects = json.loads(GLOBAL_EFFECT_POOL.read_text(encoding="utf-8"))
        photo_effects = json.loads(REAL_PHOTO_EFFECT_POOL.read_text(encoding="utf-8"))
        self.assertEqual(len(global_effects["effects"]), 27)
        self.assertEqual(len(photo_effects["effects"]), 13)

    def test_template_catalogues_use_bundled_base_when_this_machine_has_no_override(self):
        missing = Path(r"C:\fresh-machine\missing.json")
        with patch("server.template_engine.jianying59_template.sticker_skin_library.default_sticker_skin_catalog_path", return_value=missing), \
             patch("server.template_engine.jianying59_template.flower_style_library.default_flower_style_catalog_path", return_value=missing):
            self.assertEqual(resolve_sticker_skin_catalog_path(), bundled_sticker_skin_catalog_path())
            self.assertEqual(resolve_flower_style_catalog_path(), bundled_flower_style_catalog_path())
        self.assertEqual(31, len(load_sticker_skin_catalog(bundled_sticker_skin_catalog_path()).skins))
        self.assertEqual(808, len(load_flower_style_catalog(bundled_flower_style_catalog_path()).styles))

    def test_portable_spec_collects_both_template_catalogues(self):
        spec = (Path(__file__).resolve().parents[2] / "packaging" / "v2_portable.spec").read_text(encoding="utf-8")
        self.assertIn("sticker_skin_catalog.json", spec)
        self.assertIn("flower_style_catalog.json", spec)

    def test_portable_spec_includes_wechat_index_capture_runtime(self):
        root = Path(__file__).resolve().parents[2]
        spec = (root / "packaging" / "v2_portable.spec").read_text(encoding="utf-8")
        launcher = (root / "tools" / "run_v2_desktop.py").read_text(encoding="utf-8")
        self.assertIn('"mitmproxy"', spec)
        self.assertIn("wechat_index_proxy_addon.py", spec)
        self.assertIn("--run-wechat-index-capture", launcher)

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
