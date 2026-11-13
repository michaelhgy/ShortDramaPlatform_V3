"""Isolated production-card UI fixture, never starts production schedulers."""
import json
import sys
import time
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server import v2_file_service as files
out=ROOT/'local-test-output/production-order-20261026';out.mkdir(exist_ok=True)
run=out/('isolated-'+time.strftime('%H%M%S'));run.mkdir()
files.WORKSPACE=run/'workspace';files.DATA_ROOT=run/'system';files.DATABASE_INITIALIZED_PATH=None
theater=files.create_theater({'name':'卡片排序验收剧场'})
tasks=[]
for index,(name,day) in enumerate([('山海工作室','2026-10-11'),('微光剧场号','2026-10-27'),('清风影像','2026-10-28')]):
    files.create_account({'nickname':name,'channel_id':f'order-fixture-{index}','theater_id':theater['id']})
    drama=files.create_drama({'current_name':['生恩如纸，养恩如山','一口铁锅走天下','我在武侠世界抽卡成神'][index],'theater_id':theater['id']})
    tasks.append(files.create_task({'source_id':f'order-fixture-{index}','account_name':name,'drama_name':drama['current_name'],'planned_publish_at':day}))
server=ThreadingHTTPServer(('127.0.0.1',0),files.Handler)
info={'url':f'http://127.0.0.1:{server.server_port}','tasks':[t['id'] for t in tasks],'root':str(run)}
(out/'current.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(info),flush=True)
try:server.serve_forever()
finally:server.server_close()
