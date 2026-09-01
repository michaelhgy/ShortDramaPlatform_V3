import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.v2_exporter.runtime import V2ExportFailure, _is_retryable_draft_click_failure, _is_retryable_home_search_failure, file_baseline, safe_move_verified_output, source_is_new, verify_media, wait_for_stable_new_file


class V2ExportRuntimeTests(unittest.TestCase):
    def test_emergency_abort_releases_input_before_the_worker_checks_again(self) -> None:
        from server.v2_exporter.runtime import WindowsInputLease

        class Adapter:
            def __init__(self): self.released = []
            def release(self, attempt_id): self.released.append(attempt_id)
            def release_all(self): raise AssertionError("正常释放不应走兜底")
            def pause_requested(self, _attempt_id): return False
            def is_active(self, _attempt_id): return False

        lease = WindowsInputLease(maximum_seconds=60)
        adapter = Adapter()
        lease._adapter, lease._attempt_id, lease._lease_generation = adapter, "attempt", 1

        lease._emergency_abort("attempt", 1)

        self.assertEqual(["attempt"], adapter.released)
        with self.assertRaisesRegex(V2ExportFailure, "双 ESC") as raised:
            lease.require_active("attempt")
        self.assertEqual("USER_DOUBLE_ESC_ABORT", raised.exception.code)

    def test_matching_template_or_final_can_reuse_its_confirmed_export_button(self) -> None:
        from server.v2_exporter.runtime import Jianying59Bridge

        bridge = Jianying59Bridge(object(), "attempt")
        bridge._prepared_draft = ("模板-R01", "session", "controller", "export-button")
        self.assertEqual(("session", "controller", "export-button"), bridge._take_prepared_draft("模板-R01"))
        self.assertIsNone(bridge._take_prepared_draft("模板-R01"))
        bridge._prepared_draft = ("模板-R01", "session", "controller", "export-button")
        self.assertEqual(("session", "controller", "export-button"), bridge._take_prepared_draft("模板-R01"))
        bridge._prepared_draft = ("模板-R01", "session", "controller", "export-button")
        self.assertIsNone(bridge._take_prepared_draft("其他草稿"))

    def test_editor_window_probe_never_queries_home_window(self) -> None:
        from types import SimpleNamespace
        from server.v2_exporter.runtime import Jianying59Bridge

        class MissingContainer:
            def Exists(self, _timeout): return False

        class Editor:
            def Exists(self, _timeout): return True
            def Control(self, **_kwargs): return MissingContainer()

        class Uia:
            def __init__(self): self.requested_ids = []
            def WindowControl(self, **kwargs):
                control_id = kwargs["AutomationId"]
                self.requested_ids.append(control_id)
                if control_id == "HomeWindow":
                    raise AssertionError("MainWindow 已存在时不能查询 HomeWindow")
                return Editor()

        desktop = SimpleNamespace(_uia=Uia())
        page = SimpleNamespace(EDIT="edit", HOME="home", SUCCESS_PAGE="success", PARAMETER_DIALOG="dialog", EXPORTING="exporting", UNKNOWN="unknown")
        self.assertEqual("edit", Jianying59Bridge._fast_inspect_page(desktop, page))
        self.assertEqual(["MainWindow"], desktop._uia.requested_ids)

    def test_interruptible_sleep_checks_the_v2_emergency_stop(self) -> None:
        from server.v2_exporter.runtime import Jianying59Bridge

        class Lease:
            def __init__(self): self.calls = 0
            def require_active(self, _attempt_id):
                self.calls += 1
                if self.calls >= 2:
                    raise V2ExportFailure("USER_DOUBLE_ESC_ABORT", "用户双 ESC 紧急终止")

        bridge = Jianying59Bridge(Lease(), "attempt")
        with self.assertRaisesRegex(V2ExportFailure, "双 ESC"):
            bridge._interruptible_sleep(.06)

    def test_only_the_known_home_search_refresh_timeout_is_retryable(self) -> None:
        self.assertTrue(_is_retryable_home_search_failure(V2ExportFailure("UI_CONDITION_TIMEOUT", "等待搜索后的唯一完整草稿名称超过 30 秒")))
        self.assertFalse(_is_retryable_home_search_failure(V2ExportFailure("UI_CONDITION_TIMEOUT", "等待导出参数页超过 30 秒")))
        self.assertFalse(_is_retryable_home_search_failure(V2ExportFailure("DRAFT_NOT_SAFE_TO_CLICK", "草稿不在安全区域")))

    def test_only_an_unopened_draft_click_timeout_is_retryable(self) -> None:
        self.assertTrue(_is_retryable_draft_click_failure(V2ExportFailure("UI_CONDITION_TIMEOUT", "等待编辑页导出按钮超过 30 秒")))
        self.assertFalse(_is_retryable_draft_click_failure(V2ExportFailure("UI_CONDITION_TIMEOUT", "等待导出参数页超过 30 秒")))
        self.assertFalse(_is_retryable_draft_click_failure(V2ExportFailure("DRAFT_NOT_SAFE_TO_CLICK", "草稿不在安全区域")))

    def test_submission_controls_are_read_together_from_current_parameter_panel(self) -> None:
        from types import SimpleNamespace
        from server.v2_exporter.runtime import Jianying59Bridge

        class Lease:
            def require_active(self, _attempt_id): pass

        class Control:
            def Exists(self, _timeout): return True

        path, final = Control(), Control()

        class Panel:
            def TextControl(self, **kwargs):
                return final if "ExportOkBtn" in str(kwargs["Compare"]) else path

        class Finder:
            @staticmethod
            def desc_matcher(value, **_kwargs): return value

        bridge = Jianying59Bridge(Lease(), "attempt")
        session = SimpleNamespace(_raw_app=None, _trace=lambda *_args, **_kwargs: None)
        received_path, received_final = bridge._wait_for_export_submission_controls(session, SimpleNamespace(app=Panel()), Finder())
        self.assertIs(path, received_path)
        self.assertIs(final, received_final)

    def test_file_baseline_rejects_unchanged_residue_and_accepts_changed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.mp4"; path.write_bytes(b"old")
            baseline = file_baseline(path)
            self.assertFalse(source_is_new(path, baseline))
            time.sleep(.002); path.write_bytes(b"new-file")
            self.assertTrue(source_is_new(path, baseline))

    def test_stability_timeout_does_not_accept_old_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.mp4"; path.write_bytes(b"old")
            with self.assertRaises(V2ExportFailure) as raised:
                wait_for_stable_new_file(path, baseline=file_baseline(path), deadline=time.monotonic() + .01, poll_seconds=.001)
            self.assertEqual("OUTPUT_STABILITY_TIMEOUT", raised.exception.code)

    def test_safe_replace_keeps_only_new_verified_video(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source, target = root / "source.mp4", root / "target.mp4"
            source.write_bytes(b"verified-new"); target.write_bytes(b"old-formal")
            safe_move_verified_output(source, target)
            self.assertFalse(source.exists()); self.assertEqual(b"verified-new", target.read_bytes())

    def test_ffprobe_contract_accepts_h264_30fps_portrait(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video.mp4"; path.write_bytes(b"x")
            payload = {"format": {"duration": "10.0"}, "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 2400, "avg_frame_rate": "30/1"}]}
            completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()
            with patch("server.v2_exporter.runtime.subprocess.run", return_value=completed):
                result = verify_media(path, expected_duration=10)
            self.assertEqual("h264", result.codec); self.assertEqual(30, result.fps)

    def test_ffprobe_contract_accepts_hevc_and_duration_difference_when_canvas_and_fps_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video.mp4"; path.write_bytes(b"x")
            payload = {"format": {"duration": "5"}, "streams": [{"codec_type": "video", "codec_name": "hevc", "width": 1080, "height": 2400, "avg_frame_rate": "30/1"}]}
            completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()
            with patch("server.v2_exporter.runtime.subprocess.run", return_value=completed):
                result = verify_media(path, expected_duration=10)
            self.assertEqual("hevc", result.codec)

    def test_ffprobe_contract_rejects_wrong_canvas_or_frame_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video.mp4"; path.write_bytes(b"x")
            payload = {"format": {"duration": "10"}, "streams": [{"codec_type": "video", "codec_name": "hevc", "width": 1080, "height": 1920, "avg_frame_rate": "30/1"}]}
            completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()
            with patch("server.v2_exporter.runtime.subprocess.run", return_value=completed), self.assertRaisesRegex(V2ExportFailure, "媒体不符合合同"):
                verify_media(path, expected_duration=10)


if __name__ == "__main__":
    unittest.main()
