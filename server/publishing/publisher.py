"""Real publication queue submission, separate from local draft execution."""
import copy
import hashlib
import time
from datetime import datetime,timedelta
from .vcat import PublishOutcomeUnknown,PublishRejected


def batch_name(task_id,key):return 'V3Pub_'+task_id[:10]+'_'+hashlib.sha256(key.encode()).hexdigest()[:12]


def lookup_batch(record):return record.get('remote_batch') or record.get('submission',{}).get('batchSource') or record['batch_name']


def find_task(client,uid,batch):
    found=[];seen=0
    for page in range(1,101):
        value=client.call('vcat_list_publish_tasks',{'uid':uid,'batchSource':batch,'page':page,'pageSize':100})
        rows=value.get('list',[]);seen+=len(rows)
        for row in rows:
            source=row.get('batchSource') or row.get('batchName') or ''
            if isinstance(source,dict):source=str(source.get('name') or source.get('title') or '')
            if (source==batch or source.startswith(batch+'_')) and row.get('uid',uid)==uid:found.append(row)
        if not rows or seen>=value.get('total',0):break
    if len(found)>1:raise RuntimeError('同一条作品发现多个发布任务，请核对，暂不重复提交')
    return found[0] if found else None


def adopt(record,row):
    status=row.get('statusCode',row.get('status'))
    if isinstance(status,int) or str(status).isdigit():status={0:'waiting',1:'publishing',2:'success',3:'paused',4:'failed',5:'canceled',6:'localTiming'}.get(int(status),str(status))
    status={'待发布':'waiting','正在发布':'publishing','已发布':'success','发布成功':'success','已暂停':'paused','失败':'failed','发布失败':'failed','已取消':'canceled','本机定时等待':'localTiming'}.get(status,status)
    record['remote_state']=status
    record['status']={'waiting':'submitted','publishing':'publishing','success':'success','failed':'failed','canceled':'canceled','paused':'paused','localTiming':'localTiming'}.get(status,'submitted')
    identity=row.get('localId') or row.get('task',{}).get('localId')
    if identity:record['local_id']=str(identity)
    record['remote']=row
    message=row.get('error') or row.get('errorMessage') or row.get('errorMsg') or row.get('_source',{}).get('error') or ''
    if isinstance(message,dict):message=str(message)
    record['error']=str(message) if record['status'] in ('failed','canceled') else ''
    checks=verify_remote(row,record.get('payload'))
    if checks:
        record['checks']=checks
        if not all(checks.values()):record.update(status='needs_help',error='小V猫发布任务的实际参数与配置不一致，请先核对，不重复提交')


def verify_remote(row,payload):
    if not payload or not isinstance(row.get('_source',{}).get('formData'),dict):return {}
    from urllib.parse import unquote
    def path(v):return unquote(str(v or '')).replace('file:///','').replace('file://','').replace('\\','/').casefold()
    form=row['_source']['formData'];uid=payload['uid']
    checks={'account':row.get('uid')==uid,'video':path(row.get('videoPath'))==path(payload['videoPath']),
        'description':form.get('CAT_desc','')==payload.get('desc',''),'topics':form.get('topics',[])==payload.get('tags',[])}
    for key in ('CAT_extReading','CAT_location','CAT_shortTitle','tagInfo','postFlag'):checks[key]=form.get(key)==payload.get('platformOptions',{}).get(key)
    if payload.get('cover'):checks['cover']=path(form.get('CAT_cover'))==path(payload['cover'])
    checks['time_mode']=form.get('CAT_timing',{}).get('type')=={'now':1,'timing':2,'localTiming':3}[payload['scheduleType']]
    if payload.get('scheduleTime'):
        from datetime import datetime
        from .service import SHANGHAI
        expected=payload['scheduleTime']
        # The task list exposes the user-facing local time. Prefer it when
        # present: some Xiao V Cat versions serialize the form time with a
        # different timezone offset even though the queued task is correct.
        listed=[row.get('timing'),row.get('scheduleTime'),row.get('_source',{}).get('timing')]
        listed_ok=any(str(value or '')[:16]==expected for value in listed)
        if listed_ok:
            checks['time']=True
        else:
            try:checks['time']=datetime.fromisoformat(str(form['CAT_timing']['time']).replace('Z','+00:00')).astimezone(SHANGHAI).strftime('%Y-%m-%d %H:%M')==expected
            except (KeyError,ValueError):checks['time']=False
        checks['no_immediate_fallback']=form.get('CAT_timing',{}).get('autoReset') is False
    return checks


def expired_schedule(record):
    payload=record.get('payload') or {}
    schedule_type=payload.get('scheduleType') or ('timing' if record.get('time') else 'now')
    schedule_time=payload.get('scheduleTime') or record.get('time')
    if schedule_type not in ('timing','localTiming') or not schedule_time:
        return False
    from .service import SHANGHAI
    try:
        scheduled=datetime.strptime(str(schedule_time),'%Y-%m-%d %H:%M').replace(tzinfo=SHANGHAI)
    except (TypeError,ValueError):
        return True
    return scheduled<=datetime.now(SHANGHAI)


def account_level_rejection(message):
    value=str(message or '')
    return any(word in value for word in ('扫码','验证','风控','账号','登录','权限','频繁','安全'))


class Publisher:
    def __init__(self,service):self.service=service

    def schedule_plan(self,task_id,keys=None,start_time=None,interval=None):
        service=self.service;self.refresh(task_id);state=service.publication(task_id)
        rows=state.get('items',[])
        if not rows:raise ValueError('当前没有可排期重发的任务记录')
        selectable=[]
        default_retry_states={'failed','paused','canceled','pending','rejected','needs_help','localCanceled','localPaused'}
        for row in rows:
            remote=row.get('remote_state') or row.get('status')
            if row.get('status')=='success' or remote=='success':continue
            if row.get('status') in default_retry_states or remote in default_retry_states:
                selectable.append(row)
        if keys is not None:
            selected={str(key) for key in keys}
            eligible=[row for row in rows if row.get('key') in selected]
        else:eligible=selectable
        if not eligible:raise ValueError('请至少选择一条排期重发任务')
        from .service import SHANGHAI
        now=datetime.now(SHANGHAI).replace(second=0,microsecond=0)
        if start_time:
            try:start=datetime.strptime(str(start_time),'%Y-%m-%d %H:%M').replace(tzinfo=SHANGHAI)
            except ValueError:raise ValueError('排期开始时间格式无效') from None
        else:
            start=now+timedelta(minutes=10)
            start+=timedelta(minutes=(5-start.minute%5)%5)
        if start<=now+timedelta(minutes=5):raise ValueError('排期开始时间至少要晚于北京时间当前时间5分钟')
        parsed=[]
        for row in eligible:
            value=(row.get('payload') or {}).get('scheduleTime') or row.get('time')
            try:parsed.append(datetime.strptime(str(value),'%Y-%m-%d %H:%M'))
            except ValueError:parsed.append(None)
        old_intervals=[(parsed[index]-parsed[index-1]).total_seconds()/60 for index in range(1,len(parsed)) if parsed[index] and parsed[index-1] and parsed[index]>parsed[index-1]]
        try:step=max(0,int(interval)) if interval is not None else int(old_intervals[0] if old_intervals else 5)
        except (TypeError,ValueError):raise ValueError('排期间隔必须是非负整数') from None
        if step>10080:raise ValueError('排期间隔不能超过10080分钟')
        times={}
        for index,row in enumerate(eligible):
            times[row['key']]=(start+timedelta(minutes=index*step)).strftime('%Y-%m-%d %H:%M')
        all_items=[{'key':row['key'],'name':row.get('name',''),'copy':row.get('copy',1),'status':row.get('status'),'remote_state':row.get('remote_state'),'old_time':(row.get('payload') or {}).get('scheduleTime') or row.get('time',''),'new_time':times.get(row['key'],''),'selected':row in eligible} for row in rows]
        return {'keys':[row['key'] for row in eligible],'start_time':start.strftime('%Y-%m-%d %H:%M'),'interval':step,'items':all_items,'times':times}

    def prepare_full_reset(self,task_id):
        service=self.service;state=service.publication(task_id)
        if state['running']:raise ValueError('当前批次正在处理，请先停止后再重新发布')
        state=self.refresh(task_id);ctx=service.context(task_id,include_videos=False)
        plan={'success':[],'cancelled':[],'terminal':[],'pending':[],'blocked':[]}
        with service.client_factory(ctx['settings'].get('port',9222),writable=True,publishing=True) as client:
            for record in state.get('items',[]):
                status=record.get('remote_state') or record.get('status')
                item={'key':record.get('key',''),'name':record.get('name',''),'copy':record.get('copy',1),'status':record.get('status'),'remote_state':record.get('remote_state')}
                if status=='success' or record.get('status')=='success':plan['success'].append(item);continue
                local_id=str(record.get('local_id') or '')
                if not local_id:
                    if record.get('status')=='uncertain':
                        item['reason']='结果待核对，未找到可确认的小V猫任务';plan['blocked'].append(item)
                    else:plan['pending'].append(item)
                    continue
                if status in ('waiting','publishing','localTiming') or record.get('status') in ('submitted','publishing','localTiming'):
                    try:
                        client.call('vcat_cancel_publish_task',{'localId':local_id})
                        record.update(status='canceled',remote_state='canceled',error='重新发布前已取消旧小V猫任务')
                        plan['cancelled'].append({**item,'status':'canceled'})
                    except Exception as exc:
                        item['reason']=f'小V猫拒绝取消：{str(exc)[:300]}';plan['blocked'].append(item)
                    continue
                if status in ('failed','paused','canceled') or record.get('status') in ('failed','paused','canceled'):
                    plan['terminal'].append(item);continue
                item['reason']='旧任务状态无法确认，请先读取小V猫';plan['blocked'].append(item)
        state['reset_status']='blocked' if plan['blocked'] else 'awaiting_manual_cleanup'
        state['reset_plan']=plan;service.write('publish_execution',task_id,state)
        return {**plan,'ready':not bool(plan['blocked']),'state':service.publication(task_id)}

    def confirm_full_reset(self,task_id):
        service=self.service;state=service.publication(task_id)
        if state.get('reset_status')!='awaiting_manual_cleanup':raise ValueError('请先准备重新发布并处理旧批次')
        if state.get('reset_plan',{}).get('blocked'):raise ValueError('旧批次仍有未确认任务，不能进入重新发布')
        from .service import stamp
        state['reset_status']='ready';state['reset_confirmed_at']=stamp();service.write('publish_execution',task_id,state)
        return service.publication(task_id)

    def manage(self,task_id,operation,keys):
        service=self.service;self.refresh(task_id);state=service.publication(task_id)
        selected=[row for row in state.get('items',[]) if row.get('key') in keys]
        if len(selected)!=len(keys): raise ValueError('部分任务已不在当前发布结果中，请先刷新状态')
        ctx=service.context(task_id,include_videos=False)
        changed=[];skipped=[]
        with service.client_factory(ctx['settings'].get('port',9222),writable=True,publishing=True) as client:
            for record in selected:
                local_id=str(record.get('local_id') or '')
                if not local_id:
                    if operation=='pause' and record.get('status') in ('pending','rejected','needs_help'):
                        record.update(status='paused',remote_state='localPaused',error='本条尚未提交到小V猫，已在V3暂停');changed.append(record['key']);continue
                    if operation=='cancel' and record.get('status') in ('pending','rejected','needs_help'):
                        record.update(status='canceled',remote_state='localCanceled',error='本条尚未提交到小V猫，已在V3取消');changed.append(record['key']);continue
                    if operation=='retry' and record.get('status') in ('pending','rejected','needs_help'):
                        skipped.append({'key':record['key'],'reason':'本条尚未提交到小V猫，请使用“继续提交”'});continue
                    skipped.append({'key':record['key'],'reason':'没有小V猫任务ID，当前状态不能执行该操作'});continue
                remote=record.get('remote_state') or record.get('status')
                if operation=='pause':
                    if remote!='waiting':
                        skipped.append({'key':record['key'],'reason':'小V猫只允许暂停“待发布”任务'});continue
                    client.task_action('Models.PublishLog.updateRecordsByIds',{'status':3,'priorityAt':None},[local_id])
                    record.update(status='paused',remote_state='paused',error='')
                elif operation=='cancel':
                    if remote in ('success','published') or record.get('status')=='success':
                        skipped.append({'key':record['key'],'reason':'已完成任务不自动取消'});continue
                    try:
                        client.call('vcat_cancel_publish_task',{'localId':local_id})
                    except Exception as exc:
                        skipped.append({'key':record['key'],'reason':f'小V猫拒绝取消：{str(exc)[:300]}'});continue
                    record.update(status='canceled',remote_state='canceled',error='')
                elif operation=='retry':
                    if remote not in ('paused','failed','canceled') and record.get('status') not in ('paused','failed','canceled'):
                        skipped.append({'key':record['key'],'reason':'只有暂停、失败或已取消任务可以重发'});continue
                    if expired_schedule(record):
                        skipped.append({'key':record['key'],'reason':'原定时发布时间已过，请使用“重新发布”并按当前设置生成新任务'});continue
                    client.call('vcat_set_publish_priority',{'localId':local_id,'priority':True})
                    record.update(status='submitted',remote_state='waiting',error='')
                changed.append(record['key'])
        state['state']='submitted' if operation=='retry' else state.get('state','needs_help')
        service.write('publish_execution',task_id,state)
        refreshed=self.refresh(task_id)
        return {'changed':changed,'skipped':skipped,'state':refreshed}

    def refresh(self,task_id):
        service=self.service;state=service.publication(task_id)
        if state['running'] or not state['items']:return state
        ctx=service.context(task_id,include_videos=False)
        with service.client_factory(ctx['settings'].get('port',9222)) as client:
            for record in state['items']:
                if not record.get('batch_name') or record.get('status') in ('pending','rejected'):continue
                try:
                    row=find_task(client,record.get('uid') or ctx['account']['uid'],lookup_batch(record))
                    if row:adopt(record,row)
                    elif record.get('local_id'):record.update(status='uncertain',error='暂未查到已提交任务，不自动重复提交')
                except Exception as exc:record['error']=str(exc)[:800]
        state.pop('running',None);state.pop('mode',None)
        state['state']='success' if state['items'] and all(r['status']=='success' for r in state['items']) else 'needs_help' if any(r['status'] in ('failed','uncertain','needs_help','rejected','canceled') for r in state['items']) else 'submitted'
        service.write('publish_execution',task_id,state)
        return service.publication(task_id)

    def run(self,task_id,run,limit=None,selected_keys=None,new_attempt=False,reschedule=None,full_reset=False):
        from .service import fingerprint,stamp
        service=self.service;state=service.read('publish_execution',task_id,{'items':[]});old={r.get('replaces_key',r['key']):r for r in state['items']}
        state.update(state='running',error='',started_at=stamp());service.write('publish_execution',task_id,state)
        try:
            ctx=service.load(task_id)
            if ctx['mount_source']=='plugin':raise ValueError('插件方式只能生成本地草稿')
            if service.read('settings',task_id) is None:service.write('settings',task_id,ctx['settings'])
            service.connection_status(task_id)
            if any(g.get('mount_required') and g['video_ids'] for g in ctx['settings']['groups']):
                match=service.dramas(task_id)
                if match['status'] not in ('bound','auto'):raise ValueError(match.get('message') or '请确认挂载剧集')
                ctx['binding']=match['binding']
            items=service.expanded(ctx)
            if not items:raise ValueError('请至少选择一个视频')
            # Preflight the complete batch before any irreversible queue submission.
            # A new publication is intentionally independent of previous result
            # states. It uses current settings and all current expanded videos;
            # old rows are archived for traceability.
            if selected_keys:
                records_by_key={record.get('key'):record for record in state.get('items',[])}
                original_keys={records_by_key.get(key,{}).get('replaces_key') or key for key in selected_keys}
                items=[item for item in items if item['key'] in original_keys]
                if not items:raise ValueError('所选任务对应的视频已不在当前成片列表中')
            # 排期重发必须使用新排期做时间校验。原任务的时间可能已经过期，
            # 但它只作为排序参考，不能在这里再次触发“至少晚于当前 5 分钟”的旧时间校验。
            reschedule_times={}
            if reschedule:
                times=reschedule.get('times') or {}
                for row in state.get('items',[]):
                    base=row.get('replaces_key',row.get('key'))
                    if row.get('key') in times:
                        reschedule_times[base]=times[row['key']]
                    elif base in times:
                        reschedule_times[base]=times[base]
                missing=[item['key'] for item in items if item['key'] not in reschedule_times]
                if missing:raise ValueError('排期重发的任务时间不完整，请重新打开排期重发')
            prepared=[]
            for item in items:
                validation_item=item
                if reschedule:
                    new_time=reschedule_times[item['key']]
                    validation_item={**item,'time':new_time,'group':{**item['group'],'schedule_type':'timing','start_time':new_time}}
                prepared.append((item,service.payload(ctx,validation_item)))
            if reschedule:
                old_payloads={record.get('replaces_key',record.get('key')):record.get('payload') for record in state.get('items',[]) if record.get('payload')}
                adjusted=[]
                for item,payload in prepared:
                    original=old_payloads.get(item['key'])
                    value=copy.deepcopy(original) if original else payload
                    if value.get('scheduleType')=='now':value['scheduleType']='timing'
                    value['scheduleTime']=reschedule_times[item['key']]
                    adjusted.append((item,value))
                prepared=adjusted
            attempt_stamp=stamp().replace(':','').replace('-','').replace('+','')
            records=[]
            archived=[]
            run_records={}
            for item,p in prepared:
                previous=old.get(item['key'])
                key=item['key']
                if new_attempt:
                    if previous:
                        archived_item={**previous,'archived_at':stamp()}
                        if full_reset:archived_item.update(status='abandoned',remote_state='abandoned',error='旧批次已作废，重新发布创建了新批次')
                        archived.append(archived_item)
                    new_key=f"{key}:attempt:{attempt_stamp}"
                    record={'key':new_key,'name':item['video']['name'],'group_id':item['group']['id'],'group_name':item['group']['name'],'copy':item['copy'],'time':reschedule_times.get(key,item['time']) if reschedule else item['time'],'status':'pending','uid':ctx['account']['uid'],'batch_name':batch_name(task_id,new_key),'replaces_key':key,'replaces_local_id':previous.get('local_id') if previous else None}
                    records.append(record);run_records[key]=record
                else:
                    record=previous or {'key':key,'name':item['video']['name'],'group_id':item['group']['id'],'group_name':item['group']['name'],'copy':item['copy'],'time':item['time'],'status':'pending','uid':ctx['account']['uid'],'batch_name':batch_name(task_id,key)}
                    records.append(record);run_records[key]=record
            records.extend(v for k,v in old.items() if k not in run_records)
            state['items']=records
            state['previous_items']=[*state.get('previous_items',[]),*archived]
            if full_reset:
                state.pop('reset_status',None);state.pop('reset_plan',None);state['reset_completed_at']=stamp()
            service.write('publish_execution',task_id,state);created_count=0
            account_blocked=False
            for item,payload in prepared:
                record=run_records[item['key']]
                while run['mode']=='paused':time.sleep(.2)
                if run['mode']=='stopped' or (limit is not None and created_count>=limit):break
                digest=fingerprint(payload)
                if record.get('payload_hash') and record['payload_hash']!=digest and (record.get('local_id') or record['status'] in ('submitting','uncertain')):
                    record.update(status='needs_help',error='参数已变化，原发布任务保留，不自动重复发布');continue
                try:
                    with service.client_factory(ctx['settings']['port'],writable=True,publishing=True) as client:
                        row=find_task(client,ctx['account']['uid'],lookup_batch(record))
                        if row:adopt(record,row);continue
                        if record.get('local_id') or record['status'] in ('submitting','uncertain'):
                            record.update(status='uncertain',error='提交结果待核对，未查询到原任务，不自动重复发布');break
                        validation_group=item['group']
                        if reschedule:
                            validation_group={**validation_group,'schedule_type':'timing','start_time':reschedule_times[item['key']]}
                        service.validate_group(validation_group,strict=False)
                        service.validate_schedule_time(payload.get('scheduleType','now'),payload.get('scheduleTime'))
                        record.update(status='submitting',payload_hash=digest,payload=payload,error='',video_id=item['video']['id'],mount_source=ctx['mount_source'])
                        service.write('publish_execution',task_id,state)
                        result=client.call('vcat_create_publish_task',{**payload,'batchName':record['batch_name'],'start':True})
                        record['submission']=result;record['submitted_at']=stamp();created_count+=1
                        if result.get('batchSource'):record['remote_batch']=result['batchSource']
                        tasks=result.get('tasks') or []
                        identity=result.get('localId') or result.get('task',{}).get('localId') or (tasks[0].get('localId') if len(tasks)==1 else None)
                        if identity:record['local_id']=str(identity)
                        record['status']='submitted'
                        row=find_task(client,ctx['account']['uid'],lookup_batch(record))
                        if row:adopt(record,row)
                        elif not record.get('local_id'):record.update(status='uncertain',error='小V猫未返回可核对的任务编号，请读取发布状态，不要重复提交')
                except PublishOutcomeUnknown as exc:record.update(status='uncertain',error=str(exc))
                except PublishRejected as exc:
                    record.update(status='rejected',error=str(exc)[:800]);account_blocked=account_level_rejection(exc)
                except Exception as exc:
                    record.update(status='uncertain' if record.get('status')=='submitting' and not isinstance(exc,ValueError) else 'rejected',error=str(exc)[:800])
                finally:service.write('publish_execution',task_id,state)
                # A known rejection, remote failure, or parameter mismatch is
                # isolated to this item. Only an unknown submission result
                # must stop the batch, otherwise later videos would remain
                # pending even though they were never sent to Xiao V Cat.
                if record['status']=='uncertain' or account_blocked:break
            state['state']='stopped' if run['mode']=='stopped' else 'needs_help' if any(r['status'] in ('uncertain','rejected','failed','needs_help') for r in state['items']) else 'submitted'
        except Exception as exc:state.update(state='needs_help',error=str(exc)[:800])
        finally:service.write('publish_execution',task_id,state)
