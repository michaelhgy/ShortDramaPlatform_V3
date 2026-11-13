"""Per-template sticker selections and reusable transparent caches.

Planning reads only the portable individual-material library. Preparation uses
the accepted adapter, retains native animation, and publishes a cache only
after full decoding. No business files or existing prepared layouts are changed.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import random
import secrets
import subprocess
import os
import sys
import time
import uuid

PROJECT = Path(__file__).resolve().parents[3]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from server.template_engine.jianying59_template.sticker_skin_library import (
    StickerPlacement, StickerResource, choose_skin_and_layout, load_sticker_skin_catalog,
)

PROFILE = {'canvas': [1080, 2400], 'fps': 30, 'cache_size': [1080, 960],
           'cache_frames': 900, 'alpha_multiplier': 0.8}


def _quiet_run(*args, **kwargs):
    if os.name == 'nt': kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return subprocess.run(*args, **kwargs)


def _quiet_output(*args, **kwargs):
    if os.name == 'nt': kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return subprocess.check_output(*args, **kwargs)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def local_path(root, relative):
    path = (Path(root).resolve() / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Resource path escapes library: '+str(relative))
    return path


def renderer_contract():
    paths = ['tools/ffmpeg_overlay_lab/sticker_layer.py',
             'tools/ffmpeg_overlay_lab/sticker_library/template_cache.py']
    return {name: file_hash(PROJECT/name) for name in paths}


def make_batch(root, count, seed=None, seconds=600, excluded_families=()):
    if (not isinstance(count, int) or count < 1 or not math.isfinite(seconds)
            or seconds <= 0 or round(seconds*30) < 1):
        raise ValueError('Positive count and duration of at least one frame required')
    if seed is None:
        seed = secrets.randbits(64)
    if not isinstance(seed, int) or seed < 0:
        raise ValueError('Seed must be a nonnegative integer')
    root = Path(root)
    catalog = load_sticker_skin_catalog(root/'sources/usable_catalog.json')
    inventory = read(root/'inventory.json')['resources']
    motion = read(root/'sources/motion_reference.json')
    motion = {'placements': [{'legacy_role': p['legacy_role'], 'motion': p['motion']}
                             for p in motion['placements']]}
    # The old assets/catalog.json is intentionally not read here.
    groups = {}
    for skin in catalog.skins:
        resources = tuple(r for r in skin.resources if r.resource_id in inventory)
        if skin.skin_id not in excluded_families and len(resources) >= 16:
            groups[skin.skin_id] = replace(skin, resources=resources)
    if not groups:
        raise ValueError('No family with 16 usable individual stickers')
    rng = random.Random(seed); bag = []; previous = None; plans = []
    contract = renderer_contract()
    for index in range(count):
        if not bag:
            bag = sorted(groups); rng.shuffle(bag)
            if len(bag) > 1 and bag[-1] == previous:
                bag[-1], bag[0] = bag[0], bag[-1]
        family_id = bag.pop(); skin = groups[family_id]
        layout_seed = rng.getrandbits(64)
        _, pairs = choose_skin_and_layout(catalog=replace(catalog, skins=(skin,)), seed=layout_seed)
        selection = []
        for resource, placement in pairs:
            native = inventory[resource.resource_id]
            fields = ['normalized_poster', 'poster_sha256', 'size', 'kind']
            if native.get('native_cache'):
                fields += ['native_cache', 'native_cache_sha256', 'cycle_frames']
            selection.append({'resource': asdict(resource), 'placement': asdict(placement),
                              'source': {key: native[key] for key in fields}})
        settings = {'profile': PROFILE, 'selection': selection,
                    'motion_reference': motion, 'renderer': contract}
        key = digest(settings)
        template_id = f'tpl_{seed:016x}_{index+1:05d}'
        folder = f't/{template_id[-12:]}/{key[:12]}'
        plans.append({'index': index, 'mode': 'individual_materials', 'template_id': template_id,
                      'family_id': family_id, 'family': skin.skin_name, 'layout_seed': layout_seed,
                      'settings': settings, 'cache_key': key,
                      'cache': folder+'/sticker_rgba_30s.mkv', 'manifest': folder+'/cache.json',
                      'cache_frames': 900, 'start_frame': rng.randrange(900),
                      'frames': round(seconds*30), 'fps': 30, 'canvas': [1080, 2400],
                      'global_alpha_multiplier': 0.8})
        previous = family_id
    return {'schema_version': 2, 'library_id': 'stickers_v1_20261018', 'seed': seed,
            'count': count, 'seconds': seconds, 'plans': plans, 'usage_writes': False,
            'selection': 'balanced family bags; fresh individual selection and layout per template'}


def build_recipe(root, plan):
    from tools.ffmpeg_overlay_lab import sticker_layer
    settings = plan['settings']
    pairs = [(StickerResource(**p['resource']), StickerPlacement(**p['placement']))
             for p in settings['selection']]
    recipe = sticker_layer.recipe_from_pairs(
        pairs, Path(root)/'normalized', plan['family'], plan['layout_seed'], None,
        settings['motion_reference'], settings['profile']['alpha_multiplier'])
    for p, selected in zip(recipe['placements'], settings['selection']):
        source = selected['source']
        # Check the exact file used by the adapter, not just a manifest entry.
        if Path(p['source']).resolve() != local_path(root, source['normalized_poster']):
            raise ValueError('Poster path does not match selected resource')
        p['source'] = p['copy'] = source['normalized_poster']
        if source.get('native_cache'):
            p.update(native_cache=source['native_cache'], native_cycle_frames=source['cycle_frames'])
            w, h = source['size']; p['crop'] = [0, 0, w, h]
            ratio = 420*p['original_placement']['scale']/max(w, h)
            p['width'], p['height'] = max(2, round(w*ratio)), max(2, round(h*ratio))
            mt = p['motion']; mw = p['width']*(1+mt['scale_amplitude']); mh = p['height']*(1+mt['scale_amplitude'])
            angles = [(p['angle']+mt['wobble_degrees']*n/100)*math.pi/180 for n in range(-100, 101)]
            p['tile'] = [math.ceil(max(abs(mw*math.cos(t))+abs(mh*math.sin(t)) for t in angles))+12,
                         math.ceil(max(abs(mh*math.cos(t))+abs(mw*math.sin(t)) for t in angles))+12]
    recipe['intrinsic_png_shape_animation'] = any('native_cache' in p for p in recipe['placements'])
    return recipe


def prepare(root, plan, ffmpeg):
    started = time.perf_counter()
    root = Path(root).resolve(); ffmpeg = Path(ffmpeg); key = digest(plan['settings'])
    if key != plan['cache_key'] or plan['settings']['profile'] != PROFILE:
        raise ValueError('Plan changed or unsupported profile; create a new plan')
    expected = f"t/{plan['template_id'][-12:]}/{key[:12]}"
    legacy = f"templates/{plan['template_id']}/{key}"
    if not any(plan['cache'] == folder+'/sticker_rgba_30s.mkv' and plan['manifest'] == folder+'/cache.json' for folder in (expected, legacy)):
        raise ValueError('Cache path does not match template and settings')
    cache = local_path(root, plan['cache']); marker = local_path(root, plan['manifest'])
    if marker.exists():
        result = read(marker)
        if result['cache_key'] != key or file_hash(cache) != result['cache_sha256']:
            raise ValueError('Existing cache failed integrity check; preserved for inspection')
        return {'reused': True, 'wall_seconds': round(time.perf_counter()-started, 3),
                'cache': plan['cache'], 'cache_sha256': result['cache_sha256']}
    if cache.exists():
        raise FileExistsError('Cache without completion record preserved: '+str(cache))
    if plan['settings']['renderer'] != renderer_contract():
        raise ValueError('Renderer changed since planning; create a new plan')
    # All source hashes are checked before rendering. Existing completed caches
    # remain reusable independently of later catalogue or source changes.
    for selected in plan['settings']['selection']:
        source = selected['source']
        for field, hash_field in [('normalized_poster', 'poster_sha256'), ('native_cache', 'native_cache_sha256')]:
            if field in source and file_hash(local_path(root, source[field])) != source[hash_field]:
                raise ValueError('Source changed since planning: '+source[field])
    cache.parent.mkdir(parents=True, exist_ok=True)
    lock = cache.parent/'.prepare.lock'
    with lock.open('x', encoding='utf-8') as f:
        f.write('Cache preparation in progress. Do not start another writer.\n')
    try:
        from tools.ffmpeg_overlay_lab import sticker_layer
        attempt = cache.parent/('attempt_'+uuid.uuid4().hex[:12]); attempt.mkdir()
        recipe = build_recipe(root, plan); save(attempt/'recipe.json', recipe)
        graph = sticker_layer.cache_graph(recipe)
        args = [str(ffmpeg), '-hide_banner', '-nostdin', '-n', '-filter_complex_threads', '4']
        for p in recipe['placements']:
            if p.get('native_cache'):
                graph = graph.replace(f'[{p["layer"]}:v]format=rgba,',
                                      f'[{p["layer"]}:v]trim=end_frame=900,settb=1/30,setpts=N,format=rgba,')
                args += ['-threads', '1', '-stream_loop', '-1', '-i', str(local_path(root, p['native_cache']))]
            else:
                args += ['-loop', '1', '-framerate', '30', '-threads', '1', '-i', str(local_path(root, p['copy']))]
        script = attempt/'prepare.ffgraph'; script.write_text(graph, encoding='utf-8')
        pending = attempt/'sticker_rgba_30s.mkv'
        args += ['-filter_complex_script', str(script), '-map', '[out]', '-an', '-frames:v', '900', '-t', '30',
                 '-c:v', 'ffv1', '-level', '3', '-threads', '4', '-pix_fmt', 'bgra', str(pending)]
        save(attempt/'command.json', args); encode_started = time.perf_counter()
        with (attempt/'encode.log').open('wb') as log:
            run = _quiet_run(args, stdout=log, stderr=subprocess.STDOUT)
        encode_seconds = round(time.perf_counter()-encode_started, 3)
        if run.returncode:
            raise RuntimeError('Cache encoding failed; see '+str(attempt/'encode.log'))
        probe = ffmpeg.with_name('ffprobe.exe' if ffmpeg.suffix.lower()=='.exe' else 'ffprobe')
        check = _quiet_run([str(probe), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                                '-show_streams', '-of', 'json', str(pending)],
                               capture_output=True, text=True, encoding='utf-8', check=True)
        if check.stderr.strip():
            raise RuntimeError('Cache decode reported errors: '+check.stderr)
        stream = json.loads(check.stdout)['streams'][0]
        if (stream['width'], stream['height'], stream['pix_fmt'], stream['avg_frame_rate'],
                int(stream['nb_read_frames']), stream['codec_name']) != (1080, 960, 'bgra', '30/1', 900, 'ffv1'):
            raise ValueError('Cache media validation failed')
        result = {'cache_key': key, 'cache': plan['cache'], 'cache_sha256': file_hash(pending),
                  'cache_bytes': pending.stat().st_size, 'recipe': (attempt/'recipe.json').relative_to(root).as_posix(),
                  'recipe_sha256': file_hash(attempt/'recipe.json'), 'encode_seconds': encode_seconds,
                  'decoded_frames': 900, 'profile': PROFILE,
                  'wall_seconds': round(time.perf_counter()-started, 3)}
        save(attempt/'cache.json', result)
        pending.rename(cache)
        (attempt/'cache.json').rename(marker)
        return dict(result, reused=False)
    finally:
        lock.unlink()
