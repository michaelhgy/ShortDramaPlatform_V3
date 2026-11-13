"""Prepared moving-texture library and per-template random narrow-strip cache."""
from __future__ import annotations
import hashlib
import json
import math
import random
import subprocess
import os
import time
from pathlib import Path

import numpy as np

FF = Path('D:/V2_PackagingCache/ffmpeg/8.1/expanded/ffmpeg-8.1-full_build/bin/ffmpeg.exe')
FP = FF.with_name('ffprobe.exe')
W, H, FPS = 1080, 2400, 30


def _quiet_run(*args, **kwargs):
    if os.name == 'nt': kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return subprocess.run(*args, **kwargs)


def _quiet_output(*args, **kwargs):
    if os.name == 'nt': kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return subprocess.check_output(*args, **kwargs)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def run(args, log=None, raw=None):
    cmd = [str(FF), '-hide_banner', '-nostdin', '-v', 'error', '-n', *map(str, args)]
    started = time.perf_counter()
    process = _quiet_run(cmd, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = round(time.perf_counter()-started, 3)
    if log:
        log = Path(log)
        save(log.with_suffix('.command.json'), cmd)
        log.with_suffix('.log').write_bytes(process.stderr)
        save(log.with_suffix('.timing.json'), {'seconds': elapsed, 'returncode': process.returncode})
    if process.returncode:
        raise RuntimeError(process.stderr.decode('utf-8', 'replace')[-5000:])
    return process.stdout, elapsed


def probe(path):
    return json.loads(_quiet_output([str(FP), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))


def encode(cq=16):
    return ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', cq, '-b:v', 0, '-pix_fmt', 'yuv420p',
            '-r', 30, '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-movflags', '+faststart']


def verify_video(path, size, frames, audio_reference=None):
    p = probe(path)
    v = next(s for s in p['streams'] if s['codec_type'] == 'video')
    assert [v['width'], v['height']] == list(size), (path, v)
    assert v['avg_frame_rate'] == '30/1', (path, v['avg_frame_rate'])
    assert int(v.get('nb_frames', frames)) == frames
    assert abs(float(p['format']['duration'])-frames/30) < .05
    run(['-xerror', '-i', path, '-map', '0:v', '-f', 'null', '-'])
    result = {'size': size, 'frames': frames, 'fps': 30, 'full_decode_pass': True}
    if audio_reference:
        def audio_digest(file):
            b, _ = run(['-i', file, '-map', '0:a:0', '-c:a', 'copy', '-f', 'adts', '-'])
            return hashlib.sha256(b).hexdigest()
        assert audio_digest(path) == audio_digest(audio_reference)
        result['audio_unchanged'] = True
    return result


def loop_checks(path, frames, size):
    qw = max(32, round(size[0]/size[1]*240))
    raw, _ = run(['-i', path, '-vf', f'scale={qw}:240:flags=area,format=rgb24', '-frames:v', frames,
                  '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
    a = np.frombuffer(raw, np.uint8).reshape(frames, 240, qw, 3).astype(np.float32)
    differences = np.abs(a[1:]-a[:-1]).mean(axis=(1, 2, 3))
    seam = float(np.abs(a[-1]-a[0]).mean())
    p95 = float(np.percentile(differences, 95))
    assert seam <= max(2., p95*2.5), (str(path), seam, p95)
    assert float(differences.mean()) > .04, ('static asset', str(path))
    lum = a @ np.array([.2126, .7152, .0722], np.float32)
    # Dense horizontal sampling is an admission diagnostic, not proof of visual approval.
    visible = (lum > 20).mean(axis=1)
    columns = np.linspace(0, qw-1, 41).round().astype(int)
    mean_visible = visible[:, columns].mean(axis=0)
    column_motion = np.abs(lum[1:]-lum[:-1]).mean(axis=(0, 1))[columns]
    column_detail = np.abs(lum[:, 2:]-lum[:, :-2]).mean(axis=(0, 1))[columns]
    hashes, _ = run(['-stream_loop', 2, '-i', path, '-map', '0:v', '-frames:v', frames*3, '-f', 'framemd5', '-'])
    hashes = [s.rsplit(',', 1)[-1].strip() for s in hashes.decode().splitlines() if not s.startswith('#')]
    assert len(hashes) == frames*3 and hashes[:frames] == hashes[frames:frames*2] == hashes[frames*2:]
    return {'seam_mean': seam, 'neighbour_p95': p95, 'mean_motion': float(differences.mean()),
            'three_decoded_cycles_identical': True, 'cycle_frames': frames,
            'positions_sampled': 41, 'minimum_column_mean_visible_fraction': float(mean_visible.min()),
            'minimum_column_motion': float(column_motion.min()), 'minimum_column_detail': float(column_detail.min()),
            'sampled_column_visible_fractions': mean_visible.round(4).tolist(),
            'visual_status': 'PENDING_USER_REVIEW'}


def prepare_asset(root, spec):
    root = Path(root)
    folder = root/'assets'/spec['id']
    folder.mkdir(parents=True, exist_ok=True)
    source = root/spec['source']
    digest = sha(source)
    meta = folder/'asset.json'
    if meta.exists():
        asset = read(meta)
        assert asset['source_sha256'] == digest and asset['sha256'] == sha(root/asset['file'])
        return asset
    native = probe(source)
    stream = next(s for s in native['streams'] if s['codec_type'] == 'video')
    iw, ih = stream['width'], stream['height']
    x, y, cw, ch = spec['crop']
    assert all(v % 2 == 0 for v in [x, y, cw, ch])
    assert x >= 0 and y >= 0 and x+cw <= iw and y+ch <= ih
    oh = 1200
    ow = 2*round((cw/ch*oh)/2)
    n = min(300, int(float(native['format']['duration'])*30))
    overlap = 18
    period = n-overlap
    # A complete middle segment followed by tail->head blending. The file edge
    # then joins original consecutive source frames instead of two distant frames.
    weight = f'(0.5-0.5*cos(PI*min(max(T*30/{overlap-1},0),1)))'
    graph = (f'[0:v]fps=30,tpad=stop_mode=clone:stop_duration=1,trim=end_frame={n},'
             f'crop={cw}:{ch}:{x}:{y},scale={ow}:{oh}:flags=lanczos,setsar=1,'
             'format=yuv420p,settb=1/30,setpts=N,split=3[h0][m0][t0];'
             f'[h0]trim=end_frame={overlap},setpts=PTS-STARTPTS[h];'
             f'[m0]trim=start_frame={overlap}:end_frame={n-overlap},setpts=PTS-STARTPTS[m];'
             f'[t0]trim=start_frame={n-overlap}:end_frame={n},setpts=PTS-STARTPTS[t];'
             f"[t][h]blend=all_expr='A*(1-{weight})+B*{weight}':shortest=1[x];"
             f'[m][x]concat=n=2:v=1:a=0,fps=30,trim=end_frame={period},settb=1/30,setpts=N[out]')
    (folder/'loop.ffgraph').write_text(graph, encoding='utf-8')
    output = folder/'material_loop.mp4'
    if not output.exists():
        _, elapsed = run(['-threads', 4, '-filter_complex_threads', 4, '-i', source,
                          '-filter_complex_script', folder/'loop.ffgraph', '-map', '[out]', '-frames:v', period,
                          '-an', *encode(14), '-g', 30, output], folder/'prepare')
    else:
        elapsed = read(folder/'prepare.timing.json')['seconds']
    media = verify_video(output, [ow, oh], period)
    checks = loop_checks(output, period, [ow, oh])
    assert checks['minimum_column_mean_visible_fraction'] > .12, (spec['id'], 'empty columns', checks)
    assert checks['minimum_column_motion'] > .04, (spec['id'], 'static columns', checks)
    assert checks['minimum_column_detail'] > .12, (spec['id'], 'flat columns', checks)
    assert sha(source) == digest
    asset = {**spec, 'source_size': [iw, ih], 'source_sha256': digest, 'file': output.relative_to(root).as_posix(),
             'size': [ow, oh], 'frames': period, 'fps': 30, 'duration': period/30,
             'normalization_aspect_error': abs((ow/oh)/(cw/ch)-1), 'sha256': sha(output), 'bytes': output.stat().st_size,
             'prepare_seconds': elapsed, 'source_frames_used': n, 'overlap_frames': overlap,
             'loop_method': 'middle followed by cosine tail-to-head overlap; native consecutive frames at file boundary',
             'opacity': 1, 'feather_px': 0, 'colour_adjustment': None, 'speed': 1,
             'media_check': media, 'loop_check': checks, 'available_for_library_trials': True,
             'production_enabled': False, 'visual_status': 'PENDING_USER_REVIEW'}
    save(meta, asset)
    return asset


def make_plan(catalog, seed, asset_id=None, canvas=(1080, 2400), width_range=(5, 10)):
    if canvas != (1080, 2400):
        raise ValueError('v1 is calibrated for the current 1080x2400 template')
    assets = [a for a in catalog['assets'] if a['available_for_library_trials']]
    rng = random.Random(seed)
    asset = next(a for a in assets if a['id'] == asset_id) if asset_id else rng.choice(assets)
    if len(width_range)!=2 or any(type(x) is not int for x in width_range) or not 1<=width_range[0]<=width_range[1]<=W:
        raise ValueError('边条宽度必须为不超过画面1080像素的正整数，下限不能大于上限')
    widths = [rng.randint(*width_range) for _ in range(2)]
    sw = asset['size'][0]*2
    if width_range[1]>sw:raise ValueError('当前边条素材宽度不足以裁出所设置的边条')
    xs = [rng.randint(0, sw-widths[0])]
    minimum_separation = max(20, round(sw*.08))
    allowed = [(0, max(-1, xs[0]-minimum_separation)),
               (min(sw-widths[1]+1, xs[0]+minimum_separation), sw-widths[1])]
    allowed = [(lo, hi) for lo, hi in allowed if lo <= hi]
    count = sum(hi-lo+1 for lo, hi in allowed)
    ticket = rng.randrange(count)
    for lo, hi in allowed:
        if ticket <= hi-lo:
            xs.append(lo+ticket)
            break
        ticket -= hi-lo+1
    phase = rng.randrange(asset['frames'])
    sides = [{'side': name, 'width': width, 'crop_x': x, 'crop_y': 0}
             for name, width, x in zip(['left', 'right'], widths, xs)]
    return {'seed': seed, 'asset_id': asset['id'], 'asset_name': asset['name'], 'asset_file': asset['file'],
            'asset_sha256': asset['sha256'], 'native_size': asset['size'], 'scaled_size': [sw, H],
            'cycle_frames': asset['frames'], 'start_frame': phase, 'fps': 30, 'sides': sides,
            'minimum_position_separation': minimum_separation, 'opacity': 1, 'feather_px': 0,
            'playback_speed': 1, 'position_fixed_during_template': True, 'same_material_for_both_sides': True}


def prepare_strips(root, plan, folder):
    root, folder = Path(root), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cache = folder/'strips.mkv'
    meta = folder/'prepared.json'
    if meta.exists():
        result = read(meta)
        assert result['plan'] == plan and result['sha256'] == sha(cache)
        return cache, result
    source = root/plan['asset_file']
    assert sha(source) == plan['asset_sha256']
    width = sum(s['width'] for s in plan['sides'])
    graph = '[0:v]format=rgb24,split=2[l][r];'
    for tag, side in zip(['l', 'r'], plan['sides']):
        # Crop a padded local window BEFORE the exact 2x resize. This avoids
        # scaling an entire wide material to 2400 px for every template.
        cx = max(0, side['crop_x']//2-4)
        end = min(plan['native_size'][0], math.ceil((side['crop_x']+side['width'])/2)+4)
        cw = end-cx
        ox = side['crop_x']-cx*2
        graph += (f'[{tag}]crop={cw}:1200:{cx}:0:exact=1,scale={cw*2}:{H}:flags=lanczos,'
                  f'crop={side["width"]}:{H}:{ox}:0:exact=1[{tag}c];')
    graph += '[lc][rc]hstack=inputs=2,format=rgb24[out]'
    (folder/'crop.ffgraph').write_text(graph, encoding='utf-8')
    raw, crop_seconds = run(['-threads', 4, '-filter_complex_threads', 2, '-i', source, '-filter_complex', graph,
                             '-map', '[out]', '-frames:v', plan['cycle_frames'], '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], folder/'crop')
    data = np.frombuffer(raw, np.uint8).reshape(plan['cycle_frames'], H, width, 3)
    data = np.roll(data, -plan['start_frame'], axis=0)
    _, encode_seconds = run(['-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{H}', '-r', 30, '-i', '-',
                             '-frames:v', plan['cycle_frames'], '-an', '-c:v', 'ffv1', '-level', 3,
                             '-pix_fmt', 'bgr0', '-threads', 2, cache], folder/'encode', data.tobytes())
    differences = np.abs(data[1:].astype(np.float32)-data[:-1]).mean(axis=(1, 2, 3))
    seam = float(np.abs(data[-1].astype(np.float32)-data[0]).mean())
    p95 = float(np.percentile(differences, 95))
    assert seam <= max(3., p95*3), (plan, seam, p95)
    result = {'plan': plan, 'crop_seconds': crop_seconds, 'encode_seconds': encode_seconds,
              'prepare_seconds': round(crop_seconds+encode_seconds, 3), 'sha256': sha(cache),
              'seam_mean': seam, 'neighbour_p95': p95, 'bytes': cache.stat().st_size}
    save(meta, result)
    return cache, result


def overlay_graph(plan, input_index, base='body', out='out', fmt='yuv420p'):
    lw, rw = [s['width'] for s in plan['sides']]
    return (';'.join([f'[{input_index}:v]format=rgba,split=2[l][r]',
                     f'[l]crop={lw}:{H}:0:0:exact=1[lc]', f'[r]crop={rw}:{H}:{lw}:0:exact=1[rc]',
                     f'[{base}][lc]overlay=0:0:format=rgb:shortest=1[b]',
                     f'[b][rc]overlay={W-rw}:0:format=rgb:shortest=1,format={fmt}[{out}]']))


def verify_geometry_and_cycles(plan, packed):
    graph = f'color=c=0x3d4d5b:s={W}x{H}:r=30,format=rgba[body];'+overlay_graph(plan, 0, fmt='rgba')
    raw, _ = run(['-i', packed, '-filter_complex_threads', 2, '-filter_complex', graph,
                  '-map', '[out]', '-frames:v', 1, '-pix_fmt', 'rgba', '-f', 'rawvideo', '-'])
    image = np.frombuffer(raw, np.uint8).reshape(H, W, 4)
    occupied = np.where(np.any(image != image[0, W//2], axis=(0, 2)))[0].tolist()
    lw, rw = [s['width'] for s in plan['sides']]
    assert occupied == list(range(lw))+list(range(W-rw, W))
    n = plan['cycle_frames']
    hashes, _ = run(['-stream_loop', 2, '-i', packed, '-frames:v', n*3, '-f', 'framemd5', '-'])
    hashes = [s.rsplit(',', 1)[-1].strip() for s in hashes.decode().splitlines() if not s.startswith('#')]
    assert len(hashes) == n*3 and hashes[:n] == hashes[n:n*2] == hashes[n*2:]
    return {'left_width': lw, 'right_width': rw, 'no_pixels_outside_bands_before_encoding': True,
            'three_cycles_identical': True, 'frames_per_cycle': n}


def compose(base, packed, plan, output, folder):
    graph = '[0:v]trim=end_frame=300,settb=1/30,setpts=N,format=rgba[body];'+overlay_graph(plan, 1)
    _, elapsed = run(['-filter_complex_threads', 2, '-threads', 4, '-i', base, '-stream_loop', -1, '-i', packed,
                      '-filter_complex', graph, '-map', '[out]', '-map', '0:a:0?', '-frames:v', 300, '-t', 10,
                      *encode(19), '-c:a', 'copy', output], Path(folder)/'compose')
    return {'seconds': elapsed, 'media': verify_video(output, [W, H], 300, base),
            'geometry': verify_geometry_and_cycles(plan, packed)}
