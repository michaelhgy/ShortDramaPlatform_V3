"""Human-authorized, exact-task live test. Prepare, submit one, verify, then continue."""
import hashlib
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server import v2_file_service as files
from server.cover_editor import CoverStore
from server.publishing.service import PublishingService,fingerprint
from server.publishing.vcat import VcatClient

TASK='485f702c37914467917fbc2e53bbd6f6';UID='sph9U0V11Fhwl8x';NAME='一觉醒来，我被拐到了境外'
OUT=ROOT/'local-test-output/v3-real-publishing-20261026/live-485f702c';OUT.mkdir(parents=True,exist_ok=True)
service=PublishingService(files.connection,files.get_task_details,cover_resolver=CoverStore(files.WORKSPACE,files.connection).cover_info)
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def checked_context():
    ctx=service.load(TASK)
    assert ctx['account']['uid']==UID and ctx['account']['nickname']=='一只羊13652' and ctx['drama']['name']==NAME
    assert ctx['mount_source']=='mini_drama' and len(service.expanded(ctx))==9
    assert ctx['settings']['schedule']=={'schedule_type':'timing','start_time':'2026-10-28 20:00','interval':3}
    assert sum(len(g['video_ids'])*g['copies'] for g in ctx['settings']['groups'] if g['mount_required'])==6
    return ctx
def wait_local():
    for _ in range(600):
        state=service.publication(TASK)
        if not state['running']:return state
        time.sleep(.2)
    raise RuntimeError('Local submission still running; inspect before continuing')

mode=sys.argv[1]
if mode=='prepare':
    ctx=checked_context();check=service.check(TASK);assert check['ok'],check
    ctx=checked_context();items=service.expanded(ctx);payloads=[service.payload(ctx,i) for i in items]
    assert payloads[0]['scheduleTime']=='2026-10-28 20:00' and payloads[-1]['scheduleTime']=='2026-10-28 20:24'
    manifest={'task_id':TASK,'uid':UID,'settings_hash':fingerprint(ctx['settings']),'payloads':payloads,'settings':ctx['settings'],'files':{v['path']:{'size':Path(v['path']).stat().st_size,'mtime':Path(v['path']).stat().st_mtime_ns} for v in ctx['videos']}}
    if (OUT/'manifest.json').exists():assert json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))['settings_hash']==manifest['settings_hash']
    else:
        save('manifest.json',manifest)
        with closing(files.connection()) as c,closing(sqlite3.connect(OUT/'before-business.sqlite3')) as backup:c.backup(backup)
        with VcatClient() as client:
            drafts=client.call('vcat_list_drafts',{'page':1,'pageSize':100});assert len(drafts['list'])==drafts['total']
            hashes={str(d['draftId']):fingerprint(client.call('vcat_list_drafts',{'draftId':d['draftId']})) for d in drafts['list']}
            save('baseline.json',{'draft_hashes':hashes,'publish_tasks':client.call('vcat_list_publish_tasks',{'page':1,'pageSize':100}),'write_modules':client.setting.get('writeModules',{})})
    print(json.dumps({'prepared':len(payloads),'times':[p['scheduleTime'] for p in payloads],'mount_count':sum('CAT_extReading' in p['platformOptions'] for p in payloads),'output':str(OUT)},ensure_ascii=False))
elif mode in ('first','continue'):
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'));ctx=checked_context();assert fingerprint(ctx['settings'])==manifest['settings_hash'],'Configuration changed since preflight'
    if mode=='continue':
        current=service.refresh_publication(TASK);assert current['items'] and current['items'][0]['status']=='success',current
    service.publish(TASK,limit=1 if mode=='first' else None);state=wait_local();save('submission-'+mode+'.json',state)
    print(json.dumps({'state':state['state'],'records':[{'status':r['status'],'local_id':r.get('local_id'),'time':r['time'],'error':r.get('error')} for r in state['items']]},ensure_ascii=False))
elif mode=='read':
    state=service.refresh_publication(TASK);save('latest-state.json',state)
    with VcatClient() as client:
        queue=client.call('vcat_list_publish_tasks',{'uid':UID,'page':1,'pageSize':100});save('latest-queue.json',queue)
    print(json.dumps({'state':state['state'],'records':[{'status':r['status'],'local_id':r.get('local_id'),'time':r['time'],'error':r.get('error'),'checks':r.get('checks')} for r in state['items'] if r['status']!='pending'],'queue':[{'localId':r.get('localId'),'status':r.get('status'),'timing':r.get('timing'),'batchSource':r.get('batchSource'),'error':r.get('_source',{}).get('error')} for r in queue.get('list',[])]},ensure_ascii=False))
elif mode=='preserve':
    baseline=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'));manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    with VcatClient() as client:
        unchanged=all(fingerprint(client.call('vcat_list_drafts',{'draftId':int(k)}))==v for k,v in baseline['draft_hashes'].items())
        result={'original_drafts_unchanged':unchanged,'write_modules_restored':baseline['write_modules']==client.setting.get('writeModules',{}),'files_unchanged':all(Path(p).stat().st_size==v['size'] and Path(p).stat().st_mtime_ns==v['mtime'] for p,v in manifest['files'].items()),'settings_unchanged':fingerprint(checked_context()['settings'])==manifest['settings_hash']}
    save('preservation.json',result);assert all(result.values()),result;print(json.dumps(result))
else:raise ValueError('Use prepare, first, read, continue or preserve')
