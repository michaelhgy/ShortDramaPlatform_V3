"""Real encoder + explicit regeneration using synthetic media and an identity template.

All DBs, inputs and outputs belong to the supplied fresh evidence folder. The
identity cache verifies insertion changes, not the appearance of real templates.
"""
import sys
import json
import math
import struct
import uuid
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import v2_file_service as business
from server.template_library import TemplateLibrary
from server.ffmpeg_finals.service import FinalComposer
from server.ffmpeg_finals.renderer import FinalRenderer
from server.ffmpeg_templates.renderer import sha, probe, save
from server.ffmpeg_templates.precompose import VERSION, cache_key
from tools.verify_ffmpeg_insertions import run


def verify(root):
    root.mkdir(parents=True, exist_ok=False)
    previous = business.WORKSPACE, business.DATA_ROOT, business.DATABASE_INITIALIZED_PATH
    business.WORKSPACE, business.DATA_ROOT, business.DATABASE_INITIALIZED_PATH = root / 'workspace', root / 'state', None
    try:
        task = business.create_task({'source_id': uuid.uuid4().hex, 'account_name': '重新生成隔离验收', 'drama_name': '合成测试剧', 'planned_publish_at': '2026-11-03'})
        source = Path(task['paths']['materials']) / '合成测试剧-1.mp4'
        run(['-f','lavfi','-i','color=blue:s=96x160:r=30:d=3','-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac', source])
        identity = uuid.uuid4().hex
        with closing(business.connection()) as conn:
            conn.execute("INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds) VALUES(?,?,'original_material',?,?,?,?,?,?,1,'available',?,?,3)", (identity,task['id'],source.name,source.name,str(source),'',sha(source),source.stat().st_size,business.now_text(),business.now_text())); conn.commit()
        ads = business.WORKSPACE / '生成资源' / '引流视频'; ads.mkdir(parents=True, exist_ok=True)
        run(['-f','lavfi','-i','color=yellow:s=160x96:r=25:d=0.6','-f','lavfi','-i','sine=frequency=880:duration=0.6','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-t','0.6',ads/'中插01.mp4'])
        run(['-f','lavfi','-i','color=white:s=96x160:r=30:d=0.5','-c:v','libx264','-pix_fmt','yuv420p',ads/'尾插01.mp4'])
        lib = TemplateLibrary(business.WORKSPACE, business.DATA_ROOT, business.connection, lambda *args: (0.5, '1080x2400', ''))
        lib.directory.mkdir(parents=True, exist_ok=True)
        template_path = lib.directory / '模板1103-001.mp4'; template_path.write_bytes(b'identity test template')
        lib.refresh(); template_id = sha(template_path); lib.select(task['id'], template_id)
        template = {'plan': {'frames':15, 'fps':30, 'canvas':[1080,2400]}, 'caches':{}, 'identities':{}, 'package_path': str(root/'identity-package')}
        cache_root = root / 'identity-cache'; directory = cache_root / cache_key(template); directory.mkdir(parents=True)
        transfer = directory/'transfer.mkv'
        run(['-f','lavfi','-i','color=black:s=1080x2400:r=30:d=0.5','-f','lavfi','-i','color=white:s=1080x2400:r=30:d=0.5','-filter_complex','[0:v][1:v]hstack,format=gbrp[v]','-map','[v]','-frames:v','15','-c:v','ffv1',transfer])
        save(directory/'manifest.json', {'version':VERSION,'key':cache_key(template),'frames':15,'parts':[{'kind':'affine','file':'transfer.mkv','start':0,'end':15,'identities':{'transfer.mkv':sha(transfer)}}]})
        initial_cache = sha(transfer)
        def render(folder, plan, progress):
            renderer = FinalRenderer(folder, progress, cache_root=cache_root)
            renderer._hardware = {'vulkan_transfer':False, 'hevc_cache':False}
            return renderer.render(plan)
        composer = FinalComposer(lib, render=render); composer.start = lambda: None
        cases = []
        def finish(label, frames):
            assert composer.run_next()
            job = composer.snapshot()['jobs'][0]; assert job['status']=='done', job
            output = Path(job['output_path']); media = probe(output)
            video = next(s for s in media['streams'] if s['codec_type']=='video')
            assert int(video['nb_frames']) == frames and (video['width'],video['height']) == (1080,2400)
            run(['-i',output,'-f','null','-'])
            cases.append({'label':label,'file':str(output),'sha256':sha(output),'frames':frames,'duration':float(media['format']['duration']),'encoding':job['encoding']})
            return output
        with patch('server.ffmpeg_finals.service.load_template', return_value=template):
            composer.create(task['id'])
        baseline = finish('initial-no-insertions',90)
        job_id = composer.snapshot()['jobs'][0]['id']
        rule = {'midroll':{'enabled':True,'mode':'latest','file':'','min_source_duration_seconds':0,'position_start_seconds':1,'position_end_seconds':1},'endroll':{'enabled':True,'mode':'latest','file':''}}
        business.update_v2_settings({business.ENGINE_PARAMETER_KEY: rule})
        composer.regenerate(identity=job_id); assert not baseline.exists(); both = finish('single-regenerated-midroll-and-endroll',123)
        raw = run(['-i',both,'-vf','scale=2:2','-pix_fmt','rgb24','-f','rawvideo','-an','-'])
        for frame,color in {29:(0,0,255),30:(255,255,0),47:(255,255,0),48:(0,0,255),107:(0,0,255),108:(255,255,255),122:(255,255,255)}.items():
            actual = tuple(raw[frame*12:frame*12+3]); assert max(abs(a-b) for a,b in zip(actual,color)) < 28, (frame,actual,color)
        pcm = run(['-i',both,'-vn','-ac','1','-ar','48000','-f','f32le','-']); samples = struct.unpack('<'+'f'*(len(pcm)//4),pcm)
        for start,expected in [(0.2,440),(1.15,880),(1.9,440),(3.8,0)]:
            values = samples[int(start*48000):int((start+.18)*48000)]
            rms = math.sqrt(sum(x*x for x in values)/len(values)); hz = sum(a<=0<b for a,b in zip(values,values[1:]))/.18
            assert rms < .003 if not expected else rms > .01 and abs(hz-expected)<15, (start,rms,hz,expected)
        business.update_task_insertion_strategy(task['id'], {'midroll':{'enabled':False}})
        composer.regenerate(task_id=task['id']); assert not baseline.exists(); finish('batch-regenerated-current-task-tail-only',105)
        business.update_material_insertion_strategy(identity, {'endroll':{'enabled':False}})
        composer.regenerate(task_id=task['id']); assert not baseline.exists(); finish('batch-regenerated-current-material-no-insertions',90)
        assert len({case['file'] for case in cases}) == 1
        assert baseline.is_file() and sha(baseline) == cases[-1]['sha256']
        assert not list(baseline.parent.glob('*_R*.mp4'))
        assert sha(transfer)==initial_cache
        with closing(lib.connect()) as conn:
            assert conn.execute('SELECT COUNT(*) FROM outputs').fetchone()[0] == 1
            assert len(lib.used_drama_keys(conn,template_id)) == 1
        report = {'status':'PASS','cases':cases,'old_outputs_retained':False,'deleted_before_render':True,'canonical_filename_reused':True,'template_cache_unchanged':True,'usage_rows':1,'audio_and_cut_frames':'PASS','identity_template_only':True}
        save(root/'verification.json',report); print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        business.WORKSPACE, business.DATA_ROOT, business.DATABASE_INITIALIZED_PATH = previous


if __name__ == '__main__': verify(Path(sys.argv[1]).resolve())
