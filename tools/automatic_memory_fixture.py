"""Isolated process restart fixture. No business data or startup schedulers."""
import json
import sys
import time
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server import v2_file_service as files
out=ROOT/'local-test-output/auto-composition-memory-20261026';out.mkdir(parents=True,exist_ok=True)
resume='--resume-isolated' in sys.argv
previous=json.loads((out/'current.json').read_text(encoding='utf-8')) if resume else None
run=Path(previous['root']) if resume else out/('isolated-'+time.strftime('%H%M%S'))
run.mkdir(exist_ok=True)
files.WORKSPACE=run/'workspace';files.DATA_ROOT=run/'system';files.DATABASE_INITIALIZED_PATH=None
ids=previous['tasks'] if resume else []
if not resume:
    theater=files.create_theater({'name':'开关记忆隔离剧场'})
    for i,name in enumerate(['山海工作室','微光剧场号','清风影像']):
        files.create_account({'nickname':name,'channel_id':f'automatic-memory-{i}','theater_id':theater['id']})
        drama=files.create_drama({'current_name':f'开关记忆测试剧{i+1}','theater_id':theater['id']})
        task=files.create_task({'source_id':f'automatic-memory-{i}','account_name':name,'drama_name':drama['current_name'],'planned_publish_at':f'2026-10-{27+i}'})
        ids.append(task['id'])
server=ThreadingHTTPServer(('127.0.0.1',0),files.Handler)
info={'url':f'http://127.0.0.1:{server.server_port}','tasks':ids,'root':str(run)}
(out/'current.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
stop=out/'STOP'
if stop.exists():stop.unlink()
threading.Thread(target=server.serve_forever,daemon=True).start()
print(json.dumps(info),flush=True)
try:
    while not stop.exists():time.sleep(.1)
finally:server.shutdown();server.server_close()
