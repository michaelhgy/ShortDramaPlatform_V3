"""Compact production-area projection; never create or resume external tasks."""
import json
from contextlib import closing
from .delivery import delivery_confirmation, confirm_saved_deliveries


def project(state,kind):
    items=[]
    for record in state.get('items',[]):
        payload=record.get('accepted_payload') or record.get('payload') or {}
        options=payload.get('platformOptions') or {}
        mount=options.get('CAT_extReading') or {}
        component=(mount.get('_mergeObjectDesc') or {}).get('component') or {}
        location=options.get('CAT_location') or {}
        parts=record.get('key','').split(':')
        video_id=record.get('video_id') or (parts[-2] if len(parts)>=3 else '')
        submitted=bool(record.get('local_id') if kind=='publication' else record.get('draft_id'))
        items.append({'key':record.get('key',''),'video_id':video_id,'name':record.get('name',''),
            'group_name':record.get('group_name',''),'copy':record.get('copy',1),'time':record.get('time',''),
            'status':record.get('status','pending'),'error':record.get('error',''),
            'delivery_confirmed':kind=='publication' and record.get('status')=='success' and bool(delivery_confirmation(record) or record.get('delivery_confirmed')),
            'submitted':submitted,'local_id':record.get('local_id'),'draft_id':record.get('draft_id'),
            'schedule_type':payload.get('scheduleType',''),
            'submitted_at':record.get('submitted_at') or state.get('started_at',''),
            'mount':{'enabled':bool(component.get('id') or mount.get('drama',{}).get('id')),
                'source':'channels_drama' if mount.get('type')==8 else 'mini_drama' if mount.get('type')==5 else record.get('mount_source',''),
                'name':(mount.get('drama') or {}).get('name','')},
            'location':{'name':location.get('name',''),'full_address':location.get('fullAddress') or location.get('address','')}})
    return {'state':state.get('state','idle'),'running':state.get('running',False),'mode':state.get('mode'),
        'error':state.get('error',''),'items':items}


def progress(service,task_id):
    native=service.publication(task_id);error=''
    if native['items'] and not native['running']:
        try:native=service.refresh_publication(task_id)
        except (RuntimeError,ValueError,OSError) as exc:error=str(exc)[:400]
    drafts=service.execution(task_id)
    projected=project(native,'publication');draft_projected=project(drafts,'draft')
    active={'pending','submitting','submitted','publishing','localTiming','creating','checking'}
    needs_poll=bool(native['running'] or drafts['running'] or any(r['status'] in active for r in projected['items']))
    return {'task_id':task_id,'publication':projected,'drafts':draft_projected,'needs_poll':needs_poll,'refresh_error':error}


def card_summary(native,drafts):
    videos={}
    for kind,state in [('draft',drafts),('publication',native)]:
        groups={}
        for row in project(state,kind)['items']:
            if row['video_id']:groups.setdefault(row['video_id'],[]).append(row)
        for vid,items in groups.items():
            previous=videos.get(vid)
            if not previous or max((r['submitted_at'] for r in items),default='')>=max((r['submitted_at'] for r in previous[1]),default=''):
                videos[vid]=(kind,items)
    rows=[r for kind,items in videos.values() for r in items]
    if not any(r['submitted'] for r in rows):return None
    return {'total':len(rows),'done':sum(r['status'] in ('success','ready') for r in rows),
        'delivered':sum(bool(r.get('delivery_confirmed')) for r in rows),
        'processing':sum(r['status'] in ('submitting','publishing','creating','checking') for r in rows),
        'queued':sum(r['status'] in ('pending','submitted','localTiming') for r in rows),
        'paused':sum(r['status']=='paused' for r in rows),
        'issues':sum(r['status'] in ('uncertain','needs_help','failed','rejected','canceled') for r in rows),
        'draft_only':all(kind=='draft' for kind,items in videos.values()),'scheduled':all(r['schedule_type']=='timing' for r in rows)}


def progress_index(service):
    confirm_saved_deliveries(service.connection)
    states={}
    with closing(service.connection()) as conn:
        for row in conn.execute("SELECT kind,key,content FROM v3_publish_documents WHERE kind IN ('publish_execution','execution')"):
            states.setdefault(row['key'],{})[row['kind']]=json.loads(row['content'])
    result={}
    for task,values in states.items():
        summary=card_summary(values.get('publish_execution',{}),values.get('execution',{}))
        if summary:result[task]=summary
    return {'items':result}
