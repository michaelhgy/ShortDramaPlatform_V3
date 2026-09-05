import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.template_engine.jianying59_template import photo_prep


class TemplateDiagnosticsTests(unittest.TestCase):
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

            def crop(_source: Path, target: Path) -> None:
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
            self.assertIn("OCR 字幕处理", phases)
            self.assertIn("剧照处理完成", phases)
