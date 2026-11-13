"""Exercise the frozen V3 publishing/cover/catalogue APIs in a fresh isolated workspace.

Only FakeCat is used: this probe cannot connect to Xiao V Cat or publish real video.
No production/background scheduler is started.
"""
import argparse,base64,copy,io,json,os,subprocess,sys,threading,time,traceback,uuid
from contextlib import closing
from pathlib import Path
from http.server import ThreadingHTTPServer

if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class FakeCat:
    calls=[];tasks=[];drafts={}
    def __init__(self,*a,**kw):pass
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def accounts(self):return [{'uid':'release-fixture-uid','platform':'Channels','nickname':'发布验收账号','loginStatus':'登录有效'}]
    def worker(self,uid,method,params):
        assert uid=='release-fixture-uid' and method=='getDramaComponent'
        return {'list':[{'id':'event/release-fixture','name':'发布验收剧集','usable':True,'mediaCount':10}],'totalCount':1,'baseResp':{'errcode':0}}
    def find_draft(self,title):return next(({'draftId':k} for k,v in self.drafts.items() if v['title']==title),None)
    def call(self,name,args):
        self.calls.append(name);assert args.get('uid','release-fixture-uid')=='release-fixture-uid'
        if name=='vcat_create_publish_task':
            row={**copy.deepcopy(args),'localId':'fixture-'+uuid.uuid4().hex,'batchSource':args['batchName']+'_fixture','statusCode':'2'}
            self.tasks.append(row);return {'batchSource':row['batchSource'],'tasks':[{'localId':row['localId']}]}
        if name=='vcat_list_publish_tasks':
            rows=[r for r in self.tasks if r['batchSource'].startswith(args['batchSource'])]
            return {'list':copy.deepcopy(rows),'total':len(rows)}
        if name=='vcat_create_draft':
            from datetime import datetime,timezone,timedelta
            key=len(self.drafts)+1;opts={**copy.deepcopy(args['platformOptions']),'CAT_desc':args.get('desc',''),'topics':args.get('tags',[]),
                'CAT_timing':{'type':{'now':1,'timing':2,'localTiming':3}[args['scheduleType']]}}
            if args.get('cover'):opts['CAT_cover']=args['cover']
            if args.get('scheduleTime'):opts['CAT_timing'].update(time=datetime.strptime(args['scheduleTime'],'%Y-%m-%d %H:%M').replace(tzinfo=timezone(timedelta(hours=8))).isoformat(),autoReset=False)
            self.drafts[key]={'title':args['draftTitle'],'accounts':[{'uid':args['uid']}],'content':{'videoPath':args['videoPath']},'platformOptionsByUid':{args['uid']:opts}}
            return {'draftId':key}
        if name=='vcat_list_drafts':return copy.deepcopy(self.drafts[args['draftId']])
        raise AssertionError('Unexpected tool '+name)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    os.environ['V2_WORKSPACE_ROOT']=str(root/'workspace')
    result={'status':'RUNNING','real_mcp':False,'real_publication':False};http=None
    def save():(root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    try:
        from PIL import Image
        from server import v2_file_service as files
        from server.cover_editor import CoverStore
        from server.publishing.service import PublishingService
        from server.tool_resolver import resolve_ffmpeg
        from server.runtime_process import no_window_kwargs
        theater=files.create_theater({'name':'发布验收剧场'})
        account=files.create_account({'nickname':'发布验收账号','channel_id':'release-fixture-uid','theater_id':theater['id']})
        drama=files.create_drama({'current_name':'发布验收剧集','theater_id':theater['id']})
        task=files.create_task({'source_id':'release-fixture','account_name':account['nickname'],'drama_name':drama['current_name'],'planned_publish_at':'2030-01-01'})
        ids=[]
        for i,name in enumerate(['发布验收剧集-1.mp4','羊-发布验收剧集-2.mp4'],1):
            video=Path(task['paths']['finals'])/name
            subprocess.run([str(resolve_ffmpeg()),'-v','error','-n','-f','lavfi','-i','color=c=navy:s=360x640:r=30:d=2','-c:v','libx264','-preset','ultrafast',str(video)],check=True,**no_window_kwargs())
            stamp=files.now_text();fid=uuid.uuid4().hex;vid=uuid.uuid4().hex;ids.append(vid)
            with closing(files.connection()) as c:
                c.execute('INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds,resolution) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fid,task['id'],'original_material',name,name,str(video),'fixture','fixture',video.stat().st_size,i,'available',stamp,stamp,2,'360x640'))
                c.execute('INSERT INTO production_video_tasks(id,task_id,source_material_id,status,output_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(vid,task['id'],fid,'ffmpeg_done',str(video),stamp,stamp));c.commit()
        store=CoverStore(files.WORKSPACE,files.connection)
        for kind,color in [('drama','navy'),('sheep','purple')]:
            b=io.BytesIO();Image.new('RGB',(180,320),color).save(b,format='PNG')
            store.replace_original(drama['id'],{'filename':kind+'.png','content_base64':base64.b64encode(b.getvalue()).decode()},kind)
        PublishingService.__init__.__defaults__=(FakeCat,None)
        service=PublishingService(files.connection,files.get_task_details,FakeCat,store.cover_info)
        settings=service.load(task['id'])['settings'];settings['mount_source']='channels_drama'
        for g in settings['groups']:g.update(copies=2,mount_required=g['kind']=='normal')
        service.save(task['id'],settings)
        def wait(kind):
            for _ in range(500):
                state=service.execution(task['id'],kind)
                if not state['running']:return state
                time.sleep(.02)
            raise RuntimeError('Fixture worker did not stop')
        service.publish(task['id']);published=wait('publish');assert len(FakeCat.tasks)==4 and all(r['status']=='success' for r in published['items'])
        native=service.progress(task['id']);assert len(native['publication']['items'])==4
        assert {r['video_id']for r in native['publication']['items']}==set(ids)
        service.publish(task['id']);wait('publish');assert len(FakeCat.tasks)==4
        for r in FakeCat.tasks:r['statusCode']='3'
        paused=service.progress(task['id']);assert all(r['status']=='paused' for r in paused['publication']['items']) and not paused['needs_poll']
        settings=service.load(task['id'])['settings'];settings['mount_source']='plugin';service.save(task['id'],settings)
        service.publish(task['id']);draft=wait('draft');assert len(FakeCat.drafts)==4 and all(r['status']=='ready' for r in draft['items']) and len(FakeCat.tasks)==4
        assert all('CAT_extReading' not in r['platformOptionsByUid']['release-fixture-uid'] for r in FakeCat.drafts.values())
        http=ThreadingHTTPServer(('127.0.0.1',0),files.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
        import urllib.request
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));base=f'http://127.0.0.1:{http.server_port}'
        for route in [f'/api/v2/publishing/tasks/{task["id"]}/progress','/api/v2/publishing/progress-index','/cover-editor.html']:
            with opener.open(base+route,timeout=20) as response:assert response.status==200
        result.update(status='PASS',native_entries=4,draft_entries=4,duplicate_submit_protected=True,paused_tasks_preserved=True,
            cover_store=True,progress_http=True,frontend_cover_editor=True,workspace=str(files.WORKSPACE),fake_calls=FakeCat.calls)
    except Exception:result.update(status='FAIL',error=traceback.format_exc());raise
    finally:
        if http:http.shutdown();http.server_close()
        save()


if __name__=='__main__':main()
