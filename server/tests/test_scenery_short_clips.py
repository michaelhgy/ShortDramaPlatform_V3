import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from server.scenery.planning import time_segments,processing_plan,validate_plan
from server.scenery.media import SceneryMedia,remux_eligible
from server.scenery.service import SceneryLibrary


class SegmentPlanningTests(unittest.TestCase):
    def test_short_sources_are_kept_as_one_segment(self):
        for seconds in (1,3.1,15,29.999,30):
            self.assertEqual([{'start_frame':0,'frames':round(seconds*30)}],time_segments(seconds,'fixed'))

    def test_long_sources_cover_the_whole_timeline_without_overlap_gaps_or_tiny_tail(self):
        for seconds in (30.001,31,40,56,60,61.7,84,100,120,600,3601.5):
            for seed in range(30):
                segments=time_segments(seconds,seed);cursor=0
                for s in segments:
                    self.assertEqual(cursor,s['start_frame']);self.assertTrue(450<=s['frames']<=840);cursor+=s['frames']
                self.assertEqual(round(seconds*30),cursor)
                self.assertGreater(len(segments),1)

    def test_lengths_vary_instead_of_repeated_halves_or_thirty_seconds(self):
        plans=[tuple(s['frames'] for s in time_segments(120,seed)) for seed in range(20)]
        self.assertGreater(len(set(plans)),15)
        self.assertTrue(all(len(set(p))>1 and max(p)<900 for p in plans))
        self.assertEqual(time_segments(60,'fixed'),time_segments(60,'fixed'))

    def test_plan_validation_rejects_missing_coverage_and_corrupt_outputs(self):
        crops=[{'x':0}]*3;meta={'duration':60,'time_segments':time_segments(60,1)}
        meta['processing_plan']=processing_plan(crops,meta['time_segments']);validate_plan(meta,crops)
        for damage in ('gap','length','outputs','version'):
            m=copy.deepcopy(meta)
            if damage=='gap':m['time_segments'][1]['start_frame']+=1
            if damage=='length':m['time_segments'][0]['frames']=901
            if damage=='outputs':m['processing_plan']['outputs'].pop()
            if damage=='version':m['processing_plan']['version']=2
            with self.assertRaises(ValueError):validate_plan(m,crops)


class ShortClipWorkflowTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.calls=[]
        def render(src,target,rect,asset,meta,update):
            self.calls.append(copy.deepcopy(meta['segment']))
            target.write_bytes(json.dumps({'rect':rect,'segment':meta['segment']}).encode());return meta['segment']['frames']
        self.lib=SceneryLibrary(self.root/'workspace',self.root/'data',render);self.lib.start=lambda:None
        self.lib.original.mkdir(parents=True);self.source=self.lib.original/'own.mp4';self.source.write_bytes(b'own fixture')
        self.identity=self.lib.scan()['originals'][0]['id']
        probe=patch('server.scenery.service.probe',return_value={'streams':[{'codec_type':'video','width':360,'height':640,'duration':'61.7'}],'format':{'duration':'61.7'}})
        probe.start();self.addCleanup(probe.stop)
        self.crops=[{'x':0,'y':y,'width':360,'height':200} for y in (0,210,430)]

    def create(self):return self.lib.create(self.identity,self.crops,str(uuid.uuid4()))['id']
    def row(self,job):
        with self.lib.connect() as c:return dict(c.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone())

    def test_detail_preview_and_job_use_identical_time_plan_and_multiply_crops(self):
        detail=self.lib.details(self.identity);job=self.create();meta=json.loads(self.row(job)['source_meta'])
        self.assertEqual(detail['time_segments'],meta['time_segments'])
        with self.lib.connect() as c:self.assertEqual(3*len(detail['time_segments']),c.execute('SELECT COUNT(*) FROM assets').fetchone()[0])
        self.lib.run_next();self.assertEqual('done',self.row(job)['status']);self.assertFalse(self.source.exists())
        assets=self.lib.ready_assets();self.assertEqual(3*round(61.7*30),sum(a['frames'] for a in assets))
        self.assertTrue(all(0<a['frames']<=900 for a in assets));self.assertTrue(all(not a['job_id'] for a in assets))

    def test_failure_retry_reuses_verified_outputs_and_original_split(self):
        job=self.create();before=self.row(job)['source_meta'];original=self.lib.render
        def failure(*args):
            if len(self.calls)==2:raise RuntimeError('fixture failure')
            return original(*args)
        self.lib.render=failure;self.lib.run_next();self.assertTrue(self.source.exists());self.assertEqual('error',self.row(job)['status'])
        self.lib.render=original;self.lib.action('retry',job);self.assertEqual(before,self.row(job)['source_meta'])
        self.lib.run_next();self.assertEqual('done',self.row(job)['status'])
        self.assertEqual(3*len(json.loads(before)['time_segments']),len(self.calls))

    def test_invalid_saved_plan_keeps_original(self):
        job=self.create();m=json.loads(self.row(job)['source_meta']);m['processing_plan']['outputs'].pop()
        with self.lib.connect() as c:c.execute('UPDATE jobs SET source_meta=? WHERE id=?',(json.dumps(m),job))
        self.lib.run_next();self.assertTrue(self.source.exists());self.assertEqual('error',self.row(job)['status']);self.assertFalse(self.calls)

    def test_wrong_renderer_frame_count_never_publishes_or_deletes_original(self):
        self.lib.render=lambda s,t,*args:(t.write_bytes(b'bad'),901)[1]
        job=self.create();self.lib.run_next();self.assertEqual('error',self.row(job)['status']);self.assertTrue(self.source.exists())
        self.assertFalse(self.lib.ready_assets())

    def test_retry_does_not_trust_cached_frames_from_an_incompatible_old_renderer(self):
        job=self.create();original=self.lib.render
        def failure(*args):
            if len(self.calls)==1:raise RuntimeError('fixture failure')
            return original(*args)
        self.lib.render=failure;self.lib.run_next()
        with self.lib.connect() as c:c.execute('UPDATE assets SET frames=1800 WHERE sha256!=?',('',))
        self.lib.render=original;self.lib.action('retry',job);self.lib.run_next()
        self.assertEqual('error',self.row(job)['status']);self.assertTrue(self.source.exists());self.assertFalse(self.lib.ready_assets())

    def test_legacy_waiting_jobs_keep_their_original_full_length_contract(self):
        job=self.create();meta=json.loads(self.row(job)['source_meta']);meta.pop('processing_plan');meta.pop('time_segments')
        with self.lib.connect() as c:
            c.execute('UPDATE jobs SET source_meta=? WHERE id=?',(json.dumps(meta),job))
            extra=[r[0] for r in c.execute('SELECT id FROM assets ORDER BY ordinal').fetchall()[3:]]
            for identity in extra:c.execute('DELETE FROM assets WHERE id=?',(identity,))
        def legacy(src,target,rect,asset,meta,update):
            self.assertNotIn('segment',meta);target.write_bytes(str(rect).encode());return 1851
        self.lib.render=legacy;self.lib.run_next();self.assertEqual('done',self.row(job)['status'])
        self.assertTrue(all(a['frames']==1851 for a in self.lib.ready_assets()))

    def test_compatible_hd_landscape_retains_native_resolution_for_fast_remux(self):
        video={'codec_name':'h264','pix_fmt':'yuv420p','r_frame_rate':'30/1','avg_frame_rate':'30/1','nb_frames':'90','sample_aspect_ratio':'1:1'}
        with patch('server.scenery.service.probe',return_value={'streams':[{'codec_type':'video','width':1920,'height':1080,'duration':'3',**video}],'format':{'duration':'3'}}):
            self.lib.create(self.identity,[{'x':0,'y':0,'width':1920,'height':1080}],str(uuid.uuid4()))
        with self.lib.connect() as c:a=c.execute('SELECT width,height FROM assets').fetchone()
        self.assertEqual((1920,1080),tuple(a))


class SceneryMediaCommandTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.meta={'width':360,'height':200,'duration':3,'rotation':0,'video':{'codec_name':'h264','pix_fmt':'yuv420p','avg_frame_rate':'30/1','r_frame_rate':'30/1','nb_frames':'90','sample_aspect_ratio':'1:1'}}
        self.entry={'asset':{'id':'one','width':360,'height':200},'rect':{'x':0,'y':0,'width':360,'height':200},'segment':{'start_frame':0,'frames':90},'target':self.root/'one.mp4'}
        self.media=SceneryMedia()

    def test_whole_compatible_horizontal_clip_copies_video_and_drops_audio(self):
        with patch.object(self.media,'command') as command,patch.object(self.media,'validate',return_value=90):self.media.render('source',[self.entry],self.meta,lambda n:None)
        args=command.call_args.args[1];self.assertIn('copy',args);self.assertIn('-an',args);self.assertNotIn('-filter_complex',args)

    def test_different_format_fps_aspect_rotation_or_cropping_prevents_remux(self):
        for field,value in [('codec_name','hevc'),('avg_frame_rate','25/1'),('r_frame_rate','60/1'),('sample_aspect_ratio','3:1'),('pix_fmt','yuv444p'),('nb_frames','91')]:
            m=copy.deepcopy(self.meta);m['video'][field]=value;self.assertFalse(remux_eligible(self.entry['rect'],self.entry['asset'],m,self.entry['segment']))
        m=dict(self.meta,rotation=90);self.assertFalse(remux_eligible(self.entry['rect'],self.entry['asset'],m,self.entry['segment']))

    def test_three_crops_share_one_decode_and_seek_near_target_interval(self):
        entries=[]
        for i in range(3):
            e=copy.deepcopy(self.entry);e['asset']['id']=str(i);e['asset']['height']=60;e['rect'].update(y=i*65,height=60)
            e['segment']={'start_frame':755,'frames':600};e['target']=self.root/f'{i}.mp4';entries.append(e)
        with patch.object(self.media,'command') as command,patch.object(self.media,'validate',return_value=600):self.media.render('source',entries,dict(self.meta,duration=60),lambda n:None)
        args=command.call_args.args[1];self.assertEqual(1,args.count('-i'));self.assertEqual('24',args[args.index('-ss')+1])
        graph=args[args.index('-filter_complex')+1];self.assertIn('split=3',graph);self.assertEqual(1,graph.count('fps=30'));self.assertIn('trim=start_frame=35:end_frame=635',graph)
        self.assertEqual(3,args.count('-an'));self.assertEqual(3,args.count('-frames:v'))

    def test_remux_validation_failure_falls_back_to_encoding(self):
        with patch.object(self.media,'command') as command,patch.object(self.media,'validate',side_effect=[ValueError('bad timestamps'),90]):
            self.media.render('source',[self.entry],self.meta,lambda n:None)
        self.assertEqual(2,command.call_count);self.assertIn('-filter_complex',command.call_args.args[1])

    def test_output_with_audio_or_more_than_thirty_seconds_is_rejected(self):
        video={'codec_type':'video','width':360,'height':200,'nb_read_frames':'90','duration':'3','avg_frame_rate':'30/1','sample_aspect_ratio':'1:1'}
        for patch_video,extra in [({},[{'codec_type':'audio'}]),({'duration':'30.1'},[]),({'nb_read_frames':'91'},[]),({'sample_aspect_ratio':'3:1'},[])]:
            value={'streams':[{**video,**patch_video},*extra],'format':{'duration':'3'}}
            with patch('server.scenery.media.subprocess.check_output',return_value=json.dumps(value).encode()):
                with self.assertRaises(ValueError):self.media.validate(self.root/'out.mp4',self.entry['asset'],self.meta,self.entry['segment'])


if __name__=='__main__':unittest.main()
