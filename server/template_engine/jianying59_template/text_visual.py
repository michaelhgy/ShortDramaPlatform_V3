"""The two static text anchors for the native Jianying 5.9 template.

This is deliberately plain Jianying text.  It does not borrow historical
flower-text resources, and it does not create the retired notice/prompt track.
The two text anchors are added above the existing effects and sticker tracks:
one blessing in the upper photo-wall band and one series CTA in the lower band.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from pyJianYingDraft import (
    ClipSettings,
    DraftFolder,
    TextBorder,
    TextSegment,
    TextShadow,
    TextStyle,
    Timerange,
    TrackType,
)

from .project_base import T00ProjectPlan


# These are the approved historical content pools.  The former notice pool is
# intentionally absent: product has retired that third text track.
BLESSING_COPY = (
    "愿您身体健康",
    "愿您平安喜乐",
    "愿您福气常伴",
    "愿您万事顺心",
    "愿您幸福安康",
    "祝您笑口常开",
    "愿您每天都开心",
    "愿您日子越过越好",
    "愿您所遇皆温柔",
    "愿好故事陪伴您",
)
DRAMA_PROMPT_COPY = (
    "左下角免费看全集",
    "左下角免费看后续",
    "左下角免费看结局",
    "左下角免费继续看",
    "左下角免费接着看",
    "点免费剧集看全集",
    "点免费剧集看后续",
    "免费剧集接着看",
    "免费剧集看结局",
    "点击下方继续追剧",
)

BLESSING_TRACK_NAME = "T09_BLESSING_UPPER_ANCHOR"
DRAMA_PROMPT_TRACK_NAME = "T10_DRAMA_PROMPT_LOWER_ANCHOR"
FULL_DURATION_US = 180_000_000

# Plain-text size is stored directly in the text content.  Keeping a five-unit
# gap yields a ten-unit UI text-size gap in the native serializer, preserving
# the old rule that the drama CTA is 10 px stronger than the blessing.
BLESSING_FONT_SIZE = 48.0
DRAMA_PROMPT_FONT_SIZE = 53.0


@dataclass(frozen=True)
class TextAnchor:
    category: str
    track_name: str
    text: str
    transform_x: float
    transform_y: float
    font_size: float
    target_height_px: int
    rotation_degrees: float


@dataclass(frozen=True)
class TextVisualDecision:
    seed: int
    anchors: tuple[TextAnchor, TextAnchor]
    duration_seconds: int
    retired_categories: tuple[str, ...] = ("notice",)
    animation: str = "none_static_full_duration"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def decide_text_visual(*, seed: int, duration_seconds: int) -> TextVisualDecision:
    """Select copy only; geometry remains a stable, readable two-anchor layout."""
    if duration_seconds != 180:
        raise ValueError("文字视觉当前只适用于已确认的 180 秒模板")
    rng = random.Random(f"{seed}:static-text-anchors")
    return TextVisualDecision(
        seed=seed,
        duration_seconds=duration_seconds,
        anchors=(
            TextAnchor(
                category="blessing",
                track_name=BLESSING_TRACK_NAME,
                text=rng.choice(BLESSING_COPY),
                # Stay inside every allowed upper band even when T01 chooses
                # its tallest central window (77% of the canvas height).
                transform_x=-0.08,
                transform_y=0.82,
                font_size=BLESSING_FONT_SIZE,
                target_height_px=124,
                rotation_degrees=0.0,
            ),
            TextAnchor(
                category="drama_prompt",
                track_name=DRAMA_PROMPT_TRACK_NAME,
                text=rng.choice(DRAMA_PROMPT_COPY),
                # The copy may say "left bottom" for the platform CTA, but
                # the rendered text lives right of centre so it never covers
                # the platform's real lower-left mounting area.
                transform_x=0.22,
                transform_y=-0.81,
                font_size=DRAMA_PROMPT_FONT_SIZE,
                target_height_px=134,
                rotation_degrees=0.0,
            ),
        ),
    )


def _text_segment(anchor: TextAnchor, duration_seconds: int) -> TextSegment:
    is_prompt = anchor.category == "drama_prompt"
    return TextSegment(
        anchor.text,
        Timerange(0, duration_seconds * 1_000_000),
        style=TextStyle(
            size=anchor.font_size,
            bold=True,
            # The warmer blessing remains secondary; the CTA stays clean white.
            color=(1.0, 0.94, 0.76) if not is_prompt else (1.0, 1.0, 1.0),
            align=1,
            auto_wrapping=False,
            max_line_width=0.82,
        ),
        clip_settings=ClipSettings(
            rotation=anchor.rotation_degrees,
            transform_x=anchor.transform_x,
            transform_y=anchor.transform_y,
        ),
        # A dark outline and shadow make the fixed text readable over the
        # moving photo wall without inventing a themed banner resource.
        border=TextBorder(color=(0.04, 0.04, 0.04), width=40.0),
        shadow=TextShadow(
            color=(0.0, 0.0, 0.0), alpha=0.68, diffuse=12.0, distance=5.0
        ),
    )


def create_text_visual_draft(
    *,
    draft_root: Path,
    source_draft_name: str,
    output_draft_name: str,
    plan: T00ProjectPlan,
) -> TextVisualDecision:
    """Duplicate an accepted native base draft and append the two text tracks.

    The source is never modified.  No old donor, flower-text ID, notice text,
    animation, or sticker/resource lookup is involved.
    """
    if plan.duration_seconds * 1_000_000 != FULL_DURATION_US:
        raise ValueError("文字轨必须覆盖完整 180 秒模板")
    decision = decide_text_visual(seed=plan.seed, duration_seconds=plan.duration_seconds)
    folder = DraftFolder(str(draft_root))
    if not folder.has_draft(source_draft_name):
        raise FileNotFoundError(f"找不到文字试写的源草稿: {source_draft_name}")
    if folder.has_draft(output_draft_name):
        raise FileExistsError(f"文字试写草稿已存在，拒绝覆盖: {output_draft_name}")

    project = folder.duplicate_as_template(source_draft_name, output_draft_name)
    try:
        for anchor in decision.anchors:
            project.add_track(TrackType.text, anchor.track_name, absolute_index=15_000)
            project.add_segment(
                _text_segment(anchor, plan.duration_seconds), anchor.track_name
            )
        project.save()
    except Exception:
        # The copied draft is intentionally left in place for recovery and
        # diagnosis; never delete user-visible draft data as rollback.
        raise
    return decision
