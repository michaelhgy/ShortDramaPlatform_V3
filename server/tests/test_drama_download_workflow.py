"""原片下载业务回归：临时目录/本地HTTP，不接手机或真实业务库。"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from server import drama_download_reader as reader
from server.drama_download_state import fingerprint, reconcile, probe_video
from server.tool_resolver import resolve_ffmpeg

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT/'tools/short_drama_downloader_lab'


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, LAB/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'V3_DRAMA_READ_TASK_STATE': str(self.folder/'state.json')})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.old = dict(reader._STATE)
        self.addCleanup(lambda: (reader._STATE.clear(), reader._STATE.update(self.old), reader._CANCEL_EVENT.clear()))
        reader._STATE.clear()
        reader._STATE.update(status='idle', episodes={})
        reader._CANCEL_EVENT.clear()

    def test_unknown_total_or_wrong_episode_set_never_complete(self):
        self.assertFalse(reconcile(0, {}, [])['complete'])
        files, records = [], {}
        for n in [1,2,4]:
            f=self.folder/f'剧-第{n:03d}集.mp4'; f.write_bytes(b'x'*100001)
            records[str(n)]={'file':str(f),'status':'ok','link': f'http://share/{n}', 'confirmation_source':'parser', 'verified':True, **fingerprint(f)}
            files.append(f)
        result=reconcile(3,records,files)
        self.assertFalse(result['complete'])
        self.assertEqual(result['missing_video_episodes'],[3])
        files[0].write_bytes(b'y'*100002)
        self.assertEqual(reconcile(3,records,files)['missing_video_episodes'],[1,3])

    def test_duplicate_episode_does_not_count_as_verified(self):
        a=self.folder/'剧-第001集.mp4'; a.write_bytes(b'x'*100001)
        b=self.folder/'副本-第001集.mp4'; b.write_bytes(a.read_bytes())
        record={'file':str(a),'status':'ok','link':'share','verified':True,'confirmation_source':'parser',**fingerprint(a)}
        result=reconcile(1,{'1':record},[a,b])
        self.assertFalse(result['complete'])
        self.assertEqual(result['duplicate_video_episodes'],[1])

    def test_original_list_prefers_current_download_directory(self):
        from server.v2_file_service import scan_downloaded_drama_files
        current=self.folder/'原片/剧场/剧'
        legacy=self.folder/'旧目录'
        current.mkdir(parents=True); legacy.mkdir()
        for n in (1,2):
            (current/f'剧-第{n:03d}集.mp4').write_bytes(b'x'*100001)
        (legacy/'剧-第001集.mp4').write_bytes(b'x'*100001)
        (current/'剧-第003集.mp4.part').write_bytes(b'x'*100001)
        result=scan_downloaded_drama_files(self.folder/'原片','剧场','剧',str(legacy))
        self.assertEqual(result['downloaded_folder_path'],str(current))
        self.assertEqual(result['downloaded_episode_numbers'],[1,2])

    def test_results_update_counts_and_persist_per_episode(self):
        reader._STATE.update(journal_path=str(self.folder/'task.json'), expected_count=2)
        row={'episode':1,'expected_episode':1,'link':'share','status':'ok','file':'fixture.mp4','verified':True,'confirmation_source':'parser'}
        reader._consume_progress('EPISODE_RESULT='+json.dumps(row))
        self.assertEqual(reader._STATE['parsed_episodes'],[1])
        self.assertEqual(reader._STATE['verified_count'],1)
        self.assertTrue(json.loads((self.folder/'task.json').read_text())['episodes']['1']['verified'])

    def test_unhandled_failure_has_terminal_state(self):
        def failure(_):
            raise OSError('共享盘断开')
        reader._start('parse-download',failure)
        reader._THREAD.join(3)
        self.assertFalse(reader._THREAD.is_alive())
        self.assertEqual(reader._STATE['status'],'failed')
        self.assertIn('共享盘断开',reader._STATE['error'])

    def test_queue_processes_two_tasks_and_stops_when_empty(self):
        names=iter(['甲','乙',None]); calls=[]
        def read(**_):
            name=next(names)
            if name:
                reader._STATE.update(status='succeeded',task={'drama_name':name,'task_label':'#'+name,'chat_name':'任务群'})
                calls.append('read'+name)
            else:
                reader._STATE.update(status='failed',error='第一条置顶聊天中没有 #剧名')
        def prepare():
            reader._STATE.update(expected_count=1,episodes={'1':{'link':'share'}},missing_link_episodes=[])
        def step(name):
            def run(*_):
                calls.append(name+reader._STATE['task']['drama_name'])
                reader._STATE.update(status='succeeded')
                if name=='download':
                    reader._STATE['episodes']['1']['verified']=True
                    reader._STATE['parse_failed_episodes']=[]
                if name=='verify':
                    reader._STATE.update(complete=True,verified_count=1)
            return run
        with patch.object(reader,'_read_worker',read),patch.object(reader,'_prepare_task',prepare),patch.object(reader,'_collect_worker',step('collect')),patch.object(reader,'_download_worker',step('download')),patch.object(reader,'_verify_worker',step('verify')),patch.object(reader,'_delete_worker',step('delete')):
            reader._pipeline_worker()
        self.assertEqual(calls,['read甲','collect甲','download甲','verify甲','delete甲','read乙','collect乙','download乙','verify乙','delete乙'])
        self.assertEqual(len(reader._STATE['completed_tasks']),2)

    def test_parse_mismatch_reaches_repair_even_when_download_failed(self):
        calls=[]
        def read(**_):
            reader._STATE.update(status='succeeded',task={'drama_name':'甲','task_label':'#甲','chat_name':'任务群'})
        def prepare():
            reader._STATE.update(expected_count=1,episodes={'1':{'link':'share'}},missing_link_episodes=[])
        def collect(payload):
            calls.append(('collect',payload.get('repair_episodes')))
            reader._STATE['status']='succeeded'
        def download(payload):
            calls.append(('download',payload.get('episodes')))
            if payload.get('episodes'):
                reader._STATE.update(status='succeeded',parse_failed_episodes=[])
                reader._STATE['episodes']['1']['verified']=True
            else:
                reader._STATE.update(status='failed',parse_failed_episodes=[1])
        def verify():
            reader._STATE.update(status='succeeded',complete=True,expected_count=1)
        with patch.object(reader,'_read_worker',read),patch.object(reader,'_prepare_task',prepare),patch.object(reader,'_collect_worker',collect),patch.object(reader,'_download_worker',download),patch.object(reader,'_verify_worker',verify),patch.object(reader,'_delete_worker',lambda: reader._STATE.update(status='succeeded')):
            reader._pipeline_worker({'task_limit':1})
        self.assertEqual(calls,[('collect',None),('download',None),('collect',[1]),('download',[1])])

    def test_collector_only_repairs_requested_contiguous_ranges(self):
        nav=types.ModuleType('导航'); view=types.ModuleType('视图'); clip=types.ModuleType('读剪贴板历史')
        clip.newest_share=lambda:''
        with patch.dict(sys.modules,{'导航':nav,'视图':view,'读剪贴板历史':clip}):
            collector=load('阶段1_收集链接.py','collector_regression')
        nav.episode_sheet_open=lambda:True; nav.read_total_episodes=lambda:10
        taps=[]; slides=[]
        nav.tap_episode=lambda n:(taps.append(n) or True)
        nav.swipe_next_episode=lambda:slides.append(True)
        nav.wait_for_drama_banner=lambda **_:True; nav.pause_video=lambda:None
        table=self.folder/'links.txt'
        table.write_text(''.join(f'剧\t第{n}集\thttp://old/{n}\n' for n in range(1,11)),encoding='utf-8')
        with patch.object(collector,'ensure_recording_ime',lambda:True),patch.object(collector,'grab_one',lambda _,episode:f'http://new/{episode}'),patch.object(sys,'argv',['collector','--no-nav','--drama','剧','--table',str(table),'--repair','2,3,7']),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collector.main(),0)
        self.assertEqual(taps,[2,7]); self.assertEqual(len(slides),1)
        self.assertIn('第4集\thttp://old/4',table.read_text(encoding='utf-8'))
        before=table.read_bytes()
        nav.tap_episode=lambda _:False
        with patch.object(collector,'ensure_recording_ime',lambda:True),patch.object(sys,'argv',['collector','--no-nav','--drama','剧','--table',str(table),'--repair','2']),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError): collector.main()
        self.assertEqual(table.read_bytes(),before)

    def test_banner_unknown_is_not_expected_episode(self):
        view=types.ModuleType('视图')
        with patch.dict(sys.modules,{'视图':view}): nav=load('导航.py','nav_regression')
        ticks=iter([0,0,2])
        with patch.object(nav,'_banner_items',lambda **_:[{'text':'免费剧集','x':100,'y':2300}]),patch.object(nav.time,'time',lambda:next(ticks)),patch.object(nav.time,'sleep',lambda _:None):
            self.assertIsNone(nav.wait_for_drama_banner(expected_episode=11,timeout=1))
        self.assertEqual(nav._banner_episodes([{'text':'免费剧集','y':2300},{'text':'第11集','y':2305}]),[11])
        self.assertEqual(nav._banner_episodes([{'text':'免费剧集','y':2300},{'text':'第99集','y':2150}]),[])

    def test_verify_unknown_total_does_not_complete_or_delete(self):
        reader._STATE.update(task={'drama_name':'剧'}, expected_count=0, episodes={})
        with patch.object(reader,'_context',lambda:('剧','剧场',self.folder)):
            reader._verify_worker()
        self.assertEqual(reader._STATE['status'],'failed')
        self.assertFalse(reader._STATE['complete'])
        self.assertIn('总集数',reader._STATE['error'])

    def test_wrong_chat_never_deletes_messages(self):
        with patch('shutil.which',return_value='fixture-adb'):
            task_reader=load('wechat_task_reader.py','chat_regression')
        with patch.object(task_reader,'restart_main_wechat',lambda:None),patch.object(task_reader,'screenshot',lambda:object()),patch.object(task_reader,'first_pinned_chat',lambda _:'其他聊天'),patch.object(task_reader,'delete_message_at') as delete:
            with self.assertRaises(RuntimeError): task_reader.delete_current_task('#剧','任务群')
        delete.assert_not_called()

    def test_cleanup_requires_both_card_and_label_confirmation(self):
        with patch('shutil.which',return_value='fixture-adb'):
            module=load('wechat_task_reader.py','cleanup_regression')
        tag={'text':'#剧','x':600,'y':1800}
        task={'task_label':'#剧','card_position':{'x':700,'y':2000}}
        calls=[]
        with patch.object(module,'restart_main_wechat',lambda:None),patch.object(module,'screenshot',lambda:object()),patch.object(module,'first_pinned_chat',lambda _:'任务群'),patch.object(module,'ocr',side_effect=[[tag],[tag],[tag],[],[]]),patch.object(module,'main_wechat_chat',return_value=True),patch.object(module,'card_areas',return_value=[]),patch.object(module.time,'sleep',lambda _:None),patch.object(module,'read_task_from_image',return_value=task),patch.object(module,'delete_message_at',lambda x,y:(calls.append((x,y)) or True)),contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(module.delete_current_task('#剧','任务群'))
        self.assertEqual(calls,[(700,2000),(600,1800)])
        with patch.object(module,'restart_main_wechat',lambda:None),patch.object(module,'screenshot',lambda:object()),patch.object(module,'first_pinned_chat',lambda _:'任务群'),patch.object(module,'ocr',return_value=[tag]),patch.object(module,'read_task_from_image',side_effect=RuntimeError('无卡片')),patch.object(module,'delete_message_at') as delete:
            with self.assertRaises(RuntimeError): module.delete_current_task('#剧','任务群')
        delete.assert_not_called()

    def test_cleanup_does_not_treat_missing_ocr_as_card_deleted(self):
        with patch('shutil.which',return_value='fixture-adb'):
            module=load('wechat_task_reader.py','cleanup_ocr_regression')
        tag={'text':'#剧','x':600,'y':1800}
        task={'task_label':'#剧','card_position':{'x':700,'y':2000}}
        with patch.object(module,'restart_main_wechat',lambda:None),patch.object(module,'screenshot',lambda:object()),patch.object(module,'first_pinned_chat',lambda _:'任务群'),patch.object(module,'main_wechat_chat',return_value=True),patch.object(module,'ocr',side_effect=[[tag],[]]),patch.object(module,'read_task_from_image',return_value=task),patch.object(module,'delete_message_at',return_value=True) as delete:
            with self.assertRaisesRegex(RuntimeError,'未重新确认'):
                module.delete_current_task('#剧','任务群')
        self.assertEqual(delete.call_args_list,[((700,2000),)])

    def test_cleanup_preserves_label_when_card_region_remains(self):
        with patch('shutil.which',return_value='fixture-adb'):
            module=load('wechat_task_reader.py','cleanup_card_regression')
        tag={'text':'#剧','x':600,'y':1800}
        task={'task_label':'#剧','card_position':{'x':700,'y':2000}}
        with patch.object(module,'restart_main_wechat',lambda:None),patch.object(module,'screenshot',lambda:object()),patch.object(module,'first_pinned_chat',lambda _:'任务群'),patch.object(module,'main_wechat_chat',return_value=True),patch.object(module,'ocr',return_value=[tag]),patch.object(module,'card_areas',return_value=[{'top':1900}]),patch.object(module,'read_task_from_image',return_value=task),patch.object(module,'delete_message_at',return_value=True) as delete:
            with self.assertRaisesRegex(RuntimeError,'卡片删除结果尚未确认'):
                module.delete_current_task('#剧','任务群')
        self.assertEqual(delete.call_args_list,[((700,2000),)])

    def test_first_pinned_identity_comes_from_chat_header_not_date(self):
        with patch('shutil.which',return_value='fixture-adb'):
            module=load('wechat_task_reader.py','chat_header_regression')
        rows=[{'text':'昨天','x':1110,'y':285},{'text':'MichaelHe','x':340,'y':300}]
        with patch.object(module,'ocr',side_effect=[rows,[{'text':'MichaelHe','x':614,'y':180}]]),patch.object(module,'screenshot',return_value=object()),patch.object(module,'tap') as tap:
            self.assertEqual(module.first_pinned_chat(object()),'MichaelHe')
        tap.assert_called_once_with(340,300)

    def test_cleanup_inspection_can_recover_date_alias_but_not_other_chat(self):
        with patch('shutil.which',return_value='fixture-adb'):
            module=load('wechat_task_reader.py','cleanup_inspection_regression')
        with patch.object(module,'restart_main_wechat'),patch.object(module,'screenshot',return_value=object()),patch.object(module,'first_pinned_chat',return_value='MichaelHe'),patch.object(module,'ocr',return_value=[{'text':'#剧','y':1800}]),patch.object(module,'card_areas',return_value=[]),patch.object(module,'delete_message_at') as delete:
            result=module.inspect_cleanup_task('#剧','昨天')
            self.assertEqual(result,{'chat_name':'MichaelHe','task_label':'#剧','label_only':True})
            with self.assertRaisesRegex(RuntimeError,'不一致'):module.inspect_cleanup_task('#剧','别的聊天')
        delete.assert_not_called()

    def test_cleanup_retry_uses_inspection_and_preserves_video_success(self):
        reader._STATE.update(task={'task_label':'#剧','chat_name':'昨天'},complete=True,cleanup_pending=True,stage_states={'verify-download':'done'})
        commands=[]
        def run(command,consume):
            commands.append(command)
            if '--inspect-cleanup' in command:
                return 0,['CLEANUP_INSPECTION='+json.dumps({'chat_name':'MichaelHe','task_label':'#剧','label_only':True})]
            consume('TASK_JSON='+json.dumps({'error':'标签尚未删除'}))
            return 1,[]
        with patch.object(reader,'_run',run):reader._delete_worker()
        self.assertIn('--resume-label-only',commands[-1])
        self.assertIn('MichaelHe',commands[-1])
        self.assertEqual(reader._STATE['phase'],'cleanup-task')
        self.assertEqual(reader._STATE['cleanup_state'],'failed')
        self.assertEqual(reader._STATE['stage_states']['verify-download'],'done')
        self.assertTrue(reader._STATE['complete'])

    def test_old_failed_cleanup_snapshot_has_no_running_or_failed_video_stage(self):
        reader._STATE.update(status='failed',phase='verify-download',complete=True,cleanup_pending=True,stage_states={'read-task':'running','verify-download':'failed'},stage_logs={'verify-download':['视频通过','清理停止：聊天未确认']})
        result=reader.status()
        self.assertEqual(result['phase'],'cleanup-task')
        self.assertEqual(set(result['stage_states'].values()),{'done'})
        self.assertEqual(result['cleanup_error'],'聊天未确认')
        self.assertEqual(result['stage_logs']['verify-download'],['视频通过'])
        self.assertEqual(reader._STATE['stage_states']['read-task'],'running')

    def test_terminal_state_never_leaves_stage_running(self):
        reader._STATE.update(stage_states={'read-task':'running','collect-links':'running'})
        reader._set(status='failed',phase='collect-links')
        self.assertNotIn('running',reader._STATE['stage_states'].values())

    def test_cleanup_retry_preserves_other_visible_tasks(self):
        reader._STATE.update(task={'task_label':'#乙'},cleanup_pending=True,tasks=[{'task_label':'#甲'},{'task_label':'#乙'}],current_task_index=1)
        captured=[]
        def worker(_):
            captured.extend(reader._STATE['tasks'])
            reader._set(status='succeeded',phase='completed')
        reader._start('read-task',worker)
        reader._THREAD.join(3)
        self.assertEqual([row['task_label'] for row in captured],['#甲','#乙'])

    def test_last_incomplete_task_does_not_fall_back_to_previous(self):
        with patch('shutil.which',return_value='fixture-adb'):
            module=load('wechat_task_reader.py','pairing_regression')
        tags=[{'text':'#甲','x':500,'y':1000},{'text':'#乙','x':500,'y':2000}]
        cards=[{'x':600,'y':1500,'top':1100,'bottom':1900}]
        with patch.object(module,'ocr',return_value=tags),patch.object(module,'card_areas',return_value=cards):
            with self.assertRaises(RuntimeError): module.read_task_from_image(types.SimpleNamespace(height=2600),'任务群')


class DownloadIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.base=Path(cls.tmp.name)
        cls.video=cls.base/'fixture.mp4'
        subprocess.run([str(resolve_ffmpeg()),'-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=25','-t','2','-c:v','libx264','-preset','ultrafast','-crf','15',str(cls.video)],check=True,timeout=30,capture_output=True)
        cls.payload=cls.video.read_bytes(); assert len(cls.payload)>100000
        cls.calls=0
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                cls.calls+=1
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                ep=int(request['baseurl'].rsplit('/',1)[-1])
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps({'code':1,'data':{'title':f'剧第{ep}集','url':f'http://127.0.0.1:{cls.http.server_port}/video'}}).encode())
            def do_GET(self):
                self.send_response(200); self.send_header('Content-Length',str(len(cls.payload)+(10000 if self.path=='/short' else 0))); self.end_headers(); self.wfile.write(cls.payload)
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True); cls.thread.start()
        cls.downloader=load('批量解析下载.py','downloader_regression')
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.tmp.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.folder=Path(self.tmp.name)

    def test_real_video_download_resume_and_no_second_parse(self):
        table=self.folder/'links.txt'; table.write_text('剧\t第1集\thttp://share/1\n',encoding='utf-8')
        journal=self.folder/'task.json'; journal.write_text('{"episodes":{}}')
        argv=['downloader','--table',str(table),'--drama','剧','--theater','剧场','--output-root',str(self.folder),'--result-path',str(self.folder/'results.jsonl'),'--log-path',str(self.folder/'download.log'),'--resume-records',str(journal)]
        cfg={'uid':'fixture','agentid':0,'analysis_api':f'http://127.0.0.1:{self.http.server_port}/parse','request_interval_seconds':0}
        out=io.StringIO()
        with patch.object(sys,'argv',argv),patch.object(self.downloader,'load_config',lambda:cfg),contextlib.redirect_stdout(out):
            self.assertEqual(self.downloader.main(),0)
        target=self.folder/'剧场/剧/剧-第001集.mp4'
        self.assertEqual(target.read_bytes(),self.payload)
        self.assertGreater(probe_video(target)['duration'],0)
        row=json.loads((self.folder/'results.jsonl').read_text(encoding='utf-8').splitlines()[-1])
        journal.write_text(json.dumps({'episodes':{'1':row}}),encoding='utf-8')
        before=type(self).calls
        with patch.object(sys,'argv',argv),patch.object(self.downloader,'load_config',lambda:cfg),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.downloader.main(),0)
        self.assertEqual(type(self).calls,before)
        self.assertFalse(target.with_name(target.name+'.part').exists())

    def test_truncated_response_leaves_no_formal_video(self):
        target=self.folder/'broken.mp4'
        with self.assertRaises(Exception): self.downloader.download(f'http://127.0.0.1:{self.http.server_port}/short',target,3)
        self.assertFalse(target.exists())
        self.assertTrue(target.with_name(target.name+'.part').exists())

    def test_existing_successful_file_is_preserved(self):
        target=self.folder/'old.mp4'; target.write_bytes(b'original video')
        with self.assertRaises(self.downloader.EpisodeFailure):
            self.downloader.download(f'http://127.0.0.1:{self.http.server_port}/video',target,3,validate=probe_video)
        self.assertEqual(target.read_bytes(),b'original video')

    def test_owned_corrupt_download_is_backed_up_before_repair(self):
        target=self.folder/'corrupt.mp4'; target.write_bytes(b'broken-original')
        self.downloader.download(f'http://127.0.0.1:{self.http.server_port}/video',target,3,validate=probe_video,replace_invalid=True)
        self.assertEqual(target.read_bytes(),self.payload)
        backups=list(self.folder.glob('corrupt.mp4.before-repair-*'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),b'broken-original')

    def test_v3_worker_persists_real_results_and_resumes(self):
        table=self.folder/'采集表.txt'; table.write_text('剧\t第1集\thttp://share/1\n',encoding='utf-8')
        previous=dict(reader._STATE)
        old=reader._run
        wrapper=self.folder/'wrapper.py'
        cfg={'uid':'fixture','agentid':0,'analysis_api':f'http://127.0.0.1:{self.http.server_port}/parse','request_interval_seconds':0}
        wrapper.write_text(f"import importlib.util\nspec=importlib.util.spec_from_file_location('downloader', {str(LAB/'批量解析下载.py')!r})\nm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\nm.load_config=lambda:{cfg!r}\nraise SystemExit(m.main())\n",encoding='utf-8')
        def run(command,on_line):
            index=next(i for i,arg in enumerate(command) if arg.endswith('批量解析下载.py'))
            command=command[:index]+[str(wrapper)]+command[index+1:]
            return old(command,on_line)
        try:
            reader._STATE.clear();reader._STATE.update(task={'drama_name':'剧'},status='running')
            with patch.dict(os.environ,{'V3_DRAMA_READ_TASK_STATE':str(self.folder/'state.json')}),patch.object(reader,'_context',lambda:('剧','剧场',self.folder)),patch.object(reader,'_expected_episode_count',lambda _:1),patch.object(reader,'_run',run):
                reader._prepare_task()
                reader._download_worker()
                self.assertEqual(reader._STATE['status'],'succeeded')
                self.assertEqual(reader._STATE['verified_count'],1)
                reader._verify_worker()
                self.assertTrue(reader._STATE['complete'])
                count=type(self).calls
                reader._download_worker()
                self.assertEqual(type(self).calls,count)
                stored=json.loads(Path(reader._STATE['journal_path']).read_text(encoding='utf-8'))
                self.assertEqual(stored['episodes']['1']['confirmation_source'],'parser')
        finally:
            reader._STATE.clear(); reader._STATE.update(previous)


if __name__=='__main__':
    unittest.main(verbosity=2)
