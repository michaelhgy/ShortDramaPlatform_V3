"""Silent short scenery: whole-frame remux, or one decode per time interval."""
from fractions import Fraction
import json
from pathlib import Path
import subprocess
from server.ffmpeg_process import run_progress
from server.ffmpeg_templates.renderer import hidden
from server.tool_resolver import resolve_ffmpeg,resolve_ffprobe


def remux_eligible(rect,asset,meta,segment):
    v=meta.get('video',{})
    try:
        return (segment['start_frame']==0 and segment['frames']==round(meta['duration']*30) and meta['duration']<=30
                and v.get('codec_name')=='h264' and v.get('pix_fmt')=='yuv420p'
                and Fraction(v.get('avg_frame_rate','0'))==30 and Fraction(v.get('r_frame_rate','0'))==30
                and int(v.get('nb_frames',0))==segment['frames']
                and v.get('sample_aspect_ratio') in ('1:1','1/1') and meta.get('rotation',0)%360==0
                and (rect['x'],rect['y'],rect['width'],rect['height'])==(0,0,meta['width'],meta['height'])
                and (asset['width'],asset['height'])==(meta['width'],meta['height']))
    except (ValueError,ZeroDivisionError,TypeError):return False


class SceneryMedia:
    def command(self,name,args,frames,update):
        cmd=[str(resolve_ffmpeg()),'-hide_banner','-nostdin','-y','-progress','pipe:1','-nostats',*map(str,args)]
        Path(str(name)+'.command.json').write_text(json.dumps(cmd,ensure_ascii=False,indent=2),encoding='utf8')
        logpath=Path(str(name)+'.log')
        with logpath.open('wb') as log:
            code,_=run_progress(cmd,log,lambda n,end:update(min(.9,n/max(1,frames)*.9)),popen_options=hidden())
        if code:raise RuntimeError('风景处理失败：'+logpath.read_text(encoding='utf8',errors='replace')[-1000:])

    def validate(self,path,asset,meta,segment=None):
        data=json.loads(subprocess.check_output([str(resolve_ffprobe()),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],**hidden()))
        v=next(s for s in data['streams'] if s['codec_type']=='video');frames=int(v['nb_read_frames'])
        expected=segment['frames'] if segment else meta['duration']*30
        if ((v['width'],v['height'])!=(asset['width'],asset['height']) or (frames!=expected if segment else abs(frames-expected)>2)):
            raise ValueError('处理结果尺寸或时长校验失败')
        if any(s['codec_type']=='audio' for s in data['streams']):raise ValueError('风景处理结果不应包含声音')
        if segment:
            duration=float(v.get('duration') or data['format']['duration'])
            if frames>900 or duration>30.00001 or Fraction(v['avg_frame_rate'])!=30 or v.get('sample_aspect_ratio')!='1:1':
                raise ValueError('风景短片必须为30秒以内、30帧和方形像素')
        checked=subprocess.run([str(resolve_ffmpeg()),'-v','error','-xerror','-i',str(path),'-map','0:v:0','-f','null','-'],capture_output=True,**hidden())
        if checked.returncode:raise ValueError('处理结果完整解码失败')
        return frames

    def render(self,source,entries,meta,update,on_verified=None):
        """Entries share one time interval; crop outputs reuse one input decode."""
        segment=entries[0]['segment'];frames=segment['frames'];first=entries[0]
        def verified(entry):
            count=self.validate(entry['target'],entry['asset'],meta,segment)
            if on_verified:on_verified(entry,count)
            return count
        if len(entries)==1 and remux_eligible(first['rect'],first['asset'],meta,segment):
            try:
                self.command(str(first['target'])+'.remux',['-i',source,'-map','0:v:0','-an','-sn','-dn','-map_metadata','-1','-map_chapters','-1','-c:v','copy','-movflags','+faststart',first['target']],frames,update)
                return {first['asset']['id']:verified(first)}
            except (ValueError,RuntimeError) as error:
                Path(str(first['target'])+'.remux-fallback.txt').write_text(str(error),encoding='utf8')
        # One-second pre-roll preserves FPS phase even for 29.97/VFR inputs;
        # accurate seeking must not discard a frame needed at the split edge.
        seek=max(0,segment['start_frame']//30-1);offset=segment['start_frame']-seek*30
        shared=f'[0:v:0]fps=30:start_time=0,tpad=stop_mode=clone:stop_duration=0.066667,trim=start_frame={offset}:end_frame={offset+frames},setpts=N/(30*TB)'
        if len(entries)>1:shared+=f",split={len(entries)}"+''.join(f'[in{i}]' for i in range(len(entries)))
        else:shared+='[in0]'
        graph=[shared]
        for i,e in enumerate(entries):
            rect=e['rect'];asset=e['asset']
            filters=[]
            if (rect['x'],rect['y'],rect['width'],rect['height'])!=(0,0,meta['width'],meta['height']):filters.append(f"crop={rect['width']}:{rect['height']}:{rect['x']}:{rect['y']}")
            if (asset['width'],asset['height'])!=(rect['width'],rect['height']):filters.append(f"scale={asset['width']}:{asset['height']}")
            filters+=['setsar=1','format=yuv420p']
            graph.append(f'[in{i}]'+','.join(filters)+f'[out{i}]')
        args=['-threads','2','-filter_complex_threads','4']
        if seek:args+=['-ss',str(seek)]
        args+=['-i',source,'-filter_complex',';'.join(graph)]
        for i,e in enumerate(entries):
            args+=['-map',f'[out{i}]','-an','-sn','-dn','-map_metadata','-1','-map_chapters','-1','-c:v','libx264','-threads','2','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-r','30','-frames:v',str(frames),'-video_track_timescale','30000','-movie_timescale','30000','-movflags','+faststart',e['target']]
        self.command(str(first['target'])+'.encode',args,frames,update)
        return {e['asset']['id']:verified(e) for e in entries}
