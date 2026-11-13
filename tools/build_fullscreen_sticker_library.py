"""Extract static sticker frames from local Jianying payloads into a separate pool.

Reads the editor cache only. It never shares an asset ID or file with the
existing upper/lower decoration pool, and records source pixels and frame.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
from PIL import Image, ImageDraw, ImageOps


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def extract(path):
    with Image.open(path) as source:im=source.convert('RGBA')
    frame=None
    for metadata in path.parent.glob('*.json'):
        try:value=json.loads(metadata.read_text(encoding='utf8'))
        except (ValueError,OSError):continue
        frames=value.get('frames')
        if not frames:continue
        if value.get('meta',{}).get('image') not in (None,path.name):continue
        frames=list(frames.values()) if isinstance(frames,dict) else frames
        options=[]
        for i in range(0,len(frames),max(1,len(frames)//15)):
            f=frames[i];r=f.get('frame',{});x,y,w,h=[r.get(k,0) for k in ('x','y','w','h')]
            if min(w,h)<1 or x+w>im.width or y+h>im.height:continue
            tile=im.crop((x,y,x+w,y+h))
            if f.get('rotated'):tile=tile.transpose(Image.Transpose.ROTATE_90)
            box=tile.getchannel('A').getbbox()
            if box:options.append((sum(tile.getchannel('A').getdata()),i,tile.crop(box)))
        if options:
            _,i,im=max(options,key=lambda x:x[0]);frame={'metadata':str(metadata),'index':i};break
    box=im.getchannel('A').getbbox()
    if not box or im.getchannel('A').getextrema()[0]==255:return None
    im=im.crop(box)
    if min(im.size)<24:return None
    im=ImageOps.contain(im,(512,512),Image.Resampling.LANCZOS)
    return im,frame


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,default=96)
    parser.add_argument('--all',action='store_true',help='Extract all readable candidates for visual review')
    parser.add_argument('--exclude-catalog',type=Path,help='Existing independent pool to preserve and exclude')
    parser.add_argument('--selection',type=Path,help='Previously visually reviewed resource IDs')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    project=Path(__file__).resolve().parents[1]
    old=project/'tools/ffmpeg_overlay_lab/sticker_library/v1_20261018'
    inventory=json.loads((old/'inventory.json').read_text(encoding='utf8'))
    cat=json.loads((old/'sources/usable_catalog.json').read_text(encoding='utf8'))
    excluded=set(inventory['resources'])|{r['resource_id'] for s in cat['skins'] for r in s['resources']}
    if args.exclude_catalog:
        excluded|={a['resource_id'] for a in json.loads(args.exclude_catalog.read_text(encoding='utf8'))['assets']}
    cache=Path(os.environ['LOCALAPPDATA'])/'JianyingPro/User Data/Cache/artistEffect'
    candidates=sorted(p for p in cache.iterdir() if p.is_dir() and p.name not in excluded)
    if args.selection:
        allowed=set(json.loads(args.selection.read_text(encoding='utf8'))['resource_ids'])
        candidates=[p for p in candidates if p.name in allowed]
    random.Random(20261025).shuffle(candidates)
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'assets').mkdir()
    assets=[];seen=set()
    for d in candidates:
        for source in sorted(d.rglob('*.png')):
            try:result=extract(source)
            except (ValueError,OSError,Image.DecompressionBombError):continue
            if not result:continue
            im,frame=result;pixels=hashlib.sha256(im.tobytes()).hexdigest()
            if pixels in seen:continue
            seen.add(pixels);file=f'assets/{d.name}.png';im.save(args.output/file)
            assets.append({'resource_id':d.name,'id':sha(args.output/file),'file':file,
                           'name':f'全屏叠层贴纸{len(assets)+1:03d}','size':list(im.size),
                           'source':'local Jianying artistEffect cache','source_file':str(source),
                           'source_sha256':sha(source),'source_frame':frame,'mode':'static_frame'})
            break
        if not args.all and len(assets)>=args.count:break
    if not args.all and len(assets)<args.count:raise RuntimeError(f'独立可用素材不足：{len(assets)}')
    value={'schema':'v3_fullscreen_stickers_v1','created':'2026-10-25','independent_from':'sticker_library/v1_20261018',
           'excluded_resource_ids':sorted(excluded),'assets':assets}
    (args.output/'catalog.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    sheet=Image.new('RGB',(1200,((len(assets)+9)//10)*130),'#454c55');draw=ImageDraw.Draw(sheet)
    for i,a in enumerate(assets):
        with Image.open(args.output/a['file']) as im:
            im=ImageOps.contain(im,(110,103));x=i%10*120;y=i//10*130
            sheet.paste(im,(x,y),im);draw.text((x,y+105),str(i+1)+' '+a['resource_id'][-5:],fill='white')
    sheet.save(args.output/'contact_sheet.jpg')
    print(f'PASS {len(assets)} distinct sticker identities, original pool excluded: {len(excluded)}',flush=True)


if __name__=='__main__':main()
