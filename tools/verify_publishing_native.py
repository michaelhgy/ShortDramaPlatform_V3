"""Verify declaration payloads through an isolated V3 server and real LOCAL drafts."""
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.publishing.vcat import VcatClient
from server.publishing.declarations import REGIONS

OUT=ROOT/'local-test-output/v3-publishing-compat-20261026'
info=json.loads((OUT/'isolated-current.json').read_text(encoding='utf-8'))
assert Path(info['root']).is_relative_to(OUT)
base=info['url']+'/api/v2/publishing/tasks/'+info['task_id']
def api(action='',data=None):
    url=base+('/'+action if action else '')
    request=urllib.request.Request(url,data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=150) as response:return json.load(response)

ctx=api();settings=ctx['settings']
settings['schedule']={'schedule_type':'timing','start_time':(datetime.now()+timedelta(days=1)).strftime('%Y-%m-%d')+' 15:00','interval':7}
country=next(r for r in REGIONS if r['name']=='中国')
province=next(r for r in country['sub'] if r['name']=='四川')
city=next(r for r in province['sub'] if r['name']=='成都')
for group in settings['groups']:
    group.update(copies=1,title='测试草稿参数核验',desc='声明参数对照验证，仅本地草稿。',tags=['短剧','测试'])
    if group['kind']=='normal':group.update(tag_type=7,repost_source='隔离测试来源，仅核对字段')
    else:group.update(tag_type=5,shoot_date='2026-01-01',shoot_region_codes=[country['code'],province['code'],city['code']])
api('settings',settings)
assert api('check',{})['ok']
api('drafts',{})
deadline=time.monotonic()+120
while time.monotonic()<deadline:
    state=api('execution')
    if not state['running'] and state['items']:break
    time.sleep(.2)
(OUT/'native-draft-execution.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
assert state['state']=='ready',state
assert len(state['items'])==2
assert all(all(item['checks'].values()) for item in state['items'])
# Retry only reads those same drafts: no duplicate local drafts.
api('drafts',{})
deadline=time.monotonic()+120
while time.monotonic()<deadline:
    retry=api('execution')
    if not retry['running'] and retry['items']:break
    time.sleep(.2)
assert [item['draft_id'] for item in retry['items']]==[item['draft_id'] for item in state['items']]
before=json.loads((OUT/'vcat-before.json').read_text(encoding='utf-8'))
with VcatClient() as client:
    hashes={key:hashlib.sha256(json.dumps(client.call('vcat_list_drafts',{'draftId':int(key)}),sort_keys=True,ensure_ascii=False).encode()).hexdigest() for key in before['hashes']}
    tasks=client.call('vcat_list_publish_tasks',{'page':1,'pageSize':100})
    modules=client.bridge('McpServer.getSetting')['writeModules']
    total=client.call('vcat_list_drafts',{'page':1,'pageSize':100})['total']
result={'old_draft_count':len(hashes),'old_drafts_unchanged':hashes==before['hashes'],'tasks_unchanged':tasks==before['tasks'],'publish_tasks':tasks['total'],'write_modules_restored':modules==before['writeModules'],
    'new_drafts':[{'id':item['draft_id'],'time':item['time'],'tagInfo':item['payload']['platformOptions']['tagInfo'],'checks':item['checks']} for item in state['items']],
    'no_duplicates_on_retry':total==len(hashes)+2}
(OUT/'vcat-preservation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(result[key] for key in ('old_drafts_unchanged','tasks_unchanged','write_modules_restored','no_duplicates_on_retry'))
print(json.dumps(result,ensure_ascii=True))
