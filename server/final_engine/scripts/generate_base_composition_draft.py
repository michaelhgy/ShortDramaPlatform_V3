from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from server.tool_resolver import resolve_ffprobe


US = 1_000_000
CANVAS_W = 1080
CANVAS_H = 2400
ACCOUNT_PATH = ((-0.72, -0.55), (0.72, -0.20), (-0.72, 0.20), (0.72, 0.55))
MAIN_NAMES = {"draft_content.json", "draft_content.json.bak", "template.json.bak", "template-2.tmp"}


def template_skill_scripts() -> Path:
    return Path(__file__).resolve().parents[2] / "template_factory" / "scripts"


sys.path.insert(0, str(template_skill_scripts()))
from build_action_factory_test import copy_donor_skeleton, read_json, upper_uuid, write_json  # noqa: E402
from add_text_tracks_test import (  # noqa: E402
    ACCOUNT_TEXT_ALPHA,
    ACCOUNT_TEXT_SCALE,
    ACCOUNT_TEXT_SIZE,
    AI_BOTTOM_SAFE_GAP,
    AI_CENTER_INSET_X,
    AI_CENTER_INSET_Y,
    DISCLAIMER_TEXT_ALPHA,
    DISCLAIMER_TEXT_SCALE,
    DISCLAIMER_TEXT_SIZE,
    WARNING_CENTER_INSET_X,
    WARNING_CENTER_INSET_Y,
    clone_account_text_material,
    clone_disclaimer_text_material,
    make_linear_keyframe_group,
    make_text_track,
)


# These labels must be composed above the exported template video.  The
# template's central opening becomes transparent after export, so labels
# embedded in the template would otherwise disappear underneath the viral clip.
COMPOSITION_DISCLAIMERS = (
    ("imitation_warning", "影视效果请勿模仿", False, "central_top_left"),
    ("ai_disclosure", "内容由AI制作", True, "central_bottom_right"),
)

# Pixel safety margins are intentionally fixed because every template canvas is
# 1080x2400.  They are applied after reading each template's randomized opening.
TEMPLATE_OPENING_EXPAND_X_PX = 10
TEMPLATE_OPENING_EXPAND_Y_PX = 10
TEMPLATE_OPENING_MIN_EDGE_X_PX = 8
TEMPLATE_OPENING_MIN_EDGE_Y_PX = 8
MIRROR_OVERLAP_X_PX = 8
MIRROR_OVERLAP_Y_PX = 13
MIRROR_FEATHER = 0.09
# Composition-only override: the exported 1080x2400 template's inverse
# rectangle always spans the full canvas width. Its height, feather, centre,
# and every viral mirror value still come from the paired template geometry.
TEMPLATE_COMPOSITION_MASK_WIDTH_PX = CANVAS_W
# The template rectangle, not the viral mirror, owns the visual join with the
# top/bottom photo walls. Expand this inverse rectangle by 10px on each edge
# beyond its paired height. Keep the mirror height on its existing calibration.
TEMPLATE_COMPOSITION_MASK_EXTRA_Y_PER_EDGE_PX = 10


def probe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            str(resolve_ffprobe()), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate:format=duration",
            "-of", "json", str(path),
        ], check=False, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"无法读取视频: {path}")
    payload = json.loads(result.stdout)
    stream = payload.get("streams", [{}])[0]
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    duration = round(float(payload.get("format", {}).get("duration") or 0) * US)
    if width <= 0 or height <= 0 or duration <= 0:
        raise RuntimeError(f"视频元数据无效: {path}")
    return {"path": str(path), "width": width, "height": height, "duration": duration}


def probe_audio(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            str(resolve_ffprobe()), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ], check=False, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"无法读取音频: {path}")
    payload = json.loads(result.stdout)
    duration = round(float(payload.get("format", {}).get("duration") or 0) * US)
    if duration <= 0:
        raise RuntimeError(f"音频时长无效: {path}")
    return {"path": str(path), "duration": duration}


def default_canvas_scale(_: dict[str, Any]) -> float:
    """Use Jianying's default clip scaling for every viral input.

    The previous hand-built cover calculation (720×1280 -> 1.875) made the
    selected clip exceed the visible 1080×2400 canvas.  Playback review showed
    that the editor's default scale correctly places the input's two side
    edges on the canvas.  Keep this value exactly 1.0 for both portrait and
    landscape material; do not reintroduce source-resolution math here.
    """
    return 1.0


def default_display_size(meta: dict[str, Any], *, scale: float = 1.0) -> dict[str, float]:
    """Rendered size when Jianying uses the user-verified default scale.

    Default scale fits the source width to the 1080-pixel canvas width.  Mask
    width/height are material-display relative, not canvas relative.  This is
    why a 720×1280 viral clip has an effective default display height of 1920
    while the exported 1080×2400 template has a height of 2400.
    """
    width = float(CANVAS_W) * scale
    height = float(meta["height"]) * width / float(meta["width"])
    return {"width": width, "height": height}


def video_material(donor: dict[str, Any], meta: dict[str, Any], *, audio: bool) -> dict[str, Any]:
    result = copy.deepcopy(donor)
    result.update({
        "id": upper_uuid(), "local_material_id": upper_uuid(), "path": meta["path"],
        "material_name": Path(meta["path"]).name, "duration": meta["duration"],
        "width": meta["width"], "height": meta["height"], "has_audio": audio,
        "category_name": "local", "type": "video",
    })
    return result


def audio_material(meta: dict[str, Any], *, title: str, music_id: str) -> dict[str, Any]:
    """Use Jianying's verified imported-local-audio material contract.

    A local file marked ``type=local`` is rewritten by the desktop editor as
    ``none``: it appears in the import bin but cannot play.  Imported files
    must be ``extract_music`` and use their own material UUID as music_id.
    """
    material_id = upper_uuid()
    return {
        "id": material_id, "local_material_id": material_id, "type": "extract_music",
        "name": title, "path": meta["path"], "duration": meta["duration"],
        "music_id": material_id, "category_id": "", "category_name": "local",
        "check_flag": 3, "copyright_limit_type": "none", "effect_id": "",
        "formula_id": "", "app_id": 0, "source_platform": 0, "wave_points": [],
    }


def make_rectangle_mask(donor: dict[str, Any], *, width: float, height: float, feather: float, invert: bool) -> dict[str, Any]:
    result = copy.deepcopy(donor)
    result["id"] = upper_uuid()
    result["config"] = {
        "width": round(width, 9), "height": round(height, 9),
        "centerX": 0.0, "centerY": 0.0, "feather": round(feather, 9), "invert": invert,
    }
    result["name"] = "矩形"
    result["resource_type"] = "rectangle"
    return result


def make_mirror_mask(donor: dict[str, Any], *, height: float) -> dict[str, Any]:
    """Make the normal main-track mirror mask.

    Jianying exposes only its height as a usable mirror-mask control.  The
    underlying width field remains its fixed default 0.5 and must never be
    recalculated from the template opening.
    """
    result = copy.deepcopy(donor)
    result["id"] = upper_uuid()
    result["config"] = {
        "width": 0.5,
        "height": round(height, 9),
        "centerX": 0.0,
        "centerY": 0.0,
        "feather": MIRROR_FEATHER,
        "invert": False,
    }
    result["name"] = "镜面"
    result["resource_type"] = "mirror"
    return result


def paired_opening_geometry(
    *, pairing: dict[str, Any], viral: dict[str, Any], template: dict[str, Any]
) -> dict[str, Any]:
    """Map one randomized template opening to a safe mirror-mask opening.

    The template's inverse rectangle is expanded by 10 px on every edge.  The
    viral mirror keeps its fixed Jianying default width and overlaps it by
    13 px vertically on every edge, leaving source pixels beneath the feather
    instead of a black seam.  All normalisation happens in each material's
    *actual* default display coordinates, so a new template seed or a
    different viral aspect ratio does not reuse this sample's raw values.
    """
    half = pairing["central_window"]["half_extent"]
    template_display = default_display_size(template)
    viral_natural_display = default_display_size(viral)

    base_width_px = round(float(half["x"]) * template_display["width"])
    base_height_px = round(float(half["y"]) * template_display["height"])
    template_width_px = min(
        base_width_px + 2 * TEMPLATE_OPENING_EXPAND_X_PX,
        round(template_display["width"]) - 2 * TEMPLATE_OPENING_MIN_EDGE_X_PX,
    )
    template_paired_height_px = min(
        base_height_px + 2 * TEMPLATE_OPENING_EXPAND_Y_PX,
        round(template_display["height"]) - 2 * TEMPLATE_OPENING_MIN_EDGE_Y_PX,
    )
    if round(template_display["width"]) != CANVAS_W:
        raise RuntimeError(
            f"Composition template must display at {CANVAS_W}px wide, got {template_display['width']}px"
        )
    template_composition_width_px = TEMPLATE_COMPOSITION_MASK_WIDTH_PX
    template_composition_height_px = min(
        template_paired_height_px + 2 * TEMPLATE_COMPOSITION_MASK_EXTRA_Y_PER_EDGE_PX,
        round(template_display["height"]),
    )
    mirror_target_height_px = template_paired_height_px + 2 * MIRROR_OVERLAP_Y_PX

    # Portrait inputs keep the user-verified default scale 1.0.  Only a source
    # whose default displayed height cannot cover the required central opening
    # is enlarged; otherwise the mirror would expose black above/below it.
    viral_scale = max(1.0, mirror_target_height_px / viral_natural_display["height"])
    viral_display = default_display_size(viral, scale=viral_scale)
    effective_height_px = min(mirror_target_height_px, viral_display["height"])

    return {
        "template_display": template_display,
        "viral_natural_display": viral_natural_display,
        "viral_display": viral_display,
        "viral_scale": viral_scale,
        "base_opening_px": {"width": base_width_px, "height": base_height_px},
        "template_opening_px": {"width": template_width_px, "height": template_paired_height_px},
        "template_composition_mask_px": {"width": template_composition_width_px, "height": template_composition_height_px},
        "mirror_effective_px": {"height": effective_height_px},
        "template_mask": {
            "width": template_composition_width_px / template_display["width"],
            "height": template_composition_height_px / template_display["height"],
        },
        "mirror_mask": {
            "width_policy": "jianying_fixed_default_0.5_not_adjusted",
            "height": effective_height_px / viral_display["height"],
        },
    }


def disclaimer_positions(window: dict[str, float]) -> dict[str, dict[str, float]]:
    """Return calibrated text anchors inside the calculated template opening."""
    return {
        "imitation_warning": {
            "x": -window["width"] + WARNING_CENTER_INSET_X,
            "y": window["height"] - WARNING_CENTER_INSET_Y,
        },
        "ai_disclosure": {
            "x": window["width"] - AI_CENTER_INSET_X,
            "y": -window["height"] + AI_CENTER_INSET_Y,
        },
    }


def base_segment(source: dict[str, Any], *, material_id: str, start: int, duration: int,
                 source_start: int, mask_id: str, scale: float, volume: float,
                 render_index: int | None) -> dict[str, Any]:
    result = copy.deepcopy(source)
    # A Jianying main-track segment deliberately has neither of these fields.
    # Leaving an inherited value here converts it into an ordinary video track.
    result.pop("render_index", None)
    result.pop("track_render_index", None)
    result.update({
        "id": upper_uuid(), "material_id": material_id,
        "target_timerange": {"start": start, "duration": duration},
        "source_timerange": {"start": source_start, "duration": duration},
        "extra_material_refs": [mask_id], "speed": 1.0, "volume": volume,
    })
    if render_index is not None:
        result["render_index"] = render_index
        result["track_render_index"] = render_index
    result["clip"] = {
        "transform": {"x": 0.0, "y": 0.0}, "alpha": 1.0, "flip": {},
        "scale": {"x": round(scale, 9), "y": round(scale, 9)}, "rotation": 0.0,
    }
    return result


def repeated_segments(source: dict[str, Any], *, material_id: str, source_duration: int,
                      target_duration: int, mask_id: str, scale: float, render_index: int) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    cursor = 0
    while cursor < target_duration:
        duration = min(source_duration, target_duration - cursor)
        segments.append(base_segment(
            source, material_id=material_id, start=cursor, duration=duration,
            source_start=0, mask_id=mask_id, scale=scale, volume=0.0,
            render_index=render_index,
        ))
        cursor += duration
    return segments


def repeated_audio_segments(*, material_id: str, source_duration: int, target_duration: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    segments: list[dict[str, Any]] = []
    speeds: list[dict[str, Any]] = []
    cursor = 0
    while cursor < target_duration:
        duration = min(source_duration, target_duration - cursor)
        speed_id = upper_uuid()
        speeds.append({"id": speed_id, "type": "speed", "curve_speed": None, "mode": 0, "speed": 1.0})
        segments.append({
            "id": upper_uuid(), "material_id": material_id, "extra_material_refs": [speed_id],
            "target_timerange": {"start": cursor, "duration": duration},
            "source_timerange": {"start": 0, "duration": duration},
            "speed": 1.0, "volume": 1.0, "is_tone_modify": False,
            "enable_adjust": True, "enable_color_correct_adjust": False,
            "enable_color_curves": True, "enable_color_match_adjust": False,
            "enable_color_wheels": True, "enable_lut": True,
            "enable_smart_color_adjust": False, "last_nonzero_volume": 1.0,
            "reverse": False, "track_attribute": 0, "track_render_index": 0,
            "visible": True, "common_keyframes": [], "keyframe_refs": [],
        })
        cursor += duration
    return segments, speeds


def make_video_track(header: dict[str, Any], segments: list[dict[str, Any]], *, main: bool = False) -> dict[str, Any]:
    if main:
        # Do not inherit a video-track shell from the template donor.  The
        # verified Template 4 primary track has this exact lightweight shape;
        # in particular attribute=0 distinguishes it from a normal overlay.
        return {
            "type": "video",
            "id": upper_uuid(),
            "flag": 0,
            "name": "",
            "attribute": 0,
            "is_default_name": True,
            "segments": segments,
        }
    result = copy.deepcopy(header)
    result.update({"id": upper_uuid(), "type": "video", "name": "", "segments": segments})
    result["flag"] = 2
    return result


def make_audio_track(segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "audio", "id": upper_uuid(), "flag": 0, "name": "",
        "attribute": 0, "is_default_name": True, "segments": segments,
    }


def account_keyframes(duration: int) -> list[dict[str, Any]]:
    cycles = max(1, round(duration / (32 * US)))
    leg_count = cycles * len(ACCOUNT_PATH)
    offsets = [round(duration * index / leg_count) for index in range(leg_count + 1)]
    points = [ACCOUNT_PATH[index % len(ACCOUNT_PATH)] for index in range(leg_count)] + [ACCOUNT_PATH[0]]
    groups = [
        make_linear_keyframe_group("KFTypePositionX", list(zip(offsets, [point[0] for point in points]))),
        make_linear_keyframe_group("KFTypePositionY", list(zip(offsets, [point[1] for point in points]))),
    ]
    # Jianying's text-transform keyframe groups intentionally keep this blank.
    # Binding it to the segment ID moves the selection box but not the rendered
    # glyphs on the current desktop editor build.
    for group in groups:
        group["material_id"] = ""
    return groups


def patch_document(document: dict[str, Any], *, target_id: str, target: Path, viral: dict[str, Any],
                   template: dict[str, Any], pairing: dict[str, Any], account_id: str,
                   bgm: dict[str, Any] | None = None, bgm_title: str = "", bgm_id: str = "",
                   midroll: dict[str, Any] | None = None, endroll: dict[str, Any] | None = None) -> dict[str, Any]:
    result = copy.deepcopy(document)
    result["id"] = target_id
    result["path"] = str(target).replace("\\", "/")
    result["canvas_config"] = {"width": CANVAS_W, "height": CANVAS_H}
    if (midroll is None) != (endroll is None):
        raise RuntimeError("Mid-roll and end-roll must be supplied together")
    if midroll is not None and viral["duration"] <= 120 * US:
        raise RuntimeError("MIDROLL_POSITION_REVIEW_REQUIRED")
    total_duration = viral["duration"] + (midroll or {"duration": 0})["duration"] + (endroll or {"duration": 0})["duration"]
    result["duration"] = total_duration
    materials = result.setdefault("materials", {})
    videos = materials.setdefault("videos", [])
    masks = materials.setdefault("common_mask", [])
    texts = materials.setdefault("texts", [])
    if not videos or not texts:
        raise RuntimeError("供体缺少视频或文字材料，无法创建基础成片草稿")
    rectangle = next((item for item in masks if item.get("resource_type") == "rectangle" or item.get("name") == "矩形"), None)
    mirror = next((item for item in masks if item.get("resource_type") == "mirror" or item.get("name") == "镜面"), None)
    if rectangle is None or mirror is None:
        raise RuntimeError("供体缺少矩形或镜面蒙版")
    viral_material = video_material(videos[0], viral, audio=True)
    template_material = video_material(videos[0], template, audio=False)
    midroll_material = video_material(videos[0], midroll, audio=True) if midroll is not None else None
    endroll_material = video_material(videos[0], endroll, audio=True) if endroll is not None else None
    videos.extend([viral_material, template_material, *([midroll_material] if midroll_material else []), *([endroll_material] if endroll_material else [])])
    window = pairing["central_window"]
    feather = float(window["feather"])
    geometry = paired_opening_geometry(pairing=pairing, viral=viral, template=template)
    viral_scale = geometry["viral_scale"]
    template_scale = default_canvas_scale(template)
    viral_mask = make_mirror_mask(
        mirror,
        height=geometry["mirror_mask"]["height"],
    )
    template_mask = make_rectangle_mask(
        rectangle,
        width=geometry["template_mask"]["width"],
        height=geometry["template_mask"]["height"],
        feather=feather,
        invert=True,
    )
    midroll_geometry = paired_opening_geometry(pairing=pairing, viral=midroll, template=template) if midroll else None
    endroll_geometry = paired_opening_geometry(pairing=pairing, viral=endroll, template=template) if endroll else None
    midroll_mask = make_mirror_mask(mirror, height=midroll_geometry["mirror_mask"]["height"]) if midroll_geometry else None
    endroll_mask = make_mirror_mask(mirror, height=endroll_geometry["mirror_mask"]["height"]) if endroll_geometry else None
    masks.extend([viral_mask, template_mask, *([midroll_mask] if midroll_mask else []), *([endroll_mask] if endroll_mask else [])])
    header = result.get("tracks", [{}])[0]
    segment_source = header.get("segments", [{}])[0]
    if midroll is None:
        main_segments = [base_segment(segment_source, material_id=viral_material["id"], start=0,
                                      duration=viral["duration"], source_start=0, mask_id=viral_mask["id"],
                                      scale=viral_scale, volume=1.0, render_index=None)]
    else:
        insert_at = 120 * US
        main_segments = [
            base_segment(segment_source, material_id=viral_material["id"], start=0, duration=insert_at,
                         source_start=0, mask_id=viral_mask["id"], scale=viral_scale, volume=1.0, render_index=None),
            base_segment(segment_source, material_id=midroll_material["id"], start=insert_at,
                         duration=midroll["duration"], source_start=0, mask_id=midroll_mask["id"],
                         scale=midroll_geometry["viral_scale"], volume=1.0, render_index=None),
            base_segment(segment_source, material_id=viral_material["id"], start=insert_at + midroll["duration"],
                         duration=viral["duration"] - insert_at, source_start=insert_at, mask_id=viral_mask["id"],
                         scale=viral_scale, volume=1.0, render_index=None),
            base_segment(segment_source, material_id=endroll_material["id"],
                         start=viral["duration"] + midroll["duration"], duration=endroll["duration"],
                         source_start=0, mask_id=endroll_mask["id"], scale=endroll_geometry["viral_scale"],
                         volume=1.0, render_index=None),
        ]
    template_segments = repeated_segments(segment_source, material_id=template_material["id"],
                                          source_duration=template["duration"], target_duration=total_duration,
                                          mask_id=template_mask["id"], scale=template_scale, render_index=1)
    account_material = clone_account_text_material(texts[0], account_id)
    account_material["global_alpha"] = ACCOUNT_TEXT_ALPHA
    account_material["text_alpha"] = ACCOUNT_TEXT_ALPHA
    texts.append(account_material)
    account_track = make_text_track(material_id=account_material["id"], effect_ids=[], animation_ids=[],
                                    duration=total_duration, track_render_index=2,
                                    x=ACCOUNT_PATH[0][0], y=ACCOUNT_PATH[0][1],
                                    scale=ACCOUNT_TEXT_SCALE, rotation=0.0)
    account_segment = account_track["segments"][0]
    account_segment["clip"]["alpha"] = ACCOUNT_TEXT_ALPHA
    # Jianying's current draft schema reads transform motion from the segment's
    # own common_keyframes.  keyframe_refs is legacy metadata and is not a
    # substitute for actual motion data.
    account_groups = account_keyframes(total_duration)
    account_segment["common_keyframes"] = account_groups
    account_segment["keyframe_refs"] = []
    disclaimer_positions_by_key = disclaimer_positions(geometry["template_mask"])
    disclaimer_tracks = []
    disclaimer_report = []
    for key, text, vertical, anchor in COMPOSITION_DISCLAIMERS:
        material = clone_disclaimer_text_material(texts[0], text=text, vertical=vertical)
        texts.append(material)
        position = disclaimer_positions_by_key[key]
        track = make_text_track(
            material_id=material["id"], effect_ids=[], animation_ids=[], duration=total_duration,
            track_render_index=3 + len(disclaimer_tracks), x=position["x"], y=position["y"],
            scale=DISCLAIMER_TEXT_SCALE, rotation=0.0,
        )
        track["segments"][0]["clip"]["alpha"] = DISCLAIMER_TEXT_ALPHA
        disclaimer_tracks.append(track)
        disclaimer_report.append({
            "key": key, "text": text, "rendered_text": "\n".join(text) if vertical else text,
            "vertical": vertical, "anchor": anchor, "x": round(position["x"], 9),
            "y": round(position["y"], 9), "text_size": DISCLAIMER_TEXT_SIZE,
            "scale": DISCLAIMER_TEXT_SCALE, "opacity": DISCLAIMER_TEXT_ALPHA,
        })
    bgm_track = None
    bgm_report = None
    if bgm is not None:
        audios = materials.setdefault("audios", [])
        material = audio_material(bgm, title=bgm_title or Path(bgm["path"]).stem, music_id=bgm_id)
        audios.append(material)
        segments, speeds = repeated_audio_segments(
            material_id=material["id"], source_duration=bgm["duration"], target_duration=total_duration,
        )
        materials.setdefault("speeds", []).extend(speeds)
        bgm_track = make_audio_track(segments)
        bgm_report = {
            "music_id": bgm_id, "title": material["name"], "path": bgm["path"],
            "duration_microseconds": bgm["duration"], "clip_volume": 1.0,
            "segment_count": len(segments), "coverage_microseconds": total_duration,
            "normalization_contract": "local normalized asset; Jianying clip volume must remain unity",
        }
    result["tracks"] = [
        make_video_track(header, main_segments, main=True),
        make_video_track(header, template_segments),
        account_track,
        *disclaimer_tracks,
        *([bgm_track] if bgm_track is not None else []),
    ]
    result["composition_base_test"] = {
        "version": 1, "stage": "base_visual_pairing_only", "viral_path": viral["path"],
        "template_path": template["path"], "pairing_source": pairing.get("template_identity", {}),
        "duration_microseconds": total_duration,
        "viral_mask": {
            "type": "mirror", "invert": False, "width_policy": "jianying_fixed_default_0.5_not_adjusted",
            "height": viral_mask["config"]["height"], "feather": MIRROR_FEATHER,
            "scale": viral_scale, "display_size": geometry["viral_display"],
        },
        "viral_main_track": {"track_index": 0, "track_flag": 0, "segment_render_index": None, "segment_count": len(main_segments)},
        "template_mask": {
            "invert": True, "width": template_mask["config"]["width"],
            "height": template_mask["config"]["height"], "scale": template_scale,
            "display_size": geometry["template_display"],
            "width_rule": f"fixed_{TEMPLATE_COMPOSITION_MASK_WIDTH_PX}px_canvas",
        },
        "mask_mapping": {
            "formula": "template rectangle width = fixed 1080px canvas; its height = paired height + 10px extra at each edge; viral mirror retains its fixed Jianying width and prior paired +13px vertical overlap calibration",
            "geometry": geometry,
        },
        "composition_disclaimer_tracks": disclaimer_report,
        "bgm": bgm_report,
        "insertions": None if midroll is None else {
            "midroll": {"path": midroll["path"], "start_microseconds": 120 * US, "duration_microseconds": midroll["duration"]},
            "endroll": {"path": endroll["path"], "start_microseconds": viral["duration"] + midroll["duration"], "duration_microseconds": endroll["duration"]},
        },
        "template_segment_count": len(template_segments),
        "excluded": [item for item in ["head_tail_trim", "wrong_title_mosaic", "midroll" if midroll is None else None, "endroll" if endroll is None else None, "bgm" if bgm is None else None] if item],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a non-destructive base finished-video Jianying draft")
    parser.add_argument("--viral", required=True)
    parser.add_argument("--template-video", required=True)
    parser.add_argument("--pairing", required=True)
    parser.add_argument("--donor", required=True)
    parser.add_argument("--draft-root", required=True)
    parser.add_argument("--draft-name", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--midroll", type=Path, help="Local mid-roll video; insert after 120 seconds of clean viral content")
    parser.add_argument("--endroll", type=Path, help="Local end-roll video; append after clean viral content")
    parser.add_argument("--bgm", type=Path, help="已登记并归一化的本地 BGM 文件")
    parser.add_argument("--bgm-id", default="")
    parser.add_argument("--bgm-title", default="")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    viral_path, template_path, pairing_path, donor = map(Path, (args.viral, args.template_video, args.pairing, args.donor))
    for path in (viral_path, template_path, pairing_path, donor / "template.json.bak"):
        if not path.exists():
            raise FileNotFoundError(path)
    if any(character in args.draft_name for character in '<>:"/\\|?*'):
        raise ValueError("草稿名称含非法Windows路径字符")
    if (args.midroll is None) != (args.endroll is None):
        raise ValueError("--midroll and --endroll must be supplied together")
    for path in (args.midroll, args.endroll):
        if path is not None and not path.is_file():
            raise FileNotFoundError(path)
    viral, template = probe_video(viral_path), probe_video(template_path)
    midroll = probe_video(args.midroll) if args.midroll is not None else None
    endroll = probe_video(args.endroll) if args.endroll is not None else None
    bgm = probe_audio(args.bgm) if args.bgm is not None else None
    pairing = json.loads(pairing_path.read_text(encoding="utf-8-sig"))
    if pairing.get("canvas") != {"width": CANVAS_W, "height": CANVAS_H}:
        raise RuntimeError("配对参数画布不是1080x2400")
    draft_root, target = Path(args.draft_root), Path(args.draft_root) / args.draft_name
    target_id = upper_uuid()
    copy_donor_skeleton(donor, target, target_id)
    source = read_json(donor / "template.json.bak")
    patched = patch_document(
        source, target_id=target_id, target=target, viral=viral, template=template,
        pairing=pairing, account_id=args.account_id, bgm=bgm,
        bgm_title=args.bgm_title, bgm_id=args.bgm_id, midroll=midroll, endroll=endroll,
    )
    written = []
    for path in target.rglob("*"):
        # The donor's subdraft files are reusable compound assets.  The base
        # composition has no compound clips, so changing those nested timelines
        # is both unnecessary and unsafe.  Patch only the root timeline and
        # the generated main Timeline directory.
        if "subdraft" in {part.casefold() for part in path.parts}:
            continue
        if path.is_file() and path.name in MAIN_NAMES:
            write_json(path, patched)
            written.append(str(path))
    meta_path = target / "draft_meta_info.json"
    meta = read_json(meta_path)
    meta.update({"draft_id": target_id, "draft_name": args.draft_name, "draft_fold_path": str(target).replace("\\", "/"), "draft_root_path": str(draft_root), "tm_duration": patched["duration"]})
    write_json(meta_path, meta)
    report = {"status": "STRUCTURAL_PASS_VISUAL_PENDING", "draft_path": str(target), "draft_name": args.draft_name, "written_json": written, "viral": viral, "template": template, "composition": patched["composition_base_test"]}
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
