"""Prepare all fixed pixels for blends that mathematically depend on footage.

Addition clipping, soft light, colour LUTs and greyscale filters cannot be baked
into a source-independent RGBA video. Their ready pixel feeds and base transfer
are cached, leaving only the original blend/filter arithmetic at final render.
"""
from __future__ import annotations
import copy
import re
import shutil
from pathlib import Path
from server.ffmpeg_templates.renderer import EFFECTS, read, save, sha
from server.ffmpeg_finals.pipeline import Pipeline, namespace
from tools.ffmpeg_overlay_lab.effect_library.library import render_graph, resolve
from .encoding import cache_encode


def prepared_video(renderer, name, inputs, graph, count, alpha=False, gray=False, share_base=True):
    output=renderer.folder/(name+'.mkv');script=renderer.folder/(name+'.ffgraph')
    if alpha:
        graph=graph.replace('[out]','[rgba]')
        graph+=';[rgba]split=2[c][a];[c]format=gbrp[rgb];[a]alphaextract,format=gbrp[mask];[rgb][mask]hstack=inputs=2[out]'
    if name=='base_transfer' and share_base:
        from .shared_graph import share
        inputs,graph,sharing=share(inputs,graph,decoder_threads=None)
        save(renderer.folder/(name+'.sharing.json'),sharing)
    script.write_text(graph,encoding='utf8')
    # The packed edge strip can be only 10-20 px wide, below NVENC's minimum.
    encode=cache_encode('libx264' if name=='borders' else renderer.encoder)
    p=Pipeline(renderer,count);p.total=count
    p.command(name,['-filter_complex_threads','8',*inputs,'-filter_complex_script',script,'-map','[out]',
                    '-frames:v',count,'-an',*encode,'-threads','8',output],count,'准备素材相关特效缓存')
    return output


def prepare_asset(renderer, original, phase, count, index):
    asset=copy.deepcopy(original)
    feeds=list(asset['layers'])
    if (asset.get('background') or {}).get('layer'):feeds.append(asset['background']['layer'])
    for j,layer in enumerate(feeds):
        source=resolve(EFFECTS,layer['file'])
        if sha(source)!=layer['sha256']:raise ValueError('特效缓存变化：'+source.name)
        p=phase%layer['frames'];is_mask=j>=len(asset['layers'])
        prefix=f'[0:v]loop=loop=-1:size={layer["frames"]}:start=0,trim=start_frame={p}:end_frame={p+count},settb=1/30,setpts=N,'
        if is_mask:
            graph=prefix+('format=rgba,extractplanes=r' if layer.get('rgba') else 'format=gray')+',scale=1080:2400:flags=neighbor,format=gray[out]'
        else:graph=prefix+'scale=1080:2400:flags=bilinear,setsar=1,format=rgba[out]'
        path=prepared_video(renderer,f'fx{index}_feed{j}',['-threads','1','-i',source],graph,count,alpha=not is_mask,gray=is_mask)
        layer.update(file=path.name,frames=count,sha256=sha(path))
        layer['packed_alpha']=not is_mask
        if is_mask:layer['rgba']=False
    bg=asset.get('background')
    if bg and bg.get('lut'):
        source=resolve(EFFECTS,bg['lut']);target=renderer.folder/f'fx{index}.cube';shutil.copy2(source,target);bg['lut']=target.name
    return asset


class PreparedCapture(Pipeline):
    def effect(self,seg,start,n,base,prefix,inputs,next_index):
        asset=self.prepared[seg['asset_id']]
        paths,g=render_graph(self.r.folder,asset,1080,2400,n,0,1)
        # Feeds already contain the full requested time interval at output size.
        g=re.sub(r'loop=loop=-1:size=\d+:start=0,trim=start_frame=0:end_frame=\d+',f'trim=end_frame={n}',g)
        g=g.replace('scale=1080:2400:flags=bilinear,setsar=1','setsar=1').replace('scale=1080:2400:flags=neighbor,','')
        amount=seg['relative_strength_percent']/100
        if amount<1:
            g=g.replace('[0:v]trim=','[0:v]split=2[intensitybase][fxinput];[fxinput]trim=',1)
            g=g.replace('format=yuv420p[out]',f'format=yuv420p[fxout];[intensitybase]trim=end_frame={n},settb=1/30,setpts=N,format=yuv420p[ib];[fxout][ib]blend=all_mode=normal:all_opacity={amount}[out]')
        bindings={'0:v':base}
        unpack=[]
        for i,path in enumerate(paths,1):
            feed=next((x for x in asset['layers'] if Path(x['file']).name==Path(path).name),None)
            if feed and feed.get('packed_alpha'):
                label=f'{prefix}unpacked{i}'
                unpack.append(f'[{next_index}:v]format=gbrp,split=2[{label}c][{label}a];'
                              f'[{label}c]crop=1080:2400:0:0:exact=1[{label}rgb];'
                              f'[{label}a]crop=1080:2400:1080:0:exact=1,extractplanes=r[{label}mask];'
                              f'[{label}rgb][{label}mask]alphamerge[{label}]')
                bindings[f'{i}:v']=label
            else:bindings[f'{i}:v']=f'{next_index}:v'
            next_index+=1;inputs+=['-threads','1','-i',path]
        return ';'.join([*unpack,namespace(g,prefix,bindings)]),prefix+'out',next_index

    def filtered(self,name,inputs,graph,frames,stage):
        self.captured=(inputs,graph)
        return Path('unused.mp4')


def compile_special(renderer,template,schedule,piece):
    from .precompose import base_graph, _full_base_graph
    count=piece['end']-piece['start'];inputs=[];graphs=[]
    for colour,prefix in [('black','b_'),('white','w_')]:
        build_base=_full_base_graph if 'cache_trim' in piece else base_graph
        args,g=build_base(template['plan'],template['caches'],piece['start'],count,colour)
        offset=sum(x=='-i' for x in inputs)
        graphs.append(namespace(g,prefix,{f'{i}:v':f'{offset+i}:v' for i in range(args.count('-i'))}));inputs+=args
    graphs+=['[b_base]split=2[k][subtract]','[w_base][subtract]blend=all_mode=subtract[t]','[k][t]hstack=inputs=2[out]']
    base=prepared_video(renderer,'base_transfer',inputs,';'.join(graphs),count,share_base='cache_trim' not in piece)
    assets={a['id']:a for a in read(EFFECTS/'catalog.json')['assets']};prepared={}
    local_piece=copy.deepcopy(piece)
    for i,seg in enumerate(piece['segments']):
        asset=assets[seg['asset_id']]
        if asset['cache_key']!=seg['asset_key']:raise ValueError('特效版本不匹配')
        branch=f'branch{i}'
        prepared[branch]=prepare_asset(renderer,asset,seg['phase_frame']+piece['start']-seg['start_frame'],count,i)
        local_piece['segments'][i]['asset_id']=branch
    cycle=template['plan']['borders']['cycle_frames'];phase=piece['start']%cycle if cycle%3==0 else piece['start']
    borders=prepared_video(renderer,'borders',['-stream_loop','-1','-i',template['caches']['borders']],
                     f'[0:v]fps=30:round=up,trim=start_frame={phase}:end_frame={phase+count},settb=1/30,setpts=N,format=gbrp[out]',count)
    local=copy.deepcopy(template);local['caches']['borders']=str(borders)
    p=PreparedCapture(renderer,schedule['frames']);p.prepared=prepared
    p.chunk(Path('unused-base.mp4'),{'template':local},schedule,local_piece,0)
    args,g=p.captured;args=args[4:]
    g=re.sub(r'fps=30:round=up,trim=start_frame=\d+:end_frame=\d+',f'trim=end_frame={count}',g)
    runtime=renderer.folder/'runtime.ffgraph';runtime.write_text(g,encoding='utf8')
    return {'kind':'source_blend','base':base.name,'runtime':runtime.name,'inputs':list(map(str,args)),
            'render_start':piece['start'],'render_frames':count,'trim':piece.get('cache_trim',[0,count]),
            'files':[base,borders,runtime,*[p for p in renderer.folder.glob('fx*') if p.suffix in ('.mkv','.cube')],*renderer.folder.glob('fade_*.txt')]}
