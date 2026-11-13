import json
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from server import v2_file_service as service
from server.template_library import TemplateLibrary
from server.ffmpeg_finals.service import FinalComposer
from server.ffmpeg_finals.renderer import repeat_effects
from server.ffmpeg_templates.renderer import sha


class FinalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.originals=(service.WORKSPACE,service.DATA_ROOT,service.DATABASE_INITIALIZED_PATH)
        service.WORKSPACE=self.root/'workspace';service.DATA_ROOT=self.root/'state';service.DATABASE_INITIALIZED_PATH=None
        self.task=service.create_task({'source_id':uuid.uuid4().hex,'account_name':'合成验收','drama_name':'测试剧','planned_publish_at':'2026-10-19T22:00'})
        self.lib=TemplateLibrary(service.WORKSPACE,service.DATA_ROOT,service.connection,lambda *a:(10,'1080x2400',''))
        self.lib.directory.mkdir(parents=True);self.template=self.lib.directory/'模板1019-001.mp4';self.template.write_bytes(b'template')
        self.lib.refresh();self.template_id=sha(self.template);self.lib.select(self.task['id'],self.template_id)
        self.materials=[]
        with closing(service.connection()) as c:
            for i in range(2):
                identity=uuid.uuid4().hex;p=Path(self.task['paths']['materials'])/f'测试剧-{i+1}.mp4';p.write_bytes(f'source{i}'.encode());self.materials.append(p)
                c.execute("INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds) VALUES(?,?,'original_material',?,?,?,?,?,?,?,'available',?,?,10)",(identity,self.task['id'],p.name,p.name,str(p),'',sha(p),p.stat().st_size,i+1,service.now_text(),service.now_text()))
            c.commit()
        self.fake_template={'plan':{},'caches':{},'identities':{}}
        self.patches=[patch('server.ffmpeg_finals.service.load_template',return_value=self.fake_template),patch('server.ffmpeg_finals.service.probe',return_value={'streams':[{'codec_type':'video','duration':'10'}],'format':{'duration':'10'}})]
        for p in self.patches:p.start()
        def render(folder,plan,progress):
            output=folder/'final.mp4';output.write_bytes(('verified'+plan['source_sha256']).encode());return output
        self.composer=FinalComposer(self.lib,render=render);self.composer.start=lambda:None
    def tearDown(self):
        for p in self.patches:p.stop()
        service.WORKSPACE,service.DATA_ROOT,service.DATABASE_INITIALIZED_PATH=self.originals;self.temp.cleanup()
    def finish_pair(self):
        self.composer.create(self.task['id'])
        self.composer.run_next();self.composer.run_next()
        with closing(self.lib.connect()) as c:
            return [dict(r) for r in c.execute('SELECT * FROM final_jobs')]

    def test_retirement_retains_ffmpeg_jobs_counts_and_outputs(self):
        jobs=self.finish_pair()
        theater=service.create_theater({'name':'注销验收剧场'})
        account=service.create_account({'nickname':'合成验收','channel_id':'retirement-uid','theater_id':theater['id']})
        self.assertEqual(2,self.composer.snapshot()['counts']['done'])
        service.update_account(account['id'],{'status':'注销'})
        self.assertEqual(2,len(self.composer.snapshot()['jobs']))
        self.assertEqual(2,self.composer.snapshot()['counts']['done'])
        self.assertTrue(all(Path(j['output_path']).is_file() for j in jobs))
        service.update_account(account['id'],{'status':'停用'})
        self.assertEqual(2,self.composer.snapshot()['counts']['done'])

    def test_scanned_sheep_material_is_queued_last_and_final_name_keeps_marker(self):
        source=Path(self.task['paths']['materials'])/'download1-羊头.mp4'
        source.write_bytes(b'sheep-source')
        with patch.object(service,'probe_material',return_value=(10,'')),patch.object(service,'media_resolution',return_value='96x64'):
            service.scan_task(self.task['id'])
        self.composer.create(self.task['id'])
        with closing(self.lib.connect()) as c:
            plans=[json.loads(row['plan']) for row in c.execute('SELECT plan FROM final_jobs ORDER BY rowid')]
        self.assertEqual(['测试剧-1','测试剧-2','羊-测试剧-3'],[p['name'] for p in plans])
        self.assertEqual('羊-测试剧-3.mp4',Path(plans[-1]['target']).name)
        for _ in range(3):self.composer.run_next()
        self.assertTrue(all(Path(p['target']).is_file() for p in plans))

    def test_encoder_notice_tracks_running_failed_retry_and_completed_attempt(self):
        self.composer.create(self.task['id'])
        original_render=self.composer.render
        observed=[]
        def render(folder,plan,progress):
            encoder='libx264' if folder.name=='a1' else 'h264_nvenc'
            (folder/'encoder_check.json').write_text(json.dumps({'encoder':encoder,'diagnostic':'probe failed' if encoder=='libx264' else ''}),encoding='utf-8')
            observed.append(next(j for j in self.composer.snapshot()['jobs'] if j['status']=='running')['encoding'])
            if encoder=='libx264':raise RuntimeError('fixture failure after encoder detection')
            return original_render(folder,plan,progress)
        self.composer.render=render
        self.composer.run_next()
        failed=next(j for j in self.composer.snapshot()['jobs'] if j['status']=='error')
        self.assertEqual('libx264',failed['encoding']['encoder'])
        self.assertIsNotNone(observed[0]['warning'])
        self.composer.action('retry',failed['id'])
        retried=next(j for j in self.composer.snapshot()['jobs'] if j['id']==failed['id'])
        self.assertIsNone(retried['encoding'])
        self.composer.run_next()
        done=next(j for j in self.composer.snapshot()['jobs'] if j['id']==failed['id'])
        self.assertEqual('done',done['status'])
        self.assertEqual({'encoder':'h264_nvenc','warning':None},done['encoding'])
        self.assertIsNone(observed[1]['warning'])

    def assert_final_records_removed_with_usage_kept(self):
        with closing(self.lib.connect()) as c:
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM final_jobs WHERE task_id=?',(self.task['id'],)).fetchone()[0])
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM selections WHERE task_id=?',(self.task['id'],)).fetchone()[0])
            self.assertEqual(2,c.execute('SELECT COUNT(*) FROM outputs WHERE task_id=?',(self.task['id'],)).fetchone()[0])
        self.assertTrue(self.template.is_file())

    def test_delete_task_cascades_ffmpeg_records_and_owned_cache_only(self):
        jobs=self.finish_pair()
        shared=self.lib.data_root/'tg'/'shared-template'/'packed.mp4';shared.parent.mkdir(parents=True);shared.write_bytes(b'keep template cache')
        other=self.lib.data_root/'fg'/'unrelated';other.mkdir();(other/'evidence.txt').write_text('keep')
        # An arbitrary stored package_path must not redirect cleanup into assets.
        with closing(self.lib.connect()) as c:
            c.execute('UPDATE final_jobs SET package_path=?',(str(shared.parent),));c.commit()
        preview=service.cleanup_preview(self.task['id'])
        self.assertTrue(preview['canExecute'])
        self.assertTrue(all(any(item['name']==j['id'][:12] for item in preview['itemsToDelete']) for j in jobs))
        result=service.execute_cleanup(self.task['id']);self.assertEqual([],result['errors'])
        self.assert_final_records_removed_with_usage_kept()
        self.assertTrue(shared.is_file());self.assertTrue((other/'evidence.txt').is_file())
        self.assertTrue(all(not (self.composer.root/j['id'][:12]).exists() for j in jobs))
        self.assertFalse(Path(self.task['paths']['root']).exists())
        self.assertEqual([],self.composer.snapshot()['jobs'])
        self.composer.recover();self.assertEqual([],self.composer.snapshot()['jobs'])
        with self.assertRaisesRegex(ValueError,'不存在'):self.composer.create(self.task['id'])

    def test_release_cleanup_removes_queue_but_preserves_release_and_sources(self):
        jobs=self.finish_pair()
        with closing(service.connection()) as c:
            c.execute("UPDATE production_tasks SET release_status='registered',actual_release_time='2026-10-19 10:00',release_province='浙江省',process_cleanup_at='2999-01-01',raw_cleanup_at='2999-01-07' WHERE id=?",(self.task['id'],));c.commit()
        result=service.execute_cleanup(self.task['id']);self.assertFalse(result['errors'])
        self.assert_final_records_removed_with_usage_kept()
        self.assertTrue(all(p.is_file() for p in self.materials))
        self.assertTrue(all(not Path(j['output_path']).exists() for j in jobs))
        with closing(service.connection()) as c:
            row=c.execute('SELECT * FROM production_tasks WHERE id=?',(self.task['id'],)).fetchone()
            self.assertEqual('process_cleaned',row['cleanup_status']);self.assertEqual('浙江省',row['release_province'])
            self.assertEqual('2999-01-01',row['process_cleanup_at'])
        self.composer.project(jobs[0]['id']);self.composer.recover()
        self.assertEqual([],self.composer.snapshot()['jobs'])

    def test_due_cleanup_cascades_queue_and_keeps_original_deadlines(self):
        jobs=self.finish_pair()
        with closing(service.connection()) as c:
            c.execute("UPDATE production_tasks SET release_status='registered',actual_release_time='2026-01-01',process_cleanup_at='2000-01-01',raw_cleanup_at='2999-01-01' WHERE id=?",(self.task['id'],));c.commit()
        self.assertEqual({'process':1,'raw':0},service.run_due_cleanup())
        self.assert_final_records_removed_with_usage_kept()
        self.assertTrue(all(p.is_file() for p in self.materials))
        self.assertTrue(all(not (self.composer.root/j['id'][:12]).exists() for j in jobs))
        with closing(service.connection()) as c:
            c.execute("UPDATE production_tasks SET raw_cleanup_at='2000-01-01' WHERE id=?",(self.task['id'],));c.commit()
        self.assertEqual({'process':0,'raw':1},service.run_due_cleanup())
        self.assertTrue(all(not p.exists() for p in self.materials))
        self.assert_final_records_removed_with_usage_kept()

    def test_waiting_or_running_queue_blocks_cleanup_even_without_projection(self):
        self.composer.create(self.task['id'])
        with closing(service.connection()) as c:
            c.execute('DELETE FROM production_video_tasks');c.commit()
        for status in ('waiting','running'):
            with closing(self.lib.connect()) as c:c.execute('UPDATE final_jobs SET status=?',(status,));c.commit()
            self.assertFalse(service.cleanup_preview(self.task['id'])['canExecute'])
            with self.assertRaisesRegex(ValueError,'排队或合成'):service.execute_cleanup(self.task['id'])
            self.assertTrue(all(p.is_file() for p in self.materials))
        with closing(service.connection()) as c:
            c.execute("UPDATE production_tasks SET release_status='registered',actual_release_time='2026-01-01',process_cleanup_at='2000-01-01',raw_cleanup_at='2000-01-01' WHERE id=?",(self.task['id'],));c.commit()
        self.assertEqual({'process':0,'raw':0},service.run_due_cleanup())
        self.assertTrue(all(p.is_file() for p in self.materials))

    def test_partial_file_failure_keeps_queue_records_until_retry_succeeds(self):
        jobs=self.finish_pair();blocked=(self.composer.root/jobs[0]['id'][:12]).resolve();remove=service._remove_one
        def failing(path,preserve):
            if path==blocked:raise OSError('test cache locked')
            return remove(path,preserve)
        with patch.object(service,'_remove_one',side_effect=failing):result=service.execute_cleanup(self.task['id'])
        self.assertEqual('partial',result['status']);self.assertTrue(result['errors'])
        with closing(self.lib.connect()) as c:self.assertEqual(2,c.execute('SELECT COUNT(*) FROM final_jobs').fetchone()[0])
        self.assertTrue(blocked.exists())
        self.assertEqual('completed',service.execute_cleanup(self.task['id'])['status'])
        self.assert_final_records_removed_with_usage_kept()

    def test_old_orphans_hidden_then_repaired_without_touching_files_or_quota(self):
        jobs=self.finish_pair()
        with closing(service.connection()) as c:c.execute('DELETE FROM production_tasks WHERE id=?',(self.task['id'],));c.commit()
        self.assertEqual([],self.composer.snapshot()['jobs'])
        self.composer.recover();self.assert_final_records_removed_with_usage_kept()
        self.assertTrue(all((self.composer.root/j['id'][:12]).is_dir() for j in jobs))
        self.assertFalse(self.composer.run_next())

    def test_cache_prefix_collision_blocks_deleting_another_tasks_cache(self):
        jobs=self.finish_pair();identity=jobs[0]['id'][:12]+'f'*20
        with closing(self.lib.connect()) as c:
            c.execute("INSERT INTO final_jobs(id,task_id,material_id,template_id,status,plan,created_at) VALUES(?,?,?,?,?,?,?)",(identity,'other-task','other-material',self.template_id,'done','{}',service.now_text()));c.commit()
        with self.assertRaisesRegex(ValueError,'归属冲突'):service.execute_cleanup(self.task['id'])
        self.assertTrue(Path(self.task['paths']['root']).is_dir())
        self.assertTrue((self.composer.root/jobs[0]['id'][:12]).is_dir())

    def test_late_projection_cannot_restore_cleaned_task_details(self):
        jobs=self.finish_pair()
        with closing(service.connection()) as c:
            c.execute("UPDATE production_tasks SET cleanup_status='process_cleaned' WHERE id=?",(self.task['id'],))
            c.execute('DELETE FROM production_video_tasks WHERE task_id=?',(self.task['id'],));c.commit()
        self.composer.project(jobs[0]['id'])
        with closing(service.connection()) as c:self.assertEqual(0,c.execute('SELECT COUNT(*) FROM production_video_tasks').fetchone()[0])
        self.composer.recover();self.assert_final_records_removed_with_usage_kept()

    def test_atomic_quota_no_partial_jobs(self):
        self.lib.set_usage_limit(1)
        self.assertEqual(2,self.composer.create(self.task['id'])['created_count'])
        with closing(self.lib.connect()) as c:self.assertEqual(1,self.lib.reserved(c,self.template_id))
        self.composer.run_next()
        with self.assertRaisesRegex(ValueError,'排队'):self.lib.delete(self.template_id)
        self.composer.run_next()
        with closing(self.lib.connect()) as c:self.assertEqual(1,len(self.lib.used_drama_keys(c,self.template_id)))
    def test_batch_material_lengths_do_not_request_template_expansion(self):
        values=[{'streams':[{'codec_type':'video','duration':str(n)}],'format':{'duration':str(n)}} for n in (10,17)]
        with patch('server.ffmpeg_finals.service.probe',side_effect=values):self.composer.create(self.task['id'])
        with closing(self.lib.connect()) as c:plans=[json.loads(r[0]) for r in c.execute('SELECT plan FROM final_jobs')]
        self.assertEqual([300,510],sorted(p['frames'] for p in plans))
        self.assertTrue(all('template_prepare_frames' not in p for p in plans))
    def test_batch_idempotency_delete_guard_and_usage_once(self):
        self.lib.set_usage_limit(2);self.assertEqual(2,self.composer.create(self.task['id'])['created_count'])
        self.assertEqual(0,self.composer.create(self.task['id'])['created_count'])
        with self.assertRaisesRegex(ValueError,'排队'):self.lib.delete(self.template_id)
        with self.assertRaisesRegex(ValueError,'已结束'):self.lib.select(self.task['id'],None)
        self.composer.run_next();self.composer.run_next();self.assertFalse(self.composer.run_next())
        with closing(self.lib.connect()) as c:self.assertEqual(2,c.execute('SELECT COUNT(*) FROM outputs').fetchone()[0])
        self.assertEqual(1,self.lib.catalogue(self.task['id'])['items'][0]['usage_count'])
        detail=service.get_task_details(self.task['id']);self.assertEqual(['video_exported']*2,[v['display_status'] for v in detail['videos']])
        self.assertTrue(all(v['engine']=='ffmpeg' for v in detail['videos']))
    def test_failure_retry_same_plan_success_only_counts(self):
        self.composer.create(self.task['id']);job=self.composer.snapshot()['jobs'][0]['id']
        renderer=self.composer.render;self.composer.render=lambda *a:(_ for _ in ()).throw(RuntimeError('fixture failure'))
        self.composer.run_next()
        with closing(self.lib.connect()) as c:
            plan=c.execute('SELECT plan FROM final_jobs WHERE id=?',(job,)).fetchone()[0]
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM outputs').fetchone()[0])
        self.composer.action('retry',job);self.composer.render=renderer
        self.composer.run_next();self.composer.run_next()
        with closing(self.lib.connect()) as c:
            self.assertEqual(plan,c.execute('SELECT plan FROM final_jobs WHERE id=?',(job,)).fetchone()[0]);self.assertEqual(2,c.execute('SELECT COUNT(*) FROM outputs').fetchone()[0])
    def test_pause_cancel_recover_do_not_charge(self):
        self.composer.create(self.task['id']);self.composer.action('pause');self.assertFalse(self.composer.run_next())
        job=self.composer.snapshot()['jobs'][0]['id'];self.composer.action('cancel',job)
        with closing(self.lib.connect()) as c:c.execute("UPDATE final_jobs SET status='running' WHERE status='waiting'");c.commit()
        self.composer.recover();self.assertEqual(1,self.composer.snapshot()['counts']['error'])
        with closing(self.lib.connect()) as c:self.assertEqual(0,self.lib.reserved(c,self.template_id))
    def test_source_change_and_existing_target_are_preserved(self):
        self.composer.create(self.task['id']);self.materials[0].write_bytes(b'changed')
        self.composer.run_next();self.assertEqual(1,self.composer.snapshot()['counts']['error'])
        target=Path(self.task['paths']['finals'])/'测试剧-2.mp4';target.write_bytes(b'prior file')
        self.composer.run_next();self.assertEqual(b'prior file',target.read_bytes());self.assertEqual(2,self.composer.snapshot()['counts']['error'])
    def test_cleanup_blocks_queued_new_jobs(self):
        self.composer.create(self.task['id'])
        with self.assertRaisesRegex(ValueError,'FFmpeg'):service.execute_cleanup(self.task['id'])
    def test_interrupt_after_publication_recovers_without_rendering_twice(self):
        self.composer.create(self.task['id']);self.composer.run_next();job=next(j for j in self.composer.snapshot()['jobs'] if j['status']=='done')
        with closing(self.lib.connect()) as c:
            c.execute("DELETE FROM outputs WHERE output_id=?",(job['id'],));c.execute("UPDATE final_jobs SET status='running' WHERE id=?",(job['id'],));c.commit()
        self.composer.recover();self.composer.action('retry',job['id']);self.composer.render=lambda *a:(_ for _ in ()).throw(AssertionError('unexpected rerender'))
        self.composer.run_next()
        with closing(self.lib.connect()) as c:self.assertEqual('done',c.execute('SELECT status FROM final_jobs WHERE id=?',(job['id'],)).fetchone()[0])
    def test_renderer_frame_progress_reaches_existing_queue_before_publication(self):
        self.composer.create(self.task['id']);seen=[]
        def render(folder,plan,progress):
            progress(37,'合成特效与边条 · 123/300帧')
            running=next(j for j in self.composer.snapshot()['jobs'] if j['status']=='running')
            seen.append((running['progress'],running['stage']))
            output=folder/'final.mp4';output.write_bytes(b'verified progress fixture');return output
        self.composer.render=render;self.composer.run_next()
        self.assertEqual([(37,'合成特效与边条 · 123/300帧')],seen)
        self.assertEqual(100,next(j for j in self.composer.snapshot()['jobs'] if j['status']=='done')['progress'])

    def test_repeat_schedule_exact_coverage_and_boundary_fade(self):
        segment={'start_frame':0,'end_frame':300,'phase_frame':4,'flatten_mode':'screen','background_dependent':False}
        base={'frames':300,'seconds':10,'effects':{'segments':[segment],'transitions':[]},'config':{'effect_transition_seconds':[1,2]}}
        for frames in (1,150,300,301,315,630,909):
            p=repeat_effects(base,frames);segs=p['effects']['segments']
            self.assertEqual(frames,sum(s['end_frame']-s['start_frame'] for s in segs))
            self.assertEqual(max(0,len(segs)-1),len(p['effects']['transitions']))


class PipelineTests(unittest.TestCase):
    def test_every_frame_is_encoded_once_after_base_including_tiny_tail(self):
        from server.ffmpeg_finals.pipeline import pieces
        segment={'start_frame':0,'end_frame':300,'phase_frame':4,'flatten_mode':'screen','background_dependent':False}
        base={'frames':300,'seconds':10,'effects':{'segments':[segment],'transitions':[]},'config':{'effect_transition_seconds':[1,2]}}
        for frames in (1,150,300,301,315,630,909):
            schedule=pieces(repeat_effects(base,frames))
            self.assertEqual(list(range(frames)),[f for p in schedule for f in range(p['start'],p['end'])])
    def test_progress_advances_from_frames_and_is_monotonic_across_parts(self):
        from server.ffmpeg_finals.pipeline import Pipeline
        from types import SimpleNamespace
        updates=[];p=Pipeline.__new__(Pipeline)
        p.r=SimpleNamespace(progress=lambda n,s:updates.append((n,s)))
        p.frames=300;p.total=900;p.completed=0;p.last_progress=0
        for frame in (0,90,180,300):p.report('base',frame,300)
        p.completed=300
        for frame in (0,60,120):p.report('effect',frame,120)
        p.completed+=120;p.report('effect',0,180);p.report('effect',180,180)
        p.completed=600;p.report('check',150,300);p.report('check',300,300)
        self.assertEqual(sorted(x[0] for x in updates),[x[0] for x in updates])
        self.assertGreater(len(set(x[0] for x in updates)),5)
        self.assertEqual(99,updates[-1][0]);self.assertIn('300/300',updates[-1][1])
    def test_external_filter_pads_are_bound_without_colliding_local_names(self):
        from server.ffmpeg_finals.pipeline import namespace
        g=namespace('[0:v]split=2[a][b];[1:v][a]overlay[x];[x][b]blend[out]','effect_',{'0:v':'main','1:v':'8:v','out':'result'})
        self.assertIn('[8:v]',g);self.assertIn('[effect_a]',g);self.assertIn('[result]',g)
        self.assertNotIn('[a]',g);self.assertNotIn('[0:v]',g)

if __name__=='__main__':unittest.main()
