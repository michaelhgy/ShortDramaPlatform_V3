"""Owned media acceptance for the short-scenery workflow in a frozen release."""
import json
from pathlib import Path
import subprocess
import uuid
from unittest.mock import patch
from server.scenery.service import SceneryLibrary
from server.scenery.media import SceneryMedia
from server.ffmpeg_templates.renderer import probe,hidden
from server.tool_resolver import resolve_ffmpeg


def verify(root):
    root=Path(root);root.mkdir(exist_ok=False);workspace=root/'workspace';data=workspace/'系统数据'
    lib=SceneryLibrary(workspace,data);lib.start=lambda:None;lib.original.mkdir(parents=True)
    ff=str(resolve_ffmpeg());commands=[];result=[];original=SceneryMedia.command
    def command(self,name,args,frames,update):
        commands.append(list(map(str,args)));return original(self,name,args,frames,update)
    def packet_hash(p):
        return subprocess.check_output([ff,'-v','error','-i',str(p),'-map','0:v:0','-c:v','copy','-f','hash','-hash','sha256','-'],**hidden()).decode().strip()
    for label,size,rate,seconds in [('horizontal-hd','1920x1080','30',3),('vertical-long','360x640','24',33)]:
        source=lib.original/(label+'.mp4')
        subprocess.run([ff,'-v','error','-n','-f','lavfi','-i',f'testsrc2=s={size}:r={rate}:d={seconds}',
                        '-f','lavfi','-i',f'sine=frequency=440:duration={seconds}',
                        '-vf','setsar=1','-c:v','libx264','-threads','2','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,**hidden())
        identity=next(r['id'] for r in lib.scan()['originals'] if r['name']==source.name)
        detail=lib.details(identity)
        crops=([{'x':0,'y':y,'width':360,'height':200} for y in (0,210,430)] if label=='vertical-long' else [{'x':0,'y':0,'width':1920,'height':1080}])
        old_hash=packet_hash(source) if label=='horizontal-hd' else None
        job=lib.create(identity,crops,str(uuid.uuid4()))['id']
        with lib.connect() as c:names=[r[0] for r in c.execute('SELECT name FROM assets WHERE job_id=? ORDER BY ordinal',(job,))]
        start=len(commands)
        with patch.object(SceneryMedia,'command',command):assert lib.run_next()
        with lib.connect() as c:row=dict(c.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone())
        assert row['status']=='done',row['error'];assert not source.exists()
        assets={a['name']:a for a in lib.ready_assets()};outputs=[assets[name] for name in names]
        assert len(outputs)==len(crops)*len(detail['time_segments'])
        assert sum(a['frames'] for a in outputs)==len(crops)*round(detail['duration']*30)
        for a in outputs:
            media=probe(a['path']);v=next(s for s in media['streams'] if s['codec_type']=='video')
            assert not any(s['codec_type']=='audio' for s in media['streams'])
            assert 0<int(v['nb_frames'])<=900 and float(v['duration'])<=30.00001
            assert v['avg_frame_rate']=='30/1' and v['sample_aspect_ratio']=='1:1'
        own=commands[start:]
        if old_hash:
            assert len(own)==1 and 'copy' in own[0]
            assert old_hash==packet_hash(outputs[0]['path'])
            assert (outputs[0]['width'],outputs[0]['height'])==(1920,1080)
        else:
            assert len(own)==len(detail['time_segments'])==2
            assert all('split=3' in args[args.index('-filter_complex')+1] for args in own)
        result.append({'source':label,'seconds':detail['duration'],'segments':detail['time_segments'],
                       'outputs':len(outputs),'decode_commands':len(own),'silent':True,
                       'all_outputs_within_30_seconds':True,'native_hd_video_packets_unchanged':bool(old_hash)})
    value={'status':'PASS','cases':result}
    (root/'result.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    return value
