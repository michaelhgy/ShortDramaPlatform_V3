import unittest

from server import remix_planner as P
from server.remix_materials import build_lines, render_for_model


def _episode(n, texts, duration=120.0, step=4.0):
    return {"episode": n, "duration": duration,
            "segments": [{"start": 2 + i * step, "end": 2 + i * step + 3, "text": t} for i, t in enumerate(texts)]}


def _drama(episodes=12, per=25):
    transcripts = []
    for e in range(1, episodes + 1):
        texts = [f"第{e}集台词{i}内容" for i in range(1, per + 1)]
        if e > 1:  # 每集开头回顾上一集最后两句
            texts = [f"第{e - 1}集台词{per - 1}内容", f"第{e - 1}集台词{per}内容"] + texts
        transcripts.append(_episode(e, texts))
    inventory = [{"episode": e, "duration": 120.0, "source": f"ep{e}.mp4"} for e in range(1, episodes + 1)]
    return transcripts, inventory


class MaterialsTests(unittest.TestCase):
    def test_recap_removed_and_ids_stable(self):
        transcripts, _ = _drama(3)
        lines = build_lines(transcripts)
        ep2 = [l for l in lines if l["episode"] == 2]
        self.assertEqual(ep2[0]["text"], "第2集台词1内容")
        self.assertEqual(ep2[0]["id"], "E02-001")
        self.assertIn("recap_end", ep2[0])
        self.assertTrue(ep2[-1]["episode_end"])
        self.assertIn("[集末]", render_for_model(lines))

    def test_blank_lines_dropped(self):
        lines = build_lines([_episode(1, ["有内容的台词", "，。", " "])])
        self.assertEqual([l["text"] for l in lines], ["有内容的台词"])


class PlannerTests(unittest.TestCase):
    def setUp(self):
        transcripts, self.inventory = _drama()
        self.lines = build_lines(transcripts)
        self.timeline = P.Timeline(self.lines, self.inventory)

    def _raw_map(self):
        ends = []
        for e in range(1, 13):
            ends.append({"line": f"E{e:02d}-025", "type": "悬念", "reason": "集末"})
            ends.append({"line": f"E{e:02d}-012", "type": "告一段落", "reason": "中段"})
        hl = lambda line, ok=True, excluded="无": {
            "start_line": line, "conflict_id": "c", "hook_label": "冲突", "cold_start_ok": ok,
            "strong_action": ok, "visual_conflict": True, "excluded_type": excluded,
            "viewer_question": "?", "reason": "r"}
        return {
            "characters": [], "episodes": [], "conflicts": [],
            "highlights": [hl("E01-005"), hl("E06-003"), hl("E02-001", ok=False), hl("E03-001", excluded="感悟"), hl("E99-001")],
            "end_points": ends + [{"line": "E50-001", "type": "悬念", "reason": "假"}],
            "skippable": [
                {"from_line": "E03-001", "to_line": "E03-025", "what": "过渡", "used_later": False, "resume_clear": True, "reason": ""},
                {"from_line": "E09-001", "to_line": "E09-025", "what": "支线", "used_later": False, "resume_clear": True, "reason": ""},
                {"from_line": "E04-001", "to_line": "E04-010", "what": "关键", "used_later": True, "resume_clear": True, "reason": ""},
            ],
        }

    def _raw_map_many_skips(self):
        """多可跳段版本：验证跳集放量（同一高光枚举多条差异视频）。"""
        raw = self._raw_map()
        # 从 E01 的高光起点之后、到末尾之间，布满可跳段，彼此隔开
        raw["skippable"] = [
            {"from_line": f"E{e:02d}-005", "to_line": f"E{e:02d}-015", "what": "过渡",
             "used_later": False, "resume_clear": True, "reason": ""}
            for e in range(2, 12)
        ]
        return raw

    def _two_pass_caller(self, raw):
        """模拟两次调用：highlight 返回选点（不含可跳段），skippable 返回可跳段。"""
        self.calls = []
        def call(task_role, prompt, schema, schema_name):
            self.calls.append(task_role)
            if task_role == "skippable":
                return {"data": {"skippable": raw.get("skippable", [])}, "usage": {}, "model": "m"}
            picks = {k: v for k, v in raw.items() if k != "skippable"}
            return {"data": picks, "usage": {}, "model": "m"}
        return call

    def _map_many(self):
        return P.build_story_map(self.lines, self._two_pass_caller(self._raw_map_many_skips()))

    def _map(self):
        return P.build_story_map(self.lines, self._two_pass_caller(self._raw_map()))

    def test_story_map_filters_invalid_and_unqualified(self):
        story = self._map()
        self.assertEqual(self.calls, ["highlight", "skippable"])  # 选点 + 标可跳段两次调用
        self.assertEqual([h["start_line"] for h in story["highlights"]], ["E01-005", "E06-003"])
        self.assertNotIn("E50-001", [e["line"] for e in story["end_points"]])
        self.assertEqual(len(story["skippable"]), 2)  # used_later 的段被丢弃
        self.assertEqual(story["method_version"], P.METHOD_VERSION)

    def test_continuous_plans_respect_duration_and_order(self):
        story = self._map()
        candidates = P.build_candidates(story, self.timeline, "continuous", 300, 600)
        self.assertTrue(candidates)
        for c in candidates:
            self.assertTrue(300 <= c["duration"] <= 600)
            eps = [s["episode"] for s in c["segments"]]
            self.assertEqual(eps, sorted(eps))
            self.assertEqual(c["mode"], "continuous")
        self.assertEqual({c["end_type"] for c in candidates}, {"告一段落", "悬念"})

    def test_jump_plans_respect_skip_limit_and_remove_episodes(self):
        story = self._map()
        candidates = P.build_candidates(story, self.timeline, "jump", 300, 600)
        self.assertTrue(candidates)
        for c in candidates:
            self.assertTrue(1 <= len(c["skips"]) <= P.MAX_SKIPS_PER_VARIANT)
            skipped_eps = {int(s["from_line"][1:3]) for s in c["skips"]}
            self.assertFalse(skipped_eps & {s["episode"] for s in c["segments"]})

    def test_jump_volume_many_variants_per_highlight(self):
        """放量：可跳段充足时，同一高光应枚举出多条、互不相同、且每个高光不超过上限。"""
        story = self._map_many()
        candidates = P.build_candidates(story, self.timeline, "jump", 300, 600)
        by_rank = {}
        for c in candidates:
            by_rank.setdefault(c["rank"], []).append(c)
        # 至少有一个高光产出多条跳集（放量生效）
        self.assertTrue(any(len(v) >= 3 for v in by_rank.values()),
                        f"每个高光跳集条数：{ {r: len(v) for r, v in by_rank.items()} }")
        for rank, variants in by_rank.items():
            # 不超过每高光上限
            self.assertLessEqual(len(variants), P.MAX_JUMP_PER_HIGHLIGHT)
            # 跳法签名互不相同（内容有差异）
            signatures = [tuple(sorted((s["from_line"], s["to_line"]) for s in c["skips"])) for c in variants]
            self.assertEqual(len(signatures), len(set(signatures)))
            for c in variants:
                self.assertTrue(300 <= c["duration"] <= 600)
                self.assertTrue(1 <= len(c["skips"]) <= P.MAX_SKIPS_PER_VARIANT)

    def test_later_episodes_start_after_recap(self):
        segments = self.timeline.segments("E01-005", "E03-010")
        ep2 = next(s for s in segments if s["episode"] == 2)
        self.assertGreater(ep2["start"], 0.0)

    def test_review_rejects_and_respects_limit(self):
        story = self._map()
        candidates = P.build_candidates(story, self.timeline, "continuous", 300, 600)
        calls = []

        def review(c):
            calls.append(c)
            return {"passed": len(calls) % 2 == 0, "issues": [] if len(calls) % 2 == 0 else ["结尾：话没说完"]}

        chosen, rejected = P.pick_with_review(candidates, 2, review, max_reviews=3)
        self.assertLessEqual(len(calls), 3)
        self.assertTrue(all(c["review"]["passed"] for c in chosen))
        self.assertTrue(all(not c["review"]["passed"] for c in rejected))

    def test_review_parses_model_answer(self):
        story = self._map()
        candidate = P.build_candidates(story, self.timeline, "continuous", 300, 600)[0]
        bad = {"data": {"opening_ok": True, "opening_issue": "", "jumps": [], "ending_type": "不能停", "ending_issue": "问了没答"}}
        result = P.review_candidate(candidate, self.timeline, lambda *a: bad)
        self.assertFalse(result["passed"])
        self.assertIn("问了没答", result["issues"][0])


if __name__ == "__main__":
    unittest.main()
