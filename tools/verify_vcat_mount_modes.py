"""Verify both native mount payloads via isolated LOCAL drafts; never publish."""
import hashlib
import json
import sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.publishing.vcat import VcatClient,DraftOutcomeUnknown

STAMP=datetime.now(timezone(timedelta(hours=8))).strftime('%H%M%S')
OUT=ROOT/'local-test-output'/'vcat-mount-modes-20261026'/('run-'+STAMP)
OUT.mkdir(parents=True,exist_ok=False)
VIDEO=Path(r'D:/ShortDramaVideoCollector/experiments/vcat_20261026/probe-normal-1.mp4')
UID='sph9U0V11Fhwl8x'
MODES=[('miniapp',5,{},4),('channels',8,{'sceneType':3},8)]

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def all_drafts(client):
    rows=[]
    for page in range(1,101):
        r=client.call('vcat_list_drafts',{'page':page,'pageSize':100});rows.extend(r.get('list',[]))
        if len(rows)>=r['total']:return rows
    raise RuntimeError('Draft list incomplete')

assert VIDEO.is_file()
video_before=hashlib.sha256(VIDEO.read_bytes()).hexdigest()
results=[]
with VcatClient(writable=True) as client:
    assert any(a['uid']==UID and a.get('loginStatus')=='登录有效' for a in client.accounts())
    old=all_drafts(client)
    old_hashes={str(d['draftId']):digest(client.call('vcat_list_drafts',{'draftId':d['draftId']})) for d in old}
    task_before=client.call('vcat_list_publish_tasks',{'page':1,'pageSize':100})
    before_modules=client.setting.get('writeModules',{}).copy()
    save('baseline.json',{'draft_hashes':old_hashes,'publish_task_hash':digest(task_before),'publish_task_total':task_before['total'],'write_modules':before_modules,'video_sha256':video_before})
    for mode,outer,query,inner in MODES:
        first=client.worker(UID,'getDramaComponent',{**query,'page':1})
        assert first.get('baseResp',{}).get('errcode',0)==0,first.get('baseResp')
        candidate=next(d for d in first['list'] if d.get('usable'))
        lookup=client.worker(UID,'getDramaComponent',{**query,'page':1,'queryString':candidate['name']})
        matched=next(d for d in lookup['list'] if d.get('id')==candidate['id'] and d.get('usable'))
        component={'id':matched['id'],'type':inner}
        if mode=='channels':component['title']=matched['name']
        mount={'type':outer,'drama':matched,'_mergeObjectDesc':{'component':component}}
        if mode=='miniapp':mount['urlType']=12
        title=f'V3挂载参数核验-{mode}-{STAMP}'
        payload={'draftTitle':title,'uid':UID,'videoPath':str(VIDEO),'title':f'仅本地草稿参数核验：{mode}',
            'desc':'仅用于核对挂载参数，不发布。','scheduleType':'now','autoReset':False,
            'platformOptions':{'CAT_extReading':mount,'tagInfo':{'tagType':0},'postFlag':0}}
        save(mode+'-request.json',{'query':query,'total':first['totalCount'],'lookup_count':lookup['totalCount'],'payload':payload})
        assert client.find_draft(title) is None
        try:created=client.call('vcat_create_draft',payload)
        except DraftOutcomeUnknown:
            created=client.find_draft(title)
            if not created:raise
        identity=created.get('draftId') or created.get('id')
        assert identity
        expected={'uid':UID,'outer_type':outer,'inner_type':inner,'id':matched['id'],'name':matched['name']}
        reads=[]
        for _ in range(2):
            draft=client.call('vcat_list_drafts',{'draftId':identity})
            actual=draft['platformOptionsByUid'][UID]['CAT_extReading']
            assert actual==mount,(actual,mount)
            assert draft['content']['videoPath']==str(VIDEO)
            assert [a['uid'] for a in draft['accounts']]==[UID]
            reads.append(draft)
        save(mode+'-readback.json',{'expected':expected,'draft_id':identity,'reads':reads})
        result={**expected,'draft_id':identity,'query_total':first['totalCount'],'search_count':lookup['totalCount'],
            'miniapp_name':matched.get('miniAppName'),'media_count':matched.get('mediaCount'),'two_reads_equal':reads[0]==reads[1],'full_mount_equal':True}
        results.append(result)
        save('progress.json',results)
        print(json.dumps(result,ensure_ascii=False),flush=True)
with VcatClient() as client:
    old_after={key:digest(client.call('vcat_list_drafts',{'draftId':int(key)})) for key in old_hashes}
    drafts=all_drafts(client);tasks=client.call('vcat_list_publish_tasks',{'page':1,'pageSize':100})
    preservation={'old_drafts_unchanged':old_hashes==old_after,'only_two_new_drafts':{d['draftId'] for d in drafts}-{int(k) for k in old_hashes}=={r['draft_id'] for r in results},
        'publish_tasks_unchanged':digest(task_before)==digest(tasks),'publish_task_total':tasks['total'],
        'write_modules_restored':before_modules==client.setting.get('writeModules',{}),'video_unchanged':hashlib.sha256(VIDEO.read_bytes()).hexdigest()==video_before}
    save('result.json',{'results':results,'preservation':preservation,'real_publish_executed':False,'production_database_written':False})
    assert all(preservation[k] for k in ('old_drafts_unchanged','only_two_new_drafts','publish_tasks_unchanged','write_modules_restored','video_unchanged')),preservation
    print(json.dumps({'output':str(OUT),'preservation':preservation},ensure_ascii=False))
