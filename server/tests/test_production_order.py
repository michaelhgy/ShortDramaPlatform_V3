import json
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from server import v2_file_service as service
from server.production_order import ordered_tasks,move_task
from server.ffmpeg_finals.service import FinalComposer
from server.ffmpeg_templates.renderer import sha
from server.tests import test_ffmpeg_finals as fixtures

class ProductionOrderTests(unittest.TestCase):
    setUp=fixtures.FinalTests.setUp
    tearDown=fixtures.FinalTests.tearDown
    def another(self):
        task=service.create_task({'source_id':uuid.uuid4().hex,'account_name':'排序验收二','drama_name':'第二部剧','planned_publish_at':'2026-10-20'})
        self.lib.select(task['id'],self.template_id)
        with closing(service.connection()) as c:
            for index in range(2):
                p=Path(task['paths']['materials'])/f'第二部剧-{index+1}.mp4';p.write_bytes(f'other{index}'.encode())
                c.execute("INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds) VALUES(?,?,'original_material',?,?,?,?,?,?,?,'available',?,?,10)",(uuid.uuid4().hex,task['id'],p.name,p.name,str(p),'',sha(p),p.stat().st_size,index+1,service.now_text(),service.now_text()))
            c.commit()
        return task
    def move(self,source,target):
        with closing(service.connection()) as c:return move_task(c,source,target,'before')
    def test_persisted_card_order_and_invalid_drop_preserve_records(self):
        other=self.another();order=self.move(other['id'],self.task['id'])['order'];self.assertEqual([other['id'],self.task['id']],order)
        with closing(service.connection()) as c:
            self.assertEqual(order,[r['id'] for r in ordered_tasks(c)])
            with self.assertRaises(ValueError):move_task(c,self.task['id'],'missing','before')
        self.assertEqual('2026-10-19',service.list_tasks(self.task['id'])['items'][0]['planned_publish_at'])
        self.assertGreater(service.list_tasks(self.task['id'])['items'][0]['manual_order'],0)
    def test_next_final_uses_card_order_and_rechecks_after_each_finished_video(self):
        other=self.another();self.composer.create(self.task['id']);self.composer.create(other['id']);self.move(other['id'],self.task['id'])
        self.assertEqual(other['id'],self.composer.snapshot()['jobs'][0]['task_id']);self.composer.run_next()
        self.move(self.task['id'],other['id']);self.composer.run_next()
        with closing(self.lib.connect()) as c:
            done=[r['task_id'] for r in c.execute("SELECT task_id FROM final_jobs WHERE status='done' ORDER BY rowid")]
        self.assertCountEqual([self.task['id'],other['id']],done)
    def test_auto_defaults_off_queues_once_and_stops_pending_automatic_jobs(self):
        self.assertFalse(self.composer.snapshot()['auto_enabled']);self.assertFalse(self.composer.automatic_tick())
        self.composer.set_automatic(True);self.assertTrue(self.composer.automatic_tick());self.assertFalse(self.composer.automatic_tick());self.assertTrue(self.composer.run_next())
        self.composer.set_automatic(False);self.assertFalse(self.composer.run_next());self.assertTrue(any(j['auto_held'] for j in self.composer.snapshot()['jobs']))
        restarted=FinalComposer(self.lib,render=self.composer.render);restarted.start=lambda:None
        self.assertFalse(restarted.auto_enabled);self.assertFalse(restarted.run_next())
        restarted.create(self.task['id']);self.assertTrue(restarted.run_next());self.assertEqual(2,restarted.snapshot()['counts']['done'])

    def test_automatic_switch_survives_recreation_in_both_directions_and_respects_pause(self):
        self.assertFalse(self.composer.auto_enabled)
        self.composer.set_automatic(True)
        restarted=FinalComposer(self.lib,render=self.composer.render);restarted.start=lambda:None
        self.assertTrue(restarted.snapshot()['auto_enabled'])
        restarted.action('pause');self.assertFalse(restarted.automatic_tick())
        restarted.action('resume');self.assertTrue(restarted.automatic_tick())
        restarted.set_automatic(False)
        again=FinalComposer(self.lib,render=self.composer.render);again.start=lambda:None
        self.assertFalse(again.snapshot()['auto_enabled']);self.assertFalse(again.run_next())
        with self.assertRaises(ValueError):again.set_automatic('true')
        self.assertFalse(FinalComposer(self.lib).auto_enabled)
    def test_auto_follows_card_order_and_does_not_choose_missing_template(self):
        other=self.another();self.move(other['id'],self.task['id']);self.composer.set_automatic(True);self.composer.automatic_tick()
        self.assertTrue(all(j['task_id']==other['id'] for j in self.composer.snapshot()['jobs']))
        with closing(self.lib.connect()) as c:c.execute('DELETE FROM selections WHERE task_id=?',(self.task['id'],));c.commit()
        self.assertFalse(self.composer.automatic_tick())
    def test_failed_auto_job_needs_explicit_retry_which_can_run_when_switch_off(self):
        self.composer.set_automatic(True);self.composer.automatic_tick();render=self.composer.render
        self.composer.render=lambda *a:(_ for _ in ()).throw(RuntimeError('fixture failure'));self.composer.run_next();self.assertFalse(self.composer.automatic_tick())
        failed=next(j for j in self.composer.snapshot()['jobs'] if j['status']=='error');self.composer.set_automatic(False);self.composer.render=render
        self.composer.action('retry',failed['id']);self.assertTrue(self.composer.run_next())
        self.assertEqual('done',next(j for j in self.composer.snapshot()['jobs'] if j['id']==failed['id'])['status'])
    def test_registered_task_is_not_reorderable_or_auto_queued(self):
        other=self.another()
        with closing(service.connection()) as c:c.execute("UPDATE production_tasks SET release_status='registered' WHERE id=?",(self.task['id'],));c.commit()
        with self.assertRaises(ValueError):self.move(self.task['id'],other['id'])
        self.composer.set_automatic(True);self.composer.automatic_tick();self.assertTrue(all(j['task_id']==other['id'] for j in self.composer.snapshot()['jobs']))
    def test_switching_off_during_render_finishes_current_output_only(self):
        render=self.composer.render
        def finish_current(folder,plan,progress):
            self.composer.set_automatic(False)
            return render(folder,plan,progress)
        self.composer.render=finish_current;self.composer.set_automatic(True);self.composer.automatic_tick()
        self.assertTrue(self.composer.run_next());self.assertFalse(self.composer.run_next())
        self.assertEqual(1,self.composer.snapshot()['counts']['done']);self.assertEqual(1,self.composer.snapshot()['counts']['waiting'])

if __name__=='__main__':unittest.main()
