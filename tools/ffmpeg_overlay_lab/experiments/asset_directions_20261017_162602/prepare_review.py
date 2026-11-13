"""Archive generated originals and assemble review sheets; no source image edits."""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FONT = '/mnt/c/Windows/Fonts/msyh.ttc'


def run(args: list[str]) -> bytes:
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))
    return result.stdout


def save_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def inspect_asset(path: Path, transparent: bool) -> dict:
    stream = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)]))['streams'][0]
    width, height = stream['width'], stream['height']
    info = {'width': width, 'height': height, 'pixel_format': stream['pix_fmt'],
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if not transparent:
        info['bbox'] = [0, 0, width, height]
        return info
    alpha = run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-frames:v', '1',
                 '-vf', 'alphaextract', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'])
    assert len(alpha) == width * height
    assert min(alpha) == 0 and max(alpha) > 0, f'Missing useful transparency: {path}'
    left, top, right, bottom = width, height, -1, -1
    for index, value in enumerate(alpha):
        if value > 8:
            y, x = divmod(index, width)
            left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
    assert right >= left
    padding = 16
    left, top = max(0, left - padding), max(0, top - padding)
    right, bottom = min(width - 1, right + padding), min(height - 1, bottom + padding)
    info.update({'alpha_min': min(alpha), 'alpha_max': max(alpha),
                 'fully_transparent_fraction': round(alpha.count(0) / len(alpha), 6),
                 'bbox': [left, top, right - left + 1, bottom - top + 1]})
    return info


def make_card(asset: dict, info: dict) -> Path:
    previews = ROOT / 'previews'
    previews.mkdir(exist_ok=True)
    kind = asset['category']
    height = {'sticker': 300, 'texture': 650, 'particle': 420}[kind]
    art_width = 440 if kind != 'particle' else 230
    art_height = {'sticker': 190, 'texture': 545, 'particle': 260}[kind]
    label = previews / (asset['id'] + '_label.txt')
    label.write_text(asset['id'] + '  ' + asset['name'], encoding='utf-8')
    note = previews / (asset['id'] + '_note.txt')
    note.write_text({'sticker': '浅色细线 · 底色仅用于预览',
                     'texture': '纹理原图 · 后续可裁成细条',
                     'particle': '外形放大预览 · 实际使用时缩小'}[kind], encoding='utf-8')
    x, y, width, crop_height = info['bbox']
    graph = (
        f'[0:v]crop={width}:{crop_height}:{x}:{y},'
        f'scale={art_width}:{art_height}:force_original_aspect_ratio=decrease:flags=lanczos,'
        'format=rgba[art];'
        f'color=c=0x263244:s=480x{height}:r=1:d=1,format=rgba[bg];'
        f'[bg][art]overlay=x=(W-w)/2:y=64+({art_height}-h)/2:format=rgb:shortest=1,'
        f'drawtext=fontfile={FONT}:textfile={label}:fontsize=26:fontcolor=0xf5f2ed:x=20:y=16,'
        f'drawtext=fontfile={FONT}:textfile={note}:fontsize=17:fontcolor=0xbac5d4:x=20:y={height-31}'
        '[out]'
    )
    (previews / (asset['id'] + '.ffgraph')).write_text(graph, encoding='utf-8')
    destination = previews / (asset['id'] + '.png')
    run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-filter_complex_threads', '1',
         '-i', str(ROOT / 'assets' / asset['file']), '-filter_complex_script',
         str(previews / (asset['id'] + '.ffgraph')), '-map', '[out]',
         '-frames:v', '1', '-threads', '1', '-update', '1', str(destination)])
    return destination


def write_gallery(assets: list[dict]) -> None:
    cards = []
    for asset in assets:
        relative = 'assets/' + asset['file']
        cards.append(
            '<article><h2>' + html.escape(asset['id'] + ' ' + asset['name']) + '</h2>'
            '<a class="art ' + asset['category'] + '" href="' + relative + '">'
            '<img src="' + relative + '" alt="' + html.escape(asset['name']) + '"></a>'
            '<p><a href="' + relative + '">打开原图</a></p><details><summary>实际生成提示词</summary><pre>'
            + html.escape(asset['prompt']) + '</pre></details></article>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI 素材方向样图</title>
<style>body{font:16px/1.65 "Microsoft YaHei",sans-serif;background:#eef0f3;color:#172130;margin:24px auto;max-width:1500px;padding:0 18px}
h1{font-size:28px}h2{font-size:20px;margin:0 0 12px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
article{background:white;border-radius:12px;padding:18px;min-width:0}.art{height:280px;display:flex;align-items:center;justify-content:center;background:var(--preview,#263244);border-radius:8px}
.art.texture{height:480px}.art img{max-width:94%;max-height:92%;object-fit:contain}.art.particle img{max-width:62%;max-height:70%}
a{color:#2764a4}button{padding:8px 16px;margin:0 8px 14px 0;border:1px solid #b9c3cf;border-radius:6px;cursor:pointer}
pre{white-space:pre-wrap;font:13px/1.55 monospace;overflow-wrap:anywhere}summary{cursor:pointer;color:#35577a}
@media(max-width:850px){.grid{grid-template-columns:1fr}}</style>
<h1>AI 素材方向样图 · 9 组</h1>
<p>A：上下使用的独立浅色线条贴纸；B：左右细条的纹理原图；C：独立小点缀。贴纸和点缀保留真实透明背景。
这里先看题材、画法和形状；原图按自身透明度显示，未设定成片中的最终透明度。</p>
<p>预览底色仅帮助辨认透明素材，不包含在原图内。点击图片可以打开原图。</p>
<button onclick="document.documentElement.style.setProperty('--preview','#263244')">深色底</button>
<button onclick="document.documentElement.style.setProperty('--preview','#dddeda')">浅色底</button>
<p><a href="prompts.json">全部实际提示词</a> · <a href="review_manifest.json">原图来源与检查记录</a></p>
<main class="grid">''' + ''.join(cards) + '</main></html>'
    (ROOT / '先看样图.html').write_text(page, encoding='utf-8')


def main() -> None:
    assets = json.loads((ROOT / 'prompts.json').read_text(encoding='utf-8'))['assets']
    sources = {item['id']: item for item in json.loads((ROOT / 'source_manifest.json').read_text(encoding='utf-8'))}
    destination = ROOT / 'assets'
    destination.mkdir(exist_ok=True)
    results, cards = [], {}
    for asset in assets:
        source = Path(sources[asset['id']]['source'])
        target = destination / asset['file']
        if target.exists():
            raise FileExistsError(f'Refusing to replace {target}')
        shutil.copy2(source, target)
        info = inspect_asset(target, asset['transparent'])
        results.append({**asset, 'source': str(source), 'saved_path': str(target), 'checks': info})
        save_json(ROOT / 'review_manifest.json', {'tool': 'built-in image_gen',
                  'acceptance': 'USER_PENDING', 'assets': results})
        cards[asset['id']] = make_card(asset, info)
    groups = [('A', 'A_上下线条贴纸_三方向.jpg'), ('B', 'B_左右纹理_三方向.jpg'), ('C', 'C_小点缀_三方向.jpg')]
    for prefix, filename in groups:
        args = ['ffmpeg', '-v', 'error', '-nostdin', '-n', '-filter_complex_threads', '1']
        for index in range(1, 4):
            args.extend(['-i', str(cards[prefix + str(index)])])
        args.extend(['-filter_complex', '[0:v][1:v][2:v]hstack=inputs=3[out]', '-map', '[out]',
                     '-frames:v', '1', '-threads', '1', '-q:v', '2', '-update', '1', str(ROOT / filename)])
        run(args)
    write_gallery(assets)
    print(json.dumps({'saved': len(results), 'root': str(ROOT), 'alpha_checks':
                     {item['id']: item['checks'].get('fully_transparent_fraction') for item in results}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
