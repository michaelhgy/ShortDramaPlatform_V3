from __future__ import annotations
import copy
import hashlib
import json
import math
import random
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from server.ffmpeg_diagnostics import phase, current
from server.ffmpeg_process import run_progress
from server.tool_resolver import application_resource_root, resolve_ffmpeg, resolve_ffprobe
from .scenery_usage import scheduled_materials

LAB = application_resource_root()/'tools/ffmpeg_overlay_lab'
STICKERS = LAB/'sticker_library/v1_20261018'
EFFECTS = LAB/'effect_library/v1_20261018'
BORDERS = LAB/'side_strip_library/v1_20261019'


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p, obj):
    p=Path(p);p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def probe(p):
    return json.loads(subprocess.check_output([str(resolve_ffprobe()), '-v','error','-show_streams','-show_format','-of','json',str(p)], **hidden()))
def hidden():
    import os
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
def draw(rng,total,span,step=1):
    lo=math.ceil(total*span[0]/100/step)*step;hi=math.floor(total*span[1]/100/step)*step
    if lo>hi:return max(0,min(total,round(total*(span[0]+span[1])/200/step)*step))
    return rng.randrange(lo,hi+1,step)


def make_plan(config, materials, seed, photos=None):
    from tools.ffmpeg_overlay_lab.sticker_library.template_cache import make_batch
    from tools.ffmpeg_overlay_lab.effect_library.library import make_plan as effect_plan
    from tools.ffmpeg_overlay_lab.side_strip_library.library import make_plan as border_plan
    rng=random.Random(seed)
    seconds=rng.randint(config['duration_seconds']-config['duration_jitter'],config['duration_seconds']+config['duration_jitter'])
    n=rng.randint(config['scenery_count']-config['scenery_count_jitter'],config['scenery_count']+config['scenery_count_jitter'])
    if len(materials)<n: raise ValueError(f'可用风景不足：本次需要{n}条，当前剩余{len(materials)}条（含排队占用和使用上限）')
    # Search bounded random partitions with unequal initial duration; never relax the rule silently.
    groups=None
    for _ in range(400):
        chosen=rng.sample(materials,n);cut=rng.randint(2,n-2);a,b=chosen[:cut],chosen[cut:]
        da=sum(m['frames'] for m in a);db=sum(m['frames'] for m in b)
        gap=abs(da-db)/max(da,db)*100
        if config['scenery_group_gap_percent'][0]<=gap<=config['scenery_group_gap_percent'][1]:
            groups=[a,b];break
    if groups is None: raise ValueError('现有风景无法满足上下初始时长差，请补充不同时长素材或调整时长差范围')
    if rng.randrange(2): groups.reverse()
    heights=[draw(rng,2400,config['height_large_percent'],2),draw(rng,2400,config['height_small_percent'],2)]
    rng.shuffle(heights);tracks=[]
    for side,group,height in zip(['top','bottom'],groups,heights):
        center=draw(rng,height,config['mask_percent']);feather=draw(rng,height,config['feather_percent'],2)
        sequence=[];cursor=0;previous=None
        while cursor<seconds*30:
            order=group[:];rng.shuffle(order)
            if previous and order[0]['id']==previous:
                order[0],order[1]=order[1],order[0]
            for m in order:
                frames=min(m['frames'],seconds*30-cursor)
                if frames<=0:break
                sequence.append({'id':m['id'],'frames':frames,'start_frame':cursor});cursor+=frames;previous=m['id']
        tracks.append({'side':side,'height':height,'center':center,'feather':feather,'materials':group,'sequence':sequence})
    rules=read(EFFECTS/'rules.json')
    rules['selection']['effect_count']=config['effect_count']
    rules['selection']['relative_strength_percent']=config['effect_strength_percent']
    rules['timeline']['segment_seconds']=config['effect_segment_seconds']
    rules['timeline']['dual_duration_share']=[x/100 for x in config['effect_pair_percent']]
    rules['timeline']['transition_seconds']=config['effect_transition_seconds']
    fx=effect_plan(read(EFFECTS/'catalog.json'),rules,seconds,rng.getrandbits(60))
    border=border_plan(read(BORDERS/'catalog.json'),rng.getrandbits(60),width_range=config['border_width'])
    stickers=make_batch(STICKERS,1,seed=rng.getrandbits(60),seconds=seconds)['plans'][0]
    plan={'schema_version':1,'seed':seed,'seconds':seconds,'frames':seconds*30,'canvas':[1080,2400],'fps':30,
            'config':config,'tracks':tracks,'stickers':stickers,'effects':fx,'borders':border,
            'preview_only_background':'neutral; replace with main footage during future final composition'}
    from .fullscreen_layers import make_plan as layer_plan
    layers=layer_plan(config,photos or [],seed)
    if layers:plan['fullscreen_layers']=layers
    return plan


class Renderer:
    def __init__(self, folder, progress):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.ff=resolve_ffmpeg();self.fp=resolve_ffprobe();self.progress=progress;self.timings=[];self.caches={}
        # Probe actual encoder availability once, with a real frame; CPU fallback is explicit.
        with phase('encoder_probe'):
            test=subprocess.run([str(self.ff),'-v','error','-f','lavfi','-i','color=s=256x256:r=30','-frames:v','1','-c:v','h264_nvenc','-f','null','-'],capture_output=True,**hidden())
        self.encoder='h264_nvenc' if test.returncode==0 else 'libx264'
        if current(): current().update_context(encoder=self.encoder, ffmpeg=str(self.ff), ffprobe=str(self.fp))
        save(self.folder/'encoder_check.json',{'encoder':self.encoder,'returncode':test.returncode,'diagnostic':test.stderr.decode('utf-8','replace')})

    @property
    def hardware(self):
        if not hasattr(self,'_hardware'):
            from server.ffmpeg_hardware import capabilities
            started=time.monotonic()
            self._hardware=(capabilities(self.ff) if self.encoder=='h264_nvenc' else
                            {'hevc_cache':False,'vulkan_transfer':False})
            save(self.folder/'hardware_check.json',self._hardware)
            self.timings.append({'stage':'hardware_check','seconds':round(time.monotonic()-started,3)})
        return self._hardware

    @property
    def cache_encoder(self):
        return 'hevc_nvenc' if self.hardware['hevc_cache'] else self.encoder

    def encode(self):
        return (['-c:v','h264_nvenc','-preset','p4','-cq','19','-b:v','0'] if self.encoder=='h264_nvenc' else ['-c:v','libx264','-preset','veryfast','-crf','19'])+['-pix_fmt','yuv420p','-r','30','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart']

    def run(self, name, inputs, graph, output, frames, extra=None):
        script=self.folder/(name+'.ffgraph');script.write_text(graph,encoding='utf-8')
        args=['-threads','2','-filter_complex_threads','4',*map(str,inputs),'-filter_complex_script',str(script),'-map','[out]','-an','-frames:v',str(frames),*(extra or self.encode()),str(output)]
        self.command(name,args,frames)
        return Path(output)

    def command(self,name,args,frames,on_progress=None):
        cmd=[str(self.ff),'-hide_banner','-nostdin','-n','-progress','pipe:1','-stats_period','0.5','-nostats',*map(str,args)]
        save(self.folder/(name+'.command.json'),cmd);start=time.monotonic()
        with (self.folder/(name+'.log')).open('wb') as log, (self.folder/'progress.jsonl').open('a',encoding='utf-8') as trace:
            def report(frame,ended):
                trace.write(json.dumps({'stage':name,'frame':frame,'frames':frames,'elapsed':round(time.monotonic()-start,3)})+'\n');trace.flush()
                callback=on_progress or getattr(self,'_scenery_progress',None)
                if callback:callback(max(0,min(frame,frames)),frames)
            try:code,frame=run_progress(cmd,log,report,popen_options=hidden())
            except RuntimeError as error:
                log.write(('\n'+str(error)+'\n').encode('utf-8'));log.flush()
                raise RuntimeError(f'{name} 制作失败：{error}') from error
        self.timings.append({'stage':name,'seconds':round(time.monotonic()-start,3),'frames':frames,'processed_frames':frame})
        if code:
            detail=(self.folder/(name+'.log')).read_text(encoding='utf-8',errors='replace')[-1600:]
            raise RuntimeError(f'{name} 制作失败：{detail}')
        return frame

    def check_scenery(self,path,frames,height):
        video=next(s for s in probe(path)['streams'] if s['codec_type']=='video')
        actual=(video['width'],video['height'],video['avg_frame_rate'],int(video.get('nb_frames',0)))
        if actual!=(1080,height,'30/1',frames):
            raise RuntimeError(f'风景时间轴不完整：{Path(path).name}，预期{frames}帧，实际{actual}；已停止，未制作特效缓存')

    def join_scenery(self,name,paths,frames,height):
        # Every entry is a complete, normalized segment, including a separately
        # encoded final partial clip. Copy packets: no filter reinitialization,
        # no resetting N between colour ranges, and no second picture encode.
        listing=self.folder/(name+'.txt')
        listing.write_text(''.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'\n" for p in paths),encoding='utf-8')
        output=self.folder/(name+'.mp4')
        callback=getattr(self,'_scenery_progress',None)
        self.command(name,['-f','concat','-safe','0','-i',listing,'-map','0:v:0','-an','-c:v','copy','-video_track_timescale','30000','-movie_timescale','30000','-movflags','+faststart',output],frames,
                     on_progress=(lambda f,n:callback(f,n*2)) if callback else None)
        self.check_scenery(output,frames,height)
        decoded=self.command(name+'_check',['-v','error','-i',output,'-map','0:v:0','-f','null','-'],frames,
                             on_progress=(lambda f,n:callback(n+f,n*2)) if callback else None)
        if decoded!=frames or (self.folder/(name+'_check.log')).read_text(encoding='utf-8',errors='replace').strip():
            raise RuntimeError(f'风景时间轴完整解码检查失败：{name}，{decoded}/{frames}帧')
        return output

    def join(self,name,paths,frames):
        listing=self.folder/(name+'.txt')
        listing.write_text(''.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'\n" for p in paths),encoding='utf-8')
        return self.run(name,['-f','concat','-safe','0','-i',listing],'[0:v]settb=1/30,setpts=N[out]',self.folder/(name+'.mp4'),frames)

    def scenery(self,plan,preview=True):
        tracks=[];masks=[]
        work=sum(sum(n for _,n in dict.fromkeys((s['id'],s['frames']) for s in t['sequence']))+plan['frames']*2 for t in plan['tracks'])
        completed=0
        for track in plan['tracks']:
            side=track['side'];h=track['height'];ready={}
            if sum(s['frames'] for s in track['sequence'])!=plan['frames']:raise ValueError('风景排布帧数没有完整覆盖模板')
            materials={m['id']:m for m in track['materials']}
            for m in scheduled_materials(track):
                if sha(m['path'])!=m['id']:raise ValueError('风景源文件已变化：'+m['name'])
            for material_id,count in dict.fromkeys((s['id'],s['frames']) for s in track['sequence']):
                m=materials[material_id]
                if not 0<count<=m['frames']:raise ValueError('风景片段长度超出素材')
                suffix='' if count==m['frames'] else f'_trim{count}'
                file=self.folder/(side+'_'+m['id'][:12]+suffix+'.mp4')
                graph=f'[0:v]fps=30,scale=1080:{h}:force_original_aspect_ratio=increase:out_range=tv,crop=1080:{h},setsar=1,format=yuv420p,setparams=range=limited,settb=1/30,setpts=N[out]'
                self._scenery_progress=lambda f,n:self.progress(int(27*(completed+f)/work),f'准备风景片段 · {f}/{n}帧')
                # MP4's default millisecond movie clock rounds durations such
                # as 472/30. Exact frame multiples keep concat timestamps CFR.
                self.run(file.stem,['-i',m['path']],graph,file,count,extra=self.encode()+['-color_range','tv','-video_track_timescale','30000','-movie_timescale','30000'])
                self.check_scenery(file,count,h);completed+=count;ready[(material_id,count)]=file
            self._scenery_progress=lambda f,n:self.progress(int(27*(completed+f)/work),f'拼接并校验风景轨道 · {f}/{n}帧')
            tracks.append(self.join_scenery(side+'_timeline',[ready[(s['id'],s['frames'])] for s in track['sequence']],plan['frames'],h))
            completed+=plan['frames']*2
            pixels=[];start=track['center']-track['feather']//2
            for y in range(h):
                d=y if side=='top' else h-1-y
                if track['feather']:
                    t=max(0,min(1,(d-start)/track['feather']));alpha=round(255*(1-t*t*(3-2*t)))
                else:alpha=255 if d<=track['center'] else 0
                pixels.extend([alpha]*1080)
            mask=self.folder/(side+'_mask.png');im=Image.new('L',(1080,h));im.putdata(pixels);im.save(mask);masks.append(mask)
        self._scenery_progress=None
        self.caches['scenery']=[{'side':t['side'],'video':str(v),'mask':str(m)} for t,v,m in zip(plan['tracks'],tracks,masks)]
        if not preview:return None
        background=self.folder/'preview_background.png';im=Image.new('RGB',(1080,2400),'#28313a');d=ImageDraw.Draw(im)
        font_path=Path('C:/Windows/Fonts/msyh.ttc')
        if font_path.exists():
            font=ImageFont.truetype(str(font_path),36)
            d.text((540,1200),'主素材画面',fill='#788692',font=font,anchor='mm')
        im.save(background)
        h=plan['tracks'][1]['height']
        graph='[0:v]format=rgba[base];[1:v][3:v]alphamerge[t];[2:v][4:v]alphamerge[b];[base][t]overlay=0:0:format=rgb[x];'+f'[x][b]overlay=0:{2400-h}:format=rgb,format=yuv420p[out]'
        args=['-loop','1','-framerate','30','-i',background,'-i',tracks[0],'-i',tracks[1],'-loop','1','-framerate','30','-i',masks[0],'-loop','1','-framerate','30','-i',masks[1]]
        return self.run('scenery',args,graph,self.folder/'scenery.mp4',plan['frames'])

    def stickers(self,plan,base=None):
        from tools.ffmpeg_overlay_lab.sticker_library import template_cache,library
        # Runtime workspace is per-template: inputs point into the V3-only library, caches stay with this job.
        root=self.folder/'sticker_inputs'
        for earlier in sorted(self.folder.parent.glob('a*')):
            candidate=earlier/'sticker_inputs'
            if (candidate/plan['stickers']['manifest']).is_file() and (earlier/'plan.json').is_file() and read(earlier/'plan.json')==plan:
                root=candidate;break
        root.mkdir(exist_ok=True)
        # build_recipe expects normalized paths; hard links on the same drive avoid duplicate material data.
        import os,shutil
        for chosen in plan['stickers']['settings']['selection']:
            for key in ['normalized_poster','native_cache']:
                relative=chosen['source'].get(key)
                if not relative:continue
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():continue
                try:os.link(STICKERS/relative,target)
                except OSError:shutil.copy2(STICKERS/relative,target)
        self.progress(28,'制作本模板的贴纸动画缓存')
        prep=template_cache.prepare(root,plan['stickers'],self.ff)
        self.timings.append({'stage':'sticker_cache','seconds':prep['wall_seconds'],'reused':prep['reused']})
        cache=root/plan['stickers']['cache'];self.caches['stickers']=str(cache)
        if base is None:return None
        graph=library.overlay_graph(plan['frames'],phase=plan['stickers']['start_frame'])
        factor=plan['config']['sticker_alpha_percent']/80
        graph=graph.replace('format=rgba,split=2[pt][pb]',f'format=rgba,colorchannelmixer=aa={factor},split=2[pt][pb]')
        return self.run('stickers',['-i',base,'-stream_loop','-1','-i',cache],graph,self.folder/'stickers.mp4',plan['frames'])

    def effect_clip(self,base,seg,start,end,name):
        from tools.ffmpeg_overlay_lab.effect_library.library import render_graph
        asset=next(a for a in read(EFFECTS/'catalog.json')['assets'] if a['id']==seg['asset_id'])
        if asset['cache_key']!=seg['asset_key']:raise ValueError('特效资源版本已变化')
        phase=seg['phase_frame']+start-seg['start_frame']
        inputs,graph=render_graph(EFFECTS,asset,1080,2400,end-start,phase,1)
        for layer in asset['layers']+([asset['background']['layer']] if (asset.get('background') or {}).get('layer') else []):
            if sha(EFFECTS/layer['file'])!=layer['sha256']:raise ValueError('特效缓存已变化')
        # Full-result intensity preserves background-dependent filters too.
        amount=seg['relative_strength_percent']/100
        if amount<1:
            graph=graph.replace('[0:v]trim=','[0:v]split=2[intensitybase][fxinput];[fxinput]trim=',1)
            graph=graph.replace('format=yuv420p[out]',f'format=yuv420p[fxout];[intensitybase]trim=end_frame={end-start},settb=1/30,setpts=N,format=yuv420p[ib];[fxout][ib]blend=all_mode=normal:all_opacity={amount}[out]')
        args=['-ss',start/30,'-i',base]
        for p in inputs:args+=['-threads','1','-i',p]
        return self.run(name,args,graph,self.folder/(name+'.mp4'),end-start)

    def effects(self,plan,base):
        fx=plan['effects'];segments=fx['segments'];trans=fx['transitions'];parts=[]
        for i,seg in enumerate(segments):
            self.progress(45+int(30*i/len(segments)),f'全屏特效 {i+1}/{len(segments)}')
            start=trans[i-1]['end_frame'] if i else 0
            end=trans[i]['start_frame'] if i<len(trans) else plan['frames']
            if end>start:parts.append(self.effect_clip(base,seg,start,end,f'effect_{i}'))
            if i>=len(trans):continue
            t=trans[i];s,e=t['start_frame'],t['end_frame'];n=e-s
            a=self.effect_clip(base,seg,s,e,f'transition_{i}_a')
            b=self.effect_clip(base,segments[i+1],s,e,f'transition_{i}_b')
            if t['method']=='cached_effect_crossfade':
                graph=f'[0:v][1:v]blend=all_expr=\'A*(1-N/{n})+B*N/{n}\'[out]';args=['-i',a,'-i',b]
            else:
                graph=f'[2:v]trim=end_frame={n},settb=1/30,setpts=N,split=2[x][y];[0:v][x]blend=all_expr=\'A*(1-min(1,N/{n//2}))+B*min(1,N/{n//2})\'[a];[y][1:v]blend=all_expr=\'A*(1-max(0,(N-{n//2})/{n//2}))+B*max(0,(N-{n//2})/{n//2})\'[b];[a][b]blend=all_expr=\'if(lt(N,{n//2}),A,B)\'[out]'
                args=['-i',a,'-i',b,'-ss',s/30,'-i',base]
            parts.append(self.run(f'transition_{i}',args,graph,self.folder/f'transition_{i}.mp4',n))
        return self.join('effects_timeline',parts,plan['frames'])

    def render(self,plan):
        from tools.ffmpeg_overlay_lab.side_strip_library import library as edges
        from .precompose import ensure_cache, load_completed_cycle, VERSION
        from server.ffmpeg_finals.cached import render_cached
        self.progress(0,'准备上下风景及羽化蒙版');self.scenery(plan,preview=False)
        self.stickers(plan)
        from .fullscreen_layers import prepare as prepare_fullscreen
        self.progress(28,'准备全屏贴纸及真人叠层')
        overlay=prepare_fullscreen(self.folder/'fullscreen_layers',plan)
        if overlay:self.caches['fullscreen_overlay']=overlay
        self.progress(30,'准备动态边条')
        edges.FF=self.ff;edges.FP=self.fp
        packed,_=edges.prepare_strips(BORDERS,plan['borders'],self.folder/'borders')
        self.caches['borders']=str(packed)
        template={'plan':plan,'caches':self.caches,'package_path':str(self.folder),'identities':{}}
        callback=self.progress
        self.progress=lambda p,s:callback(30+int(p*.55),s)
        try:cache=ensure_cache(self,template,plan['frames'])
        finally:self.progress=callback
        self.timings.append({'stage':'template_preparation','seconds':cache['preparation_seconds'],'coverage_frames':cache['frames']})
        # Preview and finals now use exactly the same completed period.
        cache=load_completed_cycle(template,progress=lambda p,s:callback(84,s))
        background=self.folder/'preview_background.png';im=Image.new('RGB',(1080,2400),'#28313a');d=ImageDraw.Draw(im)
        font_path=Path('C:/Windows/Fonts/msyh.ttc')
        if font_path.exists():d.text((540,1200),'主素材画面',fill='#788692',font=ImageFont.truetype(str(font_path),36),anchor='mm')
        im.save(background)
        self.progress=lambda p,s:callback(85+int(p*.14),s)
        result,pipeline=render_cached(self,{'source_path':str(background),'frames':plan['frames'],'has_audio':False,'still_image':True},cache)
        result.rename(self.folder/'preview.mp4');result=self.folder/'preview.mp4'
        info=probe(result);v=next(s for s in info['streams'] if s['codec_type']=='video')
        if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))!=(1080,2400,'30/1',plan['frames']):raise RuntimeError('输出视频尺寸、帧率或帧数不符')
        pipeline.validate(result);self.progress=callback
        save(self.folder/'timings.json',self.timings)
        save(self.folder/'template.json',{'format':'v3_layered_template_v1','plan':plan,'preview':'preview.mp4','preview_sha256':sha(result),'encoder':self.encoder,'timings':self.timings,'media':info,'effects_library':str(EFFECTS),'layer_caches_preserved':True,'caches':self.caches,'final_compositor_connected':True,'precomposed':{'version':VERSION,'key':cache['key'],'coverage_frames':cache['frames']}})
        return result
