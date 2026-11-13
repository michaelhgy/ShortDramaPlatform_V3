"""Portable effect-library reader, renderer, and deterministic schedule planner.

Runtime uses only Python's standard library and caller-supplied FFmpeg paths.
All cache paths resolve inside a versioned library; provenance paths are never
used for playback. Plans do not update business usage or delete resources.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import subprocess
import time
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def resolve(root, relative):
    root=Path(root).resolve()
    p=(root/relative).resolve()
    if not p.is_relative_to(root):
        raise ValueError('Library path escapes the version directory: '+relative)
    if not p.is_file():
        raise FileNotFoundError(p)
    return p


def encode_args():
    return ['-c:v','h264_nvenc','-preset','p4','-rc','vbr','-cq','19','-b:v','0','-pix_fmt','yuv420p',
            '-fps_mode','cfr','-color_range','tv','-colorspace','bt709','-color_primaries','bt709',
            '-color_trc','bt709','-c:a','copy','-movflags','+faststart']


def render_graph(root, asset, width, height, frames, phase=0, multiplier=1):
    inputs=[]
    g=[f'[0:v]trim=end_frame={frames},settb=1/30,setpts=N,format=gbrp[raw]']
    background=asset.get('background')
    if background and background['kind']=='snow_color':
        mask=background['layer']
        inputs.append(resolve(root,mask['file']))
        p=phase%mask['frames']
        g += ['[raw]split=2[original][grayin]',
              '[grayin]colorchannelmixer=rr=.299:rg=.587:rb=.114:gr=.299:gg=.587:gb=.114:br=.299:bg=.587:bb=.114,'
              "lutrgb=r='if(lt(val,127.5),val*1.08078444,137.800016+((val-127.5)*.91921556))':g='if(lt(val,127.5),val*1.08078444,137.800016+((val-127.5)*.91921556))':b='if(lt(val,127.5),val*1.08078444,137.800016+((val-127.5)*.91921556))'[gray]",
              f'[1:v]loop=loop=-1:size={mask["frames"]}:start=0,trim=start_frame={p}:end_frame={p+frames},settb=1/30,setpts=N,'+
              ('format=rgba,extractplanes=r' if mask.get('rgba') else 'format=gray')+
              f',lut=y=val*{multiplier:.8f},format=gray,scale={width}:{height}:flags=neighbor,format=gbrp[amount]',
              '[original][gray][amount]maskedmerge=planes=7[b0]']
    elif background and background['kind']=='bubble_filter':
        lut=resolve(root,background['lut']).as_posix().replace(':','\\:')
        g += [f"[raw]lut3d=file='{lut}':interp=trilinear,noise=c0s=2:c0f=u:all_seed=1811[filtered]"]
        if multiplier<1:
            # A full-result fade is required for these assets in timelines.
            raise ValueError('Background-filter intensity must be faded as a complete result')
        g += ['[filtered]null[b0]']
    else:
        g += ['[raw]null[b0]']
    for j,layer in enumerate(asset['layers'],1):
        inputs.append(resolve(root,layer['file']))
        input_index=len(inputs);p=phase%layer['frames']
        spatial=f'scale={width}:{height}:flags=bilinear,setsar=1'
        prefix=f'[{input_index}:v]loop=loop=-1:size={layer["frames"]}:start=0,trim=start_frame={p}:end_frame={p+frames},settb=1/30,setpts=N,{spatial}'
        strength=layer['strength']*multiplier
        if layer.get('opaque') and strength==1:
            g += [prefix+f',format=gbrp[col{j}]',f'[b{j-1}][col{j}]blend=all_mode={layer["mode"]}[b{j}]']
        else:
            g += [prefix+f',format=rgba,split=2[c{j}][a{j}]',f'[c{j}]format=gbrp[col{j}]',
                  f'[a{j}]alphaextract,format=gray,lut=y=val*{strength:.8f},format=gray,format=gbrp[alpha{j}]']
            if layer['mode']=='normal':
                g += [f'[b{j-1}][col{j}][alpha{j}]maskedmerge=planes=7[b{j}]']
            else:
                g += [f'[b{j-1}]split=2[x{j}][y{j}]',f'[x{j}][col{j}]blend=all_mode={layer["mode"]}[z{j}]',
                      f'[y{j}][z{j}][alpha{j}]maskedmerge=planes=7[b{j}]']
    g += [f'[b{len(asset["layers"])}]format=yuv420p[out]']
    return inputs,';\n'.join(g)


def render_asset(root, asset, base, output, ffmpeg, seconds=10, width=1080, height=2400, phase=0):
    if width*20!=height*9:
        raise ValueError('This cache profile is 9:20; rebuild for a different aspect ratio')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError(output)
    inputs,graph=render_graph(root,asset,width,height,round(seconds*30),phase)
    script=output.with_suffix('.ffgraph');script.write_text(graph,encoding='utf-8')
    cmd=[str(ffmpeg),'-hide_banner','-nostdin','-n','-benchmark','-filter_complex_threads','4','-threads','2','-i',str(base)]
    for p in inputs:cmd+=['-threads','2','-i',str(p)]
    cmd+=['-filter_complex_script',str(script),'-map','[out]','-map','0:a:0?','-frames:v',str(round(seconds*30)),
          '-t',str(seconds),*encode_args(),str(output)]
    save(output.with_suffix('.command.json'),cmd)
    started=time.perf_counter()
    with output.with_suffix('.log').open('wb') as log:
        p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
    timing={'wall_seconds':round(time.perf_counter()-started,3),'returncode':p.returncode}
    save(output.with_suffix('.timing.json'),timing)
    if p.returncode:raise RuntimeError(output.with_suffix('.log').read_text(encoding='utf-8',errors='replace')[-4000:])
    return timing


def make_plan(catalog, rules, seconds, seed, usage=None):
    """Build a reproducible finite schedule. usage is successful-template seconds."""
    if seconds<=0:raise ValueError('Duration must be positive')
    rng=random.Random(seed);fps=rules['cache_profile']['fps'];total=round(seconds*fps)
    assets={a['id']:a for a in catalog['assets']}
    singles=[a for a in assets.values() if a['kind']=='single' and a['available_for_library_trials']]
    pairs=[a for a in assets.values() if a['kind']=='pair' and a['available_for_library_trials'] and a['flatten_mode'] in ['screen','normal']]
    effects={e['id']:e for e in catalog['effects']}
    usage=dict(usage or {})
    low,high=[round(s*fps) for s in rules['timeline']['segment_seconds']]
    if total<low:
        lengths=[total]
    else:
        kmin=math.ceil(total/high);kmax=total//low
        if seconds>=rules['timeline']['dual_share_min_template_seconds']:
            kmin=max(kmin,4)
        count=rng.randint(kmin,kmax) if kmin<=kmax else 1
        lengths=[];remaining=total
        for i in range(count):
            left=count-i-1
            if not left:x=remaining
            else:
                lo=max(low,remaining-left*high);hi=min(high,remaining-left*low)
                # Frame-exact duration; integer-second choices where possible.
                x=rng.randint(math.ceil(lo/fps),math.floor(hi/fps))*fps if math.ceil(lo/fps)<=math.floor(hi/fps) else rng.randint(lo,hi)
            lengths.append(x);remaining-=x
    target_min,target_max=rules['timeline']['dual_duration_share']
    dual_slots=[]
    if total>=rules['timeline']['dual_share_min_template_seconds']*fps and len(lengths)>=3 and pairs:
        # Randomized subset-sum, disallow adjacent dual stages. This gives an
        # actual time share instead of applying a per-stage Bernoulli guess.
        states={(0,False):[]}
        for i,length in enumerate(lengths):
            new={}
            for (amount,previous),indices in states.items():
                new[(amount,False)]=indices
                if not previous and amount+length<=total*target_max:
                    new[(amount+length,True)]=indices+[i]
            states=new
        choices=[idx for (amount,_),idx in states.items() if total*target_min<=amount<=total*target_max]
        if choices:dual_slots=rng.choice(choices)
    desired=min(len(effects),max(1,min(len(lengths)+(1 if dual_slots else 0),rng.randint(*rules['selection']['effect_count']))))
    selected=[]
    if dual_slots:
        ranked=sorted(pairs,key=lambda a:sum(usage.get(e,0) for e in a['effect_ids'])+rng.random()*60)
        selected.extend(ranked[0]['effect_ids'])
    desired=max(len(selected),desired)
    while len(selected)<desired:
        candidates=[e for e in effects if e not in selected]
        seen={effects[e]['category'] for e in selected}
        fresh=[e for e in candidates if effects[e]['category'] not in seen]
        chosen=min(fresh or candidates,key=lambda e:usage.get(e,0)+rng.random()*60)
        selected.append(chosen)
    eligible_pairs=[a for a in pairs if set(a['effect_ids'])<=set(selected)]
    last_variant={};temporary_usage=dict(usage);segments=[];cursor=0;previous=None
    for index,length in enumerate(lengths):
        if index in dual_slots:
            candidates=[a for a in eligible_pairs if not previous or a['id']!=previous['asset_id']]
            asset=rng.choice(candidates or eligible_pairs)
        else:
            candidates=[e for e in selected if not previous or previous['kind']!='single' or e not in previous['effect_ids']]
            chosen=min(candidates or selected,key=lambda e:temporary_usage.get(e,0)+rng.random()*max(60,seconds*.12))
            variants=[a for a in singles if a['effect_ids']==[chosen] and a['id']!=last_variant.get(chosen)]
            if not variants:variants=[a for a in singles if a['effect_ids']==[chosen]]
            weights=[rules['selection']['baseline_weight'] if a['variant']=='base' else 1 for a in variants]
            asset=rng.choices(variants,weights=weights,k=1)[0];last_variant[chosen]=asset['id']
        opacity=100 if asset.get('background') else rng.randint(*rules['selection']['relative_strength_percent'])
        phase=rng.randrange(asset['layers'][0]['frames'])
        segment={'index':index,'start_frame':cursor,'end_frame':cursor+length,'asset_id':asset['id'],
                 'asset_key':asset['cache_key'],'kind':asset['kind'],'effect_ids':asset['effect_ids'],
                 'phase_frame':phase,'relative_strength_percent':opacity,'flatten_mode':asset['flatten_mode'],
                 'background_dependent':bool(asset.get('background'))}
        segments.append(segment);previous=segment;cursor+=length
        for e in asset['effect_ids']:temporary_usage[e]=temporary_usage.get(e,0)+length/fps
    transitions=[]
    lo,hi=rules['timeline']['transition_seconds']
    for a,b in zip(segments,segments[1:]):
        length=2*rng.randint(round(lo*fps/2),round(hi*fps/2))
        length=min(length,a['end_frame']-a['start_frame'],b['end_frame']-b['start_frame'])//2*2
        compatible=a['flatten_mode']==b['flatten_mode'] and a['flatten_mode'] in ['screen','normal']
        # Even two cached composites can visually contain three/four source
        # effects. Keep the logical effect budget at the transition as well.
        compatible &= len(set(a['effect_ids'])|set(b['effect_ids']))<=rules['timeline']['max_simultaneous_logical_effects']
        method='cached_effect_crossfade' if compatible else 'fade_through_unmodified_base'
        transitions.append({'boundary_frame':b['start_frame'],'duration_frames':length,
            'start_frame':b['start_frame']-length//2,'end_frame':b['start_frame']+length//2,
            'method':method,'source_asset':a['asset_id'],'target_asset':b['asset_id'],
            'fade_scope':'complete_effect_result_including_background',
            'cache_key':fingerprint([a['asset_key'],b['asset_key'],a['phase_frame'],b['phase_frame'],length,
                                     a['relative_strength_percent'],b['relative_strength_percent'],method])})
    fingerprint_data=[(s['asset_id'],round((s['end_frame']-s['start_frame'])/fps/5)) for s in segments]
    plan={'schema_version':1,'library_version':catalog['version'],'catalog_fingerprint':catalog['fingerprint'],
          'rules_fingerprint':fingerprint(rules),'seed':seed,'fps':fps,'total_frames':total,'seconds':total/fps,
          'selected_effects':selected,'segments':segments,'transitions':transitions,
          'dual_duration_share':sum(s['end_frame']-s['start_frame'] for s in segments if s['kind']=='pair')/total,
          'visual_schedule_signature':fingerprint(fingerprint_data),
          'usage_writes_performed':False,'renderer_integration':'plan-only; use transitions as complete-result fades'}
    return plan


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--library',type=Path,required=True)
    sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('plan');p.add_argument('--seconds',type=float,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--usage-json',type=Path)
    p=sub.add_parser('render');p.add_argument('--asset',required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ffmpeg',type=Path,required=True);p.add_argument('--seconds',type=float,default=10)
    args=ap.parse_args();catalog=read(args.library/'catalog.json')
    if args.action=='plan':
        if args.output.exists():raise FileExistsError(args.output)
        usage=read(args.usage_json) if args.usage_json else None
        save(args.output,make_plan(catalog,read(args.library/'rules.json'),args.seconds,args.seed,usage))
    else:
        asset=next(a for a in catalog['assets'] if a['id']==args.asset)
        print(json.dumps(render_asset(args.library,asset,args.base,args.output,args.ffmpeg,args.seconds)))


if __name__=='__main__':main()
