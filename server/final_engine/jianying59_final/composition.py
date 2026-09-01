"""Native Jianying 5.9 composition plan, writer and structural validation.

This module deliberately owns finished-video business geometry.  It uses the
same native draft creation boundary as the accepted template generator, while
the old donor-based writer remains only a migration reference.
"""

from __future__ import annotations

import json
import secrets
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .visual_layers import append_visual_layers, plan_global_layers, plan_visual_layers


US = 1_000_000
CANVAS = {"width": 1080, "height": 2400}
MIRROR_FEATHER = 0.09
MAIN_MASK_FEATHER_UI = 3.0
MAIN_MASK_FEATHER = MAIN_MASK_FEATHER_UI / 100
ACCOUNT_TEXT_SCALE = 0.4
ACCOUNT_TEXT_ALPHA = 0.5
DISCLOSURE_TEXT_ALPHA = 0.6
ACCOUNT_MOTION_CYCLE_US = 32 * US
DISCLAIMER_TEXT_SIZE = 15.0
DISCLAIMER_TEXT_SCALE = 0.4
MIDROLL_INSERT_US = 120 * US
VIRAL_BASELINE_WIDTH = 9.0
VIRAL_BASELINE_HEIGHT = 16.0
GEOMETRY_SAFETY_FACTOR = 1.05

# Jianying positions text by its material anchor, not the visible glyph bounds.
# These calibrated center offsets must be applied to each template's actual
# track-1 rectangle rather than to a fixed canvas position.
WARNING_CENTER_INSET_X = 0.364592593
WARNING_CENTER_INSET_Y = 0.033
AI_CENTER_INSET_X = 0.065
AI_VISIBLE_BOTTOM_OVERHANG = 0.092
AI_BOTTOM_SAFE_GAP = 0.020
AI_CENTER_INSET_Y = AI_VISIBLE_BOTTOM_OVERHANG + AI_BOTTOM_SAFE_GAP


@dataclass(frozen=True)
class Media:
    path: Path
    width: int
    height: int
    duration_us: int


def probe_media(path: Path, *, audio_only: bool = False) -> Media:
    selector = "a:0" if audio_only else "v:0"
    entries = "format=duration" if audio_only else "stream=width,height,duration:format=duration"
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", selector, "-show_entries", entries, "-of", "json", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=20,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"ffprobe无法读取媒体：{path}")
    try:
        payload = json.loads(result.stdout)
        stream = payload.get("streams", [{}])[0]
        duration_seconds = stream.get("duration") if not audio_only else None
        if duration_seconds in (None, "N/A", ""):
            duration_seconds = payload["format"]["duration"]
        duration_us = round(float(duration_seconds) * US)
        width = 0 if audio_only else int(stream["width"])
        height = 0 if audio_only else int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"ffprobe结果不完整：{path.name}") from exc
    if duration_us <= 0 or (not audio_only and (width <= 0 or height <= 0)):
        raise ValueError(f"媒体尺寸或时长无效：{path.name}")
    return Media(path=path.resolve(), width=width, height=height, duration_us=duration_us)


def _pairing_window(pairing: dict[str, Any]) -> dict[str, dict[str, float]]:
    v2_template_format = pairing.get("kind") == "v2_template_pairing" and pairing.get("schema_version") == 1
    current_59_format = pairing.get("schema") == "jianying59_template_pairing_v1"
    legacy_format = pairing.get("canvas") == CANVAS and not v2_template_format and not current_59_format
    if not legacy_format and not current_59_format and not v2_template_format:
        raise ValueError("模板配对参数画布不是1080x2400")
    if (current_59_format or v2_template_format) and "canvas" in pairing and pairing["canvas"] != CANVAS:
        raise ValueError("模板配对参数画布不是1080x2400")
    try:
        window = pairing["central_window"]
        if legacy_format:
            rectangle = {
                "width": float(window["half_extent"]["x"]),
                "height": float(window["half_extent"]["y"]),
                "center_x": 0.0,
                "center_y": 0.0,
                "feather": float(window["feather"]),
            }
            text_window = {
                "width": float(window["half_extent"]["x"]),
                "height": float(window["half_extent"]["y"]),
                "center_x": 0.0,
                "center_y": 0.0,
            }
        elif current_59_format:
            source_mask = window["source_mask"]
            geometry = window["geometry"]
            rectangle = {
                "width": float(source_mask["width"]),
                "height": float(source_mask["height"]),
                "center_x": float(source_mask.get("center_x", 0.0)),
                "center_y": float(source_mask.get("center_y", 0.0)),
                "feather": float(source_mask.get("feather", window["feather"])),
            }
            text_window = {
                "width": rectangle["width"] * float(geometry["cover_scale"]),
                "height": rectangle["height"],
                "center_x": rectangle["center_x"],
                "center_y": rectangle["center_y"],
            }
        else:
            # V2 template jobs persist the already-resolved central-window
            # ratios.  These are the same-source values required by finished
            # composition; do not require callers to regenerate a template
            # merely because an older field layout was expected here.
            rectangle = {
                "width": float(window["width_ratio"]),
                "height": float(window["height_ratio"]),
                "center_x": 0.0,
                "center_y": 0.0,
                "feather": float(window["feather"]),
            }
            text_window = dict(rectangle)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("模板配对参数缺少当前中央窗口几何信息") from exc
    if not 0 < rectangle["width"] <= 1 or not 0 < rectangle["height"] <= 1 or not 0 <= rectangle["feather"] <= 1:
        raise ValueError("模板配对参数中央窗口范围无效")
    return {
        "rectangle": rectangle,
        "text_window": text_window,
        "template_display": {
            "width": float(geometry.get("display_width", CANVAS["width"] * geometry.get("cover_scale", 1.0))) if current_59_format else float(CANVAS["width"]),
            "height": float(geometry.get("display_height", CANVAS["height"])) if current_59_format else float(CANVAS["height"]),
        },
    }


def _display_height(media: Media, scale: float) -> float:
    return CANVAS["width"] * scale * media.height / media.width


def _display_size(media: Media, scale: float) -> dict[str, float]:
    width = CANVAS["width"] * scale
    return {"width": width, "height": width * media.height / media.width}


def _viral_baseline_display_height() -> float:
    """Return the verified 9:16 viral display height for the current canvas."""
    return CANVAS["width"] * VIRAL_BASELINE_HEIGHT / VIRAL_BASELINE_WIDTH


def _required_viral_display_height(window_height: float) -> float:
    """Keep both the verified 9:16 baseline and the feather safety margin."""
    return max(_viral_baseline_display_height(), float(window_height) * GEOMETRY_SAFETY_FACTOR)


def _viral_rectangle_geometry(
    media: Media,
    *,
    window_px: dict[str, float],
    source_rectangle: dict[str, float],
    preserve_viral_baseline: bool,
) -> dict[str, Any]:
    natural_display = _display_size(media, 1.0)
    required_display_height = float(window_px["height"])
    if preserve_viral_baseline:
        # Cropped proxies retain the verified 9:16 baseline plus a small
        # central-window-relative margin for the two feathered mask joins.
        required_display_height = _required_viral_display_height(required_display_height)
    scale = max(1.0, required_display_height / natural_display["height"])
    display = _display_size(media, scale)
    rectangle = {
        "width": round(float(window_px["width"]) / display["width"], 9),
        "height": round(float(window_px["height"]) / display["height"], 9),
        "center_x": float(source_rectangle["center_x"]),
        "center_y": float(source_rectangle["center_y"]),
        "feather": MAIN_MASK_FEATHER,
        "invert": False,
    }
    return {
        "scale": round(scale, 9),
        "display": display,
        "rectangle": rectangle,
    }


def _main_sections(
    viral: Media,
    midroll: Media,
    endroll: Media,
    *,
    window_px: dict[str, float],
    source_rectangle: dict[str, float],
) -> list[dict[str, Any]]:
    if viral.duration_us <= MIDROLL_INSERT_US:
        # A shorter cleaned source has no valid 120-second insertion point.
        # Keep its full plot content and append only the required end-roll.
        sections = [
            ("viral", viral, 0, viral.duration_us),
            ("endroll", endroll, 0, endroll.duration_us),
        ]
    else:
        sections = [
            ("viral", viral, 0, MIDROLL_INSERT_US),
            ("midroll", midroll, 0, midroll.duration_us),
            ("viral", viral, MIDROLL_INSERT_US, viral.duration_us - MIDROLL_INSERT_US),
            ("endroll", endroll, 0, endroll.duration_us),
        ]
    cursor = 0
    result = []
    for role, media, source_start, duration in sections:
        if duration <= 0:
            raise ValueError(f"{role}没有可用时长")
        geometry = _viral_rectangle_geometry(
            media,
            window_px=window_px,
            source_rectangle=source_rectangle,
            preserve_viral_baseline=role == "viral",
        )
        result.append({
            "role": role,
            "path": str(media.path),
            "target_start_us": cursor,
            "duration_us": duration,
            "source_start_us": source_start,
            "scale": geometry["scale"],
            "display": geometry["display"],
            "rectangle": geometry["rectangle"],
        })
        cursor += duration
    return result


def _loop_sections(media: Media, total_us: int, template_mask: dict[str, float]) -> list[dict[str, Any]]:
    sections = []
    cursor = 0
    while cursor < total_us:
        duration = min(media.duration_us, total_us - cursor)
        sections.append({
            "path": str(media.path),
            "target_start_us": cursor,
            "duration_us": duration,
            "source_start_us": 0,
            "rectangle": template_mask,
        })
        cursor += duration
    return sections


def _disclaimer_positions(window: dict[str, float]) -> dict[str, dict[str, float]]:
    """Calculate text material centers from the current track-1 rectangle."""
    return {
        "imitation_warning": {
            "x": round(window["center_x"] - window["width"] + WARNING_CENTER_INSET_X, 9),
            "y": round(window["center_y"] + window["height"] - WARNING_CENTER_INSET_Y, 9),
        },
        "ai_disclosure": {
            "x": round(window["center_x"] + window["width"] - AI_CENTER_INSET_X, 9),
            "y": round(window["center_y"] - window["height"] + AI_CENTER_INSET_Y, 9),
        },
    }


def build_plan(*, viral: Media, template: Media, pairing: dict[str, Any], account_id: str, midroll: Media, endroll: Media, bgm: Media, bgm_id: str, bgm_title: str, real_photo_dir: Path | None = None, real_photo_files: list[Path] | None = None, visual_seed: int | None = None) -> dict[str, Any]:
    """Calculate the fixed finished-video timeline without a donor draft."""
    if not account_id.strip():
        raise ValueError("账号ID不能为空")
    pairing_geometry = _pairing_window(pairing)
    source_rectangle = pairing_geometry["rectangle"]
    text_window = pairing_geometry["text_window"]
    template_display = pairing_geometry["template_display"]
    central_window_px = {
        "width": round(source_rectangle["width"] * template_display["width"], 9),
        "height": round(source_rectangle["height"] * template_display["height"], 9),
    }
    paired_height_px = min(text_window["height"] * CANVAS["height"] + 20.0, CANVAS["height"] - 16.0)
    template_mask = {
        "width": 1.0,
        "height": round(min(paired_height_px + 20.0, CANVAS["height"]) / CANVAS["height"], 9),
        "feather": source_rectangle["feather"],
        "invert": True,
    }
    main = _main_sections(
        viral,
        midroll,
        endroll,
        window_px=central_window_px,
        source_rectangle=source_rectangle,
    )
    main_mask = dict(main[0]["rectangle"])
    total_us = sum(int(section["duration_us"]) for section in main)
    midroll_inserted = any(section["role"] == "midroll" for section in main)
    generated_seed = int(visual_seed) if visual_seed is not None else secrets.randbits(63)
    visual_tracks: dict[str, Any] = {}
    if real_photo_dir is not None:
        visual_tracks = {
            "global_layers": plan_global_layers(seed=generated_seed),
            "real_photo": plan_visual_layers(photo_dir=real_photo_dir, photo_files=real_photo_files, duration_us=total_us, seed=generated_seed),
        }
    plan = {
        "schema": "jianying59_final_composition_v1",
        "canvas": CANVAS,
        "source": str(viral.path),
        "template": str(template.path),
        "pairing": pairing.get("template_identity", pairing.get("template", {})),
        "duration_us": total_us,
        "decisions": {
            "midroll": {
                "status": "inserted" if midroll_inserted else "skipped_short_source",
                "threshold_seconds": MIDROLL_INSERT_US // US,
                "cleaned_viral_duration_seconds": round(viral.duration_us / US, 6),
            },
        },
        "geometry": {
            "source_rectangle": source_rectangle,
            "text_window": text_window,
            "central_window_px": central_window_px,
            "viral_baseline_display_height": _viral_baseline_display_height(),
            "paired_height_px": paired_height_px,
            "template_mask": template_mask,
            "main_mask": main_mask,
        },
        "tracks": {
            "main": main,
            "template": _loop_sections(template, total_us, template_mask),
            "account_id": {"text": account_id, "motion_path": [[-0.72, -0.55], [0.72, -0.20], [-0.72, 0.20], [0.72, 0.55], [-0.72, -0.55]]},
            "disclaimers": ["影视效果请勿模仿", "内容由AI制作"],
            "disclaimer_positions": _disclaimer_positions(text_window),
            "bgm": {"path": str(bgm.path), "music_id": bgm_id, "title": bgm_title or bgm.path.stem},
            **visual_tracks,
        },
    }
    validate_plan(plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema") != "jianying59_final_composition_v1" or plan.get("canvas") != CANVAS:
        raise ValueError("成片5.9计划协议或画布异常")
    tracks = plan.get("tracks") or {}
    main = list(tracks.get("main") or [])
    template = list(tracks.get("template") or [])
    roles = [item.get("role") for item in main]
    if roles not in (["viral", "midroll", "viral", "endroll"], ["viral", "endroll"]):
        raise ValueError("成片主轨必须是爆款-中插-爆款-尾插，或短素材的爆款-尾插")
    midroll = (plan.get("decisions") or {}).get("midroll")
    if not isinstance(midroll, dict):
        raise ValueError("成片缺少中插决定记录")
    expected_midroll_status = "inserted" if "midroll" in roles else "skipped_short_source"
    if midroll.get("status") != expected_midroll_status:
        raise ValueError("成片中插决定与主轨不一致")
    main_mask = (plan.get("geometry") or {}).get("main_mask")
    if not isinstance(main_mask, dict) or main_mask.get("invert") is not False:
        raise ValueError("成片主轨必须使用非反转矩形蒙版")
    for item in main:
        rectangle = item.get("rectangle")
        if not isinstance(rectangle, dict) or rectangle.get("invert") is not False:
            raise ValueError("成片主轨每段都必须使用非反转矩形蒙版")
        if not 0 < float(rectangle.get("width", 0)) <= 1 or not 0 < float(rectangle.get("height", 0)) <= 1:
            raise ValueError("成片主轨矩形蒙版尺寸异常")
        if float(rectangle.get("feather", -1)) != MAIN_MASK_FEATHER:
            raise ValueError("成片主轨矩形蒙版羽化必须为界面值3")
        if item.get("role") == "viral":
            display = item.get("display") or {}
            try:
                display_height = float(display["height"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("爆款主轨显示高度异常") from exc
            geometry = plan.get("geometry") or {}
            window = geometry.get("central_window_px") or {}
            try:
                required_display_height = _required_viral_display_height(float(window["height"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("成片缺少中央窗口高度") from exc
            if display_height + 1e-6 < required_display_height:
                raise ValueError("爆款主轨未保留几何安全余量")
    total = int(plan.get("duration_us") or 0)
    if total <= 0 or sum(int(item.get("duration_us") or 0) for item in main) != total:
        raise ValueError("成片主轨时长异常")
    cursor = 0
    for item in template:
        start = item.get("target_start_us")
        duration = item.get("duration_us")
        if not isinstance(start, int) or start != cursor or not isinstance(duration, int) or duration <= 0:
            raise ValueError("模板视频未连续覆盖成片时长")
        cursor += duration
    if cursor != total:
        raise ValueError("模板视频未完整循环覆盖成片")
    if not str((tracks.get("account_id") or {}).get("text") or "").strip() or len(tracks.get("disclaimers") or []) != 2:
        raise ValueError("成片缺少账号ID或两条合规提示")
    if not str((tracks.get("bgm") or {}).get("path") or ""):
        raise ValueError("成片缺少BGM")
    global_layers = tracks.get("global_layers")
    real_photo = tracks.get("real_photo")
    if (global_layers is None) != (real_photo is None):
        raise ValueError("成片视觉层不完整")
    if global_layers is not None:
        effects = list(global_layers.get("effects") or [])
        if len(effects) != 2 or len({str(item.get("resource_id")) for item in effects}) != 2:
            raise ValueError("成片必须有两个不同的全长画面特效")
        photos = list(real_photo.get("photos") or [])
        if len(photos) != 6 or len({str(item.get("path")) for item in photos}) != 6:
            raise ValueError("真人组合片段必须使用6张不同图片")
        if float(real_photo.get("alpha", -1)) != 0.02 or int(real_photo.get("duration_us") or 0) != total:
            raise ValueError("真人组合片段透明度或时长不符合规则")
        if (real_photo.get("grid") or {}).get("columns") != 2 or (real_photo.get("grid") or {}).get("rows") != 3:
            raise ValueError("真人组合片段必须是2列3行")


def _add_video_segments(draft: Any, track_name: str, segments: list[dict[str, Any]], *, template: bool) -> None:
    from pyJianYingDraft import ClipSettings, MaskType, Timerange, TrackType, VideoMaterial, VideoSegment

    draft.add_track(TrackType.video, track_name)
    for item in segments:
        material = VideoMaterial(str(item["path"]))
        settings = ClipSettings(scale_x=1.0, scale_y=1.0) if template else ClipSettings(scale_x=float(item["scale"]), scale_y=float(item["scale"]))
        segment = VideoSegment(
            material,
            Timerange(int(item["target_start_us"]), int(item["duration_us"])),
            source_timerange=Timerange(int(item["source_start_us"]), int(item["duration_us"])),
            volume=0.0 if template else 1.0,
            clip_settings=settings,
        )
        if template:
            mask = item["rectangle"]
            segment.add_mask(MaskType.矩形, center_x=0.0, center_y=0.0, size=float(mask["height"]), rect_width=float(mask["width"]), feather=float(mask["feather"]) * 100, invert=True)
        else:
            mask = item["rectangle"]
            segment.add_mask(
                MaskType.矩形,
                center_x=float(mask["center_x"]),
                center_y=float(mask["center_y"]),
                size=float(mask["height"]),
                rect_width=float(mask["width"]),
                feather=float(mask["feather"]) * 100,
                invert=False,
            )
        draft.add_segment(segment, track_name)


def _latest_cache_payload(root: Path, label: str) -> Path:
    payloads = sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.stat().st_mtime, reverse=True) if root.is_dir() else []
    if not payloads:
        raise RuntimeError(f"当前剪映5.9未找到{label}本地资源，不能生成成片")
    return payloads[0]


def _attach_native_mask_paths(content_path: Path, user_data_root: Path) -> None:
    """Bind masks to the live 5.9 cache as the accepted template writer does."""
    from pyJianYingDraft import MaskType

    document = json.loads(content_path.read_text(encoding="utf-8"))
    materials = document.get("materials") or {}
    masks = list(materials.get("masks") or materials.get("common_mask") or [])
    if not masks:
        raise RuntimeError("5.9原生写入后未找到蒙版材料")
    required = {"rectangle": _latest_cache_payload(user_data_root / "Cache" / "effect" / "636077", "矩形蒙版")}
    found: set[str] = set()
    for mask in masks:
        resource_type = str(mask.get("resource_type") or "")
        if resource_type in required:
            mask["path"] = required[resource_type].as_posix()
            found.add(resource_type)
    if found != set(required):
        raise RuntimeError("5.9原生写入后缺少矩形或镜面蒙版")
    if "masks" in materials:
        materials["masks"] = masks
    else:
        materials["common_mask"] = masks
    content_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _overlay_specs(tracks: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the fixed visual contract for composition-only text overlays."""
    return [
        {
            "name": "F07_ACCOUNT_ID",
            "text": str(tracks["account_id"]["text"]),
            "x": -0.72,
            "y": -0.55,
            "alpha": ACCOUNT_TEXT_ALPHA,
            "scale": ACCOUNT_TEXT_SCALE,
            "motion_path": list(tracks["account_id"]["motion_path"]),
        },
        {
            "name": "F08_WARNING",
            "text": str(tracks["disclaimers"][0]),
            "x": float(tracks["disclaimer_positions"]["imitation_warning"]["x"]),
            "y": float(tracks["disclaimer_positions"]["imitation_warning"]["y"]),
            "alpha": DISCLOSURE_TEXT_ALPHA,
            "scale": DISCLAIMER_TEXT_SCALE,
        },
        {
            "name": "F09_AI_DISCLOSURE",
            "text": "内\n容\n由\nA\nI\n制\n作",
            "x": float(tracks["disclaimer_positions"]["ai_disclosure"]["x"]),
            "y": float(tracks["disclaimer_positions"]["ai_disclosure"]["y"]),
            "alpha": DISCLOSURE_TEXT_ALPHA,
            "scale": DISCLAIMER_TEXT_SCALE,
        },
    ]


def _account_motion_keyframes(path: list[list[float]], duration_us: int) -> list[tuple[int, float, float]]:
    """Repeat the closed four-point account path and always return to its origin."""
    if len(path) != 5 or path[0] != path[-1] or duration_us <= 0:
        raise ValueError("账号文字移动路径必须是闭合四点路径")
    points = [(float(x), float(y)) for x, y in path]
    keyframes: list[tuple[int, float, float]] = []
    cursor = 0
    while cursor < duration_us:
        cycle = min(ACCOUNT_MOTION_CYCLE_US, duration_us - cursor)
        for index, (x, y) in enumerate(points):
            offset = cursor + (cycle * index // (len(points) - 1))
            if keyframes and offset == keyframes[-1][0]:
                continue
            keyframes.append((offset, x, y))
        cursor += cycle
    return keyframes


def write_native_draft(*, plan: dict[str, Any], draft_root: Path, draft_name: str, user_data_root: Path) -> Path:
    """Create a new native draft once.  Existing drafts are never overwritten."""
    validate_plan(plan)
    target = draft_root / draft_name
    if target.exists():
        raise FileExistsError(f"成片草稿已存在，拒绝覆盖：{target}")
    from pyJianYingDraft import ClipSettings, DraftFolder, KeyframeProperty, TextSegment, TextStyle, Timerange, TrackType

    tracks = plan["tracks"]
    folder = DraftFolder(str(draft_root))
    draft = folder.create_draft(draft_name, CANVAS["width"], CANVAS["height"], fps=30)
    _add_video_segments(draft, "F01_VIRAL_MAIN", list(tracks["main"]), template=False)
    _add_video_segments(draft, "F02_TEMPLATE_LOOP", list(tracks["template"]), template=True)
    duration = int(plan["duration_us"])
    for spec in _overlay_specs(tracks):
        name = str(spec["name"])
        draft.add_track(TrackType.text, name)
        segment = TextSegment(
            str(spec["text"]),
            Timerange(0, duration),
            style=TextStyle(size=DISCLAIMER_TEXT_SIZE, alpha=float(spec["alpha"])),
            clip_settings=ClipSettings(
                scale_x=float(spec["scale"]),
                scale_y=float(spec["scale"]),
                transform_x=float(spec["x"]),
                transform_y=float(spec["y"]),
            ),
        )
        if name == "F07_ACCOUNT_ID":
            for offset, x, y in _account_motion_keyframes(list(spec["motion_path"]), duration):
                segment.add_keyframe(KeyframeProperty.position_x, offset, x)
                segment.add_keyframe(KeyframeProperty.position_y, offset, y)
        draft.add_segment(segment, name)
    try:
        from pyJianYingDraft import AudioMaterial, AudioSegment
        draft.add_track(TrackType.audio, "F10_BGM")
        audio = AudioMaterial(str(tracks["bgm"]["path"]))
        cursor = 0
        while cursor < duration:
            clip_duration = min(audio.duration, duration - cursor)
            draft.add_segment(AudioSegment(audio, Timerange(cursor, clip_duration), source_timerange=Timerange(0, clip_duration), volume=1.0), "F10_BGM")
            cursor += clip_duration
    except ImportError as exc:
        raise RuntimeError("当前 pyJianYingDraft 缺少原生音频轨 API，不能生成可验收成片草稿") from exc
    draft.save()
    content_path = target / "draft_content.json"
    if not content_path.is_file():
        raise RuntimeError("5.9原生写入后缺少draft_content.json")
    rectangle_payload = _latest_cache_payload(user_data_root / "Cache" / "effect" / "636077", "矩形蒙版")
    if "global_layers" in tracks:
        append_visual_layers(content_path=content_path, plan=plan, user_data_root=user_data_root, rectangle_payload=rectangle_payload)
    _attach_native_mask_paths(content_path, user_data_root)
    return target


def report_payload(*, plan: dict[str, Any], draft_path: Path, draft_name: str) -> dict[str, Any]:
    return {
        "status": "STRUCTURAL_PASS_VISUAL_PENDING",
        "schema": "jianying_composition_batch_v1",
        "engine": "jianying59_native_final",
        "draft_path": str(draft_path),
        "draft_name": draft_name,
        "source": plan["source"],
        "template": plan["template"],
        "pairing": plan["pairing"],
        "composition": plan,
    }
