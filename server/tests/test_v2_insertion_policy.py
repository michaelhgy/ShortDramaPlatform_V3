"""成片中插 / 尾插策略的测试（参数中心第二个参数组）。

覆盖 docs/V2参数中心规则.md §3.2 的四条硬规则：
1. 四种组合都能生成合法主轨结构；
2. **只要尾插时爆款不拆段**（拆段原本只为给中插让位）；
3. 关掉的那一条不参与检查（老代码是缺任一条直接报错）；
4. "指定某一条"素材没了必须明确报错，不静默换别的。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server import v2_file_service as service
from server.final_engine import runner
from server.final_engine.jianying59_final.composition import (
    MIDROLL_INSERT_US,
    US,
    Media,
    _main_sections,
)


def _media(name: str, seconds: float) -> Media:
    return Media(path=Path(f"C:/fake/{name}"), width=1080, height=1920, duration_us=int(seconds * US))


WINDOW_PX = {"width": 900.0, "height": 1600.0}
SOURCE_RECTANGLE = {"width": 0.9, "height": 0.75, "center_x": 0.0, "center_y": 0.0, "feather": 0.01}


def _roles(viral: Media, midroll: Media | None, endroll: Media | None) -> list[str]:
    sections = _main_sections(
        viral, midroll, endroll, window_px=WINDOW_PX, source_rectangle=SOURCE_RECTANGLE,
    )
    return [str(section["role"]) for section in sections]


class MainTrackStructureTests(unittest.TestCase):
    def test_midroll_and_endroll_keeps_the_four_segment_structure(self) -> None:
        roles = _roles(_media("爆款.mp4", 300), _media("中插01.mp4", 10), _media("尾插01.mp4", 12))
        self.assertEqual(["viral", "midroll", "viral", "endroll"], roles)

    def test_endroll_only_does_not_split_the_viral(self) -> None:
        """只要尾插时，爆款必须是**一整条**。"""
        viral = _media("爆款.mp4", 300)
        sections = _main_sections(
            viral, None, _media("尾插01.mp4", 12), window_px=WINDOW_PX, source_rectangle=SOURCE_RECTANGLE,
        )
        self.assertEqual(["viral", "endroll"], [section["role"] for section in sections])
        self.assertEqual(viral.duration_us, int(sections[0]["duration_us"]))
        self.assertEqual(0, int(sections[0]["source_start_us"]))

    def test_midroll_only_keeps_the_two_part_viral(self) -> None:
        roles = _roles(_media("爆款.mp4", 300), _media("中插01.mp4", 10), None)
        self.assertEqual(["viral", "midroll", "viral"], roles)

    def test_neither_insertion_leaves_a_single_viral_segment(self) -> None:
        viral = _media("爆款.mp4", 300)
        sections = _main_sections(
            viral, None, None, window_px=WINDOW_PX, source_rectangle=SOURCE_RECTANGLE,
        )
        self.assertEqual(["viral"], [section["role"] for section in sections])
        self.assertEqual(viral.duration_us, int(sections[0]["duration_us"]))

    def test_short_source_skips_midroll_and_keeps_the_endroll(self) -> None:
        """素材短于 120 秒没有合法插入点 → 自动跳过中插，尾插保留。"""
        roles = _roles(_media("爆款.mp4", 90), _media("中插01.mp4", 10), _media("尾插01.mp4", 12))
        self.assertEqual(["viral", "endroll"], roles)

    def test_insert_point_is_still_120_seconds(self) -> None:
        sections = _main_sections(
            _media("爆款.mp4", 300), _media("中插01.mp4", 10), _media("尾插01.mp4", 12),
            window_px=WINDOW_PX, source_rectangle=SOURCE_RECTANGLE,
        )
        self.assertEqual(MIDROLL_INSERT_US, int(sections[0]["duration_us"]))


class InsertionSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self._originals = (service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH)
        service.WORKSPACE = root / "workspace"
        service.DATA_ROOT = root / "system-data"
        service.DATABASE_INITIALIZED_PATH = None
        self.promotion = service.WORKSPACE / "生成资源" / "引流视频"
        self.promotion.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH = self._originals
        self.temp.cleanup()

    def _write(self, name: str) -> Path:
        path = self.promotion / name
        path.write_bytes(b"")
        return path

    def _row(self, strategy: object = "") -> dict[str, object]:
        return {"midroll_endroll_strategy": json.dumps(strategy, ensure_ascii=False) if strategy else ""}

    def test_unconfigured_keeps_historical_behaviour(self) -> None:
        self._write("中插01.mp4")
        self._write("中插03.mov")
        self._write("尾插01.mp4")
        self._write("尾插02.mp4")
        midroll, endroll = runner.resolve_insertion_media(task_row=self._row(), settings={})
        self.assertEqual("中插03.mov", midroll.name)
        self.assertEqual("尾插02.mp4", endroll.name)

    def test_disabled_slot_returns_none_and_never_raises(self) -> None:
        """关掉的那一条即使目录里一条素材都没有，也不能让任务失败。"""
        self._write("尾插01.mp4")
        strategy = {
            "midroll": {"enabled": False, "mode": "latest", "file": ""},
            "endroll": {"enabled": True, "mode": "latest", "file": ""},
        }
        midroll, endroll = runner.resolve_insertion_media(task_row=self._row(strategy), settings={})
        self.assertIsNone(midroll)
        self.assertEqual("尾插01.mp4", endroll.name)

    def test_both_disabled_returns_none_pair(self) -> None:
        strategy = {
            "midroll": {"enabled": False, "mode": "latest", "file": ""},
            "endroll": {"enabled": False, "mode": "latest", "file": ""},
        }
        self.assertEqual((None, None), runner.resolve_insertion_media(task_row=self._row(strategy), settings={}))

    def test_enabled_slot_with_no_material_still_fails_loudly(self) -> None:
        strategy = {
            "midroll": {"enabled": True, "mode": "latest", "file": ""},
            "endroll": {"enabled": False, "mode": "latest", "file": ""},
        }
        with self.assertRaisesRegex(RuntimeError, "中插"):
            runner.resolve_insertion_media(task_row=self._row(strategy), settings={})

    def test_locked_material_is_used_even_when_a_newer_one_exists(self) -> None:
        self._write("中插01.mp4")
        self._write("中插02.mp4")
        strategy = {
            "midroll": {"enabled": True, "mode": "locked", "file": "中插01.mp4"},
            "endroll": {"enabled": False, "mode": "latest", "file": ""},
        }
        midroll, _ = runner.resolve_insertion_media(task_row=self._row(strategy), settings={})
        self.assertEqual("中插01.mp4", midroll.name)

    def test_locked_material_that_disappeared_fails_loudly(self) -> None:
        strategy = {
            "midroll": {"enabled": True, "mode": "locked", "file": "中插01.mp4"},
            "endroll": {"enabled": False, "mode": "latest", "file": ""},
        }
        with self.assertRaisesRegex(RuntimeError, "中插01.mp4"):
            runner.resolve_insertion_media(task_row=self._row(strategy), settings={})

    def test_global_parameter_center_default_is_used_when_the_task_has_no_override(self) -> None:
        self._write("尾插01.mp4")
        settings = {service.ENGINE_PARAMETER_KEY: {
            "midroll": {"enabled": False, "mode": "latest", "file": ""},
            "endroll": {"enabled": True, "mode": "latest", "file": ""},
        }}
        midroll, endroll = runner.resolve_insertion_media(task_row=self._row(), settings=settings)
        self.assertIsNone(midroll)
        self.assertEqual("尾插01.mp4", endroll.name)

    def test_task_override_wins_over_the_global_default(self) -> None:
        self._write("中插01.mp4")
        settings = {service.ENGINE_PARAMETER_KEY: {
            "midroll": {"enabled": False, "mode": "latest", "file": ""},
            "endroll": {"enabled": True, "mode": "latest", "file": ""},
        }}
        task_strategy = {
            "midroll": {"enabled": True, "mode": "latest", "file": ""},
            "endroll": {"enabled": False, "mode": "latest", "file": ""},
        }
        midroll, endroll = runner.resolve_insertion_media(task_row=self._row(task_strategy), settings=settings)
        self.assertEqual("中插01.mp4", midroll.name)
        self.assertIsNone(endroll)


class InsertionCommandTests(unittest.TestCase):
    def test_command_omits_a_disabled_slot(self) -> None:
        root = Path("C:/fake")
        command = runner._processed_composition_command(
            source=root / "素材.mp4", template_video=root / "模板.mp4", pairing=root / "配对.json",
            draft_root=root / "drafts", user_data_root=root / "User Data", jianying_app_root=root / "JianyingPro",
            real_photo_dir=root / "真人图片", draft_prefix="前缀", account_id="账号",
            midroll=None, endroll=root / "尾插01.mp4", bgm=root / "bgm.m4a", work_dir=root / "work",
        )
        self.assertNotIn("--midroll", command)
        self.assertEqual(str(root / "尾插01.mp4"), command[command.index("--endroll") + 1])

    def test_command_omits_both_slots_when_neither_is_wanted(self) -> None:
        root = Path("C:/fake")
        command = runner._processed_composition_command(
            source=root / "素材.mp4", template_video=root / "模板.mp4", pairing=root / "配对.json",
            draft_root=root / "drafts", user_data_root=root / "User Data", jianying_app_root=root / "JianyingPro",
            real_photo_dir=root / "真人图片", draft_prefix="前缀", account_id="账号",
            midroll=None, endroll=None, bgm=root / "bgm.m4a", work_dir=root / "work",
        )
        self.assertNotIn("--midroll", command)
        self.assertNotIn("--endroll", command)

    def test_insertion_arguments_passes_only_the_requested_slots(self) -> None:
        from server.final_engine.scripts.run_jianying_composition_batch import insertion_arguments

        self.assertEqual(["--midroll", "中插01.mp4"], insertion_arguments(Path("中插01.mp4"), None))
        self.assertEqual(["--endroll", "尾插01.mp4"], insertion_arguments(None, Path("尾插01.mp4")))
        self.assertEqual([], insertion_arguments(None, None))


class ActiveChainAcceptsOptionalInsertionsTests(unittest.TestCase):
    """防回归：V2 正式链路里 --midroll / --endroll 必须是**可选**参数。

    这是"中插/尾插四种组合"能成立的前提。三个脚本里任何一个被改回 required=True，
    都会让"不要某一条"在运行时直接失败，所以用源码断言把它钉住。
    """

    SCRIPTS = (
        "server/final_engine/scripts/run_jianying_composition_batch.py",
        "server/final_engine/scripts/generate_jianying59_composition_draft.py",
        "server/final_engine/scripts/generate_composition_from_detection_reports.py",
    )

    def test_no_active_script_requires_an_insertion_media_argument(self) -> None:
        repository_root = Path(__file__).resolve().parents[2]
        for relative in self.SCRIPTS:
            source = (repository_root / relative).read_text(encoding="utf-8")
            for flag in ("--midroll", "--endroll"):
                self.assertNotIn(
                    f'"{flag}", required=True', source,
                    f"{relative} 把 {flag} 改回了必填；四种组合里的「不要这一条」会直接失败",
                )


if __name__ == "__main__":
    unittest.main()
