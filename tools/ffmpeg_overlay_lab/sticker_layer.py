"""Adapt the existing sixteen-sticker planner to a reusable FFmpeg layer.

Reads the installed catalogue and original PNGs without changing either.
The source selector remains the project's actual choose_skin_and_layout.
Animation comes from the previously reviewed motion recipe. No Jianying UI,
downloads, resource activation, or business usage-counter writes occur here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import math
from pathlib import Path
import shutil

from PIL import Image
from server.template_engine.jianying59_template.sticker_skin_library import (
    choose_skin_and_layout, load_sticker_skin_catalog,
)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def make_recipe(catalog_path, source_root, family, seed, assets_dir,
                motion_reference, alpha_multiplier=0.8):
    if not 0 < alpha_multiplier <= 1:
        raise ValueError('Use a positive strength at or below the reference')
    catalog = load_sticker_skin_catalog(Path(catalog_path))
    skin = next(s for s in catalog.skins if s.skin_name == family)
    _, pairs = choose_skin_and_layout(catalog=replace(catalog, skins=(skin,)), seed=seed)
    # Replaying the actual selector must reproduce resources and placement.
    assert pairs == choose_skin_and_layout(catalog=replace(catalog, skins=(skin,)), seed=seed)[1]
    return recipe_from_pairs(pairs, source_root, family, seed, assets_dir,
                             motion_reference, alpha_multiplier)


def recipe_from_pairs(pairs, source_root, family, seed, assets_dir,
                      motion_reference, alpha_multiplier=0.8):
    """Adapt a saved selection using the same accepted geometry and motion.

    With assets_dir=None the portable library's own posters are used directly;
    planning and recipe construction do not create duplicate image copies.
    """
    if not 0 < alpha_multiplier <= 1:
        raise ValueError('Use a positive strength at or below the reference')
    placements = []
    if assets_dir is not None:
        assets_dir = Path(assets_dir)
        assets_dir.mkdir(parents=True, exist_ok=True)
    for i, (resource, place) in enumerate(pairs):
        source = Path(source_root) / resource.resource_id / resource.payload_md5 / 'singleImage.png'
        if not source.is_file():
            raise FileNotFoundError(f'{family}: selected PNG unavailable: {source}')
        target = assets_dir / f'{i:02d}_{resource.resource_id}.png' if assets_dir is not None else source
        digest = sha256(source)
        if not target.exists():
            shutil.copy2(source, target)
        assert sha256(target) == digest
        with Image.open(target) as im:
            rgba = im.convert('RGBA')
            alpha = rgba.getchannel('A')
            bounds = alpha.getbbox()
            if bounds is None or alpha.getextrema()[0] != 0:
                raise ValueError(f'Expected visible content and transparent background: {source}')
            x, y, right, bottom = bounds
            w, h = right - x, bottom - y
            original_size = list(rgba.size)
        ratio = 420 * place.scale / max(w, h)
        width, height = max(2, round(w * ratio)), max(2, round(h * ratio))
        band = int(place.role.startswith('bottom'))
        center = [round(540 + place.transform_x * 540),
                  round(1200 - place.transform_y * 1200 - 1920 * band)]
        reference = motion_reference['placements'][i]
        assert place.role.rsplit('_', 1)[-1] == reference['legacy_role'].rsplit('_', 1)[-1]
        motion = deepcopy(reference['motion'])
        max_w = width * (1 + motion['scale_amplitude'])
        max_h = height * (1 + motion['scale_amplitude'])
        angles = [(place.rotation + motion['wobble_degrees'] * n / 100) * math.pi / 180
                  for n in range(-100, 101)]
        tile = [math.ceil(max(abs(max_w * math.cos(t)) + abs(max_h * math.sin(t)) for t in angles)) + 12,
                math.ceil(max(abs(max_h * math.cos(t)) + abs(max_w * math.sin(t)) for t in angles)) + 12]
        placements.append({
            'layer': i, 'band': band, 'legacy_role': place.role,
            'resource_id': resource.resource_id, 'name': resource.name,
            'source': str(source), 'copy': str(target), 'sha256': digest,
            'source_size': original_size, 'crop': [x, y, w, h],
            'width': width, 'height': height, 'tile': tile, 'center': center,
            'angle': place.rotation, 'original_alpha': place.alpha,
            'opacity': round(place.alpha * alpha_multiplier, 6),
            'motion': motion, 'original_placement': asdict(place),
        })
    assert len(placements) == len({p['resource_id'] for p in placements}) == 16
    return {
        'family': family, 'seed': seed, 'count': 16, 'top_count': 8, 'bottom_count': 8,
        'canvas': [1080, 2400], 'bands': [[0, 480], [1920, 2400]],
        'cache_size': [1080, 960], 'fps': 30, 'cache_seconds': 30, 'preview_seconds': 10,
        'global_alpha_multiplier': alpha_multiplier, 'allows_overlap': True,
        'selector': 'server.template_engine.jianying59_template.sticker_skin_library.choose_skin_and_layout',
        'layout': 'original selection, 16 slots, scales, rotations, alpha hierarchy; coordinates converted to pixels',
        'motion': 'reviewed per-slot presets, phases and 5/6/10-second periods; joint repeat every 30 seconds',
        'intrinsic_png_shape_animation': False, 'placements': placements,
        'cache_layout': 'RGBA top 1080x480 then bottom 1080x480; unpack to y=0 and y=1920',
        'status': 'PREVIEW_PENDING',
    }


def cache_graph(recipe):
    graph = []
    for p in recipe['placements']:
        i = p['layer']; x, y, w, h = p['crop']; mt = p['motion']; phase = mt['phase']
        scale = f"scale=w='{p['width']}*(1+{mt['scale_amplitude']}*sin(2*PI*t/{mt['scale_period']}+{phase}))':h=-1:eval=frame:flags=bilinear"
        angle = f"({p['angle']}+{mt['wobble_degrees']}*sin(2*PI*t/{mt['rotate_period']}+{phase}))*PI/180"
        cw, ch = p['tile']
        graph.append(f"[{i}:v]format=rgba,crop={w}:{h}:{x}:{y},{scale},rotate=angle='{angle}':ow={cw}:oh={ch}:c=none,colorchannelmixer=aa={p['opacity']}[asset{i}]")
    for band, name in [(0, 'top'), (1, 'bottom')]:
        graph.append(f'color=c=black@0:s=1080x480:r=30:d=30,format=rgba[{name}base]')
        last = name + 'base'
        for j, p in enumerate(p for p in recipe['placements'] if p['band'] == band):
            mt = p['motion']; phase = mt['phase']; cx, cy = p['center']
            xx = f"round({cx}+{mt['drift_x']}*sin(2*PI*t/{mt['period']}+{phase})-w/2)"
            yy = f"round({cy}+{mt['drift_y']}*cos(2*PI*t/{mt['rotate_period']}+{phase})-h/2)"
            out = name if j == 7 else f'{name}{j}'
            graph.append(f"[{last}][asset{p['layer']}]overlay=x='{xx}':y='{yy}':eval=frame:format=rgb:alpha=straight:shortest=1[{out}]")
            last = out
    graph.append('[top][bottom]vstack=2,format=bgra[out]')
    return ';\n'.join(graph)


def overlay_before_effect(effect_graph, packed_input_index):
    original = '[0:v]trim=end_frame=300,settb=1/30,setpts=N,format=gbrp[raw]'
    assert effect_graph.count(original) == 1
    prelude = (
        '[0:v]trim=end_frame=300,settb=1/30,setpts=N,format=rgba[base];\n'
        f'[{packed_input_index}:v]trim=end_frame=300,settb=1/30,setpts=N,format=rgba,split=2[pt][pb];\n'
        '[pt]crop=1080:480:0:0[topstick];[pb]crop=1080:480:0:480[bottomstick];\n'
        '[base][topstick]overlay=0:0:format=rgb:alpha=straight:shortest=1[withtop];\n'
        '[withtop][bottomstick]overlay=0:1920:format=rgb:alpha=straight:shortest=1,format=gbrp[raw]'
    )
    return effect_graph.replace(original, prelude)
