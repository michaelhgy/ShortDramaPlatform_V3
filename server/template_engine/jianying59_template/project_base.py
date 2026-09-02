"""T00 project-start contract for the native Jianying 5.9 template generator."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from server.tool_resolver import resolve_ffprobe
from server.runtime_process import no_window_kwargs


CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 2400
FRAME_RATE = 30
# Product decision made after the historical specification: template duration
# is fixed to three minutes.  The seed still controls every later track choice.
TEMPLATE_DURATION_SECONDS = 180


@dataclass(frozen=True)
class VideoProbe:
    path: Path
    width: int
    height: int
    duration_seconds: float


@dataclass(frozen=True)
class T00ProjectPlan:
    seed: int
    canvas_width: int = CANVAS_WIDTH
    canvas_height: int = CANVAS_HEIGHT
    frame_rate: int = FRAME_RATE
    duration_seconds: int = TEMPLATE_DURATION_SECONDS
    duration_mode: str = "fixed_180_seconds_by_product_decision"
    all_video_segments_muted: bool = True
    short_media_policy: str = "repeat_segments_never_stretch"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def build_t00_plan(seed: int) -> T00ProjectPlan:
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("随机种子必须是非负整数")
    return T00ProjectPlan(seed=seed)


def probe_video(path: Path, *, ffprobe_bin: str | None = None) -> VideoProbe:
    """Read the real media dimensions required by the T00 input contract."""
    command = [
        ffprobe_bin or str(resolve_ffprobe()),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20, **no_window_kwargs())
    if result.returncode != 0:
        raise ValueError(f"ffprobe无法读取视频 {path.name}: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(payload["format"]["duration"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"ffprobe结果不完整: {path.name}") from error
    if width <= 0 or height <= 0 or duration <= 0:
        raise ValueError(f"视频尺寸或时长无效: {path.name}")
    return VideoProbe(path=path, width=width, height=height, duration_seconds=duration)


def select_three_portrait_videos(probes: Iterable[VideoProbe]) -> tuple[VideoProbe, VideoProbe, VideoProbe]:
    """Keep source order, skip invalid orientations, and fail instead of degrading."""
    selected = [item for item in probes if item.height > item.width]
    if len(selected) < 3:
        raise ValueError(f"竖屏视频不足3条：仅找到{len(selected)}条；不得使用横屏或方形素材降级")
    return selected[0], selected[1], selected[2]


def create_native_t00_draft(*, draft_root: Path, draft_name: str, plan: T00ProjectPlan):
    """Create the one native 5.9 draft/timeline that later tracks populate.

    T00 intentionally adds no visible layer.  The eventual duration becomes
    visible once T01 writes the first repeated video segments.
    """
    if not draft_name or draft_name.strip() != draft_name:
        raise ValueError("草稿名不能为空，且首尾不能有空格")
    from pyJianYingDraft import DraftFolder

    return DraftFolder(str(draft_root)).create_draft(
        draft_name,
        plan.canvas_width,
        plan.canvas_height,
        plan.frame_rate,
    )
