import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from server.ffmpeg_templates.config import DEFAULTS,validate
from server.ffmpeg_templates.service import TemplateMaker
from server.ffmpeg_templates import renderer

class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.materials=[]
        for i in range(8):
            p=self.root/f'scene{i}.mp4';p.write_bytes(f'landscape {i}'.encode())
            # Short fixtures ensure all four candidates actually appear. Long
            # candidates cut off by the template are covered by usage regressions.
            self.materials.append({'id':renderer.sha(p),'path':str(p),'name':p.name,'frames':(i%4+2)*30,'size':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns})
        self.published=[]
        def render(folder,plan,progress):
            progress(60,'testing');out=folder/'preview.mp4';out.write_bytes(str(plan['seed']).encode());return out
        self.maker=TemplateMaker(self.root,self.root/'system',publish=lambda:self.published.append(True),render=render)
        self.maker.scan=lambda:(self.materials,[])
        self.maker.start=lambda:None
        config=dict(DEFAULTS,duration_seconds=10,duration_jitter=0,scenery_count=4,scenery_usage_limit=2)
        self.maker.save_config(config)
    def tearDown(self):self.temp.cleanup()
    def create(self,count=1):return self.maker.create(count,str(uuid.uuid4()))
    def test_parameter_read_recovers_missing_template_library_default(self):
        from contextlib import closing
        from server.template_library import TemplateLibrary
        library=TemplateLibrary(self.root,self.root/'system',None,None)
        with closing(library.connect()) as conn:
            conn.execute('DELETE FROM library_settings')
            conn.commit()
        config=self.maker.config()
        self.assertEqual(config['template_usage_limit'],20)
        self.assertEqual(config['duration_seconds'],10)

    def test_encoder_notice_tracks_running_failed_retry_and_completed_attempt(self):
        self.create()
        original_render=self.maker.render
        observed=[]
        def render(folder,plan,progress):
            encoder='libx264' if folder.name=='a1' else 'h264_nvenc'
            (folder/'encoder_check.json').write_text(json.dumps({'encoder':encoder,'diagnostic':'probe failed' if encoder=='libx264' else ''}),encoding='utf-8')
            observed.append(self.maker.snapshot()['jobs'][0]['encoding'])
            if encoder=='libx264':raise RuntimeError('fixture failure after encoder detection')
            return original_render(folder,plan,progress)
        self.maker.render=render
        self.maker.run_next()
        failed=self.maker.snapshot()['jobs'][0]
        self.assertEqual('libx264',failed['encoding']['encoder'])
        self.assertIsNotNone(observed[0]['warning'])
        self.maker.retry(failed['id'])
        self.assertIsNone(self.maker.snapshot()['jobs'][0]['encoding'])
        self.maker.run_next()
        done=self.maker.snapshot()['jobs'][0]
        self.assertEqual('done',done['status'])
        self.assertEqual({'encoder':'h264_nvenc','warning':None},done['encoding'])
        self.assertIsNone(observed[1]['warning'])
    def test_deleted_and_missing_completed_templates_hidden_without_erasing_history(self):
        from server.template_library import TemplateLibrary
        from contextlib import closing
        self.create(2)
        self.maker.run_next();self.maker.run_next()
        first,second=self.maker.snapshot()['jobs']
        Path(first['output_path']).unlink()
        library=TemplateLibrary(self.root,self.root/'system',None,None)
        with closing(library.connect()) as c:
            c.execute('INSERT INTO deleted_templates VALUES(?,?,?)',(second['output_sha256'],'2026-10-19','test-trash'))
            c.commit()
        snapshot=self.maker.snapshot()
        self.assertEqual(snapshot['jobs'],[])
        self.assertEqual(snapshot['counts']['done'],0)
        self.assertTrue(Path(second['output_path']).is_file())
        with self.maker.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM usages').fetchone()[0],8)

    def test_exhausted_template_remains_in_history_but_not_available_for_preview(self):
        from server.template_library import TemplateLibrary
        from contextlib import closing
        self.create();self.maker.run_next()
        job=self.maker.snapshot()['jobs'][0]
        library=TemplateLibrary(self.root,self.root/'system',None,None)
        library.set_usage_limit(1)
        with closing(library.connect()) as c:
            c.execute('INSERT INTO outputs(output_id,task_id,template_id,account_key,account_name,drama_key,drama_name,output_path) VALUES(?,?,?,?,?,?,?,?)',('o','t',job['output_sha256'],'a','a','d','d','output.mp4'))
            c.commit()
        snapshot=self.maker.snapshot()
        self.assertEqual(snapshot['counts']['done'],1)
        self.assertEqual(snapshot['jobs'][0]['availability'],'exhausted')
        self.assertIsNone(snapshot['jobs'][0]['preview_url'])
        self.assertTrue(Path(job['output_path']).is_file())

    def test_config_rejects_unknown_nan_bad_ranges(self):
        for changes in [dict(width=720),dict(duration_seconds=float('nan')),dict(border_width=[10,5]),dict(scenery_count=3),dict(mask_percent=[-1,101]),dict(duration_jitter=600),dict(fps=True)]:
            with self.assertRaises(ValueError):validate(dict(DEFAULTS,**changes))
    def test_plan_constraints_and_parameter_snapshot(self):
        self.create(2)
        with self.maker.connect() as c:plans=[json.loads(r[0]) for r in c.execute('SELECT plan FROM jobs')]
        self.assertNotEqual(plans[0]['stickers']['cache_key'],plans[1]['stickers']['cache_key'])
        for p in plans:
            a,b=p['tracks'];self.assertFalse({m['id'] for m in a['materials']}&{m['id'] for m in b['materials']})
            self.assertNotEqual(sum(m['frames'] for m in a['materials']),sum(m['frames'] for m in b['materials']))
            for t in p['tracks']:
                self.assertEqual(sum(s['frames'] for s in t['sequence']),p['frames'])
                self.assertTrue(all(x['id']!=y['id'] for x,y in zip(t['sequence'],t['sequence'][1:])))
                self.assertEqual(t['height']%2,0);self.assertEqual(t['feather']%2,0)
        self.maker.save_config(dict(self.maker.config(),duration_seconds=30))
        self.assertEqual(self.maker.snapshot()['jobs'][0]['seconds'],10)
    def test_quota_reservation_atomic_and_idempotent(self):
        request=str(uuid.uuid4());one=self.maker.create(2,request);two=self.maker.create(2,request)
        self.assertEqual(one['batch_id'],two['batch_id']);self.assertEqual(len(self.maker.snapshot()['jobs']),2)
        with self.assertRaises(ValueError):self.create(10)
        self.assertEqual(len(self.maker.snapshot()['jobs']),2)
        with self.maker.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],8)
    def test_success_publish_usage_once(self):
        self.create();self.assertTrue(self.maker.run_next());self.assertFalse(self.maker.run_next())
        job=self.maker.snapshot()['jobs'][0];self.assertEqual(job['status'],'done');self.assertEqual(len(self.published),1)
        self.assertTrue(Path(job['output_path']).is_file());self.assertTrue(Path(job['output_path']).with_suffix('.template.json').is_file())
        with self.maker.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM usages').fetchone()[0],4)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)

    def test_short_names_do_not_collide_with_existing_files(self):
        self.create();job=self.maker.snapshot()['jobs'][0]
        self.assertRegex(job['display_name'],r'^模板\d{4}-\d{3}$')
        self.maker.output.mkdir(parents=True,exist_ok=True)
        following=self.maker.output/(job['display_name'][:-3]+'002.mp4');following.write_bytes(b'keep')
        self.create();names=[j['display_name'] for j in self.maker.snapshot()['jobs']]
        self.assertEqual(len(names),len(set(names)));self.assertNotIn(following.stem,names)
        self.assertEqual(b'keep',following.read_bytes())
    def test_failure_retry_same_plan_and_sources_preserved(self):
        self.create();job=self.maker.snapshot()['jobs'][0]['id']
        with self.maker.connect() as c:before=c.execute('SELECT plan FROM jobs WHERE id=?',(job,)).fetchone()[0]
        original=self.maker.render;self.maker.render=lambda *args: (_ for _ in ()).throw(RuntimeError('test render failure'))
        self.maker.run_next();self.assertEqual(self.maker.snapshot()['counts']['error'],1)
        with self.maker.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)
        self.maker.retry(job);self.maker.render=original;self.maker.run_next()
        with self.maker.connect() as c:self.assertEqual(before,c.execute('SELECT plan FROM jobs WHERE id=?',(job,)).fetchone()[0])
        self.assertEqual(self.maker.snapshot()['counts']['done'],1)
        self.assertTrue(all(Path(m['path']).is_file() for m in self.materials))
    def test_pause_cancel_and_recovery(self):
        self.create(2);self.maker.pause(True);self.assertFalse(self.maker.run_next())
        job=self.maker.snapshot()['jobs'][0]['id'];self.maker.cancel(job)
        self.maker.pause(False);self.maker.run_next();self.assertEqual(self.maker.snapshot()['counts']['done'],1)
        self.create()
        with self.maker.connect() as c:c.execute("UPDATE jobs SET status='running' WHERE status='waiting'")
        self.maker.recover();self.assertEqual(self.maker.snapshot()['counts']['error'],1)
    def test_changed_source_fails_without_consumption(self):
        self.create()
        for m in self.materials:Path(m['path']).write_bytes(b'changed')
        self.maker.run_next();self.assertEqual(self.maker.snapshot()['counts']['error'],1)
        with self.maker.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM usages').fetchone()[0],0)
    def test_configured_border_width_preserves_crop_bounds_and_separation(self):
        from tools.ffmpeg_overlay_lab.side_strip_library.library import make_plan
        catalogue=renderer.read(renderer.BORDERS/'catalog.json')
        for seed in range(200):
            plan=make_plan(catalogue,seed,width_range=[6,8])
            a,b=plan['sides']
            self.assertGreaterEqual(abs(a['crop_x']-b['crop_x']),plan['minimum_position_separation'])
            for side in [a,b]:
                self.assertTrue(6<=side['width']<=8)
                self.assertTrue(0<=side['crop_x']<=plan['scaled_size'][0]-side['width'])

    def test_long_schedule_covers_exactly_and_has_transitions(self):
        config=dict(self.maker.config(),duration_seconds=120,effect_segment_seconds=[10,20])
        p=renderer.make_plan(config,self.materials,8675309)
        self.assertGreater(len(p['effects']['transitions']),1)
        self.assertEqual(sum(s['end_frame']-s['start_frame'] for s in p['effects']['segments']),3600)
        for t in p['tracks']:
            self.assertEqual(t['sequence'][-1]['start_frame']+t['sequence'][-1]['frames'],3600)
            self.assertTrue(all(x['id']!=y['id'] for x,y in zip(t['sequence'],t['sequence'][1:])))

if __name__=='__main__':unittest.main()
