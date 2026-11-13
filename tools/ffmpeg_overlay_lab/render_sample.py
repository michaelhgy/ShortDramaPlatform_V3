#!/usr/bin/env python3
"""Isolated 30-second overlay experiment; never changes production or inputs.

Run from WSL with the existing Windows FFmpeg 8.1. The reusable cache stores
straight colour and lossless alpha separately; the source video is never baked
into it. Timings include starting FFmpeg and writing the output files.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


W, H, FPS, SECONDS = 1080, 2400, 30, 30
FFMPEG = Path('/mnt/d/V2_PackagingCache/ffmpeg/8.1/expanded/ffmpeg-8.1-full_build/bin/ffmpeg.exe')
FFPROBE = FFMPEG.with_name('ffprobe.exe')
DEFAULT_SOURCE = Path('/mnt/d/短剧推广运营系统/生产文件/9月23日/千层蛋糕酥脆/别惹那个装傻的学霸/素材/别惹那个装傻的学霸-3.mp4')
REFERENCE = Path('/mnt/c/Users/Michael/Videos/测试.mp4')
CACHE_ROOT = Path('/mnt/c/Users/Michael/AppData/Local/JianyingPro/User Data/Cache/artistEffect')
DOWNLOADS = Path('/mnt/c/Users/Michael/Downloads')


def ffpath(path: Path) -> str:
    value = str(path.resolve())
    if value.startswith('/mnt/') and len(value) > 6 and value[6] == '/':
        return value[5].upper() + ':' + value[6:]
    raise ValueError(f'Windows FFmpeg requires a Windows-mounted path: {path}')


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def probe(path: Path) -> dict:
    result = subprocess.run([str(FFPROBE), '-v', 'error', '-show_streams',
                             '-show_format', '-of', 'json', ffpath(path)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return json.loads(result.stdout)


def run_stage(root: Path, name: str, arguments: list[str]) -> dict:
    command = [str(FFMPEG), '-hide_banner', '-nostdin', '-n', '-benchmark', *arguments]
    save_json(root / f'{name}.command.json', command)
    print(f'START {name}', flush=True)
    started = time.perf_counter()
    with (root / f'{name}.log').open('wb') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.perf_counter() - started
    record = {'stage': name, 'wall_seconds': round(elapsed, 3), 'returncode': result.returncode}
    log_text = (root / f'{name}.log').read_text(encoding='utf-8', errors='replace')
    native_time = re.search(r'\brtime=(\d+(?:\.\d+)?)s', log_text)
    if native_time:
        record['ffmpeg_reported_render_seconds'] = float(native_time.group(1))
    save_json(root / f'{name}.timing.json', record)
    print(json.dumps(record), flush=True)
    if result.returncode:
        raise RuntimeError((root / f'{name}.log').read_text(encoding='utf-8', errors='replace')[-3500:])
    return record


def sticker(resource_id: str, filename: str = 'final.gif') -> Path:
    matches = sorted((CACHE_ROOT / resource_id).glob(f'*/{filename}'))
    if not matches:
        raise FileNotFoundError(f'Existing local resource missing: {resource_id}/{filename}')
    return matches[0]


def write_mask(path: Path, width: int, height: int, top: bool) -> None:
    # Lossless grayscale; generate once rather than evaluate a full-frame
    # pixel expression for every output frame. Alpha 0 is fully transparent.
    rows = []
    for y in range(height):
        value = 1 - max(0.0, min(1.0, (y - 110) / (height - 110))) if top else min(1.0, y / (height - 130))
        rows.append(bytes([round(255 * value)]) * width)
    path.write_bytes(f'P5\n{width} {height}\n255\n'.encode() + b''.join(rows))


def make_recipe() -> dict:
    placements = [
        ('7491340491716365593', '木马', 235, 24, 12),
        ('7491358339939470616', '日记', 250, 315, 0),
        ('7491481426798513433', 'HAPPY', 295, 710, 0),
        ('7491329449451851033', '奶茶', 210, 24, 2170),
        ('7491483053198462233', 'Travel', 380, 330, 2110),
        ('7491328248979328280', '汽车', 225, 810, 2160),
    ]
    return {
        'schema': 'ffmpeg_overlay_lab_v1', 'canvas': [W, H], 'fps': FPS,
        'seconds': SECONDS, 'seed': 20261017,
        'landscapes': [str(DOWNLOADS / f'feb ({i}).mp4') for i in (2, 3, 16, 17)],
        'scenery_segment_seconds': 15,
        'top_band': {'height': 620, 'crop_y': 760, 'feather_start': 110},
        'bottom_band': {'height': 570, 'crop_y': 700, 'canvas_y': 1830, 'feather_end': 440},
        'full_frame_sticker': {'path': str(sticker('6943059535720451364', 'singleImage.png')), 'name': '可爱卡通人物HelloKitty', 'opacity': 0.02},
        'stickers': [{'resource_id': rid, 'name': name, 'path': str(sticker(rid)),
                      'width': width, 'x': x, 'y': y, 'opacity': 0.62}
                     for rid, name, width, x, y in placements],
        'edge_particles': {'method': 'FFmpeg animated light dots, approximate replacement for Jianying particle effect',
                           'edge_width_pixels': 10, 'count_per_side': 6},
        'main_fit': 'cover canvas, centre crop, preserve aspect ratio',
        'cache': {'colour': 'H.264/NVENC CQ17, yuv420p', 'alpha': 'FFV1 lossless gray'},
        'output_encoding': {'codec': 'h264_nvenc', 'preset': 'p4', 'cq': 22,
                            'target_bitrate': '6M', 'max_bitrate': '8M', 'audio': 'AAC 128k stereo'},
    }


def prepare_effect(root: Path, recipe: dict) -> dict:
    args = ['-filter_complex_threads', '6']
    for filename in recipe['landscapes']:
        args += ['-stream_loop', '-1', '-i', ffpath(Path(filename))]
    for item in recipe['stickers']:
        asset = Path(item['path'])
        if asset.suffix.lower() == '.gif':
            args += ['-ignore_loop', '0', '-i', ffpath(asset)]
        else:
            args += ['-loop', '1', '-framerate', str(FPS), '-i', ffpath(asset)]
    texture_index = 4 + len(recipe['stickers'])
    top_alpha_index, bottom_alpha_index = texture_index + 1, texture_index + 2
    args += ['-loop', '1', '-framerate', str(FPS), '-i', ffpath(Path(recipe['full_frame_sticker']['path']))]
    args += ['-loop', '1', '-framerate', str(FPS), '-i', ffpath(root / 'top_alpha.pgm')]
    args += ['-loop', '1', '-framerate', str(FPS), '-i', ffpath(root / 'bottom_alpha.pgm')]
    graph = [f'color=c=black@0.0:s={W}x{H}:r={FPS}:d={SECONDS},format=rgba[clear]']
    for i, (height, y) in enumerate([(620, 760), (620, 600), (570, 700), (570, 900)]):
        graph.append(f'[{i}:v]trim=duration=15,setpts=PTS-STARTPTS,fps={FPS},scale={W}:-2,'
                     f'crop={W}:{height}:0:{y},setsar=1,format=rgba[sc{i}]')
    graph += ['[sc0][sc1]concat=n=2:v=1:a=0[top]', '[sc2][sc3]concat=n=2:v=1:a=0[bottom]',
              f'[{top_alpha_index}:v]format=gray[ta]', f'[{bottom_alpha_index}:v]format=gray[ba]',
              '[top][ta]alphamerge[topa]', '[bottom][ba]alphamerge[bottoma]',
              '[clear][topa]overlay=x=0:y=0:format=rgb:alpha=straight:shortest=1[s1]',
              '[s1][bottoma]overlay=x=0:y=1830:format=rgb:alpha=straight:shortest=1[s2]',
              f'[{texture_index}:v]fps=30,scale=1080:2400,format=rgba,colorchannelmixer=aa=0.02[texture]',
              '[s2][texture]overlay=format=rgb:alpha=straight:shortest=1[s3]']
    previous = 's3'
    for i, item in enumerate(recipe['stickers']):
        graph.append(f'[{i + 4}:v]fps={FPS},scale={item["width"]}:{item.get("height", -2)},format=rgba,'
                     f'colorchannelmixer=aa={item["opacity"]}[st{i}]')
        output = f'decor{i}'
        # Small deterministic movement in addition to the original GIF frames.
        graph.append(f'[{previous}][st{i}]overlay=x=\'{item["x"]}+5*sin(2*PI*t/6+{i})\':'
                     f'y=\'{item["y"]}+4*sin(2*PI*t/5+{i})\':format=rgb:alpha=straight:shortest=1[{output}]')
        previous = output
    particles = []
    for side in range(2 if recipe.get('edge_particles', {}).get('enabled', True) else 0):
        for i in range(6):
            x = ('1' if side == 0 else 'w-9') + f'+2*sin(t*1.2+{i})'
            y = f'mod({i * 389 + side * 173}+t*{45+i*9},h+24)-12'
            particles.append("drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='·':"
                             f"fontsize=15:fontcolor=0xffd27d@0.8:x='{x}':y='{y}'")
    graph.append(f'[{previous}]' + (','.join(particles) + ',' if particles else '') + 'split=2[ec][ea]')
    graph += ['[ec]format=yuv420p[colour]', '[ea]alphaextract[alpha]']
    script = root / 'prepare_effect.ffgraph'
    script.write_text(';\n'.join(graph), encoding='utf-8')
    args += ['-filter_complex_script', ffpath(script),
             '-map', '[colour]', '-an', '-t', str(SECONDS), '-c:v', 'h264_nvenc', '-preset', 'p4',
             '-rc', 'vbr', '-cq', '17', '-b:v', '0', '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr',
             '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
             '-movflags', '+faststart', ffpath(root / 'effect_colour.mp4'),
             '-map', '[alpha]', '-an', '-t', str(SECONDS), '-c:v', 'ffv1', '-level', '3',
             '-threads', '4', '-pix_fmt', 'gray', ffpath(root / 'effect_alpha.mkv')]
    return run_stage(root, '01_prepare_effect', args)


def compose(root: Path, source: Path) -> dict:
    graph = (f'[0:v]trim=duration={SECONDS},setpts=PTS-STARTPTS,fps={FPS},'
             f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[main];'
             '[1:v][2:v]alphamerge[effect];'
             '[main][effect]overlay=format=yuv420:alpha=straight:shortest=1[out]')
    (root / 'compose.ffgraph').write_text(graph, encoding='utf-8')
    return run_stage(root, '02_compose_cached_effect', [
        '-filter_complex_threads', '6', '-i', ffpath(source),
        '-i', ffpath(root / 'effect_colour.mp4'), '-i', ffpath(root / 'effect_alpha.mkv'),
        '-filter_complex_script', ffpath(root / 'compose.ffgraph'), '-map', '[out]', '-map', '0:a:0?',
        '-t', str(SECONDS), '-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', '22',
        '-b:v', '6M', '-maxrate:v', '8M', '-bufsize:v', '16M',
        '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '2',
        '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
        '-movflags', '+faststart', ffpath(root / 'FFmpeg_30秒效果测试.mp4')])


def verify(root: Path) -> dict:
    output = root / 'FFmpeg_30秒效果测试.mp4'
    info = probe(output)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    assert (video['width'], video['height'], video['avg_frame_rate']) == (W, H, '30/1')
    assert int(video['nb_frames']) == FPS * SECONDS
    assert abs(float(info['format']['duration']) - SECONDS) < 0.1
    assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac'
    decode = run_stage(root, '03_decode_validation', [
        '-v', 'error', '-xerror', '-i', ffpath(output), '-map', '0:v', '-map', '0:a', '-f', 'null', '-'])
    save_json(root / 'output_probe.json', info)
    return {'media_validation': 'PASS', 'duration_seconds': float(info['format']['duration']),
            'frames': int(video['nb_frames']), 'canvas': [W, H], 'fps': 30,
            'audio_codec': audio['codec_name'], 'decode_validation': decode,
            'file_size_bytes': output.stat().st_size, 'visual_acceptance': 'USER_PENDING'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
    root = args.output_dir or Path('/mnt/c/Users/Michael/Videos') / f'FFmpeg结构测试_{stamp}'
    if root.exists():
        raise FileExistsError(f'Refusing to overwrite an existing experiment: {root}')
    recipe = make_recipe()
    inputs = [args.source, REFERENCE, FFMPEG, FFPROBE,
              *(Path(p) for p in recipe['landscapes']),
              *(Path(s['path']) for s in recipe['stickers']), Path(recipe['full_frame_sticker']['path'])]
    for p in inputs:
        if not p.is_file():
            raise FileNotFoundError(p)
    root.mkdir(parents=True)
    save_json(root / 'recipe.json', recipe)
    save_json(root / 'input_snapshot.json', [
        {'path': str(p), 'size': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns} for p in inputs])
    write_mask(root / 'top_alpha.pgm', W, 620, True)
    write_mask(root / 'bottom_alpha.pgm', W, 570, False)
    print(f'OUTPUT_DIRECTORY {root}', flush=True)
    timings = [prepare_effect(root, recipe), compose(root, args.source)]
    checks = verify(root)
    # A watchable reference excerpt, not a new Jianying export benchmark.
    run_stage(root, '04_reference_excerpt', ['-i', ffpath(REFERENCE), '-t', str(SECONDS),
              '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy', '-movflags', '+faststart',
              ffpath(root / '剪映参考_原样片前30秒.mp4')])
    current = [{'path': str(p), 'size': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns} for p in inputs]
    original = json.loads((root / 'input_snapshot.json').read_text(encoding='utf-8'))
    assert current == original, 'An input changed during the experiment; investigate before accepting.'
    report = {
        'schema': 'ffmpeg_overlay_sample_report_v1', 'created_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'status': 'MEDIA_PASS_VISUAL_PENDING', 'source': str(args.source), 'source_range_seconds': [0, 30],
        'reference': str(REFERENCE), 'output': str(root / 'FFmpeg_30秒效果测试.mp4'),
        'runtime': 'Windows FFmpeg 8.1 launched from WSL; Windows-mounted inputs and outputs',
        'gpu': 'NVIDIA GeForce RTX 4080 SUPER', 'timings': timings,
        'first_output_render_seconds': round(sum(t['wall_seconds'] for t in timings), 3),
        'reuse_composition_seconds': timings[1]['wall_seconds'],
        'ffmpeg_reported_render_seconds': {
            item['stage']: item.get('ffmpeg_reported_render_seconds') for item in timings},
        'reuse_speed_times_realtime': round(SECONDS / timings[1]['wall_seconds'], 3),
        'jianying_export_seconds': None,
        'timing_scope': 'FFmpeg start, decode, filtering, encoding and file write; excludes asset discovery, human work and verification',
        'source_files_unchanged_size_mtime': True, 'checks': checks,
        'limitations': ['Approximate particle replacement, not the native Jianying particle engine',
                        'No measured Jianying export time; cannot claim a speedup factor',
                        'H.264 colour cache is high-quality lossy; alpha cache is lossless',
                        'One 30-second experiment, not a full-length production benchmark'],
    }
    save_json(root / 'timing_report.json', report)
    prep, render = (t['wall_seconds'] for t in timings)
    (root / '查看说明.txt').write_text(
        f'先看：FFmpeg_30秒效果测试.mp4\n对照：剪映参考_原样片前30秒.mp4\n\n'
        f'两条均取同一故事原片的前30秒，FFmpeg版本从未叠加装饰的原素材制作。\n'
        f'分辨率1080×2400，30帧，保留原声。\n'
        f'效果准备一次：{prep:.3f}秒。\n复用效果后的单条合成：{render:.3f}秒。\n'
        f'首条两阶段渲染合计：{prep + render:.3f}秒。\n'
        '粒子为FFmpeg轻粒子近似实现；其余复用本机风景和贴纸素材。\n'
        '剪映参考仅从用户现有成片截取，未测剪映重新导出耗时。\n'
        '所有源文件和现有生产流程均未改动。effect_colour.mp4、effect_alpha.mkv为成对复用的中间效果层。\n',
        encoding='utf-8-sig')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
