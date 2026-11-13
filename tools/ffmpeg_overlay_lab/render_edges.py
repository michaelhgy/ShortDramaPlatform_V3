#!/usr/bin/env python3
"""Add 10-pixel animated video strips to the already accepted effect layout.

The accepted colour/alpha caches remain read-only. Only the new narrow border
animation is prepared before a fresh source+effects composition is measured.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from render_sample import FFMPEG, FPS, H, SECONDS, W, ffpath, probe, run_stage, save_json, verify


DEFAULT_BASE = Path('/mnt/c/Users/Michael/Videos/FFmpeg结构测试_20261017_151908')
DEFAULT_EDGE_VIDEO = Path('/mnt/c/Users/Michael/Downloads/feb (3).mp4')


def prepare_edges(root: Path, asset: Path) -> dict:
    graph = (
        '[0:v]trim=duration=30,setpts=PTS-STARTPTS,fps=30,'
        'scale=80:2400:flags=bilinear,eq=brightness=0.14:saturation=1.2,split=2[a][b];'
        "[a]crop=w=10:h=2400:x='35+25*sin(2*PI*t/8)':y=0[left];"
        "[b]crop=w=10:h=2400:x='35+25*cos(2*PI*t/10)':y=0,vflip[right];"
        '[left][right]hstack=inputs=2,format=yuv420p[out]'
    )
    (root / 'prepare_edges.ffgraph').write_text(graph, encoding='utf-8')
    # A 20px-wide stream is tiny; software H.264 avoids NVENC minimum width
    # limitations without expanding it to a full-frame video.
    return run_stage(root, '01_prepare_side_video', [
        '-filter_complex_threads', '4', '-stream_loop', '-1', '-i', ffpath(asset),
        '-filter_complex_script', ffpath(root / 'prepare_edges.ffgraph'), '-map', '[out]',
        '-an', '-t', str(SECONDS), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '12',
        '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-movflags', '+faststart',
        ffpath(root / 'side_animation_packed.mp4')])


def compose_edges(root: Path, base: Path, source: Path) -> dict:
    graph = (
        f'[0:v]trim=duration={SECONDS},setpts=PTS-STARTPTS,fps={FPS},'
        f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[main];'
        '[1:v][2:v]alphamerge[effect];'
        '[main][effect]overlay=format=yuv420:alpha=straight:shortest=1[body];'
        '[3:v][4:v]alphamerge,split=2[els][ers];'
        '[els]crop=10:2400:0:0[el];[ers]crop=10:2400:10:0[er];'
        '[body][el]overlay=x=0:y=0:format=yuv420:alpha=straight:shortest=1[withleft];'
        '[withleft][er]overlay=x=1070:y=0:format=yuv420:alpha=straight:shortest=1[out]'
    )
    (root / 'compose_edges.ffgraph').write_text(graph, encoding='utf-8')
    return run_stage(root, '02_compose_with_side_video', [
        '-filter_complex_threads', '6', '-i', ffpath(source),
        '-i', ffpath(base / 'effect_colour.mp4'), '-i', ffpath(base / 'effect_alpha.mkv'),
        '-i', ffpath(root / 'side_animation_packed.mp4'),
        '-loop', '1', '-framerate', str(FPS), '-i', ffpath(root / 'side_alpha.pgm'),
        '-filter_complex_script', ffpath(root / 'compose_edges.ffgraph'), '-map', '[out]', '-map', '0:a:0?',
        '-t', str(SECONDS), '-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', '22',
        '-b:v', '6M', '-maxrate:v', '8M', '-bufsize:v', '16M',
        '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '2',
        '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        '-movflags', '+faststart', ffpath(root / 'FFmpeg_30秒效果测试.mp4')])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-experiment', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--edge-video', type=Path, default=DEFAULT_EDGE_VIDEO)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    base = args.base_experiment.resolve()
    baseline = json.loads((base / 'timing_report.json').read_text(encoding='utf-8'))
    source = Path(baseline['source'])
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
    root = args.output_dir or Path('/mnt/c/Users/Michael/Videos') / f'FFmpeg双侧动态测试_{stamp}'
    if root.exists():
        raise FileExistsError(f'Refusing to overwrite: {root}')
    inputs = [source, args.edge_video, base / 'effect_colour.mp4', base / 'effect_alpha.mkv']
    before = [{'path': str(p), 'size': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns} for p in inputs]
    root.mkdir(parents=True)
    save_json(root / 'input_snapshot.json', before)
    # The inner three pixels feather into the accepted body. No pixels outside
    # the two 10px strips receive the new effect.
    row = bytes([255] * 7 + [170, 85, 0] + [0, 85, 170] + [255] * 7)
    (root / 'side_alpha.pgm').write_bytes(b'P5\n20 2400\n255\n' + row * H)
    save_json(root / 'recipe.json', {
        'schema': 'ffmpeg_side_overlay_lab_v1', 'base_experiment': str(base),
        'base_user_feedback': '效果没问题，基本是一样的了；需要补充左右两边会动的素材',
        'source': str(source), 'edge_video': str(args.edge_video), 'canvas': [W, H],
        'fps': FPS, 'seconds': SECONDS, 'edge_width_pixels': 10, 'inner_feather_pixels': 3,
        'method': 'Two animated vertical crops from an existing flower video, independently panning; right strip vertically flipped',
        'base_effect_changed': False, 'ai_assets_generated_this_run': False,
    })
    print(f'OUTPUT_DIRECTORY {root}', flush=True)
    prep = prepare_edges(root, args.edge_video)
    render = compose_edges(root, base, source)
    checks = verify(root)
    after = [{'path': str(p), 'size': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns} for p in inputs]
    assert before == after, 'Input size or modification time changed during the experiment'
    animation = probe(root / 'side_animation_packed.mp4')
    packed_video = next(s for s in animation['streams'] if s['codec_type'] == 'video')
    assert (packed_video['width'], packed_video['height']) == (20, 2400)
    assert int(packed_video['nb_frames']) == SECONDS * FPS
    report = {
        'schema': 'ffmpeg_side_overlay_report_v1', 'created_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'status': 'MEDIA_PASS_SIDE_EFFECT_VISUAL_PENDING', 'output': str(root / 'FFmpeg_30秒效果测试.mp4'),
        'base_experiment': str(base), 'base_main_effect_user_accepted': True,
        'source': str(source), 'edge_width_pixels': 10, 'new_edge_asset': str(root / 'side_animation_packed.mp4'),
        'timings': [prep, render], 'new_side_effect_preparation_seconds': prep['wall_seconds'],
        'composition_seconds': render['wall_seconds'],
        'previous_composition_seconds': baseline['reuse_composition_seconds'],
        'comparison_scope': 'Same source, 30s, 1080x2400, NVENC p4 CQ22 6M target / 8M max; single runs, not a controlled statistical benchmark',
        'accepted_base_cache_rebuilt': False, 'source_files_unchanged_size_mtime': True,
        'checks': checks, 'ai_generation_executed': False,
    }
    save_json(root / 'timing_report.json', report)
    (root / '查看说明.txt').write_text(
        'FFmpeg_30秒效果测试.mp4 是补充左右动态素材后的新版。\n'
        '沿用上一版已认可的主体效果缓存，左右各10像素，内侧3像素羽化。\n'
        '边条取自现有花海视频，使用不同的移动裁切；不是静态描边。\n'
        f'新增边条准备：{prep["wall_seconds"]:.3f}秒。\n'
        f'带双侧动态素材的30秒成片合成：{render["wall_seconds"]:.3f}秒。\n'
        '未重新准备主体效果，未执行AI批量生成，未更改生产流程或源素材。\n', encoding='utf-8-sig')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
