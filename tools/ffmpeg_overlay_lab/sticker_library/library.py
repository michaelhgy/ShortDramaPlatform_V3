"""Draw and lay out individual stickers afresh for each new generation.

No Jianying cache, original image catalogue, or model is required at playback.
Planning is deterministic and never changes business files or usage counters.
"""
from __future__ import annotations
import argparse
import json
import math
import random
import subprocess
import time
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def resolve(root, relative):
    root = Path(root).resolve(); path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Resource path escapes library: '+str(relative))
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def make_prepared_batch(catalog, count, seed, seconds=600, excluded_families=()):
    """Balanced shuffled bags: every family once per round, then layout bags.

    A single prepared layout spans the template. Animation phase is an integer
    frame; it changes start time without changing scale, alpha or composition.
    """
    if not isinstance(count, int) or count < 1 or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Positive count and finite duration required')
    fps = catalog['profile']['fps']; total = round(seconds * fps)
    if total < 1: raise ValueError('Duration shorter than one frame')
    groups = {}
    for asset in catalog['assets']:
        if asset['available'] and asset['family_id'] not in excluded_families:
            groups.setdefault(asset['family_id'], []).append(asset)
    if not groups: raise ValueError('No available sticker families')
    rng = random.Random(seed); family_bag = []; variant_bags = {}; previous = None
    last_variant = {}; plans = []
    for index in range(count):
        if not family_bag:
            family_bag = sorted(groups); rng.shuffle(family_bag)
            if len(family_bag) > 1 and family_bag[-1] == previous:
                family_bag[-1], family_bag[0] = family_bag[0], family_bag[-1]
        family = family_bag.pop(); bag = variant_bags.get(family, [])
        if not bag:
            bag = sorted(groups[family], key=lambda a: a['id']); rng.shuffle(bag)
            if len(bag) > 1 and bag[-1]['id'] == last_variant.get(family):
                bag[-1], bag[0] = bag[0], bag[-1]
        asset = bag.pop(); variant_bags[family] = bag
        phase = rng.randrange(asset['cache_frames'])
        plans.append({'index': index, 'asset_id': asset['id'], 'family_id': family,
                      'family': asset['family'], 'cache': asset['cache'],
                      'cache_sha256': asset['cache_sha256'], 'cache_frames': asset['cache_frames'],
                      'start_frame': phase, 'frames': total, 'fps': fps,
                      'global_alpha_multiplier': 0.8, 'canvas': catalog['profile']['canvas']})
        previous = family; last_variant[family] = asset['id']
    return {'schema_version': 1, 'library_id': catalog['library_id'], 'seed': seed,
            'count': count, 'seconds': seconds, 'plans': plans,
            'usage_writes': False, 'selection': 'balanced shuffled family and per-family variant bags'}


def template_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('template_stickers', Path(__file__).with_name('template_cache.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def make_batch(root, count, seed=None, seconds=600, excluded_families=()):
    """Default new-template planner. Never samples the 93 prepared layouts."""
    return template_module().make_batch(root, count, seed, seconds, excluded_families)


def prepare(root, plan, ffmpeg):
    if plan.get('mode') != 'individual_materials':
        resolve(root, plan['cache'])
        return {'reused': True, 'mode': 'prepared_layout'}
    return template_module().prepare(root, plan, ffmpeg)


def overlay_graph(frames, phase=0, input_index=1, output='out', final_format='yuv420p'):
    if not isinstance(frames, int) or frames < 1 or not isinstance(phase, int) or not 0 <= phase < 900:
        raise ValueError('Invalid frame count or phase')
    # Stream looping is supplied at the input. No in-filter 900-frame buffer.
    return ';\n'.join([
        f'[0:v]trim=end_frame={frames},settb=1/30,setpts=N,format=rgba[base]',
        f'[{input_index}:v]trim=start_frame={phase}:end_frame={phase+frames},settb=1/30,setpts=N,format=rgba,split=2[pt][pb]',
        '[pt]crop=1080:480:0:0[topstick]', '[pb]crop=1080:480:0:480[bottomstick]',
        '[base][topstick]overlay=0:0:format=rgb:alpha=straight:shortest=1[withtop]',
        f'[withtop][bottomstick]overlay=0:1920:format=rgb:alpha=straight:shortest=1,format={final_format}[{output}]',
    ])


def render(root, plan, base, output, ffmpeg):
    if plan['canvas'] != [1080, 2400] or plan['fps'] != 30:
        raise ValueError('Rebuild the library for other dimensions/frame rates')
    output = Path(output)
    if output.exists(): raise FileExistsError(output)
    ffmpeg = Path(ffmpeg)
    ffprobe = ffmpeg.with_name('ffprobe.exe' if ffmpeg.suffix.lower()=='.exe' else 'ffprobe')
    probe = subprocess.run([str(ffprobe), '-v', 'error', '-select_streams', 'v:0', '-show_streams', '-show_format',
                            '-of', 'json', str(base)], capture_output=True, text=True, encoding='utf-8', check=True)
    info = json.loads(probe.stdout); stream = info['streams'][0]
    if [stream['width'], stream['height']] != plan['canvas'] or stream['avg_frame_rate'] != '30/1':
        raise ValueError('Base must match the library canvas and frame rate')
    if float(stream.get('duration') or info['format']['duration']) + 1/30 < plan['frames']/30:
        raise ValueError('Base is shorter than the requested template')
    output.parent.mkdir(parents=True, exist_ok=True)
    preparation = prepare(root, plan, ffmpeg)
    cache = resolve(root, plan['cache'])
    script = output.with_suffix('.ffgraph')
    script.write_text(overlay_graph(plan['frames'], plan['start_frame']), encoding='utf-8')
    command = [str(ffmpeg), '-hide_banner', '-nostdin', '-n', '-filter_complex_threads', '4',
               '-threads', '2', '-i', str(base), '-threads', '2', '-stream_loop', '-1', '-i', str(cache),
               '-filter_complex_script', str(script), '-map', '[out]', '-map', '0:a:0?',
               '-frames:v', str(plan['frames']), '-t', str(plan['frames']/30),
               '-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', '19', '-b:v', '0',
               '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-c:a', 'copy', '-movflags', '+faststart', str(output)]
    save(output.with_suffix('.command.json'), command)
    start = time.perf_counter()
    with output.with_suffix('.log').open('wb') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    timing = {'wall_seconds': round(time.perf_counter()-start, 3), 'returncode': result.returncode,
              'preparation': preparation}
    save(output.with_suffix('.timing.json'), timing)
    if result.returncode: raise RuntimeError(output.with_suffix('.log').read_text(errors='replace')[-3000:])
    return timing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan'); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--count', type=int, default=1); p.add_argument('--seed', type=int)
    p.add_argument('--seconds', type=float, default=600); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('generate'); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--seconds', type=float, default=600); p.add_argument('--seed', type=int)
    p.add_argument('--base', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ffmpeg', type=Path, required=True)
    p = sub.add_parser('prepare'); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--index', type=int, default=0)
    p.add_argument('--ffmpeg', type=Path, required=True)
    p = sub.add_parser('render'); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--index', type=int, default=0)
    p.add_argument('--base', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ffmpeg', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'plan':
        if args.output.exists(): raise FileExistsError(args.output)
        batch = make_batch(args.root, args.count, args.seed, args.seconds)
        save(args.output, batch)
        print(json.dumps({'plan': str(args.output), 'seed': batch['seed'], 'count': batch['count']}, ensure_ascii=False))
    elif args.command == 'generate':
        plan_file = args.output.with_suffix('.stickers.json')
        if args.output.exists() or plan_file.exists():
            raise FileExistsError('Generation already exists; replay its saved plan for a retry: '+str(plan_file))
        batch = make_batch(args.root, 1, args.seed, args.seconds)
        save(plan_file, batch)
        print(json.dumps(render(args.root, batch['plans'][0], args.base, args.output, args.ffmpeg), ensure_ascii=False))
    elif args.command == 'prepare':
        print(json.dumps(prepare(args.root, read(args.plan)['plans'][args.index], args.ffmpeg), ensure_ascii=False))
    else:
        print(json.dumps(render(args.root, read(args.plan)['plans'][args.index], args.base, args.output, args.ffmpeg), ensure_ascii=False))


if __name__ == '__main__': main()
