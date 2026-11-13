"""Isolated V3 UI/API fixture server. No scheduler and no production database."""
import json
import os
import base64
import shutil
import sys
import threading
import time
import uuid
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import v2_file_service as files

OUT=Path(os.environ.get('V3_PUBLISH_PROBE_OUTPUT') or (ROOT/'local-test-output'/'v3-publishing-20261026'))
OUT.mkdir(parents=True,exist_ok=True)
if '--resume-isolated' in sys.argv:
    info=json.loads((OUT/'isolated-current.json').read_text(encoding='utf-8'))
    LIVE=Path(info['root'])
    files.WORKSPACE=LIVE/'workspace';files.DATA_ROOT=LIVE/'system';files.DATABASE_INITIALIZED_PATH=None
    files.connection().close()
    server=ThreadingHTTPServer(('127.0.0.1',0),files.Handler)
    info['url']=f'http://127.0.0.1:{server.server_port}'
    (OUT/'isolated-current.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=True),flush=True)
    server.serve_forever()
    sys.exit(0)
LIVE=OUT/('isolated-'+time.strftime('%H%M%S'))
LIVE.mkdir(parents=True)
files.WORKSPACE=LIVE/'workspace';files.DATA_ROOT=LIVE/'system';files.DATABASE_INITIALIZED_PATH=None
theater=files.create_theater({'name':'发布隔离验证剧场'})
account=files.create_account({'nickname':'一只羊13652','channel_id':'sph9U0V11Fhwl8x','theater_id':theater['id']})
drama=files.create_drama({'current_name':'生恩如纸，养恩如山','history_names':['生恩如纸 养恩如山'],'theater_id':theater['id']})
task=files.create_task({'source_id':'isolated-publishing','account_name':account['nickname'],'drama_name':drama['current_name'],'planned_publish_at':''})
media=Path(r'D:\ShortDramaVideoCollector\experiments\vcat_20261026')
videos=[]
with closing(files.connection()) as conn:
    sources=[('probe-normal-1.mp4','生恩如纸养恩如山-1.mp4'),('羊-probe-2.mp4','羊-生恩如纸养恩如山-2.mp4')]
    if '--production-progress-fixture' in sys.argv:sources=[sources[0],('probe-normal-1.mp4','生恩如纸养恩如山-2.mp4'),('羊-probe-2.mp4','羊-生恩如纸养恩如山-3.mp4')]
    for index,(source,name) in enumerate(sources,1):
        final=Path(task['paths']['finals'])/name;shutil.copy2(media/source,final)
        material=Path(task['paths']['materials'])/name;shutil.copy2(media/source,material)
        file_id=uuid.uuid4().hex;video_id=uuid.uuid4().hex;stamp=files.now_text()
        conn.execute('''INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds,resolution)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(file_id,task['id'],'original_material',name,name,str(material),'fixture','fixture',material.stat().st_size,index,'available',stamp,stamp,2,'360x640'))
        conn.execute('INSERT INTO production_video_tasks(id,task_id,source_material_id,status,output_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(video_id,task['id'],file_id,'ffmpeg_done',str(final),stamp,stamp))
        videos.append(video_id)
    conn.commit()
if '--with-two-covers' in sys.argv:
    from server.cover_editor import CoverStore
    cover_store=CoverStore(files.WORKSPACE,files.connection)
    for kind,filename in [('drama','probe-cover.png'),('sheep','probe-cover-sheep.png')]:
        cover_store.replace_original(drama['id'],{'filename':filename,'content_base64':base64.b64encode((media/filename).read_bytes()).decode()},kind)
if '--legacy-publish-group' in sys.argv:
    from server.publishing.service import PublishingService
    service=PublishingService(files.connection,files.get_task_details)
    setting=service.load(task['id'])['settings'];group=setting['groups'][0]
    group.update(name='分组 1',kind='custom',copies=3)
    setting.update(groups=[group],assignment_mode='manual')
    service.write('settings',task['id'],setting)
address_fixture={}
if '--mount-source-fixture' in sys.argv:
    from server.publishing.service import PublishingService
    from server.tests.test_publishing import FakeCat
    mini={'id':'fixture-mini-selected','name':drama['current_name'],'usable':True,'mediaCount':104,'miniAppName':'测试短剧小程序','questFlag':{'fixture':1}}
    video={'id':'fixture-channel-selected','name':drama['current_name'],'usable':True,'mediaCount':104}
    with closing(files.connection()) as conn:
        conn.execute('INSERT INTO v3_catalog_task_mounts VALUES(?,?,?,?)',(task['id'],'mini_drama',mini['id'],json.dumps(mini,ensure_ascii=False)));conn.commit()
    class MountCat(FakeCat):
        calls=[];drafts={};next_id=1;publications=[]
        def accounts(self):return [{'uid':account['channel_id'],'platform':'Channels','loginStatus':'登录有效'}]
        def worker(self,uid,method,params):
            if method!='getDramaComponent':return super().worker(uid,method,params)
            self.calls.append((method,params))
            return {'list':[(video if params.get('sceneType')==3 else mini)],'totalCount':1,'baseResp':{'errcode':0}}
        def call(self,name,args):
            if '--publication-fixture' in sys.argv:
                if name=='vcat_create_publish_task':
                    row={**args,'localId':'fixture-publish-'+uuid.uuid4().hex,'batchSource':args['batchName'],'status':'success'}
                    self.publications.append(row);return {'localId':row['localId']}
                if name=='vcat_list_publish_tasks':
                    if '--production-progress-fixture' in sys.argv:
                        control=OUT/'progress-control.json'
                        statuses=json.loads(control.read_text(encoding='utf-8')).get('statuses',[]) if control.exists() else [2,2,1,0,0,0,3,3,3]
                        for index,row in enumerate(self.publications):row['statusCode']=str(statuses[index] if index<len(statuses) else 2)
                    rows=[r for r in self.publications if r['uid']==args['uid'] and r['batchSource']==args['batchSource']]
                    return {'list':rows,'total':len(rows)}
            return super().call(name,args)
    PublishingService.__init__.__defaults__=(MountCat,None)
    if '--production-progress-fixture' in sys.argv:
        from server.publishing.publisher import batch_name
        service=PublishingService(files.connection,files.get_task_details)
        setting=service.load(task['id'])['settings'];setting['schedule']={'schedule_type':'timing','start_time':'2026-10-30 20:00','interval':3};setting['sync_location']=False
        for group in setting['groups']:
            sheep=group['kind']=='sheep'
            group.update(copies=3,mount_required=not sheep,location={'name':'羊组测试地址' if sheep else '丹景山观景台','fullAddress':'四川省成都市测试地址','poiCheckSum':'fixture-b' if sheep else 'fixture-a','_searchQuery':{'query':'fixture'}})
        service.write('settings',task['id'],setting)
        ctx=service.load(task['id']);ctx['binding']={'source':'mini_drama','drama':mini}
        records=[]
        for index,item in enumerate(service.expanded(ctx)):
            payload=service.payload(ctx,item);identity='fixture-publish-'+str(index);batch=batch_name(task['id'],item['key'])
            record={'key':item['key'],'video_id':item['video']['id'],'name':item['video']['name'],'group_name':item['group']['name'],'copy':item['copy'],'time':item['time'],'status':'submitted','uid':account['channel_id'],'batch_name':batch,'local_id':identity,'payload':payload}
            records.append(record);MountCat.publications.append({**payload,'localId':identity,'batchSource':batch,'statusCode':'0'})
        service.write('publish_execution',task['id'],{'items':records,'state':'submitted','started_at':'2026-10-26T20:00:00+08:00'})
if '--address-book-fixture' in sys.argv:
    other_account=files.create_account({'nickname':'地址库测试账号B','channel_id':'fixture-only-uid-b','theater_id':theater['id']})
    other_task=files.create_task({'source_id':'isolated-address-book-b','account_name':other_account['nickname'],'drama_name':drama['current_name'],'planned_publish_at':''})
    address_fixture={'other_task_id':other_task['id']}
if '--planned-date-fixture' in sys.argv:
    files.create_drama({'current_name':'日期新建验证剧','theater_id':theater['id']})
    with closing(files.connection()) as conn:
        conn.execute("UPDATE production_tasks SET planned_publish_at='2026-10-26T08:00' WHERE id=?",(task['id'],))
        conn.execute("UPDATE production_video_tasks SET started_at='2026-10-26T08:00:00',finished_at='2026-10-26T08:02:05' WHERE id=?",(videos[0],))
        conn.commit()
# Do not call create_v2_server: it starts background production/cleanup schedulers.
server=ThreadingHTTPServer(('127.0.0.1',0),files.Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
info={'url':f'http://127.0.0.1:{server.server_port}','task_id':task['id'],'drama_id':drama['id'],'account_id':account['id'],'root':str(LIVE),'video_ids':videos,**address_fixture}
(OUT/'isolated-current.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(info,ensure_ascii=True),flush=True)
try:
    while not (LIVE/'STOP').exists():time.sleep(.2)
finally:
    server.shutdown();server.server_close()
