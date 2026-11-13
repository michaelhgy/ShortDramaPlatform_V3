import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from server import v2_file_service as service
from server import production_materials as materials


class MaterialDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original = service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH
        service.WORKSPACE = self.root / 'workspace'
        service.DATA_ROOT = self.root / 'data'
        service.DATABASE_INITIALIZED_PATH = None
        self.task = service.create_task({'source_id': 'material-manager', 'account_name': '测试账号', 'drama_name': '测试短剧'})
        self.task_id = self.task['id']
        self.source = Path(self.task['paths']['materials']) / '测试短剧-1.mp4'
        self.source.write_bytes(b'original-video')
        self.material_id = uuid.uuid4().hex
        self.job_id = uuid.uuid4().hex
        stamp = service.now_text()
        with closing(service.connection()) as conn, conn:
            conn.execute("INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at) VALUES(?,?,'original_material',?,?,?,'md5','sha',?,1,'available',?,?)", (self.material_id,self.task_id,self.source.name,self.source.name,str(self.source),self.source.stat().st_size,stamp,stamp))
            conn.commit()
        self.library_path = service.DATA_ROOT / 'database' / 'v3_template_library.db'
        self.library_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.library_path)) as conn, conn:
            conn.execute('CREATE TABLE final_jobs(id TEXT PRIMARY KEY,task_id TEXT,material_id TEXT,status TEXT,plan TEXT,output_path TEXT,stage TEXT,error TEXT)')
            conn.execute('CREATE TABLE outputs(output_id TEXT PRIMARY KEY, output_path TEXT)')
        self.final = Path(self.task['paths']['finals']) / self.source.name
        self.final.write_bytes(b'final-video')
        with closing(service.connection()) as conn, conn:
            conn.execute("INSERT INTO production_video_tasks(id,task_id,source_material_id,status,draft_path,output_path,created_at,updated_at) VALUES(?,?,?,'ffmpeg_done','',?,?,?)", (self.job_id,self.task_id,self.material_id,str(self.final),stamp,stamp))
            conn.commit()
        plan = {'material_id':self.material_id,'task_id':self.task_id,'target':str(self.final)}
        with closing(sqlite3.connect(self.library_path)) as conn, conn:
            conn.execute("INSERT INTO final_jobs VALUES(?,?,?,'done',?,?,'完成','')", (self.job_id,self.task_id,self.material_id,json.dumps(plan),str(self.final)))
            conn.execute('INSERT INTO outputs VALUES(?,?)', (self.job_id,str(self.final)))
        self.cache = service.DATA_ROOT / 'fg' / self.job_id[:12]
        (self.cache / 'a1').mkdir(parents=True)
        (self.cache / 'a1' / 'final.mp4').write_bytes(b'cached-final')
        (self.cache / 'a1' / 'plan.json').write_text('{}')
        self.neighbor = self.final.with_name('测试短剧-10.mp4')
        self.neighbor.write_bytes(b'keep-neighbor')

    def tearDown(self):
        service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH = self.original
        self.temp.cleanup()

    def preview(self):
        return materials.preview(self.material_id)

    def delete(self):
        return materials.delete(self.material_id, self.preview()['confirmation_token'])

    def test_delete_original_finals_cache_jobs_keep_template_usage_and_unrelated_files(self):
        history = self.cache / 'regeneration_history'
        history.mkdir()
        previous = self.final.with_name('测试短剧-1_R02.mp4')
        previous.write_bytes(b'previous-final')
        (history / 'old.json').write_text(json.dumps({'id':self.job_id,'material_id':self.material_id,'output_path':str(previous)}))
        plan = self.preview()
        self.assertTrue(plan['can_delete'])
        self.assertEqual(1, plan['job_count'])
        result = self.delete()
        for p in (self.source,self.final,self.cache,previous): self.assertFalse(p.exists(), p)
        self.assertEqual(b'keep-neighbor',self.neighbor.read_bytes())
        self.assertEqual([],result['task']['materials'])
        self.assertEqual([],result['task']['videos'])
        with closing(service.connection()) as conn, conn:
            self.assertEqual('deleted',conn.execute('SELECT status FROM production_files WHERE id=?',(self.material_id,)).fetchone()[0])
            self.assertEqual(0,conn.execute('SELECT COUNT(*) FROM production_video_tasks').fetchone()[0])
        with closing(sqlite3.connect(self.library_path)) as conn, conn:
            self.assertEqual(0,conn.execute('SELECT COUNT(*) FROM final_jobs').fetchone()[0])
            self.assertEqual(1,conn.execute('SELECT COUNT(*) FROM outputs').fetchone()[0])
        self.assertEqual('completed',json.loads(Path(result['audit_path']).read_text(encoding='utf-8'))['state'])

    def test_export_jobs_attempts_and_events_are_removed_even_without_foreign_key_cascades(self):
        stamp = service.now_text()
        with closing(service.connection()) as conn, conn:
            conn.execute("INSERT INTO export_jobs(id,production_task_id,subject_type,subject_id,draft_name,draft_path,target_path,status,created_at,updated_at) VALUES('export',?,'final',?,'test','',?,'completed',?,?)", (self.task_id,self.job_id,str(self.final),stamp,stamp))
            conn.execute("INSERT INTO export_attempts(id,job_id,attempt_no,status,created_at,updated_at) VALUES('attempt','export',1,'completed',?,?)", (stamp,stamp))
            conn.execute("INSERT INTO export_events(id,attempt_id,sequence_no,event_type,phase,message,created_at) VALUES('event','attempt',1,'done','done','done',?)", (stamp,))
        self.delete()
        with closing(service.connection()) as conn:
            for table in ('export_jobs','export_attempts','export_events'):
                self.assertEqual(0,conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])

    def test_submitted_external_publication_blocks_local_cascade(self):
        document = {'items':[{'video_id':self.job_id,'local_id':'submitted-external-task','status':'waiting'}]}
        with closing(service.connection()) as conn, conn:
            conn.execute("INSERT INTO v3_publish_documents VALUES('publish_execution',?,?,?)", (self.task_id,json.dumps(document),service.now_text()))
        self.assertFalse(self.preview()['can_delete'])
        with self.assertRaisesRegex(ValueError,'外部发布'): self.delete()
        self.assertTrue(self.source.exists());self.assertTrue(self.final.exists())

    def test_waiting_job_is_removed_but_running_job_blocks(self):
        with closing(sqlite3.connect(self.library_path)) as conn, conn: conn.execute("UPDATE final_jobs SET status='running'")
        self.assertFalse(self.preview()['can_delete'])
        with self.assertRaisesRegex(ValueError,'正在合成'): self.delete()
        self.assertTrue(self.source.exists())
        with closing(sqlite3.connect(self.library_path)) as conn, conn: conn.execute("UPDATE final_jobs SET status='waiting'")
        self.assertTrue(self.preview()['can_delete'])
        self.delete()
        with closing(sqlite3.connect(self.library_path)) as conn, conn: self.assertEqual(0,conn.execute('SELECT COUNT(*) FROM final_jobs').fetchone()[0])

    def test_changed_file_after_confirmation_is_not_deleted(self):
        token = self.preview()['confirmation_token']
        self.source.write_bytes(b'changed-original')
        with self.assertRaisesRegex(ValueError,'确认期间发生变化'): materials.delete(self.material_id,token)
        self.assertTrue(self.final.exists())
        self.assertTrue(self.source.exists())

    def test_shared_unscanned_material_directory_blocks(self):
        other = service.create_task({'source_id':'shared-task','account_name':'其他账号','drama_name':'其他短剧'})
        with closing(service.connection()) as conn, conn:
            conn.execute('UPDATE production_tasks SET material_path=? WHERE id=?',(str(self.source.parent),other['id']));conn.commit()
        self.assertFalse(self.preview()['can_delete'])
        with self.assertRaisesRegex(ValueError,'使用'): self.delete()
        self.assertTrue(self.source.exists())

    def test_published_task_blocks(self):
        with closing(service.connection()) as conn, conn:
            conn.execute("UPDATE production_tasks SET release_status='registered' WHERE id=?",(self.task_id,));conn.commit()
        with self.assertRaisesRegex(ValueError,'登记发布'): self.preview()
        self.assertTrue(self.source.exists())

    def test_untrusted_output_path_blocks_before_any_removal(self):
        protected = self.root / 'unrelated.mp4';protected.write_bytes(b'keep')
        with closing(sqlite3.connect(self.library_path)) as conn, conn: conn.execute('UPDATE final_jobs SET output_path=?',(str(protected),))
        with self.assertRaisesRegex(ValueError,'删除路径'): self.preview()
        self.assertTrue(self.source.exists());self.assertTrue(self.final.exists());self.assertTrue(protected.exists())

    def test_failure_leaves_original_and_records_available_for_retry(self):
        original_unlink = Path.unlink
        def fail(path,*args,**kwargs):
            if path == self.final: raise PermissionError('test-file-in-use')
            return original_unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail):
            with self.assertRaisesRegex(ValueError,'删除未完成'): self.delete()
        self.assertTrue(self.source.exists())
        with closing(service.connection()) as conn, conn: self.assertEqual(1,conn.execute('SELECT COUNT(*) FROM production_video_tasks').fetchone()[0])
        self.delete();self.assertFalse(self.source.exists())

    def test_partial_failure_marks_records_and_can_be_retried(self):
        original_unlink = Path.unlink
        def fail(path,*args,**kwargs):
            if path == self.source: raise PermissionError('test-original-in-use')
            return original_unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail):
            with self.assertRaisesRegex(ValueError,'删除未完成'): self.delete()
        self.assertTrue(self.source.exists());self.assertFalse(self.final.exists())
        self.assertEqual('deletion_failed',service.get_task_details(self.task_id)['materials'][0]['status'])
        self.delete();self.assertFalse(self.source.exists())

    def test_rescan_keeps_deletion_tombstone_and_never_reuses_highest_sequence(self):
        self.delete()
        self.source.with_name('new.mp4').write_bytes(b'new-video')
        with patch.object(service,'probe_material',return_value=(12,'')),patch.object(service,'media_resolution',return_value='720x1280'):
            first=service.scan_task(self.task_id);second=service.scan_task(self.task_id)
        self.assertEqual(['测试短剧-2.mp4'],[x['name'] for x in first['items']])
        self.assertEqual(['测试短剧-2.mp4'],[x['name'] for x in second['items']])
        with closing(service.connection()) as conn, conn:
            self.assertEqual('deleted',conn.execute('SELECT status FROM production_files WHERE id=?',(self.material_id,)).fetchone()[0])

    def test_recorded_root_outside_production_workspace_is_rejected(self):
        outside = self.root / 'outside'; outside.mkdir()
        protected = outside / self.source.name; protected.write_bytes(b'keep-outside')
        with closing(service.connection()) as conn, conn:
            conn.execute('UPDATE production_tasks SET final_path=? WHERE id=?',(str(outside),self.task_id))
            conn.execute('UPDATE production_video_tasks SET output_path=? WHERE id=?',(str(protected),self.job_id))
        with self.assertRaisesRegex(ValueError,'生产文件工作区'): self.preview()
        self.assertTrue(protected.exists());self.assertTrue(self.source.exists())

    def test_foreign_cache_prefix_collision_blocks(self):
        with closing(sqlite3.connect(self.library_path)) as conn, conn:
            conn.execute("INSERT INTO final_jobs VALUES(?,?,?,'done','{}','','','')",(self.job_id[:12]+'f'*20,'other','other'))
        with self.assertRaisesRegex(ValueError,'归属冲突'): self.preview()
        self.assertTrue(self.source.exists())

    def test_http_preview_and_delete_use_confirmation_token(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),service.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}/api/v2/production-files/{self.material_id}'
        def post(suffix,body):
            with urlopen(Request(base+suffix,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=15) as response:
                return json.load(response)
        try:
            plan=post('/delete-preview',{})
            result=post('/delete',{'confirmation_token':plan['confirmation_token']})
            self.assertEqual([],result['task']['videos']);self.assertFalse(self.source.exists())
        finally: server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__': unittest.main()
