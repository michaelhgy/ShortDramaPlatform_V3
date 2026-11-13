"""Two picture passes, existing layer caches, stream-copy publication.

Graphs preserve the accepted filter order and frame schedule. Intermediate H.264
round trips are intentionally removed; source media and template caches are read-only.
"""
from __future__ import annotations
import re
import json
import os
import time
from pathlib import Path
from server.ffmpeg_diagnostics import phase
from server.ffmpeg_process import run_progress
from server.ffmpeg_templates.renderer import EFFECTS, read, save, sha, hidden
from tools.ffmpeg_overlay_lab.effect_library.library import render_graph
from tools.ffmpeg_overlay_lab.sticker_library.library import overlay_graph as sticker_graph


def namespace(graph, prefix, bindings):
    """Rename local pad labels while binding external input/output pads explicitly."""
    return re.sub(r'\[([^\]]+)\]', lambda m:'['+bindings.get(m[1],prefix+m[1])+']', graph)


def pieces(plan):
    segments=plan['effects']['segments'];trans=plan['effects']['transitions'];result=[]
    for i,segment in enumerate(segments):
        start=trans[i-1]['end_frame'] if i else 0
        end=trans[i]['start_frame'] if i<len(trans) else plan['frames']
        if end>start:result.append({'start':start,'end':end,'segments':[segment]})
        if i<len(trans):
            t=trans[i]
            result.append({'start':t['start_frame'],'end':t['end_frame'],'segments':[segment,segments[i+1]],'transition':t})
    if not result or result[0]['start']!=0 or result[-1]['end']!=plan['frames'] or any(a['end']!=b['start'] for a,b in zip(result,result[1:])):
        raise ValueError('特效时间轴没有精确覆盖成片')
    return result


class Pipeline:
    def __init__(self, renderer, frames, load_assets=True):
        self.r=renderer;self.frames=frames;self.completed=0;self.total=frames*3
        self.assets={a['id']:a for a in read(EFFECTS/'catalog.json')['assets']} if load_assets else {}
        self.verified=set();self.last_progress=0

    def report(self, stage, frame, count):
        done=max(0,min(count,frame))
        progress=min(99,int((self.completed+done)*99/self.total))
        self.last_progress=max(self.last_progress,progress)
        self.r.progress(self.last_progress,f'{stage} · {done}/{count}帧')

    def command(self, name, args, frames, stage, count_work=True):
        with phase('ffmpeg:' + name, frames=frames, label=stage):
            return self._command(name, args, frames, stage, count_work)

    def _command(self, name, args, frames, stage, count_work=True):
        cmd=[str(self.r.ff),'-hide_banner','-nostdin','-n','-progress','pipe:1','-stats_period','0.5','-nostats',*map(str,args)]
        save(self.r.folder/(name+'.command.json'),cmd);start=time.monotonic();last_emit=0
        self.report(stage,0,frames)
        with (self.r.folder/(name+'.log')).open('wb') as log, (self.r.folder/'progress.jsonl').open('a',encoding='utf-8') as trace:
            def report(frame, ended):
                nonlocal last_emit
                if time.monotonic()-last_emit>=.8 or ended:
                    # Muxing is reported separately; it is not another picture render.
                    if count_work:self.report(stage,frame,frames)
                    else:self.r.progress(self.last_progress,f'{stage} · {max(0,min(frames,frame))}/{frames}帧')
                    trace.write(json.dumps({'stage':name,'frame':frame,'frames':frames,'elapsed':round(time.monotonic()-start,3),'progress':self.last_progress})+'\n');trace.flush();last_emit=time.monotonic()
            try:
                code,frame=run_progress(cmd,log,report,popen_options=hidden())
            except RuntimeError as error:
                log.write(('\n'+str(error)+'\n').encode('utf-8'));log.flush()
                raise RuntimeError(f'{stage}失败：{error}') from error
        elapsed=round(time.monotonic()-start,3)
        self.processed_frames=frame
        self.r.timings.append({'stage':name,'seconds':elapsed,'frames':frames})
        if code:
            tail=(self.r.folder/(name+'.log')).read_text(encoding='utf-8',errors='replace')[-2200:]
            raise RuntimeError(f'{stage}失败：{tail}')
        if count_work:self.report(stage,frames,frames);self.completed+=frames

    def filtered(self,name,inputs,graph,frames,stage):
        script=self.r.folder/(name+'.ffgraph');script.write_text(graph,encoding='utf-8')
        output=self.r.folder/(name+'.mp4')
        encode=self.r.encode();idx=encode.index('-movflags');encode=encode[:idx]+encode[idx+2:]
        args=['-threads','2','-filter_complex_threads',str(min(8,os.cpu_count() or 4)),*inputs,'-filter_complex_script',script,'-map','[out]','-an','-frames:v',frames,*encode,output]
        self.command(name,args,frames,stage)
        return output

    def base(self,job,plan):
        cache=job['template']['caches'];args=['-i',job['source_path']]
        for layer in cache['scenery']:args+=['-stream_loop','-1','-i',layer['video']]
        for layer in cache['scenery']:args+=['-loop','1','-framerate','30','-i',layer['mask']]
        args+=['-stream_loop','-1','-i',cache['stickers']]
        bottom=plan['tracks'][1]['height']
        g=f'[0:v]fps=30,scale=1080:2400:force_original_aspect_ratio=increase,crop=1080:2400,setsar=1,tpad=stop_mode=clone:stop_duration=1,trim=end_frame={self.frames},settb=1/30,setpts=N,format=rgba[main];[1:v][3:v]alphamerge[t];[2:v][4:v]alphamerge[b];[main][t]overlay=0:0:format=rgb[x];[x][b]overlay=0:{2400-bottom}:format=rgb,format=yuv420p[scenery];'
        sg=sticker_graph(self.frames,phase=plan['stickers']['start_frame'])
        factor=plan['config']['sticker_alpha_percent']/80
        sg=sg.replace('format=rgba,split=2[pt][pb]',f'format=rgba,colorchannelmixer=aa={factor},split=2[pt][pb]')
        g+=namespace(sg,'st_',{'0:v':'scenery','1:v':'5:v','out':'out'})
        return self.filtered('base',args,g,self.frames,'合成风景、羽化与贴纸')

    def effect(self,seg,start,n,base,prefix,inputs,next_index):
        asset=self.assets[seg['asset_id']]
        if asset['cache_key']!=seg['asset_key']:raise ValueError('特效资源版本已变化')
        for layer in asset['layers']+([asset['background']['layer']] if (asset.get('background') or {}).get('layer') else []):
            path=EFFECTS/layer['file']
            if str(path) not in self.verified:
                if sha(path)!=layer['sha256']:raise ValueError('特效缓存已变化')
                self.verified.add(str(path))
        paths,g=render_graph(EFFECTS,asset,1080,2400,n,seg['phase_frame']+start-seg['start_frame'],1)
        amount=seg['relative_strength_percent']/100
        if amount<1:
            g=g.replace('[0:v]trim=','[0:v]split=2[intensitybase][fxinput];[fxinput]trim=',1)
            g=g.replace('format=yuv420p[out]',f'format=yuv420p[fxout];[intensitybase]trim=end_frame={n},settb=1/30,setpts=N,format=yuv420p[ib];[fxout][ib]blend=all_mode=normal:all_opacity={amount}[out]')
        bindings={'0:v':base}
        for i,path in enumerate(paths,1):
            bindings[f'{i}:v']=f'{next_index}:v';next_index+=1
            inputs+=['-threads','1','-i',path]
        return namespace(g,prefix,bindings),prefix+'out',next_index

    def chunk(self,base,job,plan,piece,index):
        s=piece['start'];n=piece['end']-s
        inputs=['-ss',str(s/30),'-i',base];next_index=1
        segs=piece['segments'];graphs=[]
        if len(segs)==1:
            g,out,next_index=self.effect(segs[0],s,n,'0:v','fx_',inputs,next_index);graphs.append(g)
        else:
            method=piece['transition']['method'];through=method!='cached_effect_crossfade'
            graphs.append('[0:v]'+('split=3[basea][baseb][plain]' if through else 'split=2[basea][baseb]'))
            ga,a,next_index=self.effect(segs[0],s,n,'basea','a_',inputs,next_index)
            gb,b,next_index=self.effect(segs[1],s,n,'baseb','b_',inputs,next_index)
            graphs += [ga,gb]
            # Set one scalar per frame instead of evaluating arithmetic per pixel.
            # FFmpeg blend's N starts at 1; timestamps start at 0.
            commands=[]
            for f in range(n):
                stamp=max(0,(f-.0001)/30)
                weights={'fade':1-(f+1)/n} if not through else {
                    'fadea':1-min(1,(f+1)/(n//2)),
                    'fadeb':1-max(0,((f+1)-(n//2))/(n//2)),
                    'choose':1 if f+1<n//2 else 0}
                commands.append(f'{stamp:.9f} '+','.join(f'blend@{target} all_opacity {weight:.12f}' for target,weight in weights.items())+';')
            command_file=self.r.folder/f'fade_{index:03d}.txt'
            command_file.write_text('\n'.join(commands),encoding='utf-8')
            command_path=command_file.resolve().as_posix().replace(':','\\:').replace("'", "'\\''")
            graphs.append(f"[{a}]sendcmd=f='{command_path}'[commanded]")
            if not through:graphs.append(f'[commanded][{b}]blend@fade=all_mode=normal:all_opacity=1[mix]')
            else:
                graphs.append(f"[plain]trim=end_frame={n},settb=1/30,setpts=N,format=yuv420p,split=2[x][y];[commanded][x]blend@fadea=all_mode=normal:all_opacity=1[a];[y][{b}]blend@fadeb=all_mode=normal:all_opacity=1[b];[a][b]blend@choose=all_mode=normal:all_opacity=1[mix]")
            out='mix'
        cycle=plan['borders']['cycle_frames']
        # An integral-millisecond loop can seek by phase. For other periods,
        # retain the original accumulated MKV timestamps across all loops.
        phase=s%cycle if cycle%3==0 else s
        inputs+=['-stream_loop','-1','-i',job['template']['caches']['borders']]
        # Prepared side strips are opaque RGB; replacing the edge columns avoids
        # two full-frame alpha overlays while preserving their exact placement.
        lw,rw=[side['width'] for side in plan['borders']['sides']]
        graphs.append(f'[{out}]format=gbrp,crop={1080-lw-rw}:2400:{lw}:0:exact=1[center]')
        # Match legacy overlay framesync: MKV millisecond timestamps sometimes
        # hold the previous strip frame. Normalize once before stacking so the
        # narrow strips cannot become the main video's clock.
        graphs.append(f'[{next_index}:v]fps=30:round=up,trim=start_frame={phase}:end_frame={phase+n},settb=1/30,setpts=N,format=gbrp,split=2[edge_l][edge_r];[edge_l]crop={lw}:2400:0:0:exact=1[left];[edge_r]crop={rw}:2400:{lw}:0:exact=1[right];[left][center][right]hstack=inputs=3:shortest=1,format=yuv420p[out]')
        return self.filtered(f'part_{index:03d}',inputs,';'.join(graphs),n,f'合成特效与边条 {index+1}/{len(pieces(plan))}')

    def mux(self,paths,job):
        listing=self.r.folder/'parts.txt'
        listing.write_text(''.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'\n" for p in paths),encoding='utf-8')
        result=self.r.folder/'final.mp4'
        from .insertion import has_insertions, timeline_graph
        if has_insertions(job) and job['has_audio']:
            inputs, graph, _, label = timeline_graph(job, 0, self.frames, video=False, audio=True)
            # Input zero is the completed video, audio source inputs start at one.
            graph=re.sub(r'\[(\d+):a:0\]', lambda m:f'[{int(m[1])+1}:a:0]', graph)
            script=self.r.folder/'timeline_audio.ffgraph';script.write_text(graph,encoding='utf-8')
            args=['-f','concat','-safe','0','-i',listing,*inputs,'-filter_complex_script',script,
                  '-map','0:v','-map',f'[{label}]','-c:v','copy','-c:a','aac','-b:a','192k']
        else:
            args=['-f','concat','-safe','0','-i',listing,'-i',job['source_path'],'-map','0:v','-c:v','copy']
            if job['has_audio']:args+=['-map','1:a:0','-c:a','aac','-b:a','192k','-af','aresample=async=1:first_pts=0,apad']
        args+=['-t',str(self.frames/30),'-movflags','+faststart',result]
        self.command('mux',args,self.frames,'拼接视频并保留原声',count_work=False)
        return result

    def validate(self,result):
        # Full CPU decode is faster for this check on the reference machine;
        # keep it independent of the GPU used for composition.
        name='decode_check'
        args=['-v','error','-xerror','-err_detect','explode']
        self.command(name,[*args,'-i',result,'-map','0:v:0','-map','0:a?','-f','null','-'],
                     self.frames,'校验完整成片')
        if self.processed_frames!=self.frames or (self.r.folder/(name+'.log')).read_text(encoding='utf-8',errors='replace').strip():
            raise RuntimeError('成片完整解码检查失败或帧数不完整')
