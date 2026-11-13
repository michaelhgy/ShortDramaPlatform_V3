"""Static full-frame overlays, laid out once and baked into the template cycle."""
from __future__ import annotations
import hashlib
import json
import math
import random
from pathlib import Path
from PIL import Image, ImageOps
from server.tool_resolver import application_resource_root

STICKER_ROOT = application_resource_root()/'tools/ffmpeg_overlay_lab/fullscreen_stickers/v1_20261025'
SIZE = (1080, 2400)


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def sticker_catalog():
    value = json.loads((STICKER_ROOT/'catalog.json').read_text(encoding='utf8'))
    if value.get('schema') != 'v3_fullscreen_stickers_v1': raise ValueError('全屏叠层贴纸库版本不支持')
    return value['assets']


def cells(count):
    """Divide the whole canvas, including a partial last row, without holes."""
    columns=max(1,round(math.sqrt(count*SIZE[0]/SIZE[1])))
    rows=math.ceil(count/columns)
    result=[]; cursor=0
    for row in range(rows):
        columns=count//rows+(row<count%rows)
        for col in range(columns):
            result.append([round(col*SIZE[0]/columns), round(row*SIZE[1]/rows),
                           round((col+1)*SIZE[0]/columns), round((row+1)*SIZE[1]/rows)])
            cursor+=1
    return result


def make_plan(config, photos, seed):
    rng=random.Random(f'{seed}:fullscreen-layers-v1'); result={}
    for kind, enabled, key in [('photos','photo_layer_enabled','photo_layer'),
                               ('stickers','overlay_sticker_enabled','overlay_sticker')]:
        if not config.get(enabled, False): continue
        count=rng.randint(*config[key+'_count'])
        pool=photos if kind=='photos' else sticker_catalog()
        if len(pool)<count:
            title='真人图片（扣除已用及排队占用）' if kind=='photos' else '独立全屏叠层贴纸'
            raise ValueError(f'{title}不足：本模板需要{count}个，当前可用{len(pool)}个')
        chosen=rng.sample(pool,count); placements=[]
        for source,cell in zip(chosen,cells(count)):
            placements.append({'source':source,'cell':cell,'angle':rng.randint(-18,18) if kind=='stickers' else 0,
                               'scale':rng.uniform(1.05,1.3), 'center':[rng.uniform(.4,.6),rng.uniform(.4,.6)]})
        result[kind]={'opacity_percent':config[key+'_opacity_percent'],'placements':placements}
    return result


def photo_sources(plan):
    return [p['source'] for p in plan.get('fullscreen_layers',{}).get('photos',{}).get('placements',[])]


def prepare(folder, plan):
    """Keep original sources out of the final renderer, including after quota deletion."""
    layers=plan.get('fullscreen_layers',{})
    if not layers: return None
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    merged=Image.new('RGBA',SIZE)
    for kind in ('photos','stickers'):
        layer=layers.get(kind)
        if not layer: continue
        canvas=Image.new('RGBA',SIZE)
        for p in layer['placements']:
            source=p['source']
            path=Path(source['path']) if kind=='photos' else (STICKER_ROOT/source['file'])
            if path.is_symlink() or not path.is_file() or digest(path)!=source['id']:
                raise ValueError('叠层素材缺失或变化：'+source.get('name',path.name))
            if kind=='stickers' and not path.resolve().is_relative_to(STICKER_ROOT.resolve()):
                raise ValueError('全屏叠层贴纸路径不合法')
            with Image.open(path) as im: im=ImageOps.exif_transpose(im).convert('RGBA')
            x,y,right,bottom=p['cell']; w,h=right-x,bottom-y
            if kind=='photos':
                im=ImageOps.fit(im,(w,h),method=Image.Resampling.LANCZOS,centering=tuple(p['center']))
                canvas.alpha_composite(im,(x,y))
            else:
                box=im.getchannel('A').getbbox()
                if not box: raise ValueError('全屏叠层贴纸为空：'+source['name'])
                im=im.crop(box)
                im=ImageOps.contain(im,(max(1,round(w*p['scale'])),max(1,round(h*p['scale']))),Image.Resampling.LANCZOS)
                im=im.rotate(p['angle'],Image.Resampling.BICUBIC,expand=True)
                px=round(x+w*p['center'][0]-im.width/2);py=round(y+h*p['center'][1]-im.height/2)
                canvas.alpha_composite(im,(px,py))
        # Apply opacity once to the combined layer, not repeatedly at intersections.
        canvas.putalpha(canvas.getchannel('A').point(lambda a:round(a*layer['opacity_percent']/100)))
        canvas.save(folder/(kind+'.png')); merged=Image.alpha_composite(merged,canvas)
    output=folder/'combined.png'; merged.save(output)
    return str(output)
