import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from server.template_engine.generate_v2_template import _trace
from server.template_engine import runner
from server.template_engine.jianying59_template import photo_prep


class TemplateDiagnosticsTests(unittest.TestCase):
    def test_worker_trace_has_its_own_precise_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "执行过程.jsonl"
            _trace(trace, "抽取候选画面", "测试")
            payload = json.loads(trace.read_text(encoding="utf-8"))
            self.assertEqual("抽取候选画面", payload["phase"])
            self.assertIn("T", payload["occurred_at"])

    def test_runner_preserves_worker_event_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "执行过程.jsonl"
            trace.write_text(json.dumps({
                "occurred_at": "2026-09-05T14:47:29.123",
                "phase": "剧照处理完成",
                "message": "抽帧 1.0 秒，OCR 2.0 秒",
            }, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(
                [("剧照处理完成", "抽帧 1.0 秒，OCR 2.0 秒", "2026-09-05T14:47:29.123")],
                runner._worker_trace_entries(trace),
            )

    def test_photo_preparation_reports_video_frame_and_ocr_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "剧集.mp4"
            source.write_bytes(b"source")
            video = photo_prep.VideoSource(path=source, duration_seconds=100.0)
            events: list[tuple[str, str]] = []

            def extract(*, target: Path, **_kwargs: object) -> None:
                target.write_bytes(b"frame")

            def measure(*, source: photo_prep.VideoSource, time_seconds: float, **_kwargs: object) -> photo_prep.FrameCandidate:
                return photo_prep.FrameCandidate(source=source, time_seconds=time_seconds, width=1080, height=1920,
                                                 sharpness=1.0, exposure_penalty=0.0, perceptual_key=(1,))

            # 2026-09-18 起 _crop_three_four 多了 face（人脸感知裁切）与 variant（保底凑数）两个关键字参数，
            # 桩函数必须跟着改，否则这条测试会因为签名不匹配而失败。
            def crop(_source: Path, target: Path, *, face: object = None, variant: bool = False) -> None:
                target.write_bytes(target.name.encode("utf-8"))

            with patch.object(photo_prep, "account_day_video_sources", return_value=((), (video,))), \
                 patch.object(photo_prep, "_extract_frame", side_effect=extract), \
                 patch.object(photo_prep, "_measure_frame", side_effect=measure), \
                 patch.object(photo_prep, "_crop_three_four", side_effect=crop), \
                 patch.object(photo_prep, "soften_detected_text", return_value=0):
                photo_prep.prepare_drama_photos(
                    account_day_dir=root, output_dir=root / "剧照", seed=1,
                    progress=lambda phase, message: events.append((phase, message)),
                )

            phases = [phase for phase, _message in events]
            self.assertIn("剧集素材已就绪", phases)
            self.assertIn("抽取候选画面", phases)
            self.assertIn("分析候选画面", phases)
            self.assertIn("裁切剧照", phases)
            self.assertIn("OCR 字幕处理", phases)
            self.assertIn("剧照处理完成", phases)
            # 裁切这一步必须说明是"以人脸为中心"还是"按画面中心"，
            # 否则任务日志里看不出这一张到底走的是哪条路。
            crop_messages = [message for phase, message in events if phase == "裁切剧照"]
            self.assertTrue(crop_messages)
            self.assertTrue(all("人脸" in message or "中心裁切" in message for message in crop_messages))
            completed = [message for phase, message in events if phase == "剧照处理完成"]
            self.assertEqual(10, len(completed))
            self.assertTrue(all("抽帧" in message and "OCR" in message and "本张合计" in message for message in completed))
