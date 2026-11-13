import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from server.scenery.service import SceneryLibrary
from server.ffmpeg_templates.service import TemplateMaker

class SceneryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.workspace=Path(self.temp.name)/'workspace';self.data=Path(self.temp.name)/'data'
        self.calls=[]
        def render(src,target,rect,asset,meta,progress):
            self.calls.append(asset['name']);target.write_bytes(src.read_bytes()+json.dumps(rect).encode());progress(.9);return 90
        self.lib=SceneryLibrary(self.workspace,self.data,render);self.lib.start=lambda:None
        self.lib.original.mkdir(parents=True);self.source=self.lib.original/'随便叫什么.mp4';self.source.write_bytes(b'original')
        self.patch=patch('server.scenery.service.probe',return_value={'streams':[{'codec_type':'video','width':360,'height':640,'duration':'3'}],'format':{'duration':'3'}});self.patch.start()
        self.identity=self.lib.scan()['originals'][0]['id']
        self.crops=[{'x':0,'y':y,'width':360,'height':200} for y in (0,220,440)]
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def create(self):return self.lib.create(self.identity,self.crops,str(uuid.uuid4()))['id']

    def test_batch_rejects_bad_source_individually_and_replays_after_source_deletion(self):
        second=self.lib.original/'第二条.mp4';second.write_bytes(b'second')
        identity=next(r['id'] for r in self.lib.scan()['originals'] if r['name']==second.name)
        items=[{'source_id':i,'crops':self.crops,'request_id':str(uuid.uuid4())} for i in (self.identity,'f'*64,identity)]
        first=self.lib.create_batch(items)['results']
        self.assertIn('id',first[0]);self.assertIn('error',first[1]);self.assertIn('id',first[2])
        while self.lib.run_next():pass
        self.assertFalse(self.source.exists());self.assertFalse(second.exists())
        self.assertEqual(first,self.lib.create_batch(items)['results'])
        self.assertEqual(2,len(self.lib.snapshot()['jobs']));self.assertEqual(6,len(self.lib.ready_assets()))

    def test_batch_failed_middle_job_does_not_block_later_jobs_and_respects_pause(self):
        for name in ('中间失败.mp4','最后成功.mp4'):(self.lib.original/name).write_bytes(name.encode())
        rows={r['name']:r['id'] for r in self.lib.scan()['originals']}
        items=[{'source_id':rows[n],'crops':self.crops,'request_id':str(uuid.uuid4())} for n in (self.source.name,'中间失败.mp4','最后成功.mp4')]
        self.lib.action('pause');results=self.lib.create_batch(items)['results']
        self.assertTrue(self.lib.snapshot()['paused']);self.assertFalse(self.lib.run_next())
        render=self.lib.render
        def fail(src,*args):
            if src.name=='中间失败.mp4':raise RuntimeError('模拟处理中断')
            return render(src,*args)
        self.lib.render=fail;self.lib.action('resume')
        while self.lib.run_next():pass
        jobs={j['id']:j for j in self.lib.snapshot()['jobs']}
        self.assertEqual(['done','error','done'],[jobs[r['id']]['status'] for r in results])
        self.assertTrue((self.lib.original/'中间失败.mp4').exists());self.assertFalse((self.lib.original/'最后成功.mp4').exists())
        self.assertEqual('中间失败.mp4',jobs[results[1]['id']]['name'])

    def test_batch_duplicate_sources_rejected_before_any_enqueue(self):
        item={'source_id':self.identity,'crops':self.crops,'request_id':str(uuid.uuid4())}
        for items in ([],[item,{**item,'request_id':str(uuid.uuid4())}],[item]*201,[{**item,'request_id':None}]):
            with self.assertRaises(ValueError):self.lib.create_batch(items)
        self.assertEqual([],self.lib.snapshot()['jobs']);self.assertTrue(self.source.exists())

    def test_manual_original_delete_blocks_active_and_keeps_other_originals(self):
        job=self.create();other=self.lib.original/'不删除.mp4';other.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError,'排队'):self.lib.delete_original(self.identity)
        self.lib.action('cancel',job);self.lib.delete_original(self.identity)
        self.assertFalse(self.source.exists());self.assertTrue(other.exists());self.assertEqual([],self.lib.snapshot()['jobs'])

    def test_manual_original_delete_after_failed_processing_cleans_job_and_staging(self):
        job=self.create();render=self.lib.render
        def fail(*args):
            if len(self.calls)==1:raise RuntimeError('interrupted')
            return render(*args)
        self.lib.render=fail;self.lib.run_next();folder=self.lib.root/'jobs'/job
        self.assertTrue(folder.is_dir());self.lib.delete_original(self.identity)
        self.assertFalse(folder.exists());self.assertEqual([],self.lib.snapshot()['jobs']);self.assertEqual([],self.lib.ready_assets())

    def test_manual_original_delete_after_failed_unlink_preserves_published_outputs(self):
        job=self.create();unlink=Path.unlink
        def fail(p,*a,**k):
            if p==self.source:raise PermissionError('occupied')
            return unlink(p,*a,**k)
        with patch.object(Path,'unlink',fail):self.lib.run_next()
        self.lib.delete_original(self.identity)
        self.assertEqual(3,len(self.lib.ready_assets()));self.assertTrue(all(not a['job_id'] for a in self.lib.ready_assets()))
        self.assertEqual([],self.lib.snapshot()['jobs']);self.assertFalse(self.source.exists())

    def test_manual_ready_delete_protects_reservations_and_keeps_usage(self):
        self.create();self.lib.run_next();a=self.lib.ready_assets()[0]
        maker=TemplateMaker(self.workspace,self.data)
        with maker.connect() as c:
            c.execute('INSERT INTO usages VALUES(?,?)',('done',a['sha256']));c.execute('INSERT INTO reservations VALUES(?,?)',('waiting',a['sha256']))
        with self.assertRaisesRegex(ValueError,'占用'):self.lib.delete_asset(a['id'])
        with maker.connect() as c:c.execute('DELETE FROM reservations')
        self.lib.delete_asset(a['id']);self.assertFalse(Path(a['path']).exists());self.assertEqual(2,len(self.lib.ready_assets()))
        with maker.connect() as c:self.assertEqual(1,c.execute('SELECT COUNT(*) FROM usages').fetchone()[0])

    def test_manual_delete_rejects_changed_files(self):
        self.source.write_bytes(b'changed longer original')
        with self.assertRaisesRegex(ValueError,'变化'):self.lib.delete_original(self.identity)
        self.assertTrue(self.source.exists());self.lib.scan();self.create();self.lib.run_next()
        a=self.lib.ready_assets()[0];p=Path(a['path']);p.write_bytes(b'changed processed')
        with self.assertRaisesRegex(ValueError,'变化'):self.lib.delete_asset(a['id'])
        self.assertTrue(p.exists())
    def test_raw_never_eligible_named_results_and_original_removal(self):
        maker=TemplateMaker(self.workspace,self.data);maker.start=lambda:None
        self.assertEqual([],maker.scan()[0])
        request=str(uuid.uuid4());first=self.lib.create(self.identity,self.crops,request);self.assertEqual(first,self.lib.create(self.identity,self.crops,request))
        self.lib.run_next();self.assertEqual('done',self.lib.snapshot()['jobs'][0]['status'])
        self.assertFalse(self.source.exists());self.assertEqual([],self.lib.snapshot()['originals'])
        assets=self.lib.ready_assets();self.assertEqual(['风景000001.mp4','风景000002.mp4','风景000003.mp4'],[a['name'] for a in assets])
        self.assertEqual(3,len(maker.scan()[0]))
        with self.lib.connect() as c:
            job=c.execute('SELECT * FROM jobs').fetchone()
            for key in ('source_id','source_path','source_hash'):self.assertEqual('',job[key])
            self.assertEqual('{}',job['source_meta']);self.assertTrue(all(not a['job_id'] for a in assets))
    def test_partial_failure_keeps_original_retry_reuses_completed_crop(self):
        job=self.create();original=self.lib.render
        def failure(*args):
            if len(self.calls)==1:raise ValueError('second crop fails')
            return original(*args)
        self.lib.render=failure;self.lib.run_next()
        self.assertTrue(self.source.exists());self.assertEqual([],self.lib.ready_assets())
        self.lib.render=original;self.lib.action('retry',job);self.lib.run_next()
        self.assertFalse(self.source.exists());self.assertEqual(3,len(self.calls))
    def test_delete_failure_retries_only_deletion(self):
        job=self.create();unlink=Path.unlink
        def fail(p,*a,**k):
            if p==self.source:raise PermissionError('occupied')
            return unlink(p,*a,**k)
        with patch.object(Path,'unlink',fail):self.lib.run_next()
        self.assertTrue(self.source.exists());self.assertEqual(3,len(self.lib.ready_assets()))
        self.lib.action('retry',job);self.lib.run_next();self.assertFalse(self.source.exists());self.assertEqual(3,len(self.calls))
    def test_changed_original_or_result_prevents_delete(self):
        job=self.create();original=self.lib.render
        def change(*args):
            result=original(*args);self.source.write_bytes(b'changed');return result
        self.lib.render=change;self.lib.run_next();self.assertTrue(self.source.exists())
        self.assertEqual('error',self.lib.snapshot()['jobs'][0]['status']);self.assertEqual([],self.lib.ready_assets())
    def test_original_not_deleted_if_published_result_changed_before_retry(self):
        job=self.create();unlink=Path.unlink
        def fail(p,*a,**k):
            if p==self.source:raise PermissionError('occupied')
            return unlink(p,*a,**k)
        with patch.object(Path,'unlink',fail):self.lib.run_next()
        target=Path(self.lib.ready_assets()[0]['path']);target.write_bytes(b'changed result')
        self.lib.action('retry',job);self.lib.run_next()
        self.assertTrue(self.source.exists());self.assertEqual('error',self.lib.snapshot()['jobs'][0]['status'])

    def test_legacy_queued_template_protects_its_original(self):
        maker=TemplateMaker(self.workspace,self.data)
        with maker.connect() as c:
            c.execute("INSERT INTO jobs(id,batch_id,ordinal,status,plan,created_at) VALUES('legacy','batch',1,'waiting',?,'2026-10-19')",(json.dumps({'tracks':[{'materials':[{'path':str(self.source)}]}]}),))
        with self.assertRaisesRegex(ValueError,'旧模板'):self.create()
        self.assertTrue(self.source.exists());self.assertEqual([],self.lib.snapshot()['jobs'])

    def test_foreign_target_never_overwritten(self):
        self.create();self.lib.ready.mkdir(exist_ok=True);target=self.lib.ready/'风景000001.mp4';target.write_bytes(b'foreign')
        self.lib.run_next();self.assertEqual(b'foreign',target.read_bytes());self.assertTrue(self.source.exists())
    def test_exhausted_only_processed_files_removed_usage_kept_reservation_protected(self):
        self.create();self.lib.run_next();a=self.lib.ready_assets()[0]
        maker=TemplateMaker(self.workspace,self.data);maker.save_config({**maker.config(),'scenery_usage_limit':1})
        with maker.connect() as c:
            c.execute('INSERT INTO usages VALUES(?,?)',('done',a['sha256']))
            c.execute('INSERT INTO reservations VALUES(?,?)',('waiting',a['sha256']))
        self.lib.clean_exhausted();self.assertTrue(Path(a['path']).exists())
        with maker.connect() as c:c.execute('DELETE FROM reservations')
        raw=self.lib.original/'留着.mp4';raw.write_bytes(b'raw')
        self.lib.clean_exhausted();self.assertFalse(Path(a['path']).exists());self.assertTrue(raw.exists());self.assertEqual(2,len(self.lib.ready_assets()))
        with maker.connect() as c:self.assertEqual(1,c.execute('SELECT COUNT(*) FROM usages').fetchone()[0])
    def test_replaced_exhausted_file_not_deleted(self):
        self.create();self.lib.run_next();a=self.lib.ready_assets()[0];p=Path(a['path']);p.write_bytes(b'foreign changed')
        maker=TemplateMaker(self.workspace,self.data);maker.save_config({**maker.config(),'scenery_usage_limit':1})
        with maker.connect() as c:c.execute('INSERT INTO usages VALUES(?,?)',('done',a['sha256']))
        self.lib.clean_exhausted();self.assertEqual(b'foreign changed',p.read_bytes());self.assertTrue(self.lib.ready_assets()[0]['error'])
    def test_template_success_consumes_processed_assets_and_cleans_them(self):
        self.create();self.lib.run_next()
        self.source.write_bytes(b'another original')
        self.lib.scan();self.create();self.lib.run_next()
        def render(folder,plan,progress):
            p=folder/'preview.mp4';p.write_bytes(b'template fixture');return p
        maker=TemplateMaker(self.workspace,self.data,render=render);maker.start=lambda:None
        maker.save_config({**maker.config(),'duration_seconds':10,'duration_jitter':0,'scenery_usage_limit':1,'scenery_count':6})
        self.assertEqual(6,len(maker.scan()[0]))
        maker.create(1,str(uuid.uuid4()));self.assertTrue(all(a['reserved']==1 for a in self.lib.ready_assets()))
        maker.run_next();self.assertEqual('done',maker.snapshot()['jobs'][0]['status'])
        self.assertEqual([],self.lib.ready_assets());self.assertEqual([],list(self.lib.ready.glob('*.mp4')))
        with maker.connect() as c:self.assertEqual(6,c.execute('SELECT COUNT(*) FROM usages').fetchone()[0])

    def test_bad_rects_and_duplicate_requests_cannot_schedule_destructive_work(self):
        for rect in ({'x':-2,'y':0,'width':360,'height':200},{'x':0,'y':0,'width':361,'height':200},{'x':0,'y':0,'width':100,'height':200},{'x':0,'y':600,'width':360,'height':200}):
            with self.assertRaises(ValueError):self.lib.create(self.identity,[rect],str(uuid.uuid4()))
        self.create()
        with self.assertRaises(ValueError):self.create()
        self.assertTrue(self.source.exists())
    def test_cancel_and_recovery_leave_original(self):
        job=self.create();self.lib.action('cancel',job);self.assertFalse(self.lib.run_next());self.assertTrue(self.source.exists())
        job=self.create()
        with self.lib.connect() as c:c.execute("UPDATE jobs SET status='running' WHERE id=?",(job,))
        self.lib.recover();self.assertEqual('error',next(j for j in self.lib.snapshot()['jobs'] if j['id']==job)['status']);self.assertTrue(self.source.exists())
    def test_legacy_folder_unknown_files_are_raw_and_name_collision_skipped(self):
        self.lib.ready.mkdir(exist_ok=True);other=self.lib.ready/'风景000001.mp4';other.write_bytes(b'legacy raw')
        self.lib.scan();self.assertEqual(2,len(self.lib.snapshot()['originals']))
        self.create();self.lib.run_next();self.assertEqual('风景000002.mp4',self.lib.ready_assets()[0]['name']);self.assertTrue(other.exists())

if __name__=='__main__':unittest.main()
