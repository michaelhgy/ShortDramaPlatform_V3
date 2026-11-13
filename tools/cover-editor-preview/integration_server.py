"""Full built UI/API fixture with an isolated database; no production schedulers or publishing."""
import json
import shutil
import sys
import time
import uuid
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from server import v2_file_service as files

out=ROOT/'local-test-output/cover-integration-20261026';out.mkdir(parents=True,exist_ok=True)
run=out/('isolated-'+time.strftime('%H%M%S'));run.mkdir()
if '--flower-library-test' in sys.argv:
    import server.flower_library as flower_module
    original_library=flower_module.FlowerLibrary
    class IsolatedFlowerLibrary(original_library):
        def __init__(self,*args,**kwargs):
            kwargs['machine_path']=run/'flower-machine.json'
            super().__init__(*args,**kwargs)
    flower_module.FlowerLibrary=IsolatedFlowerLibrary
files.WORKSPACE=run/'workspace';files.DATA_ROOT=run/'system';files.DATABASE_INITIALIZED_PATH=None
theater=files.create_theater({'name':'封面隔离验收剧场'})
account=files.create_account({'nickname':'封面隔离账号','channel_id':'fixture-cover-ui','theater_id':theater['id']})
drama=files.create_drama({'current_name':'一口铁锅走天下','theater_id':theater['id']})
other=files.create_drama({'current_name':'模板套用测试剧','theater_id':theater['id']})
task=files.create_task({'source_id':'cover-isolated','account_name':account['nickname'],'drama_name':drama['current_name'],'planned_publish_at':'2026-10-27T15:00'})
second=files.create_task({'source_id':'cover-isolated-other','account_name':account['nickname'],'drama_name':other['current_name'],'planned_publish_at':'2026-10-27T16:00'})
videos=[]
with closing(files.connection()) as conn:
    for index,name in enumerate(['一口铁锅走天下-1.mp4','羊-一口铁锅走天下-2.mp4'],1):
        target=Path(task['paths']['finals'])/name
        source=Path(r'D:\ShortDramaVideoCollector\experiments\vcat_20261026')/('probe-normal-1.mp4' if index==1 else '羊-probe-2.mp4')
        if source.is_file():shutil.copyfile(source,target)
        else:target.write_bytes(b'isolated-cover-path-fixture')
        material=Path(task['paths']['materials'])/name;shutil.copyfile(target,material)
        fid=uuid.uuid4().hex;vid=uuid.uuid4().hex;stamp=files.now_text()
        conn.execute('''INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds,resolution)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(fid,task['id'],'original_material',name,name,str(material),'fixture','fixture',material.stat().st_size,index,'available',stamp,stamp,2,'360x640'))
        conn.execute('INSERT INTO production_video_tasks(id,task_id,source_material_id,status,output_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(vid,task['id'],fid,'ffmpeg_done',str(target),stamp,stamp));videos.append(vid)
    conn.commit()
server=ThreadingHTTPServer(('127.0.0.1',0),files.Handler)
info={'url':f'http://127.0.0.1:{server.server_port}','task_id':task['id'],'second_task_id':second['id'],'drama_id':drama['id'],'second_drama_id':other['id'],'account_id':account['id'],'root':str(run),'videos':videos}
(out/'current.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(info,ensure_ascii=True),flush=True)
try:server.serve_forever()
finally:server.server_close()
