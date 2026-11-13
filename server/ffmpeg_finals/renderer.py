from __future__ import annotations

from server.ffmpeg_diagnostics import phase, current
from copy import deepcopy
import time
from pathlib import Path
from server.ffmpeg_templates.renderer import Renderer, read, save, sha, probe


def load_template(path, template_id, data_root):
    path=Path(path);sidecar=path.with_suffix('.template.json')
    if not sidecar.is_file():
        raise ValueError('这个模板只有普通视频，缺少分层缓存；请选用“模板制作”生成的新模板')
    meta=read(sidecar)
    if meta.get('format')!='v3_layered_template_v1' or meta.get('preview_sha256')!=template_id or sha(path)!=template_id:
        raise ValueError('模板视频与配方不匹配，请重新生成模板')
    package=Path(meta['package_path']).resolve();data=Path(data_root).resolve()
    if not any(package.is_relative_to(data/p) for p in ('tg','template_generation/packages')):
        raise ValueError('模板分层包不属于当前工作区')
    description=package/'template.json';value=read(description);plan=value['plan'];caches=deepcopy(value.get('caches') or {})
    if value.get('preview_sha256')!=template_id:
        raise ValueError('模板分层包身份不匹配')
    if (plan['canvas'],plan['fps'])!=([1080,2400],30):raise ValueError('模板规格不受支持')
    if 'scenery' not in caches:
        caches['scenery']=[{'side':t['side'],'video':str(package/(t['side']+'_timeline.mp4')),'mask':str(package/(t['side']+'_mask.png'))} for t in plan['tracks']]
    if 'stickers' not in caches:
        found=[p/'sticker_inputs'/plan['stickers']['cache'] for p in sorted(package.parent.glob('a*'))]
        caches['stickers']=str(next((p for p in found if p.is_file()),package/'sticker_inputs'/plan['stickers']['cache']))
    if 'borders' not in caches:caches['borders']=str(package/'borders/strips.mkv')
    files=[description]
    for t in caches['scenery']:files += [Path(t['video']),Path(t['mask'])]
    files += [Path(caches['stickers']),Path(caches['borders'])]
    identities={}
    for p in files:
        p=p.resolve()
        if not p.is_relative_to(data) or not p.is_file():raise ValueError('模板缓存缺失，请重新制作模板：'+p.name)
        identities[str(p)]=sha(p)
    return {'plan':plan,'caches':caches,'identities':identities,'package_path':str(package)}


def repeat_effects(plan, frames):
    """Repeat the saved schedule, including transitions at template boundaries."""
    out=deepcopy(plan);cycle=plan['frames'];segments=[]
    for offset in range(0,frames,cycle):
        for original in plan['effects']['segments']:
            start=offset+original['start_frame']
            if start>=frames:break
            segment=deepcopy(original);segment.update(start_frame=start,end_frame=min(frames,offset+original['end_frame']),index=len(segments))
            segments.append(segment)
    transitions=[]
    duration=plan['config']['effect_transition_seconds'][0]*30
    for a,b in zip(segments,segments[1:]):
        boundary=b['start_frame'];n=min(duration,a['end_frame']-a['start_frame'],b['end_frame']-b['start_frame'])
        n=n//2*2
        if n<2:continue
        original=next((t for t in plan['effects']['transitions'] if t['boundary_frame']==boundary%cycle),None)
        if original:
            n=min(original['duration_frames'],n);method=original['method']
        else:
            method='cached_effect_crossfade' if a['flatten_mode']==b['flatten_mode'] and not a['background_dependent'] and not b['background_dependent'] else 'fade_through_unmodified_base'
        transitions.append({'boundary_frame':boundary,'start_frame':boundary-n//2,'end_frame':boundary+n//2,'duration_frames':n,'method':method})
    # Very short terminal segments still need a boundary entry for the renderer's indexing.
    if len(transitions)!=max(0,len(segments)-1):
        # Fold a one-frame tail into its preceding effect rather than emit a broken transition.
        if len(segments)>1 and segments[-1]['end_frame']-segments[-1]['start_frame']<2:
            segments[-2]['end_frame']=frames;segments.pop()
        else:raise ValueError('特效切换时间不足')
    out['effects']['segments']=segments;out['effects']['transitions']=transitions
    out['frames']=frames;out['seconds']=frames/30
    return out


def validate_output_video(video, frames):
    if (video['width'],video['height'],video['avg_frame_rate'],int(video.get('nb_frames',0)))!=(1080,2400,'30/1',frames):
        raise RuntimeError('成片规格或帧数不符')
    if (video.get('sample_aspect_ratio'),video.get('display_aspect_ratio'))!=('1:1','9:20'):
        raise RuntimeError('成片显示比例不符：必须为方形像素和9:20画幅，已停止保存')


class FinalRenderer(Renderer):
    def __init__(self,folder,progress,cache_root=None):
        super().__init__(folder,progress)
        self.cache_root=cache_root

    def render(self, job):
        from server.ffmpeg_templates.precompose import load_completed_cycle, verified_file
        from .cached import render_cached
        start=time.monotonic();self.progress(0,'检查素材与已完成模板')
        with phase('source_metadata_and_insertions_validation'):
            source=Path(job['source_path']);template=job['template']
            if not verified_file(source,job['source_sha256']):raise ValueError('主素材已变化，请重新扫描后提交')
            job=dict(job)
            insertion_plan=job.get('insertions') if isinstance(job.get('insertions'), dict) else {}
            for item in list(insertion_plan.get('segments') or []):
                if item.get('kind') != 'insertion':
                    continue
                insertion_path=Path(str(item.get('path') or ''))
                if not insertion_path.is_file() or (item.get('sha256') and not verified_file(insertion_path, str(item['sha256']))):
                    raise ValueError(f"{item.get('slot') or '插片'}素材已变化或不存在，请重新提交")
            job['source_has_audio']=bool(job.get('has_audio')) and any(stream['codec_type']=='audio' for stream in probe(source)['streams'])
            source_video=next(s for s in probe(source)['streams'] if s['codec_type']=='video')
            from .insertion import has_insertions
            job['source_fps']='30/1' if has_insertions(job) else source_video.get('avg_frame_rate')
            job['source_original_fps']=source_video.get('avg_frame_rate')
            for name in ('width','height','pix_fmt','color_space','color_trc','field_order','codec_name'):
                job['source_'+name]=source_video.get(name)
            job['source_sar']=source_video.get('sample_aspect_ratio')
            job['source_rotation']=any(s.get('rotation',0) for s in source_video.get('side_data_list',[]))
        self.timings.append({'stage':'source_validation','seconds':round(time.monotonic()-start,3)})
        frames=job['frames'];callback=self.progress
        # Queued plans may still contain template_prepare_frames. Ignore it:
        # final composition only reads/repeats a completed template period.
        if current(): current().update_context(source={key:value for key,value in job.items() if key.startswith('source_') and key not in ('source_path','source_sha256')})
        with phase('template_cache_validation'):
            cache=load_completed_cycle(template,self.cache_root,self.progress)
        self.timings.append({'stage':'template_cache_check','seconds':cache['verification_seconds'],
                             'reused':True,'coverage_frames':cache['frames']})
        result,pipeline=render_cached(self,job,cache)
        with phase('output_metadata_validation'):
            info=probe(result);v=next(s for s in info['streams'] if s['codec_type']=='video')
        validate_output_video(v,frames)
        audio=[s for s in info['streams'] if s['codec_type']=='audio']
        if bool(audio)!=job['has_audio']:raise RuntimeError('成片音轨检查失败')
        if audio and abs(float(audio[0].get('duration',frames/30))-frames/30)>.15:raise RuntimeError('原声音轨时长不符')
        pipeline.validate(result);self.progress=callback
        if current(): current().update_context(acceleration=getattr(pipeline,'acceleration',{}),renderer_timings=self.timings)
        save(self.folder/'check.json',{'status':'PASS','media':info,'timings':self.timings,'encoder':self.encoder,
             'template_cache_reused':cache['reused'],'new_cache_seconds':0 if cache['reused'] else cache['preparation_seconds'],
             'insertions':insertion_plan,'picture_encode_passes':1,'cache_root':cache['root'],'coverage_frames':cache['frames'],
             'acceleration':getattr(pipeline,'acceleration',{'transfer':'cpu'}),
             'template_loop_frames':cache['loop_frames'],'template_repeat_count':(frames+cache['loop_frames']-1)//cache['loop_frames'],
             'source_dependent_parts':sum(x['kind']!='affine' for x in cache['parts'] if x['start']<frames)})
        return result
