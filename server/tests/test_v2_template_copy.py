"""Tests for the user-editable template copy pools and empty-pool omission."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server.template_engine.jianying59_template.template_copy import (
    DEFAULT_BLESSING_COPY,
    DEFAULT_DRAMA_PROMPT_COPY,
    load_template_copy,
)
from server.template_engine.jianying59_template.track10_11_flower_text import decide_flower_text


class TemplateCopyTests(unittest.TestCase):
    def test_missing_path_returns_defaults(self) -> None:
        blessing, drama = load_template_copy(path=None)
        self.assertEqual(DEFAULT_BLESSING_COPY, blessing)
        self.assertEqual(DEFAULT_DRAMA_PROMPT_COPY, drama)

    def test_nonexistent_file_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blessing, drama = load_template_copy(path=Path(tmp) / "不存在.json")
        self.assertEqual(DEFAULT_BLESSING_COPY, blessing)
        self.assertEqual(DEFAULT_DRAMA_PROMPT_COPY, drama)

    def test_empty_arrays_mean_omit_both_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "模板文案.json"
            path.write_text(json.dumps({"blessing": [], "drama_prompt": []}, ensure_ascii=False), encoding="utf-8")
            blessing, drama = load_template_copy(path=path)
        self.assertEqual((), blessing)
        self.assertEqual((), drama)

    def test_missing_field_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "模板文案.json"
            path.write_text(json.dumps({"blessing": ["你好"]}, ensure_ascii=False), encoding="utf-8")
            blessing, drama = load_template_copy(path=path)
        self.assertEqual(("你好",), blessing)
        self.assertEqual(DEFAULT_DRAMA_PROMPT_COPY, drama)

    def test_non_list_field_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "模板文案.json"
            path.write_text(json.dumps({"blessing": "不是数组"}, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_template_copy(path=path)


class FlowerTextDecisionTests(unittest.TestCase):
    def test_both_pools_empty_omits_both_tracks(self) -> None:
        decision = decide_flower_text(
            seed=1, duration_seconds=180, central_window_boundary_ratio=0.75,
            blessing_pool=(), drama_prompt_pool=(),
        )
        self.assertIsNone(decision.blessing_text)
        self.assertIsNone(decision.drama_prompt_text)
        self.assertIsNone(decision.blessing_style)
        self.assertIsNone(decision.drama_prompt_style)
        self.assertIsNone(decision.blessing_position)
        self.assertIsNone(decision.drama_prompt_position)

    def test_only_blessing_keeps_drama_omitted(self) -> None:
        decision = decide_flower_text(
            seed=1, duration_seconds=180, central_window_boundary_ratio=0.75,
            blessing_pool=("你好",), drama_prompt_pool=(),
        )
        self.assertEqual("你好", decision.blessing_text)
        self.assertIsNone(decision.drama_prompt_text)
        self.assertIsNotNone(decision.blessing_style)
        self.assertIsNone(decision.drama_prompt_style)
        self.assertIsNotNone(decision.blessing_position)
        self.assertIsNone(decision.drama_prompt_position)


if __name__ == "__main__":
    unittest.main()
