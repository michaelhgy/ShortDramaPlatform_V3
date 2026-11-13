"""广告恢复与固定区域OCR的隔离检查；不连接手机、不读写业务记录。"""
from __future__ import annotations
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

LAB = Path(__file__).resolve().parents[2] / "tools/short_drama_downloader_lab"


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, LAB / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self): self.now = 0.0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class AdRetryTests(unittest.TestCase):
    def setUp(self):
        self.nav = types.ModuleType("导航")
        self.view = types.ModuleType("视图")
        clip = types.ModuleType("读剪贴板历史")
        clip.newest_share = lambda: ""
        with patch.dict(sys.modules, {"导航": self.nav, "视图": self.view, "读剪贴板历史": clip}):
            self.collector = load("阶段1_收集链接.py", "collector_ad_fixture")
        self.clock = Clock()
        self.slides = []
        self.nav.swipe_next_episode = lambda: self.slides.append(self.clock.now)
        self.nav.pause_video = Mock()
        self.nav.read_drama_banner = Mock(return_value=(None, []))
        self.nav.wait_for_drama_banner = Mock(side_effect=self.wait)
        self.collector.progress = Mock()
        self.patches = [patch.object(self.collector.time, "monotonic", self.clock.monotonic),
                        patch.object(self.collector.time, "sleep", self.clock.sleep)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def wait(self, **kwargs):
        self.clock.sleep(kwargs["timeout"])
        return None

    def test_normal_transition_has_no_ad_delay_or_extra_swipe(self):
        self.nav.wait_for_drama_banner.side_effect = None
        self.nav.wait_for_drama_banner.return_value = {"text": "免费剧集第10集"}
        self.assertTrue(self.collector.advance_episode(10))
        self.assertEqual(self.slides, [0])
        self.assertEqual(self.clock.now, 0)
        self.nav.read_drama_banner.assert_not_called()
        self.nav.pause_video.assert_called_once()

    def test_ad_requires_second_swipe_after_minimum_play_time(self):
        def wait(**kwargs):
            self.clock.sleep(kwargs["timeout"])
            return {"text": "免费剧集第10集"} if len(self.slides) == 2 else None
        self.nav.wait_for_drama_banner.side_effect = wait
        self.assertTrue(self.collector.advance_episode(10))
        self.assertEqual(len(self.slides), 2)
        self.assertGreaterEqual(self.slides[1] - self.slides[0], 7)
        self.nav.pause_video.assert_called_once()
        logs = [call.args[0] for call in self.collector.progress.call_args_list]
        self.assertTrue(any("再次滑动" in line for line in logs))
        self.assertTrue(any("已等待" in line for line in logs))

    def test_persistent_ad_stops_after_bounded_retries(self):
        self.assertFalse(self.collector.advance_episode(10))
        self.assertEqual(len(self.slides), 4)
        self.assertTrue(all(b-a >= 7 for a,b in zip(self.slides, self.slides[1:])))
        self.assertLessEqual(self.clock.now, 45)
        self.nav.pause_video.assert_not_called()

    def test_wrong_episode_reselects_without_another_swipe(self):
        self.nav.read_drama_banner.return_value = ({"text": "免费剧集第11集"}, [11])
        with patch.object(self.collector, "recover_episode", return_value=True) as recover:
            self.assertTrue(self.collector.advance_episode(10))
        recover.assert_called_once_with(10)
        self.assertEqual(len(self.slides), 1)
        self.nav.pause_video.assert_not_called()

    def test_unknown_number_on_real_banner_uses_selection(self):
        self.nav.read_drama_banner.return_value = ({"text": "免费剧集"}, [])
        with patch.object(self.collector, "recover_episode", return_value=False) as recover:
            self.assertFalse(self.collector.advance_episode(10))
        recover.assert_called_once_with(10)
        self.assertEqual(len(self.slides), 1)

    def test_target_returns_during_wait_without_extra_swipe(self):
        self.nav.read_drama_banner.side_effect = [(None, []), ({"text":"免费剧集第10集"}, [10])]
        self.assertTrue(self.collector.advance_episode(10))
        self.assertEqual(len(self.slides), 1)
        self.nav.pause_video.assert_called_once()

    def test_timeout_does_not_start_another_swipe(self):
        self.nav.wait_for_drama_banner.side_effect = lambda **_: self.clock.sleep(50)
        self.assertFalse(self.collector.advance_episode(10))
        self.assertEqual(len(self.slides), 1)
        self.nav.pause_video.assert_not_called()

    def test_restart_keeps_nine_links_and_selects_only_tenth(self):
        self.nav.episode_sheet_open = lambda: True
        self.nav.read_total_episodes = lambda: 10
        self.nav.tap_episode = Mock(return_value=True)
        with tempfile.TemporaryDirectory() as folder:
            table = Path(folder) / "links.txt"
            before = "".join(f"剧\t第{n}集\thttps://fixture/{n}\n" for n in range(1,10))
            table.write_text(before, encoding="utf-8")
            with patch.object(self.collector, "ensure_recording_ime", return_value=True), \
                 patch.object(self.collector, "grab_one", return_value="https://fixture/10") as grab, \
                 patch.object(sys, "argv", ["collector", "--no-nav", "--drama", "剧", "--table", str(table)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.collector.main(), 0)
            self.nav.tap_episode.assert_called_once_with(10)
            grab.assert_called_once_with("", episode=10)
            after = table.read_text(encoding="utf-8")
            self.assertTrue(all(line in after.splitlines() for line in before.splitlines()))
            self.assertEqual(len(after.splitlines()), 10)


class BannerRegionTests(unittest.TestCase):
    def setUp(self):
        self.view = types.ModuleType("视图")
        self.view.screenshot = Mock(return_value=object())
        self.view.refresh = Mock()
        with patch.dict(sys.modules, {"视图": self.view}):
            self.nav = load("导航.py", "nav_ad_fixture")

    def test_narrow_match_avoids_wide_ocr(self):
        row = [{"text":"免费剧集第10集", "y":2300}]
        self.view.refresh.return_value = row
        self.assertEqual(self.nav._banner_items(expected_episode=10), row)
        self.view.screenshot.assert_called_once()
        self.view.refresh.assert_called_once_with(crop=self.nav.R_BANNER_TEXT, img=self.view.screenshot.return_value)

    def test_failed_narrow_uses_wide_crop_on_same_screenshot(self):
        row = [{"text":"免费剧集第10集", "y":2300}]
        self.view.refresh.side_effect = [[], row]
        self.assertEqual(self.nav._banner_items(expected_episode=10), row)
        self.view.screenshot.assert_called_once()
        self.assertEqual([c.kwargs["crop"] for c in self.view.refresh.call_args_list],
                         [self.nav.R_BANNER_TEXT, self.nav.R_BANNER_LEFT])

    def test_wrong_narrow_number_does_not_pollute_wide_result(self):
        wide = [{"text":"免费剧集第10集", "y":2300}]
        self.view.refresh.side_effect = [[{"text":"免费剧集第99集", "y":2300}], wide]
        self.assertEqual(self.nav.read_drama_banner(expected_episode=10)[1], [10])


if __name__ == "__main__":
    unittest.main()
