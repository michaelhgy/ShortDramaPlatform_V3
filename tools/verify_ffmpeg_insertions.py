"""Isolated real FFmpeg insertion verification; uses generated media only."""
import sys, json, subprocess, copy, math, struct
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.ffmpeg_finals.renderer import FinalRenderer
from server.ffmpeg_templates.renderer import sha, probe, save
from server.ffmpeg_templates.precompose import VERSION, cache_key
from server.tool_resolver import resolve_ffmpeg


def run(args):
    result=subprocess.run([str(resolve_ffmpeg()),'-v','error','-nostdin','-n',*map(str,args)],capture_output=True)
    if result.returncode: raise RuntimeError(result.stderr.decode('utf8','replace'))
    return result.stdout


def verify(root):
    root.mkdir(parents=True,exist_ok=False)
    source=root/'source.mp4';middle=root/'middle.mp4';end=root/'end.mp4'
    run(['-f','lavfi','-i','color=red:s=96x160:r=24:d=1','-f','lavfi','-i','color=green:s=96x160:r=24:d=1','-f','lavfi','-i','color=blue:s=96x160:r=24:d=1','-f','lavfi','-i','sine=frequency=440:duration=3', '-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-map','3:a','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',source])
    run(['-f','lavfi','-i','color=yellow:s=160x96:r=25:d=0.6','-f','lavfi','-i','sine=frequency=880:duration=0.6','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-t','0.6',middle])
    run(['-f','lavfi','-i','color=white:s=96x160:r=30:d=0.5','-c:v','libx264','-pix_fmt','yuv420p',end])
    source_silent=root/'source_silent.mp4';run(['-i',source,'-an','-c:v','copy',source_silent])
    transfer=root/'transfer.mkv'
    run(['-f','lavfi','-i','color=black:s=1080x2400:r=30:d=0.5','-f','lavfi','-i','color=white:s=1080x2400:r=30:d=0.5','-filter_complex','[0:v][1:v]hstack,format=gbrp[v]','-map','[v]','-frames:v','15','-c:v','ffv1',transfer])
    segments=[{'kind':'source','source_start_frame':0,'frames':30},{'kind':'insertion','slot':'midroll','path':str(middle),'sha256':sha(middle),'frames':18,'has_audio':True},{'kind':'source','source_start_frame':30,'frames':60},{'kind':'insertion','slot':'endroll','path':str(end),'sha256':sha(end),'frames':15,'has_audio':False}]
    report=[]
    for name,silent,segmented in [('affine',False,False),('segmented-silent-source',True,True),('segmented-overlap',False,True)]:
        template={'plan':{'frames':15,'fps':30,'canvas':[1080,2400]},'caches':{},'identities':{},'package_path':str(root/'package')}
        cache_root=root/(name+'-cache');directory=cache_root/cache_key(template);directory.mkdir(parents=True)
        import shutil
        shutil.copyfile(transfer,directory/'transfer.mkv')
        part={'kind':'affine','file':'transfer.mkv','start':0,'end':15,'identities':{'transfer.mkv':sha(transfer)}}
        if segmented:
            (directory/'effect').mkdir();shutil.copyfile(transfer,directory/'effect'/'base.mkv')
            (directory/'effect'/'runtime.ffgraph').write_text('[0:v]null[out]',encoding='utf8')
            part={'kind':'source_blend','directory':'effect','base':'base.mkv','runtime':'runtime.ffgraph','inputs':[],'start':0,'end':15,'render_start':0,'render_frames':15,'trim':[0,15],'identities':{'effect/base.mkv':sha(transfer),'effect/runtime.ffgraph':sha(directory/'effect'/'runtime.ffgraph')}}
        parts=[part]
        if name=='segmented-overlap':
            part.update(start=3,trim=[3,15])
            parts=[{'kind':'affine','file':'transfer.mkv','start':0,'end':3,'identities':{'transfer.mkv':sha(transfer)}},part]
        save(directory/'manifest.json',{'version':VERSION,'key':cache_key(template),'frames':15,'parts':parts})
        src=source_silent if silent else source
        job={'source_path':str(src),'source_sha256':sha(src),'source_has_audio':not silent,'has_audio':True,'source_frames':90,'frames':123,'template':template,'insertions':{'segments':segments,'total_frames':123}}
        renderer=FinalRenderer(root/name,lambda *args:None,cache_root=cache_root)
        renderer._hardware={'vulkan_transfer':False,'hevc_cache':False}
        output=renderer.render(job)
        # Check both sides of each cut at exact frame indices.
        raw=run(['-i',output,'-vf','scale=2:2','-pix_fmt','rgb24','-f','rawvideo','-an','-'])
        expected={29:(255,0,0),30:(255,255,0),47:(255,255,0),48:(0,128,0),77:(0,128,0),78:(0,0,255),107:(0,0,255),108:(255,255,255),122:(255,255,255)}
        for frame,color in expected.items():
            actual=tuple(raw[frame*12:frame*12+3]);assert len(actual)==3 and max(abs(a-b) for a,b in zip(actual,color))<28,(name,frame,actual,color)
        pcm=run(['-i',output,'-vn','-ac','1','-ar','48000','-f','f32le','-'])
        samples=struct.unpack('<'+'f'*(len(pcm)//4),pcm)
        checks=[]
        for start,expected_hz in [(0.2,0 if silent else 440),(1.15,880),(1.9,0 if silent else 440),(3.8,0)]:
            data=samples[int(start*48000):int((start+.18)*48000)]
            rms=math.sqrt(sum(x*x for x in data)/len(data))
            crossings=sum(a<=0<b for a,b in zip(data,data[1:]));hz=crossings/.18
            assert rms<.003 if not expected_hz else rms>.01 and abs(hz-expected_hz)<15,(name,start,rms,hz,expected_hz)
            checks.append({'at':start,'rms':round(rms,5),'hz':round(hz,1)})
        report.append({'name':name,'file':str(output),'frames':123,'audio_checks':checks,'encoder':renderer.encoder,'check':'PASS'})
    save(root/'verification.json',{'status':'PASS','cases':report})
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': verify(Path(sys.argv[1]).resolve())

