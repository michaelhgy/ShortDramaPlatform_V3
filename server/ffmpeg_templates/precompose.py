"""Source-independent template pixels, prepared once and reused by final jobs.

Normal and screen compositions are affine in each RGB channel: K + T * source.
Keeping RGB transmission (rather than a scalar alpha) preserves coloured screen
effects. Cache videos contain compressed 4:4:4 K and T side by side.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
import uuid
from fractions import Fraction
from pathlib import Path
from server.ffmpeg_templates.renderer import EFFECTS, read, save, sha, probe
from server.ffmpeg_finals.pipeline import Pipeline, namespace, pieces
from server.ffmpeg_finals.renderer import repeat_effects
from tools.ffmpeg_overlay_lab.sticker_library.library import overlay_graph
from .encoding import cache_encode


VERSION = 'rgb-transfer-hwdecode-v3'
LEGACY_VERSIONS = ('rgb-transfer-h264-8m-v2',)
_locks = {}; _locks_guard = threading.Lock()
_verified = {}; _verified_guard = threading.Lock()


def verified_file(path, digest):
    """Hash immutable files once per process; recheck after any stat change."""
    st=path.stat();stamp=(st.st_size,st.st_mtime_ns,st.st_ctime_ns,digest)
    key=str(path.resolve())
    with _verified_guard:
        if _verified.get(key)==stamp:return True
    if sha(path)!=digest:return False
    after=path.stat()
    if (after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=stamp[:3]:return False
    with _verified_guard:_verified[key]=stamp
    return True


def fingerprint_file(path):
    before=path.stat();digest=sha(path);after=path.stat()
    a=(before.st_size,before.st_mtime_ns,before.st_ctime_ns)
    b=(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
    if a!=b:raise RuntimeError('缓存校验期间文件发生变化')
    with _verified_guard:_verified[str(path.resolve())]=(*b,digest)
    return digest


def load_completed_cycle(template, root=None, progress=None):
    """Read one finished template period. Never render, extend, or write caches.

    Older expanded manifests remain usable: only their original first period
    is selected. Missing/incomplete templates fail explicitly in the final job.
    """
    started=time.monotonic();cycle=template['plan']['frames']
    base=Path(root) if root is not None else Path(template['package_path'])/'precomposed'
    # Old templates remain immutable and usable. Never transcode them while
    # composing a final, or replace an invalid new manifest with an older one.
    for version in (VERSION, *LEGACY_VERSIONS):
        key=cache_key(template,version)
        directory=base/key;manifest=directory/'manifest.json'
        if manifest.is_file():break
    if not manifest.is_file():raise ValueError('模板缺少已完成的效果缓存，请在模板制作中重新生成；成片不会临时制作模板')
    value=read(manifest)
    if value.get('version')!=version or value.get('key')!=key:raise ValueError('模板预合成缓存版本不匹配')
    selected=[];cursor=0
    for item in value['parts']:
        if cursor>=cycle:break
        if item['start']!=cursor or not cursor<item['end']<=cycle:
            raise ValueError('模板原始周期缓存不完整，请重新制作模板')
        selected.append(copy.deepcopy(item));cursor=item['end']
    if cursor!=cycle:raise ValueError('模板原始周期缓存不完整，请重新制作模板')
    for number,item in enumerate(selected,1):
        if progress:progress(0,f'检查已完成模板 · {number}/{len(selected)}段')
        for file,digest in item['identities'].items():
            path=(directory/file).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file() or not verified_file(path,digest):
                raise ValueError('模板预合成缓存损坏，已保留现场：'+file)
    return {**value,'root':str(directory),'frames':cycle,'loop_frames':cycle,
            'parts':selected,'tails':{},'reused':True,'preparation_seconds':0,
            'verification_seconds':round(time.monotonic()-started,3)}


def cache_key(template, version=VERSION):
    value = {'version': version, 'plan': template['plan'], 'caches': template['caches']}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def transfer_apply(source, cache, prefix, out):
    return (f'[{cache}]settb=1/30,setpts=N,format=gbrp,split=2[{prefix}k][{prefix}t];'
            f'[{prefix}k]crop=1080:2400:0:0:exact=1[{prefix}K];'
            f'[{prefix}t]crop=1080:2400:1080:0:exact=1[{prefix}T];'
            f'[{source}][{prefix}T]blend=all_mode=multiply[{prefix}m];'
            f'[{prefix}m][{prefix}K]blend=all_mode=addition[{out}]')


def main_graph(frames, output='main', source_fps=None):
    try: low_rate = 0 < Fraction(str(source_fps)) < 30
    except (ValueError, ZeroDivisionError): low_rate = False
    # Resize/convert each real picture once before fps duplicates it. Keep the
    # old order for high/unknown rates so dropped pictures are not processed.
    spatial='scale=1080:2400:force_original_aspect_ratio=increase,crop=1080:2400,setsar=1'
    filters=spatial+',format=gbrp,fps=30' if low_rate else 'fps=30,'+spatial
    return (f'[0:v]{filters},tpad=stop_mode=clone:stop_duration=1,'
            f'trim=end_frame={frames},settb=1/30,setpts=N,format=gbrp[{output}]')


def affine_asset(asset):
    return not asset.get('background') and all(x['mode'] in ('normal', 'screen') for x in asset['layers'])


class Capture(Pipeline):
    def filtered(self, name, inputs, graph, frames, stage):
        self.captured = (inputs, graph)
        return Path('unused-base.mp4')


def _full_base_without_overlay(plan, caches, start, count, colour):
    """Use each saved layer's own clock; never reset it at a template boundary."""
    args = []
    g = [f'color=c={colour}:s=1080x2400:r=30,trim=end_frame={count},settb=1/30,setpts=N,format=rgba[main]']
    for i, layer in enumerate(caches['scenery']):
        phase = start % plan['frames']
        if phase+count<=plan['frames']:
            args += ['-ss',str(phase/30),'-i',layer['video']]
            phase=0
        else:
            args += ['-stream_loop', '-1', '-i', layer['video']]
        g.append(f'[{i}:v]trim=start_frame={phase}:end_frame={phase+count},settb=1/30,setpts=N[v{i}]')
    for layer in caches['scenery']:
        args += ['-loop', '1', '-framerate', '30', '-i', layer['mask']]
    args += ['-stream_loop', '-1', '-i', caches['stickers']]
    bottom = plan['tracks'][1]['height']
    g += ['[v0][2:v]alphamerge[t]', '[v1][3:v]alphamerge[b]',
          '[main][t]overlay=0:0:format=rgb[x]',
          f'[x][b]overlay=0:{2400-bottom}:format=rgb[scenery]']
    phase = (plan['stickers']['start_frame'] + start) % 900
    sg = overlay_graph(count, phase=phase, final_format='gbrp')
    factor = plan['config']['sticker_alpha_percent'] / 80
    sg = sg.replace('format=rgba,split=2[pt][pb]', f'format=rgba,colorchannelmixer=aa={factor},split=2[pt][pb]')
    g.append(namespace(sg, 'st_', {'0:v': 'scenery', '1:v': '4:v', 'out': 'base'}))
    return args, ';'.join(g)


def sticker_stream(path, phase, count, index=4):
    """Seek a finite suffix, then loop the whole period from its first frame.

    Combining input -ss with -stream_loop can repeat the last FFV1 GOP near
    EOF. Separate inputs avoid that. Seek on exact 100ms boundaries so MKV's
    millisecond rounding cannot discard a frame at x/30 seconds.
    """
    if phase==0:
        return ['-stream_loop','-1','-i',path],f'[{index}:v]trim=end_frame={count},settb=1/30,setpts=N[packedstick]'
    anchor=phase//3*3;offset=phase-anchor;tail=min(count,900-phase)
    args=['-ss',str(anchor/30),'-i',path]
    g=f'[{index}:v]trim=start_frame={offset}:end_frame={offset+tail},settb=1/30,setpts=N'
    if tail==count:return args,g+'[packedstick]'
    args+=['-stream_loop','-1','-i',path]
    g+=f'[tailstick];[{index+1}:v]trim=end_frame={count-tail},settb=1/30,setpts=N[loopstick];[tailstick][loopstick]concat=n=2:v=1:a=0,settb=1/30,setpts=N[packedstick]'
    return args,g


def _regional_base_without_overlay(plan, caches, start, count, colour):
    """Keep the original blend order, computing only the two occupied regions."""
    top,bottom=[t['height'] for t in plan['tracks']]
    a,b=max(top,480),max(bottom,480)
    if a+b>=2400:
        return _full_base_without_overlay(plan,caches,start,count,colour)
    args,_=_full_base_without_overlay(plan,caches,start,count,colour)
    phase=start%plan['frames'] if start%plan['frames']+count>plan['frames'] else 0
    clock=f'trim=end_frame={count},settb=1/30,setpts=N'
    g=[f'color=c={colour}:s=1080x{h}:r=30,{clock},format=rgba[{label}]'
       for h,label in [(a,'topbg'),(b,'bottombg'),(2400-a-b,'middle')]]
    g += [f'[{i}:v]trim=start_frame={phase}:end_frame={phase+count},settb=1/30,setpts=N[v{i}]' for i in range(2)]
    g += ['[v0][2:v]alphamerge[t]','[v1][3:v]alphamerge[b]',
          '[topbg][t]overlay=0:0:format=rgb[topscene]',
          f'[bottombg][b]overlay=0:{b-bottom}:format=rgb[bottomscene]']
    sticker_phase=(plan['stickers']['start_frame']+start)%900
    sticker_args,sticker_graph=sticker_stream(caches['stickers'],sticker_phase,count)
    args=args[:-4]+sticker_args
    factor=plan['config']['sticker_alpha_percent']/80
    g += [sticker_graph,f'[packedstick]format=rgba,colorchannelmixer=aa={factor},split=2[pt][pb]',
          '[pt]crop=1080:480:0:0[topstick]','[pb]crop=1080:480:0:480[bottomstick]',
          '[topscene][topstick]overlay=0:0:format=rgb:alpha=straight:shortest=1,format=gbrp[topready]',
          f'[bottomscene][bottomstick]overlay=0:{b-480}:format=rgb:alpha=straight:shortest=1,format=gbrp[bottomready]',
          '[middle]format=gbrp[gap]',
          '[topready][gap][bottomready]vstack=inputs=3:shortest=1,format=gbrp[base]']
    return args,';'.join(g)


def _with_fullscreen_overlay(args,graph,plan,caches,count):
    overlay=caches.get('fullscreen_overlay')
    if not overlay:
        if plan.get('fullscreen_layers'):raise ValueError('全屏叠层缓存缺失，请重新制作模板')
        return args,graph
    index=args.count('-i')
    args=[*args,'-loop','1','-framerate','30','-threads','1','-i',overlay]
    graph=graph.replace('[base]','[underlay]')
    graph+=(f';[{index}:v]trim=end_frame={count},settb=1/30,setpts=N,format=rgba[full_overlay];'
            '[underlay][full_overlay]overlay=0:0:format=rgb:alpha=straight:shortest=1,format=gbrp[base]')
    return args,graph


def _full_base_graph(plan,caches,start,count,colour):
    return _with_fullscreen_overlay(*_full_base_without_overlay(plan,caches,start,count,colour),plan,caches,count)


def base_graph(plan,caches,start,count,colour):
    return _with_fullscreen_overlay(*_regional_base_without_overlay(plan,caches,start,count,colour),plan,caches,count)


def transfer_graph(renderer, template, schedule, piece):
    count = piece['end'] - piece['start']
    p = Capture(renderer, schedule['frames'])
    p.chunk(Path('unused-base.mp4'), {'template': template}, schedule, piece, 0)
    effect_inputs, effect_graph = p.captured
    # The first input is the old base render; substitute the in-memory base.
    effect_inputs = effect_inputs[4:]
    effect_graph = effect_graph.replace('format=yuv420p', 'format=gbrp')
    inputs = []; graphs = []
    for colour, prefix in [('black', 'black_'), ('white', 'white_')]:
        offset = sum(1 for x in inputs if x == '-i')
        # A sliced transition uses mutable sendcmd blend parameters. Preserve
        # its original frame-request order, including the final half-seam.
        build_base = _full_base_graph if 'cache_trim' in piece else base_graph
        base_inputs, graph = build_base(template['plan'], template['caches'], piece['start'], count, colour)
        base_count=base_inputs.count('-i')
        graphs.append(namespace(graph, prefix, {f'{i}:v': f'{offset+i}:v' for i in range(base_count)}))
        inputs += base_inputs
        bindings = {'0:v': prefix+'base', 'out': prefix+'out'}
        extra_count = sum(1 for x in effect_inputs if x == '-i')
        bindings.update({f'{i+1}:v': f'{offset+base_count+i}:v' for i in range(extra_count)})
        branch_graph=effect_graph
        if 'transition' in piece:
            old=renderer.folder/'fade_000.txt';new=renderer.folder/(prefix+'fade.txt')
            commands=old.read_text(encoding='utf8')
            for target in ('fadea','fadeb','choose','fade'):
                # Word boundaries avoid renaming fadea a second time as fade.
                import re
                commands=re.sub(r'blend@'+target+r'\b','blend@'+prefix+target,commands)
                branch_graph=re.sub(r'blend@'+target+r'\b','blend@'+prefix+target,branch_graph)
            new.write_text(commands,encoding='utf8')
            branch_graph=branch_graph.replace(old.resolve().as_posix().replace(':','\\:'),new.resolve().as_posix().replace(':','\\:'))
        graphs.append(namespace(branch_graph, prefix+'fx_', bindings))
        inputs += effect_inputs
    graphs += ['[black_out]split=2[k][subtract]',
               '[white_out][subtract]blend=all_mode=subtract[transmission]',
               '[k][transmission]hstack=inputs=2,format=gbrp[out]']
    return inputs, ';'.join(graphs)


def schedule_range(plan, start, end):
    # Look beyond the cached end so a template seam is rendered as a seam,
    # not mistaken for the end of a finished video.
    cycle = plan['frames']
    schedule = repeat_effects(plan, ((end // cycle) + 2) * cycle)
    result = []
    for item in pieces(schedule):
        a, b = max(start, item['start']), min(end, item['end'])
        if b <= a:
            continue
        if 'transition' in item and (a != item['start'] or b != item['end']):
            # Keep original N/duration for sliced transition frames.
            item = copy.deepcopy(item)
            item['cache_trim'] = [a-item['start'], b-item['start']]
        else:
            item = copy.deepcopy(item); item.update(start=a, end=b)
        result.append(item)
    return schedule, result


def compile_piece(renderer, template, schedule, piece, name):
    assets = {a['id']: a for a in read(EFFECTS/'catalog.json')['assets']}
    if any(s['relative_strength_percent'] and not affine_asset(assets[s['asset_id']]) for s in piece['segments']):
        raise ValueError('This piece requires source-dependent blend compilation')
    inputs, graph = transfer_graph(renderer, template, schedule, piece)
    count = piece['end'] - piece['start']
    if 'cache_trim' in piece:
        a,b = piece['cache_trim'];graph=graph.replace('[out]', '[uncut]')
        graph += f';[uncut]trim=start_frame={a}:end_frame={b},settb=1/30,setpts=N[out]';count=b-a
    from .shared_graph import share
    if 'cache_trim' in piece:
        sharing={'shared':False,'reason':'preserve sliced transition command order'}
    else:
        inputs,graph,sharing=share(inputs,graph,decoder_threads=None)
    save(renderer.folder/(name+'.sharing.json'),sharing)
    script = renderer.folder/(name+'.ffgraph');script.write_text(graph, encoding='utf-8')
    output = renderer.folder/(name+'.mkv')
    p = Pipeline(renderer, count);p.total=count
    args = ['-filter_complex_threads','8', *inputs, '-filter_complex_script',script,'-map','[out]',
            '-frames:v',count,'-an',*cache_encode(renderer.cache_encoder),
            '-threads','8','-fps_mode','cfr',output]
    p.command(name,args,count,'预合成模板效果')
    return output


def compile_record(child,template,schedule,item,root):
    actual_start=item['start']+item.get('cache_trim',[0,0])[0]
    actual_end=item['start']+item['cache_trim'][1] if 'cache_trim' in item else item['end']
    count=actual_end-actual_start;folder=child.folder
    assets={a['id']:a for a in read(EFFECTS/'catalog.json')['assets']}
    if all(not s['relative_strength_percent'] or affine_asset(assets[s['asset_id']]) for s in item['segments']):
        output=compile_piece(child,template,schedule,item,'transfer')
        media=probe(output);v=next(s for s in media['streams'] if s['codec_type']=='video')
        if (v['width'],v['height'])!=(2160,2400):raise RuntimeError('预合成缓存尺寸错误')
        record={'kind':'affine','file':str(output.relative_to(root)),
                'codec':v.get('codec_name','h264')};files=[output]
    else:
        from .precompose_special import compile_special
        record=compile_special(child,template,schedule,item);files=record.pop('files')
        record['directory']=str(folder.relative_to(root))
    for i,path in enumerate(files):
        if path.suffix!='.mkv':continue
        n=record.get('render_frames',count);verifier=Pipeline(child,n,load_assets=False);verifier.total=n
        verifier.command(f'verify{i}',['-v','error','-i',path,'-f','null','-'],n,'校验模板缓存')
        if (folder/f'verify{i}.log').read_text(encoding='utf8',errors='replace').strip():raise RuntimeError('模板预合成缓存解码失败')
        if verifier.processed_frames!=n:raise RuntimeError('模板预合成缓存帧数不匹配')
    record.update(start=actual_start,end=actual_end,identities={str(p.relative_to(root)):fingerprint_file(p) for p in files},bytes=sum(p.stat().st_size for p in files))
    return record


def ensure_cache(renderer, template, frames, root=None, prepare_endings=False):
    """Append immutable, source-independent frames, never rebuild an existing span.

    Different layer periods deliberately remain independent. A longer batch can
    extend this template's shared cache once, before any picture composition.
    Completed spans survive interruptions; manifest replacement is atomic.
    """
    if not 1 <= frames <= 120*60*30:
        raise ValueError('模板预合成时长无效')
    key=cache_key(template)
    root=Path(root) if root is not None else Path(template['package_path'])/'precomposed'
    root=root/key;root.mkdir(parents=True,exist_ok=True)
    with _locks_guard:lock=_locks.setdefault(str(root.resolve()),threading.Lock())
    started=time.monotonic()
    with lock:
        manifest=root/'manifest.json'
        value=read(manifest) if manifest.exists() else {'version':VERSION,'key':key,'frames':0,'parts':[],'timings':[]}
        if value['version']!=VERSION or value['key']!=key:raise ValueError('模板预合成缓存版本不匹配')
        cursor=0
        for number,item in enumerate(value['parts'],1):
            renderer.progress(0,f'校验已完成模板缓存 · {number}/{len(value["parts"])}段')
            if item['start']!=cursor or item['end']<=cursor:raise ValueError('模板缓存时间轴损坏')
            cursor=item['end']
            for file,digest in item['identities'].items():
                path=(root/file).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file() or not verified_file(path,digest):
                    raise ValueError('模板预合成缓存损坏，已保留现场：'+file)
        if cursor!=value['frames']:raise ValueError('模板缓存覆盖帧数不匹配')
        for tail in value.get('tails',{}).values():
            for branch in tail['branches']:
                for file,digest in branch['identities'].items():
                    path=(root/file).resolve()
                    if not path.is_relative_to(root.resolve()) or not path.is_file() or not verified_file(path,digest):
                        raise ValueError('模板结尾缓存损坏：'+file)
        before=value['frames'];cycle=template['plan']['frames']
        target=before if frames<=before else min(120*60*30,((frames+cycle-1)//cycle)*cycle)
        changed=target>before
        tail_schedule,tail_items=schedule_range(template['plan'],0,target)
        # Completed-period playback truncates existing pictures, so new
        # templates do not need per-final ending variants. Legacy diagnostic
        # callers can explicitly request those variants.
        transitions=[p for p in tail_items if 'transition' in p] if prepare_endings else []
        pending=[p for p in transitions if str(p['transition']['boundary_frame']) not in value.get('tails',{})]
        tail_frames=sum((p['end']-p['start'])*(2 if p['transition']['method']=='cached_effect_crossfade' else 3) for p in pending)
        total_work=max(1,target-before+tail_frames)
        # Prepare whole template periods so a slightly longer next video is a hit.
        if target>before:
            for path,digest in template.get('identities',{}).items():
                if sha(path)!=digest:raise ValueError('模板输入缓存变化，停止预合成：'+Path(path).name)
            schedule,items=schedule_range(template['plan'],before,target)
            from server.ffmpeg_templates.renderer import Renderer
            for index,item in enumerate(items):
                actual_start=item['start']+item.get('cache_trim',[0,0])[0]
                actual_end=item['start']+item['cache_trim'][1] if 'cache_trim' in item else item['end']
                folder=root/f'{actual_start:08d}_{actual_end:08d}_{uuid.uuid4().hex[:8]}'
                emitted=[0]
                def progress(p,s):
                    done=actual_start-before+(actual_end-actual_start)*p/100
                    emitted[0]=max(emitted[0],int(done))
                    renderer.progress(min(99,int(emitted[0]*99/total_work)),f'模板一次性预合成 · {emitted[0]}/{total_work}帧；{s}')
                child=Renderer(folder,progress)
                t=time.monotonic()
                record=compile_record(child,template,schedule,item,root)
                value['parts'].append(record);value['frames']=actual_end
                value['timings'].append({'start':actual_start,'end':actual_end,'seconds':round(time.monotonic()-t,3)})
                pending=root/('manifest.'+uuid.uuid4().hex+'.json');save(pending,value);pending.replace(manifest)
        # Finite videos must not start fading to an effect beyond their end.
        # Cache unmixed branch pictures around every boundary as well; finals
        # only choose/blend those completed pictures for their actual last frame.
        tail_done=target-before
        for i,item in enumerate(transitions):
            boundary=str(item['transition']['boundary_frame'])
            if boundary in value.get('tails',{}):continue
            changed=True;t=time.monotonic()
            from server.ffmpeg_templates.renderer import Renderer
            branches=[];variants=copy.deepcopy(item['segments'])
            if item['transition']['method']!='cached_effect_crossfade':
                plain=copy.deepcopy(variants[0]);plain['relative_strength_percent']=0;variants.append(plain)
            for j,seg in enumerate(variants):
                folder=root/f'tail_{boundary}_{j}_{uuid.uuid4().hex[:8]}'
                count=item['end']-item['start']
                child=Renderer(folder,lambda p,s:renderer.progress(min(99,int(99*(tail_done+count*p/100)/total_work)),f'预合成结尾备用画面 {i+1}/{len(transitions)}；{s}'))
                branch={'start':item['start'],'end':item['end'],'segments':[seg]}
                branches.append(compile_record(child,template,tail_schedule,branch,root))
                tail_done+=count
            value.setdefault('tails',{})[boundary]={'transition':item['transition'],'branches':branches}
            value['timings'].append({'stage':'tail_variants','boundary':int(boundary),'seconds':round(time.monotonic()-t,3)})
            pending=root/('manifest.'+uuid.uuid4().hex+'.json');save(pending,value);pending.replace(manifest)
        value['root']=str(root);value['reused']=not changed
        value['preparation_seconds']=round(time.monotonic()-started,3)
        return value
