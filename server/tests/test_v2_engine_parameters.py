"""参数中心（engine parameters）的后端测试。

覆盖 docs/V2参数中心规则.md 里两条最容易出错的语义：
1. 文案池的"字段缺失 = 用默认池"与"空数组 = 不要这条轨道"**不能混**。
2. 插片策略"从未设置过"必须等于**改动前的历史行为**（中插、尾插都要，各取最新序号）。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server import v2_file_service as service
from server.template_engine.jianying59_template.template_copy import (
    DEFAULT_BLESSING_COPY,
    DEFAULT_DRAMA_PROMPT_COPY,
)


class EngineParameterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self._originals = (service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH)
        service.WORKSPACE = root / "workspace"
        service.DATA_ROOT = root / "system-data"
        service.DATABASE_INITIALIZED_PATH = None
        (service.WORKSPACE / "生成资源" / "引流视频").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH = self._originals
        self.temp.cleanup()

    def _write_promotion_video(self, name: str) -> None:
        (service.promotion_video_dir() / name).write_bytes(b"")

    # ---------------- 文案 ----------------

    def test_unconfigured_copy_returns_bundled_defaults(self) -> None:
        parameters = service.get_engine_parameters()
        copy = parameters["template_copy"]
        self.assertEqual(list(DEFAULT_BLESSING_COPY), copy["blessing"])
        self.assertEqual(list(DEFAULT_DRAMA_PROMPT_COPY), copy["drama_prompt"])
        self.assertFalse(copy["configured"])

    def test_legacy_copy_file_is_read_when_database_has_no_value(self) -> None:
        service.template_copy_file_path().parent.mkdir(parents=True, exist_ok=True)
        service.template_copy_file_path().write_text(
            json.dumps({"blessing": ["旧文件里的祝福"], "drama_prompt": ["旧文件里的引导"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        copy = service.get_engine_parameters()["template_copy"]
        self.assertEqual(["旧文件里的祝福"], copy["blessing"])
        self.assertEqual(["旧文件里的引导"], copy["drama_prompt"])

    def test_saving_copy_writes_database_and_projection_file(self) -> None:
        service.write_template_copy(blessing=["愿您平安喜乐"], drama_prompt=["左下角免费看全集"])
        copy = service.get_engine_parameters()["template_copy"]
        self.assertEqual(["愿您平安喜乐"], copy["blessing"])
        self.assertTrue(copy["configured"])
        projected = json.loads(service.template_copy_file_path().read_text(encoding="utf-8"))
        self.assertEqual({"blessing": ["愿您平安喜乐"], "drama_prompt": ["左下角免费看全集"]}, projected)

    def test_empty_pool_means_omit_the_track_not_fall_back_to_default(self) -> None:
        service.write_template_copy(blessing=[], drama_prompt=["左下角免费看全集"])
        copy = service.get_engine_parameters()["template_copy"]
        self.assertEqual([], copy["blessing"])
        self.assertEqual(["左下角免费看全集"], copy["drama_prompt"])
        projected = json.loads(service.template_copy_file_path().read_text(encoding="utf-8"))
        self.assertEqual([], projected["blessing"])

    def test_blank_lines_are_dropped(self) -> None:
        service.write_template_copy(blessing=["  愿您平安喜乐  ", "", "   "], drama_prompt=None)
        copy = service.get_engine_parameters()["template_copy"]
        self.assertEqual(["愿您平安喜乐"], copy["blessing"])
        # 未提交的池保持原值（这里是默认池），不能因为保存另一个池而被清空。
        self.assertEqual(list(DEFAULT_DRAMA_PROMPT_COPY), copy["drama_prompt"])

    def test_non_list_pool_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            service.write_template_copy(blessing="不是数组", drama_prompt=None)

    # ---------------- 成片插片 ----------------

    def test_unconfigured_strategy_keeps_historical_behaviour(self) -> None:
        parameters = service.get_engine_parameters()
        self.assertFalse(parameters["midroll_endroll"]["configured"])
        strategy = parameters["midroll_endroll"]["strategy"]
        self.assertEqual({"enabled": True, "mode": "latest", "file": ""}, strategy["midroll"])
        self.assertEqual({"enabled": True, "mode": "latest", "file": ""}, strategy["endroll"])

    def test_all_four_combinations_round_trip(self) -> None:
        for midroll_enabled in (True, False):
            for endroll_enabled in (True, False):
                saved = service.update_engine_parameters({
                    "midroll_endroll": {
                        "midroll": {"enabled": midroll_enabled, "mode": "latest", "file": ""},
                        "endroll": {"enabled": endroll_enabled, "mode": "latest", "file": ""},
                    }
                })
                strategy = saved["midroll_endroll"]["strategy"]
                self.assertIs(midroll_enabled, strategy["midroll"]["enabled"])
                self.assertIs(endroll_enabled, strategy["endroll"]["enabled"])

    def test_locking_a_missing_file_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            service.update_engine_parameters({
                "midroll_endroll": {
                    "midroll": {"enabled": True, "mode": "locked", "file": "中插99.mp4"},
                    "endroll": {"enabled": True, "mode": "latest", "file": ""},
                }
            })

    def test_locked_file_is_persisted_as_a_name_not_a_path(self) -> None:
        self._write_promotion_video("中插03.mov")
        saved = service.update_engine_parameters({
            "midroll_endroll": {
                "midroll": {"enabled": True, "mode": "locked", "file": "D:\\别的目录\\中插03.mov"},
                "endroll": {"enabled": True, "mode": "latest", "file": ""},
            }
        })
        self.assertEqual(
            {"enabled": True, "mode": "locked", "file": "中插03.mov"},
            saved["midroll_endroll"]["strategy"]["midroll"],
        )

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            service.update_engine_parameters({"midroll_endroll": {"中插": {"enabled": True}}})

    def test_unknown_parameter_group_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            service.update_engine_parameters({"something_else": {}})

    def test_saving_one_group_does_not_touch_the_other(self) -> None:
        service.write_template_copy(blessing=["愿您平安喜乐"], drama_prompt=["左下角免费看全集"])
        service.update_engine_parameters({
            "midroll_endroll": {
                "midroll": {"enabled": False, "mode": "latest", "file": ""},
                "endroll": {"enabled": True, "mode": "latest", "file": ""},
            }
        })
        copy = service.get_engine_parameters()["template_copy"]
        self.assertEqual(["愿您平安喜乐"], copy["blessing"])

    def test_stored_strategy_survives_garbage(self) -> None:
        service._save_setting(service.ENGINE_PARAMETER_KEY, "不是字典")
        strategy = service.get_engine_parameters()["midroll_endroll"]["strategy"]
        self.assertTrue(strategy["midroll"]["enabled"])
        self.assertTrue(strategy["endroll"]["enabled"])


if __name__ == "__main__":
    unittest.main()
