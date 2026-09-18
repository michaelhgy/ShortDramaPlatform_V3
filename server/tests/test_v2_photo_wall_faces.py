"""照片墙选人与裁切规则的测试。

覆盖 2026-09-18 用户报的缺陷与新增需求：
1. **"标准化后不是3:4" 报错**：老代码用 `round(<浮点>)` 凑比例，约三分之二的画面尺寸会差 1 像素，
   然后被精确校验拒掉。这里把它钉死：任何尺寸都必须得到精确 3:4。
2. **缓存命中也必须校验**：老代码 `if not target.is_file()` 直接信任缓存，一个坏缓存会让任务永远失败。
3. **照片墙要抽人物剧照**（用户需求）：有人脸的候选必须优先于更"清晰"的空画面。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.template_engine.jianying59_template import drama_face
from server.template_engine.jianying59_template.photo_prep import (
    MAX_PHOTOS_PER_PERSON,
    MAX_PHOTOS_PER_VIDEO,
    MIN_SOURCE_GAP_SECONDS,
    PHOTO_COUNT,
    WINDOW_COUNT,
    FrameCandidate,
    VideoSource,
    choose_photo_set,
    planned_windows,
    select_photo_set,
)
from server.template_engine.jianying59_template.track02_03 import (
    _is_exact_three_four,
    _write_exact_three_four,
)


def _candidate(*, seconds: float, sharpness: float, face_score: float, face_count: int = 0,
               perceptual_key: tuple[int, ...] = (0,) * 16, frontal_score: float = 0.0,
               face_width: float = 0.0) -> FrameCandidate:
    return FrameCandidate(
        source=VideoSource(path=Path("C:/fake/剧集-1.mp4"), duration_seconds=600.0),
        time_seconds=seconds, width=1080, height=1920, sharpness=sharpness, exposure_penalty=0.0,
        perceptual_key=perceptual_key, face_count=face_count, face_score=face_score,
        frontal_score=frontal_score, face_width=face_width,
    )


def _box_size(box: tuple[int, int, int, int]) -> tuple[int, int]:
    return box[2] - box[0], box[3] - box[1]


class ExactThreeFourCropTests(unittest.TestCase):
    """所有尺寸都必须裁出**精确** 3:4 —— 这是报错的根因。"""

    REALISTIC_AND_AWKWARD = (
        (720, 1280), (1080, 1920), (576, 1248), (1920, 1080), (1280, 720),
        (136, 241), (137, 243), (139, 247), (140, 248), (124, 220),
        (100, 1000), (5000, 200), (1080, 1081), (1079, 1920), (3, 4), (4, 4), (5, 5), (11, 12),
    )
    TOO_SMALL_TO_CROP = ((1, 1), (1, 100), (2, 2), (2, 100))

    def test_center_crop_is_always_exactly_three_four(self) -> None:
        for width, height in self.REALISTIC_AND_AWKWARD:
            with self.subTest(size=f"{width}x{height}"):
                box = drama_face.center_crop_box(image_width=width, image_height=height)
                cropped_width, cropped_height = _box_size(box)
                self.assertEqual(
                    cropped_width * 4, cropped_height * 3,
                    f"{width}x{height} 裁成了 {cropped_width}x{cropped_height}，不是精确 3:4",
                )

    def test_face_centered_crop_is_always_exactly_three_four(self) -> None:
        face = drama_face.FaceBox(x=200, y=300, width=180, height=180, score=0.95)
        for width, height in self.REALISTIC_AND_AWKWARD:
            with self.subTest(size=f"{width}x{height}"):
                box = drama_face.face_centered_crop_box(image_width=width, image_height=height, face=face)
                cropped_width, cropped_height = _box_size(box)
                self.assertEqual(cropped_width * 4, cropped_height * 3)

    def test_a_frame_too_small_to_crop_fails_loudly(self) -> None:
        """不能静默返回 0 像素宽的裁剪结果。"""
        for width, height in self.TOO_SMALL_TO_CROP:
            with self.subTest(size=f"{width}x{height}"):
                with self.assertRaisesRegex(ValueError, "太小"):
                    drama_face.center_crop_box(image_width=width, image_height=height)

    def test_zero_or_negative_size_is_rejected(self) -> None:
        for width, height in ((0, 100), (100, 0), (-4, 100)):
            with self.subTest(size=f"{width}x{height}"):
                with self.assertRaises(ValueError):
                    drama_face.center_crop_box(image_width=width, image_height=height)

    def test_crop_box_stays_inside_the_frame(self) -> None:
        face = drama_face.FaceBox(x=5, y=5, width=120, height=120, score=0.9)
        for width, height in ((720, 1280), (1080, 1920), (400, 1200)):
            box = drama_face.face_centered_crop_box(image_width=width, image_height=height, face=face)
            self.assertGreaterEqual(box[0], 0)
            self.assertGreaterEqual(box[1], 0)
            self.assertLessEqual(box[2], width)
            self.assertLessEqual(box[3], height)

    def test_face_centered_crop_keeps_the_face_near_the_middle(self) -> None:
        width, height = 1080, 1920
        face = drama_face.FaceBox(x=800, y=200, width=150, height=150, score=0.9)
        box = drama_face.face_centered_crop_box(image_width=width, image_height=height, face=face)
        left, top, right, bottom = box
        self.assertLessEqual(left, face.center_x)
        self.assertGreaterEqual(right, face.center_x)
        self.assertLessEqual(top, face.center_y)
        self.assertGreaterEqual(bottom, face.center_y)

    def test_the_old_rounding_rule_would_have_failed_these_sizes(self) -> None:
        """留证：老写法在这两个尺寸上会得到不精确的 3:4。"""
        for width, height in ((136, 241), (137, 243)):
            old_height = round(width / (3 / 4))
            self.assertNotEqual(width * 4, old_height * 3)
            new_width, new_height = _box_size(
                drama_face.center_crop_box(image_width=width, image_height=height)
            )
            self.assertEqual(new_width * 4, new_height * 3)


class FaceScoringTests(unittest.TestCase):
    def test_single_clear_face_beats_a_crowd(self) -> None:
        single = (drama_face.FaceBox(x=400, y=600, width=300, height=300, score=0.95),)
        crowd = tuple(
            drama_face.FaceBox(x=40 + index * 90, y=900, width=80, height=80, score=0.95)
            for index in range(9)
        )
        self.assertGreater(
            drama_face.face_score(faces=single, image_width=1080, image_height=1920),
            drama_face.face_score(faces=crowd, image_width=1080, image_height=1920),
        )

    def test_no_face_scores_zero(self) -> None:
        self.assertEqual(0.0, drama_face.face_score(faces=(), image_width=1080, image_height=1920))

    def test_a_face_at_the_very_edge_scores_lower_than_a_centred_one(self) -> None:
        centred = (drama_face.FaceBox(x=440, y=760, width=200, height=200, score=0.9),)
        edge = (drama_face.FaceBox(x=0, y=760, width=200, height=200, score=0.9),)
        self.assertGreater(
            drama_face.face_score(faces=centred, image_width=1080, image_height=1920),
            drama_face.face_score(faces=edge, image_width=1080, image_height=1920),
        )

    def test_a_tiny_face_scores_lower_than_a_reasonable_one(self) -> None:
        tiny = (drama_face.FaceBox(x=500, y=900, width=24, height=24, score=0.9),)
        reasonable = (drama_face.FaceBox(x=440, y=760, width=220, height=220, score=0.9),)
        self.assertGreater(
            drama_face.face_score(faces=reasonable, image_width=1080, image_height=1920),
            drama_face.face_score(faces=tiny, image_width=1080, image_height=1920),
        )


class FrameChoiceTests(unittest.TestCase):
    def test_a_face_frame_wins_over_a_sharper_empty_frame(self) -> None:
        empty = _candidate_at(name="剧集-1.mp4", seconds=100.0, sharpness=900.0, face_score=0.0,
                              perceptual_key=(0,) * 16)
        with_face = _candidate_at(name="剧集-2.mp4", seconds=100.0, sharpness=40.0, face_score=0.9,
                                  frontal_score=0.95, perceptual_key=(9,) * 16)
        selection = choose_photo_set(candidates=(empty, with_face), count=1)
        self.assertEqual((with_face,), selection)

    def test_no_face_anywhere_still_returns_a_photo_instead_of_failing(self) -> None:
        dull = _candidate_at(name="剧集-1.mp4", seconds=10.0, sharpness=5.0, face_score=0.0,
                             perceptual_key=(1,) * 16)
        sharper = _candidate_at(name="剧集-2.mp4", seconds=400.0, sharpness=500.0, face_score=0.0,
                                perceptual_key=(7,) * 16)
        selection = choose_photo_set(candidates=(dull, sharper), count=1)
        self.assertEqual((sharper,), selection)

    def test_a_near_identical_frame_is_not_picked_twice(self) -> None:
        first = _candidate_at(name="剧集-1.mp4", seconds=50.0, sharpness=100.0, face_score=0.9,
                              frontal_score=0.90, perceptual_key=(5,) * 16)
        duplicate = _candidate_at(name="剧集-1.mp4", seconds=90.0, sharpness=100.0, face_score=0.95,
                                  frontal_score=0.95, perceptual_key=(5,) * 16)
        different = _candidate_at(name="剧集-2.mp4", seconds=90.0, sharpness=100.0, face_score=0.8,
                                  frontal_score=0.85, perceptual_key=(200,) * 16)
        selection = choose_photo_set(candidates=(first, duplicate, different), count=2)
        self.assertEqual(2, len(selection))
        # 两张几乎一样的画面只能留一张：留的是**更好的那前一张**（0.95），
        # 稍差的那张（0.9）被丢掉，位置让给不同来源的照片。
        self.assertIn(duplicate, selection)
        self.assertIn(different, selection)
        self.assertNotIn(first, selection)


def _candidate_at(*, name: str, seconds: float, sharpness: float, face_score: float,
                  perceptual_key: tuple[int, ...] | None = None, frontal_score: float = 0.0,
                  face_width: float = 200.0, eyes_closed: float = 0.0, mouth_open: float = 0.0,
                  smile: float = 0.0, expression_measured: bool = False) -> FrameCandidate:
    """A candidate from a named video, so source-identity rules can be tested."""
    key = perceptual_key if perceptual_key is not None else (int(seconds) % 255,) * 16
    return FrameCandidate(
        source=VideoSource(path=Path(f"C:/fake/{name}"), duration_seconds=600.0),
        time_seconds=seconds, width=1080, height=1920, sharpness=sharpness, exposure_penalty=0.0,
        perceptual_key=key, face_count=1 if face_score > 0 else 0, face_score=face_score,
        frontal_score=frontal_score if face_score > 0 else 0.0, face_width=face_width if face_score > 0 else 0.0,
        eyes_closed=eyes_closed, mouth_open=mouth_open, smile=smile, expression_measured=expression_measured,
    )


class SamplingWindowTests(unittest.TestCase):
    """新采样策略：把整批素材切成窗口，再全局挑最好的 10 张。"""

    def test_windows_cover_the_whole_timeline_without_gaps(self) -> None:
        windows = planned_windows(total_duration=5066.0, count=WINDOW_COUNT)
        self.assertEqual(WINDOW_COUNT, len(windows))
        self.assertAlmostEqual(0.0, windows[0][0])
        self.assertAlmostEqual(5066.0, windows[-1][1])
        for (start, end), (next_start, _next_end) in zip(windows, windows[1:]):
            self.assertLess(start, end)
            self.assertAlmostEqual(end, next_start)

    def test_a_single_drama_day_is_still_split_into_windows(self) -> None:
        """12 集、5000 秒也是分散取样的；老做法在 5000 秒里只取 10 个点。"""
        windows = planned_windows(total_duration=5066.0, count=WINDOW_COUNT)
        self.assertEqual(WINDOW_COUNT, len(windows))

    def test_invalid_input_is_rejected(self) -> None:
        for total, count in ((0.0, 12), (-5.0, 12), (100.0, 0)):
            with self.subTest(total=total, count=count):
                with self.assertRaises(ValueError):
                    planned_windows(total_duration=total, count=count)


class PhotoSetSelectionTests(unittest.TestCase):
    def test_it_fills_the_wall_with_the_best_photos(self) -> None:
        # 分散在多集里，每集不超过 MAX_PHOTOS_PER_VIDEO；正面分要过门槛（≥MIN_FRONTAL_SCORE）。
        candidates = [
            _candidate_at(name=f"剧集-{index % 6 + 1}.mp4", seconds=float(index * 30), sharpness=100.0,
                          face_score=0.8, frontal_score=1.0 - index * 0.008)
            for index in range(24)
        ]
        selection = choose_photo_set(candidates=candidates, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection))
        self.assertTrue(all(item.face_score >= 0.5 for item in selection))
        self.assertTrue(all(item.frontal_score >= 0.75 for item in selection))

    def test_a_candidate_below_the_frontal_gate_is_dropped(self) -> None:
        profile = _candidate_at(name="剧集-1.mp4", seconds=10.0, sharpness=900.0, face_score=0.99,
                                frontal_score=0.60)
        frontal = _candidate_at(name="剧集-2.mp4", seconds=10.0, sharpness=100.0, face_score=0.70,
                                frontal_score=0.95)
        selection = choose_photo_set(candidates=[profile, frontal], count=2)
        self.assertEqual((frontal,), selection)

    def test_relaxing_the_gate_recovers_a_candidate(self) -> None:
        profile = _candidate_at(name="剧集-1.mp4", seconds=10.0, sharpness=900.0, face_score=0.99,
                                frontal_score=0.60)
        selection = choose_photo_set(candidates=[profile], count=1, min_frontal_score=0.0)
        self.assertEqual((profile,), selection)

    def test_a_perfectly_frontal_face_beats_a_higher_raw_face_score(self) -> None:
        profile = _candidate_at(name="剧集-1.mp4", seconds=10.0, sharpness=900.0, face_score=0.95,
                                frontal_score=0.1)
        frontal = _candidate_at(name="剧集-2.mp4", seconds=10.0, sharpness=100.0, face_score=0.70,
                                frontal_score=1.0)
        selection = choose_photo_set(candidates=[profile, frontal], count=1)
        self.assertEqual((frontal,), selection)

    def test_a_tiny_face_is_never_picked(self) -> None:
        tiny = _candidate_at(name="剧集-1.mp4", seconds=10.0, sharpness=2000.0, face_score=0.95,
                             frontal_score=1.0, face_width=40.0)
        usable = _candidate_at(name="剧集-2.mp4", seconds=10.0, sharpness=100.0, face_score=0.6,
                               frontal_score=1.0, face_width=180.0)
        selection = choose_photo_set(candidates=[tiny, usable], count=2)
        self.assertEqual((usable,), selection)

    def test_one_video_cannot_supply_the_whole_wall(self) -> None:
        candidates = [
            _candidate_at(name="剧集-1.mp4", seconds=float(index * 60), sharpness=100.0,
                          face_score=0.9, frontal_score=1.0)
            for index in range(12)
        ]
        selection = choose_photo_set(candidates=candidates, count=PHOTO_COUNT)
        self.assertEqual(MAX_PHOTOS_PER_VIDEO, len(selection))

    def test_two_photos_from_the_same_moment_are_not_both_used(self) -> None:
        same_shot = [
            _candidate_at(name="剧集-1.mp4", seconds=100.0 + index * 0.5, sharpness=500.0, face_score=0.9,
                          frontal_score=1.0)
            for index in range(4)
        ]
        elsewhere = [
            _candidate_at(name=f"剧集-{index + 2}.mp4", seconds=300.0 + index * 60, sharpness=300.0,
                          face_score=0.7, frontal_score=0.9)
            for index in range(6)
        ]
        selection = choose_photo_set(candidates=same_shot + elsewhere, count=PHOTO_COUNT)
        close_pairs = [
            (left, right)
            for left in selection for right in selection
            if left is not right
            and left.source.path == right.source.path
            and 0 < abs(left.time_seconds - right.time_seconds) < MIN_SOURCE_GAP_SECONDS
        ]
        self.assertEqual([], close_pairs, "同一集里太近的两张不该同时入选")

    def test_it_reports_fewer_when_material_is_insufficient(self) -> None:
        selection = choose_photo_set(
            candidates=[_candidate_at(name=f"剧集-{index + 1}.mp4", seconds=float(index * 60),
                                      sharpness=100.0, face_score=0.9, frontal_score=1.0)
                        for index in range(3)],
            count=PHOTO_COUNT,
        )
        self.assertEqual(3, len(selection))

    def test_face_quality_outranks_sharpness(self) -> None:
        faceless_but_sharp = _candidate_at(name="剧集-1.mp4", seconds=10.0, sharpness=5000.0, face_score=0.0)
        face_but_soft = _candidate_at(name="剧集-2.mp4", seconds=10.0, sharpness=50.0, face_score=0.8,
                                      frontal_score=0.9)
        selection = choose_photo_set(candidates=[faceless_but_sharp, face_but_soft], count=1)
        self.assertEqual((face_but_soft,), selection)


class GuaranteedTenPhotosTests(unittest.TestCase):
    """用户 2026-09-18 明确："宁可 10 张里有些质量差，也不能少数量。"

    模板对剧照有三道硬校验（恰好 10 个文件 / 路径不重复 / SHA256 不重复），
    所以选图必须**永远凑满 10 张**，靠降级阶梯而不是报错。
    """

    def test_plenty_of_good_photos_uses_the_strict_rung(self) -> None:
        candidates = [
            _candidate_at(name=f"剧集-{index % 8 + 1}.mp4", seconds=float(index * 40), sharpness=100.0,
                          face_score=0.9, frontal_score=1.0 - index * 0.005, face_width=200.0)
            for index in range(40)
        ]
        selection, stage = select_photo_set(candidates=candidates, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection))
        self.assertEqual("strict", stage)

    def test_only_a_few_usable_photos_still_returns_ten(self) -> None:
        """只有 3 张像样的画面时，仍然必须给出 10 张。"""
        good = [
            _candidate_at(name=f"剧集-{index + 1}.mp4", seconds=float(index * 90), sharpness=100.0,
                          face_score=0.9, frontal_score=0.9, face_width=200.0)
            for index in range(3)
        ]
        selection, stage = select_photo_set(candidates=good, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection), "数量不足 10 张就不能交给模板")
        self.assertNotEqual("strict", stage, "只有 3 张可用时必然是降级档")
        self.assertEqual(3, len({item.source.path for item in selection}))

    def test_a_single_frame_still_returns_ten(self) -> None:
        only = [_candidate_at(name="剧集-1.mp4", seconds=10.0, sharpness=100.0, face_score=0.8,
                              frontal_score=0.8, face_width=200.0)]
        selection, stage = select_photo_set(candidates=only, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection))
        self.assertEqual("variants", stage)

    def test_no_candidates_is_the_only_hard_failure(self) -> None:
        with self.assertRaises(RuntimeError):
            select_photo_set(candidates=[], count=PHOTO_COUNT)

    def test_a_low_frontal_pool_drops_to_a_relaxed_rung(self) -> None:
        weak = [
            _candidate_at(name=f"剧集-{index % 5 + 1}.mp4", seconds=float(index * 50), sharpness=100.0,
                          face_score=0.6, frontal_score=0.60, face_width=200.0)
            for index in range(30)
        ]
        selection, stage = select_photo_set(candidates=weak, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection))
        self.assertIn(stage, {"relaxed_frontal", "relaxed_size", "relaxed_all"})
        self.assertTrue(all(item.frontal_score >= 0.55 for item in selection))

    def test_expression_gate_keeps_closed_eyes_out_of_the_strict_rung(self) -> None:
        blinking = [
            _candidate_at(name=f"剧集-{index % 4 + 1}.mp4", seconds=float(index * 60), sharpness=100.0,
                          face_score=0.9, frontal_score=0.95, face_width=200.0, eyes_closed=0.9,
                          expression_measured=True)
            for index in range(14)
        ]
        selection, stage = select_photo_set(candidates=blinking, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection))
        self.assertNotEqual("strict", stage, "全是闭眼时不应该算严格档")


class IdentityDeduplicationTests(unittest.TestCase):
    """同一位演员最多占 2 张（实测不加这条会 10 张里 3 张是同一人）。"""

    @staticmethod
    def _identity(seed: int):
        import numpy

        # 每个 seed 必须是**互不相同**的身份：早先用 seed % 4 让 0 和 4 撞成同一个人，
        # 结果"8 个人"实际只有 4 个，严格档自然凑不满 10 张（测试自己造成的假象）。
        vector = numpy.zeros(24, dtype=numpy.float32)
        vector[seed % 24] = 1.0

        class _Identity:
            def __init__(self) -> None:
                self.vector = vector

            def is_same_person(self, other: object) -> bool:
                return bool(numpy.dot(self.vector, other.vector) >= 0.5)

        return _Identity()

    def test_the_same_person_is_capped_in_the_strict_rung(self) -> None:
        """严格档必须守住"同一位演员最多 2 张"（人数够的时候）。"""
        candidates = []
        for person_index in range(8):
            identity = self._identity(person_index)
            for shot in range(3):
                candidate = _candidate_at(
                    name=f"剧集-{person_index * 3 + shot + 1}.mp4", seconds=float(shot * 90),
                    sharpness=100.0, face_score=0.9, frontal_score=0.95 - person_index * 0.01,
                    face_width=200.0,
                    # 画面指纹要彼此拉开（差异阈值是 8），否则会被"近似重复"规则挡掉——
                    # 那是另一条规则，不该在这里干扰身份上限的验证。
                    perceptual_key=((person_index * 3 + shot) * 10,) * 16,
                )
                object.__setattr__(candidate, "identity", identity)
                candidates.append(candidate)
        selection, stage = select_photo_set(candidates=candidates, count=PHOTO_COUNT)
        self.assertEqual("strict", stage, "8 个人、每人 3 张，严格档应该够用")
        self.assertEqual(PHOTO_COUNT, len(selection))
        counts: dict[int, int] = {}
        for item in selection:
            counts[id(item.identity)] = counts.get(id(item.identity), 0) + 1
        self.assertLessEqual(max(counts.values()), MAX_PHOTOS_PER_PERSON,
                             "同一位演员不该超过 2 张")

    def test_quantity_wins_over_the_person_cap_at_the_last_resort(self) -> None:
        """人数实在不够时，数量优先：允许同一个人多出现几次（用户要求 10 张不能少）。"""
        person = self._identity(0)
        other = self._identity(1)
        candidates = []
        for index in range(6):
            candidate = _candidate_at(name=f"剧集-{index + 1}.mp4", seconds=float(index * 70),
                                      sharpness=100.0, face_score=0.9, frontal_score=0.95, face_width=200.0)
            object.__setattr__(candidate, "identity", person if index < 3 else other)
            candidates.append(candidate)
        selection, stage = select_photo_set(candidates=candidates, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection), "必须凑满 10 张")
        self.assertNotEqual("strict", stage, "只有两个人时必然是降级档")

    def test_missing_identity_model_never_drops_candidates(self) -> None:
        candidates = [
            _candidate_at(name=f"剧集-{index % 6 + 1}.mp4", seconds=float(index * 50), sharpness=100.0,
                          face_score=0.9, frontal_score=0.95, face_width=200.0)
            for index in range(20)
        ]
        selection, stage = select_photo_set(candidates=candidates, count=PHOTO_COUNT)
        self.assertEqual(PHOTO_COUNT, len(selection))
        self.assertEqual("strict", stage, "身份模型不可用时不应影响正常挑选")


class PhotoCacheTests(unittest.TestCase):
    """剧照缓存按"账号+剧集"复用；素材变了必须自动重做。"""

    def test_fingerprint_changes_when_material_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "剧集-1.mp4"
            video.write_bytes(b"a" * 128)
            from server.template_engine.jianying59_template.photo_prep import material_fingerprint

            source = VideoSource(path=video, duration_seconds=10.0)
            first = material_fingerprint([source])
            self.assertEqual(first, material_fingerprint([source]), "同一素材的指纹必须稳定")
            video.write_bytes(b"b" * 256)
            self.assertNotEqual(first, material_fingerprint([source]), "素材变了指纹就要变")

    def test_cache_root_is_isolated_per_account_and_drama(self) -> None:
        from server.template_engine.jianying59_template.photo_prep import photo_cache_root

        data_root = Path("C:/系统数据")
        first = photo_cache_root(data_root, account="账号A", drama="剧集A")
        second = photo_cache_root(data_root, account="账号B", drama="剧集A")
        self.assertNotEqual(first, second, "不同账号绝不能共用同一份剧照")
        self.assertIn("账号A", str(first))

    def test_an_incomplete_cache_is_not_reused(self) -> None:
        from server.template_engine.jianying59_template.photo_prep import _cache_is_usable

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertFalse(_cache_is_usable(directory, count=PHOTO_COUNT), "空目录不算缓存")
            for index in range(3):
                (directory / f"剧集人物_{index + 1:03d}.jpg").write_bytes(b"x")
            self.assertFalse(_cache_is_usable(directory, count=PHOTO_COUNT), "只有 3 张不算可用缓存")

    def test_old_fingerprint_caches_are_pruned(self) -> None:
        """换素材会产生新指纹；旧的不能无限堆积。"""
        import os
        import time

        from server.template_engine.jianying59_template.photo_prep import prune_photo_cache

        with tempfile.TemporaryDirectory() as temporary:
            unit_root = Path(temporary)
            for index in range(5):
                directory = unit_root / f"fingerprint{index}"
                directory.mkdir()
                (directory / "剧集人物_001.jpg").write_bytes(b"x")
                stamp = time.time() - (5 - index) * 60
                os.utime(directory, (stamp, stamp))
            removed = prune_photo_cache(unit_root, keep=3)
            self.assertEqual(2, removed)
            self.assertEqual(3, len([p for p in unit_root.iterdir() if p.is_dir()]))


class CacheVerificationTests(unittest.TestCase):
    """缓存命中必须校验尺寸，不能盲信 —— 否则一个坏缓存会让任务永远失败。"""

    def _image(self, path: Path, size: tuple[int, int]) -> None:
        from PIL import Image

        Image.new("RGB", size, (120, 120, 120)).save(path, format="JPEG")

    def test_missing_file_is_not_accepted_as_a_cache_hit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(_is_exact_three_four(Path(temporary) / "不存在.jpg"))

    def test_a_bad_cache_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad = Path(temporary) / "照片墙_3x4_03_29648c8d701f.jpg"
            self._image(bad, (720, 961))          # 差一个像素，正是报错那条的形状
            self.assertFalse(_is_exact_three_four(bad))

    def test_a_good_cache_file_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            good = Path(temporary) / "照片墙_3x4_03_abc123.jpg"
            self._image(good, (720, 960))
            self.assertTrue(_is_exact_three_four(good))

    def test_rewriting_an_awkward_source_produces_an_exact_three_four_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "剧集人物_003.jpg"
            target = Path(temporary) / "照片墙_3x4_03_abc123.jpg"
            self._image(source, (136, 241))
            _write_exact_three_four(source, target)
            self.assertTrue(_is_exact_three_four(target))

    def test_rewriting_replaces_a_bad_cache_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "剧集人物_003.jpg"
            target = Path(temporary) / "照片墙_3x4_03_abc123.jpg"
            self._image(source, (1080, 1920))
            self._image(target, (721, 961))
            self.assertFalse(_is_exact_three_four(target))
            _write_exact_three_four(source, target)
            self.assertTrue(_is_exact_three_four(target))


class ModelResourceTests(unittest.TestCase):
    """模型必须随仓库分发：目标机器可能长期离线。"""

    def test_model_file_is_present_and_plausible(self) -> None:
        model = drama_face.model_path()
        self.assertTrue(model.is_file(), f"缺少人脸检测模型：{model}")
        self.assertGreater(model.stat().st_size, 100_000)
        self.assertLess(model.stat().st_size, 5_000_000)

    def test_license_file_is_present(self) -> None:
        license_file = drama_face.model_path().parent / "YuNet-LICENSE.txt"
        self.assertTrue(license_file.is_file(), "缺少模型许可证文件（MIT 要求随附版权声明）")
        self.assertIn("MIT", license_file.read_text(encoding="utf-8"))

    def test_detector_is_available_in_this_environment(self) -> None:
        self.assertTrue(drama_face.detector_available(), "本机应能加载 YuNet 检测器")

    def test_empty_input_returns_no_faces_instead_of_raising(self) -> None:
        self.assertEqual((), drama_face.detect_faces(None))


if __name__ == "__main__":
    unittest.main()
