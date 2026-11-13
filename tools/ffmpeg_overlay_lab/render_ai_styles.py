#!/usr/bin/env python3
"""Compare three AI-generated overlay styles on the same 30-second source.

Image generation is done separately by the built-in imagegen tool. This script
only uses saved PNGs, existing scenery and FFmpeg. No production paths change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from render_sample import (
    DEFAULT_SOURCE, FFMPEG, FPS, H, SECONDS, W, compose, ffpath, make_recipe,
    prepare_effect, probe, run_stage, save_json, verify, write_mask,
)


STYLES = [('gold', '01_暖金流光'), ('cyan', '02_青蓝柔光'), ('purple', '03_粉紫星点')]


def prepare_base(root: Path) -> dict:
    recipe = make_recipe()
    recipe['stickers'] = []
    recipe['edge_particles']['enabled'] = False
    recipe['purpose'] = 'Shared scenery and 2% full-frame layer, without the old top/bottom stickers'
    root.mkdir()
    save_json(root / 'recipe.json', recipe)
    write_mask(root / 'top_alpha.pgm', W, 620, True)
    write_mask(root / 'bottom_alpha.pgm', W, 570, False)
    return prepare_effect(root, recipe)


def prepare_edges(root: Path, texture: Path) -> dict:
    # Mirror the image vertically before scrolling so its top/bottom seam
    # joins identical edge pixels. Both motion periods divide the 30s length.
    graph = (
        '[0:v]scale=80:1200:flags=bilinear,format=yuv420p,split=2[a][b];'
        '[b]vflip[bf];[a][bf]vstack=inputs=2,split=2[ls][rs];'
        "[ls]scroll=vertical=0.0033333333,crop=10:2400:x='35+25*sin(2*PI*t/10)':y=0[l];"
        "[rs]scroll=vertical=-0.0033333333,crop=10:2400:x='35+25*cos(2*PI*t/15)':y=0[r];"
        '[l][r]hstack=inputs=2,format=yuv420p[out]'
    )
    (root / 'prepare_edges.ffgraph').write_text(graph, encoding='utf-8')
    return run_stage(root, '01_prepare_ai_edge_animation', [
        '-filter_complex_threads', '4', '-loop', '1', '-framerate', str(FPS), '-i', ffpath(texture),
        '-filter_complex_script', ffpath(root / 'prepare_edges.ffgraph'), '-map', '[out]',
        '-an', '-t', str(SECONDS), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '12',
        '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-movflags', '+faststart',
        ffpath(root / 'side_animation_packed.mp4')])


def prepare_style_cache(root: Path, common: Path, stickers: Path) -> dict:
    graph = (
        '[0:v][1:v]alphamerge[base];'
        '[2:v]scale=1080:-2,format=rgba,colorchannelmixer=aa=0.70,split=2[ds1][ds2];'
        '[ds1]crop=1080:360:0:0[dt];[ds2]crop=1080:360:0:ih-360[db];'
        "[base][dt]overlay=x='4*sin(2*PI*t/6)':y='3*sin(2*PI*t/5)':format=rgb:alpha=straight:shortest=1[d1];"
        "[d1][db]overlay=x='-4*sin(2*PI*t/6)':y='2040-3*sin(2*PI*t/5)':format=rgb:alpha=straight:shortest=1[decor];"
        '[3:v][4:v]alphamerge,split=2[els][ers];'
        '[els]crop=10:2400:0:0[el];[ers]crop=10:2400:10:0[er];'
        '[decor][el]overlay=x=0:y=0:format=rgb:alpha=straight:shortest=1[e1];'
        '[e1][er]overlay=x=1070:y=0:format=rgb:alpha=straight:shortest=1,split=2[ec][ea];'
        '[ec]format=yuv420p[colour];[ea]alphaextract[alpha]'
    )
    (root / 'prepare_style.ffgraph').write_text(graph, encoding='utf-8')
    return run_stage(root, '02_prepare_style_effect_cache', [
        '-filter_complex_threads', '6', '-i', ffpath(common / 'effect_colour.mp4'),
        '-i', ffpath(common / 'effect_alpha.mkv'),
        '-loop', '1', '-framerate', str(FPS), '-i', ffpath(stickers),
        '-i', ffpath(root / 'side_animation_packed.mp4'),
        '-loop', '1', '-framerate', str(FPS), '-i', ffpath(root / 'side_alpha.pgm'),
        '-filter_complex_script', ffpath(root / 'prepare_style.ffgraph'),
        '-map', '[colour]', '-an', '-t', str(SECONDS), '-c:v', 'h264_nvenc', '-preset', 'p4',
        '-rc', 'vbr', '-cq', '17', '-b:v', '0', '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr',
        '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        '-movflags', '+faststart', ffpath(root / 'effect_colour.mp4'),
        '-map', '[alpha]', '-an', '-t', str(SECONDS), '-c:v', 'ffv1', '-level', '3',
        '-threads', '4', '-pix_fmt', 'gray', ffpath(root / 'effect_alpha.mkv')])


def image_info(path: Path, transparent: bool) -> dict:
    info = probe(path)['streams'][0]
    result = {'path': str(path), 'width': info['width'], 'height': info['height'],
              'pix_fmt': info['pix_fmt'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if transparent:
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-frames:v', '1',
                                  '-vf', 'alphaextract', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
                                 capture_output=True)
        if decoded.returncode:
            raise RuntimeError(f'Missing actual alpha: {path}')
        values = decoded.stdout
        assert len(values) == info['width'] * info['height']
        result.update({'alpha_min': min(values), 'alpha_max': max(values),
                       'fully_transparent_fraction': round(sum(v == 0 for v in values) / len(values), 5)})
        assert result['fully_transparent_fraction'] > 0.5, f'Overlay obscures too much of the canvas: {path}'
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--stage', choices=['base', 'styles', 'all'], default='all')
    args = parser.parse_args()
    root, assets = args.output_dir, args.assets_dir
    root.mkdir(parents=True, exist_ok=True)
    common = root / '00_共用风景底层'
    if args.stage in ['base', 'all']:
        if common.exists():
            raise FileExistsError(f'Refusing to replace existing base cache: {common}')
        base_timing = prepare_base(common)
        save_json(root / 'base_timing.json', base_timing)
    if args.stage == 'base':
        return
    if not (common / 'effect_alpha.mkv').is_file():
        raise FileNotFoundError('Prepare the shared base cache first')
    results = []
    source_before = (DEFAULT_SOURCE.stat().st_size, DEFAULT_SOURCE.stat().st_mtime_ns)
    for key, name in STYLES:
        target = root / name
        if target.exists():
            raise FileExistsError(f'Refusing to replace existing style: {target}')
        texture, overlay = assets / f'{key}_texture.png', assets / f'{key}_stickers.png'
        material_info = [image_info(texture, False), image_info(overlay, True)]
        target.mkdir()
        save_json(target / 'recipe.json', {
            'style': key, 'name': name, 'assets': material_info, 'generated_with': 'built-in image_gen',
            'source': str(DEFAULT_SOURCE), 'source_range_seconds': [0, 30],
            'same_scenery_and_full_frame_2_percent_layer': True, 'old_top_bottom_stickers_removed': True,
            'edge_width_pixels': 10, 'edge_inner_feather_pixels': 3, 'new_sticker_opacity': 0.70,
            'new_sticker_bands': [[0, 360], [2040, 2400]],
            'animation': 'AI still textures animated with mirrored scroll/pan; transparent stickers gently float',
        })
        row = bytes([255] * 7 + [170, 85, 0] + [0, 85, 170] + [255] * 7)
        (target / 'side_alpha.pgm').write_bytes(b'P5\n20 2400\n255\n' + row * H)
        edge_timing = prepare_edges(target, texture)
        cache_timing = prepare_style_cache(target, common, overlay)
        composition_timing = compose(target, DEFAULT_SOURCE)
        checks = verify(target)
        report = {
            'schema': 'ai_overlay_style_trial_v1', 'style': key, 'name': name,
            'output': str(target / 'FFmpeg_30秒效果测试.mp4'), 'assets': material_info,
            'timings': [edge_timing, cache_timing, composition_timing],
            'composition_seconds': composition_timing['wall_seconds'],
            'style_preparation_seconds': round(edge_timing['wall_seconds'] + cache_timing['wall_seconds'], 3),
            'checks': checks, 'visual_acceptance': 'USER_PENDING',
        }
        save_json(target / 'timing_report.json', report)
        results.append(report)
        save_json(root / 'comparison_report.json', {'styles': results, 'complete': len(results) == len(STYLES)})
    assert source_before == (DEFAULT_SOURCE.stat().st_size, DEFAULT_SOURCE.stat().st_mtime_ns)
    (root / '先看这里.txt').write_text(
        '三版均为同一段原声剧情的前30秒，1080×2400，30帧。\n'
        '01_暖金流光：暖金丝光边条＋银杏细线装饰。\n'
        '02_青蓝柔光：青蓝水光边条＋云纹水波装饰。\n'
        '03_粉紫星点：粉紫星光边条＋星月花朵装饰。\n'
        '每个目录中的 FFmpeg_30秒效果测试.mp4 即对应成片。\n'
        '本次AI生成边条纹理和上下透明贴纸，运动由FFmpeg制作；风景和主轨保持相同。\n'
        '素材与完整提示词位于项目 tools/ffmpeg_overlay_lab/experiments 对应实验目录。\n', encoding='utf-8-sig')
    print(json.dumps({'output_root': str(root), 'styles': [{'name': r['name'], 'output': r['output'],
                         'composition_seconds': r['composition_seconds']} for r in results]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
