"""Persistent preparation, native publication and resumable plugin local drafts."""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import uuid
from contextlib import closing
from datetime import datetime,timedelta,timezone
from pathlib import Path

from .matching import normalized_name,search_terms,rank_candidates
from .planning import prepare_settings,schedule_groups
from .declarations import tag_info,SHORT_TITLE,REGIONS
from .vcat import VcatClient,DraftRejected,DraftOutcomeUnknown
from .profiles import PublishProfiles,effective_group
from .mounting import task_mount,resolve_source,validate_source,binding_key,component

RUN_LOCK=threading.RLock()
RUNS={}
SHANGHAI=timezone(timedelta(hours=8))


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS v3_publish_documents (
        kind TEXT NOT NULL, key TEXT NOT NULL, content TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(kind,key))''')
    from server.operations_collection import initialize as initialize_operations
    initialize_operations(conn)


def stamp():return datetime.now(SHANGHAI).isoformat(timespec='seconds')
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class PublishingService:
    def __init__(self,connection,details,client_factory=VcatClient,cover_resolver=None,cover_root=None):
        self.connection=connection;self.details=details;self.client_factory=client_factory;self.cover_resolver=cover_resolver;self.cover_root=cover_root

    def covers(self):
        from .covers import PublishCoverStore
        if self.cover_root is not None:return PublishCoverStore(self.cover_root)
        with closing(self.connection()) as conn:
            database=Path(conn.execute('PRAGMA database_list').fetchone()[2])
        # Production DB lives in workspace/database; isolated DBs stay in their temp root.
        parent=database.parent
        return PublishCoverStore((parent.parent if parent.name=='database' else parent)/'发布封面')

    def import_cover(self,task_id,payload):
        self.context(task_id,include_videos=False)
        return self.covers().import_image(payload.get('data_url',''))

    def read(self,kind,key,default=None):
        with closing(self.connection()) as conn:
            row=conn.execute('SELECT content FROM v3_publish_documents WHERE kind=? AND key=?',(kind,key)).fetchone()
            return json.loads(row[0]) if row else default

    def write(self,kind,key,value):
        with closing(self.connection()) as conn:
            conn.execute('INSERT INTO v3_publish_documents VALUES(?,?,?,?) ON CONFLICT(kind,key) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at',
                (kind,key,json.dumps(value,ensure_ascii=False),stamp()))
            if kind == 'publish_execution':
                from server.operations_collection import record_executions
                record_executions(conn, [(key, item) for item in [*value.get('previous_items', []), *value.get('items', [])] if item.get('uid') and item.get('key')])
            conn.commit()

    def context(self,task_id,include_videos=True):
        saved=self.read('settings',task_id,{})
        with closing(self.connection()) as conn:
            task=conn.execute('SELECT * FROM production_tasks WHERE id=?',(task_id,)).fetchone()
            if not task:raise ValueError('制作任务不存在')
            mount=task_mount(conn,task_id);source=resolve_source(saved,mount)
            account=conn.execute('SELECT * FROM accounts WHERE id=?',(saved.get('account_id',''),)).fetchone() if saved.get('account_id') else None
            if not account:account=conn.execute('SELECT * FROM accounts WHERE nickname=?',(task['account_name'],)).fetchone()
            if not account:raise ValueError('请先在业务资料中补齐当前账号及平台ID')
            drama=conn.execute('SELECT * FROM dramas WHERE id=? AND theater_id=?',(saved.get('drama_id',''),account['theater_id'])).fetchone() if saved.get('drama_id') else None
            if not drama:
                rows=conn.execute('''SELECT * FROM dramas d WHERE d.theater_id=? AND (d.current_name=? OR EXISTS
                    (SELECT 1 FROM drama_aliases a WHERE a.drama_id=d.id AND a.alias_name=?))''',(account['theater_id'],task['drama_name'],task['drama_name'])).fetchall()
                if len(rows)!=1:raise ValueError('制作任务未能唯一对应剧集档案，请核对当前剧名和历史剧名')
                drama=rows[0]
            aliases=[r[0] for r in conn.execute('SELECT alias_name FROM drama_aliases WHERE drama_id=?',(drama['id'],))]
            profile=conn.execute('SELECT cover_path,updated_at FROM drama_profiles WHERE drama_id=?',(drama['id'],)).fetchone()
            theater=conn.execute('SELECT name FROM theaters WHERE id=?',(drama['theater_id'],)).fetchone()
        detail=self.details(task_id) if include_videos else {}
        videos=[]
        for v in detail.get('videos',[]):
            path=str(v.get('output_path') or '')
            if not path:continue
            videos.append({'id':v['id'],'name':Path(path).name,'path':path,'exists':Path(path).is_file(),
                'duration':v.get('output_duration_seconds') or v.get('source_duration_seconds') or 0,
                'sheep':any(str(n).startswith(('羊-','羊_','羊 ')) or str(n).strip()=='羊' for n in (Path(path).name,v.get('name',''),v.get('original_name',''))),'sequence':v.get('sequence_no') or 0})
        videos.sort(key=lambda v:(v['sequence'],v['name']))
        cover=str(profile['cover_path'] or '') if profile else ''
        legacy_cover={'path':cover,'exists':bool(cover and Path(cover).is_file()),'url':f"/api/v2/dramas/{drama['id']}/cover?v={Path(cover).stat().st_mtime_ns}" if cover and Path(cover).is_file() else ''}
        cover_info=self.cover_resolver(drama['id']) if self.cover_resolver else {'cover':legacy_cover,'sheep_cover':legacy_cover,'sheep_cover_visible':False}
        return {'task_id':task_id,'account':{'id':account['id'],'nickname':account['nickname'],'uid':account['channel_id']},
            'drama':{'id':drama['id'],'name':drama['current_name'],'history_names':aliases,'theater_id':drama['theater_id'],'theater_name':theater[0] if theater else ''},
            **cover_info,
            'videos':videos,'planned_time':str(task['planned_publish_at'] or '')[:10],'settings':saved,
            'mount_source':source,'task_mount_source':mount.get('source',''),'task_mount':mount}

    def load(self,task_id):
        ctx=self.context(task_id);uid=ctx['account']['uid'];drama_id=ctx['drama']['id']
        saved=ctx['settings']
        initial={**(ctx['settings'] or {'account_id':ctx['account']['id'],'drama_id':drama_id,'port':9222,'groups':[]}),'mount_source':ctx['mount_source']}
        ctx['settings']=prepare_settings(initial,ctx['videos'],self.read('address_default',uid))
        ctx['binding']=self.mount_binding(ctx)
        ctx['addresses']=self.read('addresses',uid,[])
        ctx['public_addresses']=self.public_addresses()
        ctx['default_address']=self.read('address_default',uid)
        ctx['history']=self.histories()
        ctx['execution']=self.execution(task_id)
        ctx['publication']=self.publication(task_id)
        ctx['shoot_regions']=REGIONS
        profiles=PublishProfiles(self)
        if not saved:
            default=profiles.default(uid)
            if default:
                try:ctx['settings']=profiles.apply(ctx['settings'],default,ctx)['settings']
                except ValueError as exc:
                    import copy
                    safe=copy.deepcopy(default);safe['config']['location']={**safe['config']['location'],'mode':'none','checksum':''}
                    ctx['settings']=profiles.apply(ctx['settings'],safe,ctx)['settings']
                    ctx['settings']['profile_ref']['problem']=str(exc)+'；请在默认配置中修正并重新应用方案'
        else:ctx['settings']=profiles.restore_new_groups(ctx['settings'],saved)
        ctx['settings']=prepare_settings(ctx['settings'],ctx['videos'],ctx['default_address'])
        ctx['profile_library']=profiles.public(uid)
        ctx['profile_state']=profiles.state(ctx['settings'])
        return ctx

    def mount_binding(self,ctx):
        source=ctx['mount_source'];uid=ctx['account']['uid'];drama_id=ctx['drama']['id']
        if source=='plugin':return None
        local=self.read('task_binding',ctx['task_id']+':'+source)
        if local and local.get('account_uid')==uid:return local
        selected=ctx['task_mount'];snapshot=selected.get('snapshot') or {}
        if selected.get('source')==source and selected.get('external_id') and snapshot.get('id')==selected['external_id']:
            return {'drama':{**snapshot,'usable':True},'account_only':True,'source':source,'from_task':True,'account_uid':uid,'confirmed_at':''}
        return self.read('binding',binding_key(drama_id,source,uid)) or self.read('binding',binding_key(drama_id,source,'shared'))

    def profile_library(self,task_id):
        return PublishProfiles(self).public(self.context(task_id,include_videos=False)['account']['uid'])

    def profile_save(self,task_id,payload):
        result=PublishProfiles(self).save(self.context(task_id,include_videos=False)['account']['uid'],payload)
        self.remember_groups([effective_group(result['profile']['config'],kind) for kind in ('normal','sheep')])
        result['history']=self.histories()
        return result

    def histories(self):
        value={key:self.read('history',key,[]) for key in ('title','video_title','desc','tags','comment','repost_source')}
        value['short_title']=self.read('history','short_title',value['title'])
        return value

    def profile_history(self,task_id):
        self.context(task_id,include_videos=False)
        return self.histories()

    def profile_delete(self,task_id,payload):
        return PublishProfiles(self).delete(self.context(task_id,include_videos=False)['account']['uid'],payload.get('id'),payload.get('revision'))

    def profile_capture(self,task_id,payload):
        ctx=self.load(task_id)
        settings=prepare_settings(payload.get('settings') or ctx['settings'],ctx['videos'],ctx['default_address'])
        return {'config':PublishProfiles(self).capture(settings,ctx)}

    def profile_preview(self,task_id,payload):
        ctx=self.load(task_id)
        if ctx['execution']['running'] or ctx['publication']['running']:raise ValueError('请先停止当前任务，再切换方案')
        settings=prepare_settings(payload.get('settings') or ctx['settings'],ctx['videos'],ctx['default_address'])
        profiles=PublishProfiles(self);profile=profiles.find(payload.get('id'))
        result=profiles.apply(settings,profile,ctx,payload.get('scopes'))
        result['settings']=prepare_settings(result['settings'],ctx['videos'],ctx['default_address'])
        return result

    def save(self,task_id,payload):
        if self.execution(task_id)['running'] or self.publication(task_id)['running']:raise ValueError('正在执行，请先暂停或停止后再修改设置')
        if self.active_publication_items(task_id):raise ValueError('小V猫仍有待发布或正在处理的任务，请先取消或等待状态完成后再修改设置')
        ctx=self.context(task_id)
        source=validate_source(payload.get('mount_source') or ctx['mount_source'])
        groups=payload.get('groups')
        if not isinstance(groups,list) or len(groups)>50:raise ValueError('发布分组无效')
        # Normalize on the server as well: normal use never needs manual checkboxes.
        payload=prepare_settings(payload,ctx['videos'],self.read('address_default',ctx['account']['uid']))
        groups=payload['groups']
        ids={v['id'] for v in ctx['videos']};used=set();group_ids=set()
        for group in groups:
            if not isinstance(group,dict) or not group.get('id') or group['id'] in group_ids:raise ValueError('发布分组编号无效')
            group_ids.add(group['id'])
            selected=group.get('video_ids',[])
            if not isinstance(selected,list) or len(set(selected))!=len(selected) or any(v not in ids or v in used for v in selected):raise ValueError('视频只能属于一个分组，请检查视频选择')
            used.update(selected)
            self.validate_group(group,strict=False)
        port=int(payload.get('port',9222))
        if not 1<=port<=65535:raise ValueError('连接端口无效')
        self.write('settings',task_id,{'account_id':ctx['account']['id'],'drama_id':ctx['drama']['id'],'port':port,'groups':groups,
            'schedule':payload['schedule'],'assignment_mode':payload['assignment_mode'],'assignment_confirmed':bool(payload.get('assignment_confirmed')),'group_order':payload['group_order'],
            'sync_location':payload['sync_location'],'mount_source':source,'profile_ref':payload.get('profile_ref',ctx['settings'].get('profile_ref'))})
        self.remember_groups(groups)
        return self.load(task_id)

    def remember_groups(self,groups):
        for group in groups:
            for key in ('video_title','short_title','desc','comment','repost_source'):
                value=group.get(key,'').strip()
                if value:self.remember('history',key,value)
            if group.get('tags'):self.remember('history','tags',' '.join(group['tags']))

    def remember(self,kind,key,value):
        values=self.read(kind,key,self.read('history','title',[]) if kind=='history' and key=='short_title' else [])
        self.write(kind,key,[value]+[v for v in values if v!=value][:99])

    def validate_group(self,g,strict=True):
        if g.get('schedule_type') not in ('now','timing','localTiming'):raise ValueError('请选择有效的时间方式')
        for key,low,high in [('copies',1,100),('interval',0,10080)]:
            n=g.get(key,1 if key=='copies' else 0)
            if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or n!=int(n) or not low<=n<=high:raise ValueError('发布份数或间隔无效')
        if g.get('order') not in ('round','consecutive'):raise ValueError('视频排列方式无效')
        if g.get('cover_mode') not in ('auto','drama','none','custom'):raise ValueError('封面方式无效')
        if g.get('cover_source','auto') not in ('auto','custom'):raise ValueError('封面来源无效')
        cover_id=g.get('custom_cover_id','')
        if cover_id and (not isinstance(cover_id,str) or not re.fullmatch(r'[a-f0-9]{64}',cover_id)):
            raise ValueError('自定义封面编号无效，请重新选择图片')
        if g.get('cover_mode')=='custom' and cover_id:self.covers().path(cover_id)
        if g.get('cover_mode')=='custom' and not cover_id:raise ValueError('请先选择自定义封面图片')
        title=str(g.get('short_title',g.get('title','')));desc=str(g.get('desc',''));tags=g.get('tags',[])
        if len(str(g.get('video_title','')))>100:raise ValueError('视频标题最多100字')
        if title and not 6<=len(title)<=16:raise ValueError('视频号短标题填写时须为6–16字；也可以留空')
        if title and not SHORT_TITLE.fullmatch(title):raise ValueError('短标题包含特殊字符；符号仅支持书名号、引号、冒号、加号、问号、百分号，逗号可用空格替代')
        if len(desc)>1000:raise ValueError('简介最多1000字')
        if not isinstance(tags,list) or len(tags)>10 or any(not isinstance(t,str) or not t.strip() or len(t)>50 for t in tags):raise ValueError('话题最多10个，每个最多50字')
        tag_info(g,strict=strict)
        loc=g.get('location')
        if loc and (not isinstance(loc,dict) or not loc.get('poiCheckSum') or not loc.get('_searchQuery')):raise ValueError('地址信息不完整，请从搜索候选重新选择')
        if strict and g['schedule_type']!='now':
            self.validate_schedule_time(g['schedule_type'],g.get('start_time',''))

    @staticmethod
    def validate_schedule_time(schedule_type,value):
        """Validate the actual item time, using Beijing wall-clock time."""
        if schedule_type=='now':return
        try:start=datetime.strptime(str(value or ''),'%Y-%m-%d %H:%M').replace(tzinfo=SHANGHAI)
        except ValueError:raise ValueError('请选择开始日期和时间') from None
        if start<=datetime.now(SHANGHAI)+timedelta(minutes=5):raise ValueError('定时开始时间须至少晚于当前时间5分钟，请重新调整')

    def connection_status(self,task_id):
        ctx=self.load(task_id)
        with self.client_factory(ctx['settings']['port']) as client:
            matches=[a for a in client.accounts() if a['uid']==ctx['account']['uid'] and a.get('platform')=='Channels']
            if len(matches)!=1:raise ValueError('小V猫中没有唯一匹配的平台账号，请核对账号ID，不按昵称自动替换')
            account=matches[0]
            if account.get('loginStatus')!='登录有效':raise ValueError('当前小V猫账号登录失效，请先处理登录')
            return {'connected':True,'account':account,'message':'已按账号ID匹配'}

    def addresses(self,task_id,query):
        if not str(query).strip():raise ValueError('请输入城市或地点名称')
        ctx=self.load(task_id)
        terms=[str(query).strip()];seen=set();items=[]
        with self.client_factory(ctx['settings']['port']) as client:
            for term in terms:
                result=client.worker(ctx['account']['uid'],'getPositionsWithLocation',{'query':term,'latitude':0,'longitude':0})
                current=result.get('address') or {}
                if len(terms)==1:
                    place=str(query).strip()
                    for prefix in (current.get('province',''),current.get('city',''),str(current.get('city','')).removesuffix('市')):
                        if prefix and place.startswith(prefix):place=place[len(prefix):].strip()
                    if place and place!=str(query).strip():terms.append(place)
                    elif len(str(query).split())>1:terms.append(str(query).split()[-1])
                for loc in [current]+result.get('list',[]):
                    if not isinstance(loc,dict) or not loc.get('poiCheckSum') or loc['poiCheckSum'] in seen:continue
                    seen.add(loc['poiCheckSum'])
                    items.append({**loc,'_searchQuery':result.get('_searchQuery') or {'query':term,'latitude':0,'longitude':0}})
        names={normalized_name(t) for t in terms}
        items.sort(key=lambda loc:(normalized_name(loc.get('name','')) not in names,not any(n and n in normalized_name(loc.get('name','')) for n in names)))
        return {'items':items,'queries':terms}

    def public_addresses(self):
        saved=self.read('public_addresses','shared')
        if saved is not None:return saved
        # Existing confirmed records seed the shared library without writing on GET.
        # Once the shared document exists (even empty), deletions stay deleted.
        seen=set();values=[]
        with closing(self.connection()) as conn:
            rows=conn.execute("SELECT kind,content FROM v3_publish_documents WHERE kind IN ('addresses','address_default') ORDER BY updated_at DESC").fetchall()
        for row in rows:
            content=json.loads(row['content'])
            for address in content if row['kind']=='addresses' else [content]:
                if not isinstance(address,dict) or not address.get('poiCheckSum') or not address.get('_searchQuery'):continue
                key=address['poiCheckSum']
                if key in seen:continue
                seen.add(key);values.append(address)
        return values

    def address_book(self,task_id):
        uid=self.context(task_id,include_videos=False)['account']['uid']
        return {'addresses':self.read('addresses',uid,[]),'public_addresses':self.public_addresses(),'default_address':self.read('address_default',uid)}

    def save_address(self,task_id,address,default=False):
        if not isinstance(address,dict) or not address:raise ValueError('请从地址候选或地址库中选择完整地址')
        self.validate_group({'schedule_type':'now','order':'round','cover_mode':'none','location':address},False)
        uid=self.context(task_id,include_videos=False)['account']['uid']
        with RUN_LOCK:
            values=self.read('addresses',uid,[]);shared=self.public_addresses()
            documents=[('addresses',uid,[address]+[v for v in values if v['poiCheckSum']!=address['poiCheckSum']][:99]),
                ('public_addresses','shared',[address]+[v for v in shared if v['poiCheckSum']!=address['poiCheckSum']])]
            if default:documents.append(('address_default',uid,address))
            with closing(self.connection()) as conn:
                conn.executemany('INSERT INTO v3_publish_documents VALUES(?,?,?,?) ON CONFLICT(kind,key) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at',
                    [(kind,key,json.dumps(value,ensure_ascii=False),stamp()) for kind,key,value in documents]);conn.commit()
        return {'saved':True,**self.address_book(task_id)}

    def delete_address(self,task_id,checksum,scope='account'):
        uid=self.context(task_id,include_videos=False)['account']['uid']
        if scope not in ('account','public'):raise ValueError('地址库范围无效')
        with RUN_LOCK:
            if scope=='public':self.write('public_addresses','shared',[v for v in self.public_addresses() if v['poiCheckSum']!=checksum])
            else:
                self.write('addresses',uid,[v for v in self.read('addresses',uid,[]) if v['poiCheckSum']!=checksum])
                if (self.read('address_default',uid) or {}).get('poiCheckSum')==checksum:self.write('address_default',uid,None)
        return {'deleted':True,**self.address_book(task_id)}

    def dramas(self,task_id,query='',recheck=False):
        ctx=self.load(task_id);uid=ctx['account']['uid'];binding=ctx['binding']
        source=ctx['mount_source']
        if source=='plugin':return {'items':[],'binding':None,'status':'plugin','queries':[],'mount_source':source,'message':'插件挂载仅生成本地草稿，不附加原生短剧挂载'}
        names=[ctx['drama']['name']]+ctx['drama']['history_names']
        terms=search_terms([query] if query else ([binding['drama']['name']] if binding else names))
        candidates=[];queries=[]
        with self.client_factory(ctx['settings']['port']) as client:
            for term in terms[:10]:
                for page in range(1,21):
                    result=client.worker(uid,'getDramaComponent',{**({'sceneType':3} if source=='channels_drama' else {}),'page':page,'queryString':term})
                    if result.get('baseResp',{}).get('errcode',0):raise RuntimeError('剧集查询失败，请先检查当前账号权限与登录')
                    candidates.extend(result.get('list',[]))
                    if not result.get('list') or page*20>=result.get('totalCount',0):break
                queries.append(term)
                rows,auto=rank_candidates(candidates,names)
                if binding and any(c['id']==binding['drama']['id'] and c.get('usable') for c in rows):break
                if not binding and auto and not query:break
            rows,auto=rank_candidates(candidates,names)
        if binding and not query:
            matched=next((c for c in rows if c['id']==binding['drama']['id']),None)
            if matched and matched.get('usable'):
                updated={**binding,'drama':{k:v for k,v in matched.items() if k not in ('score','exact')},'checked_at':stamp(),'source':source,'account_uid':uid}
                self.write('task_binding',task_id+':'+source,updated)
                return {'items':rows,'binding':updated,'status':'bound','queries':queries,'mount_source':source}
            return {'items':rows,'binding':binding,'status':'unavailable','queries':queries,'mount_source':source,'message':'原关联剧集在当前账号下未找到或不可挂载，请核对；不会自动改挂其他剧集'}
        if auto and not binding:
            linked=self.bind(task_id,auto,confirmed=True,account_only=False)
            return {'items':rows,'binding':linked,'status':'auto','queries':queries,'mount_source':source}
        return {'items':rows,'binding':binding,'status':'choose' if rows else 'not_found','queries':queries,'mount_source':source,
            'message':'请选择正确剧集；确实找不到时，当前账号可能没有该剧挂载权限'}

    def bind(self,task_id,drama,confirmed=False,account_only=False,source=None):
        if not confirmed:raise ValueError('文字不同的剧集需要人工确认')
        if not isinstance(drama,dict) or not drama.get('id') or not drama.get('name') or drama.get('usable') is not True:raise ValueError('请选择可挂载的真实剧集')
        ctx=self.context(task_id);uid=ctx['account']['uid']
        if source is not None and source!=ctx['mount_source']:raise ValueError('挂载方式已变化，请重新匹配后选择')
        source=ctx['mount_source']
        if source=='plugin':raise ValueError('插件方式不选择原生挂载剧集')
        clean={k:v for k,v in drama.items() if k not in ('score','exact')}
        value={'drama':clean,'account_only':bool(account_only),'confirmed_at':stamp(),'source':source,'account_uid':uid}
        self.write('task_binding',task_id+':'+source,value)
        self.write('binding',binding_key(ctx['drama']['id'],source,uid if account_only else 'shared'),value)
        if not account_only:
            self.write('binding',binding_key(ctx['drama']['id'],source,uid),None)
        return value

    def execution(self,task_id,kind='draft'):
        with RUN_LOCK:run=RUNS.get(task_id)
        values=self.read('execution' if kind=='draft' else 'publish_execution',task_id,{'items':[],'state':'idle'})
        running=bool(run and run.get('target','draft')==kind and run['thread'].is_alive())
        if not running and values.get('state')=='running':values['state']='interrupted'
        return {**values,'running':running,'mode':run.get('mode') if running else None}

    def publication(self,task_id):return self.execution(task_id,'publish')

    def active_publication_items(self,task_id):
        state=self.publication(task_id)
        active_remote={'waiting','publishing','localTiming'}
        active_local={'submitted','publishing','localTiming'}
        return [item for item in state.get('items',[]) if item.get('local_id') and (item.get('remote_state') in active_remote or item.get('status') in active_local)]

    def refresh_publication(self,task_id):
        from .publisher import Publisher
        from .delivery import apply_completion
        from server.operations_collection import associate_publications, publication_completion
        result = Publisher(self).refresh(task_id)
        try:
            with self.client_factory(self.read('settings',task_id,{}).get('port',9222)) as client:
                associate_publications(self.connection,client)
        except Exception:
            result['attribution_warning'] = '作品公开状态同步暂未完成'
        # Explicit successful delivery evidence is sufficient even if the public
        # works list is unavailable or has no actual public release timestamp.
        try:
            gate = publication_completion(self.connection, task_id, result)
            result['cleanup_gate'] = gate
            confirmed = set(gate.get('confirmed_keys', []))
            for item in result.get('items', []):
                item['delivery_confirmed'] = item.get('key') in confirmed
                if item['delivery_confirmed']:
                    item.setdefault('delivery_confirmed_at', stamp())
            self.write('publish_execution', task_id, result)
            if gate.get('complete'):
                with closing(self.connection()) as conn:
                    apply_completion(conn, task_id, gate, expected_content=json.dumps(result, ensure_ascii=False))
                    conn.commit()
        except Exception:
            result['cleanup_gate'] = {'complete': False, 'reason': 'cleanup_gate_update_failed'}
        return result

    def progress(self,task_id):
        from .progress import progress
        return progress(self,task_id)

    def publish(self,task_id,limit=None,selected_keys=None,new_attempt=False,reschedule=None,full_reset=False):
        if self.load(task_id)['mount_source']=='plugin':return self.start(task_id)
        state=self.publication(task_id)
        if not new_attempt and state.get('reset_status') in ('blocked','awaiting_manual_cleanup','ready'):
            raise ValueError('当前批次正在进行整批作废，请完成重新发布确认后再提交')
        from .publisher import Publisher
        with RUN_LOCK:
            run=RUNS.get(task_id)
            if run and run['thread'].is_alive():raise ValueError('本任务正在处理，请勿重复启动')
            run={'mode':'running','target':'publish'}
            thread=threading.Thread(target=Publisher(self).run,args=(task_id,run,limit,selected_keys,new_attempt,reschedule,full_reset),daemon=True,name='V3-publications')
            run['thread']=thread;RUNS[task_id]=run;thread.start()
        return {'accepted':True,'target':'publish'}

    def republish(self,task_id,selected_keys=None):
        state=self.publication(task_id)
        if state.get('reset_status')!='ready':raise ValueError('请先取消旧任务、处理官方后台视频并确认旧批次作废')
        return self.publish(task_id,selected_keys=selected_keys,new_attempt=True,full_reset=True)

    def prepare_republish(self,task_id):
        from .publisher import Publisher
        return Publisher(self).prepare_full_reset(task_id)

    def confirm_republish(self,task_id):
        from .publisher import Publisher
        return Publisher(self).confirm_full_reset(task_id)

    def schedule_retry_preview(self,task_id,payload):
        from .publisher import Publisher
        return Publisher(self).schedule_plan(task_id,payload.get('keys'),payload.get('start_time'),payload.get('interval'))

    def schedule_retry(self,task_id,payload):
        from .publisher import Publisher
        plan=Publisher(self).schedule_plan(task_id,payload.get('keys'),payload.get('start_time'),payload.get('interval'))
        return {**self.publish(task_id,selected_keys=plan['keys'],new_attempt=True,reschedule=plan),'plan':plan}

    def manage_publication_tasks(self,task_id,operation,keys):
        if operation not in ('pause','retry','cancel') or not isinstance(keys,list) or not keys:
            raise ValueError('请选择要操作的发布任务')
        state=self.publication(task_id)
        if state['running']:raise ValueError('当前批次正在处理，请稍后再操作')
        from .publisher import Publisher
        return Publisher(self).manage(task_id,operation,keys)

    def continue_publication(self,task_id,keys=None):
        state=self.publication(task_id)
        if state['running']:raise ValueError('当前批次正在处理，请稍后再操作')
        items=state.get('items',[])
        pending=[item for item in items if item.get('status') in ('pending','rejected') and not item.get('local_id')]
        selected=keys if isinstance(keys,list) and keys else [item['key'] for item in pending]
        allowed={item['key'] for item in pending}
        if not selected:raise ValueError('当前没有尚未提交的小V猫任务')
        if any(key not in allowed for key in selected):raise ValueError('“继续提交”只能选择尚未提交的小V猫任务')
        from .publisher import expired_schedule
        if any(expired_schedule(item) for item in pending if item['key'] in selected):raise ValueError('原定发布时间已过，请使用“排期重发”重新安排时间')
        return self.publish(task_id,selected_keys=selected)

    def action(self,task_id,action):
        if action not in ('pause','resume','stop'):raise ValueError('任务操作无效')
        with RUN_LOCK:
            run=RUNS.get(task_id)
            if run and run['thread'].is_alive():
                run['mode']={'pause':'paused','resume':'running','stop':'stopped'}[action]
                return self.execution(task_id,run.get('target','draft'))
        if action=='resume':return self.start(task_id)
        return self.execution(task_id)

    def draft_assist(self,task_id,key,action,confirmed=False):
        state=self.execution(task_id)
        if state['running']:raise ValueError('请先停止本批次，再人工处理草稿')
        record=next((i for i in state['items'] if i['key']==key),None)
        if not record or not record.get('draft_id'):raise ValueError('该条尚未有可读取的草稿编号')
        ctx=self.load(task_id)
        with self.client_factory(ctx['settings']['port']) as client:
            if action=='open-draft':return client.open_draft(record['draft_id'])
            detail=client.call('vcat_list_drafts',{'draftId':record['draft_id']})
        base=record.get('payload')
        if not base:raise ValueError('缺少本条原始参数，请先重新读取并检查')
        uid=base['uid'];options=detail.get('platformOptionsByUid',{}).get(uid)
        accounts=detail.get('accounts',[])
        if len(accounts)!=1 or accounts[0].get('uid')!=uid or not options:raise ValueError('草稿账号发生变化，不能直接采纳，请改回原账号')
        from urllib.parse import unquote
        def clean(v):return unquote(str(v or '')).replace('file:///','').replace('file://','').replace('\\','/').casefold()
        if clean(detail.get('content',{}).get('videoPath'))!=clean(base['videoPath']):raise ValueError('草稿视频发生变化，请改回原视频或另建分组')
        value={**base,'platformOptions':{k:options[k] for k in ('CAT_shortTitle','CAT_location','CAT_extReading','tagInfo','postFlag') if k in options},
            'desc':options.get('CAT_desc',''),'tags':options.get('topics',[])}
        timing=options.get('CAT_timing',{'type':1})
        value['scheduleType']={1:'now',2:'timing',3:'localTiming'}.get(timing.get('type'),'now')
        if timing.get('time'):
            value['scheduleTime']=datetime.fromisoformat(str(timing['time']).replace('Z','+00:00')).astimezone(SHANGHAI).strftime('%Y-%m-%d %H:%M')
        else:value.pop('scheduleTime',None)
        value['autoReset']=False
        if options.get('CAT_cover'):value['cover']=options['CAT_cover']
        else:value.pop('cover',None)
        if options.get('CAT_comment'):value['comment']=options['CAT_comment']
        else:value.pop('comment',None)
        checks=verify_draft(detail,value)
        if not all(checks.values()):raise ValueError('当前草稿仍有不完整参数，请核对时间和设置')
        summary={'draft_id':record['draft_id'],'address':(options.get('CAT_location') or {}).get('name') or '不显示位置',
            'drama':((options.get('CAT_extReading') or {}).get('drama') or {}).get('name') or '不挂载',
            'time':value.get('scheduleTime') or '立即模式','description':value['desc']}
        if confirmed:
            record.update(accepted_payload=value,status='ready',checks=checks,error='')
            state.pop('running',None);state.pop('mode',None)
            state['state']='ready' if all(i['status']=='ready' for i in state['items']) else 'needs_help'
            self.write('execution',task_id,state)
        return {'summary':summary,'accepted':bool(confirmed)}

    def expanded(self,ctx):
        result=[];videos={v['id']:v for v in ctx['videos']}
        for group in schedule_groups(ctx['settings'])['groups']:
            selected=[videos[v] for v in group['video_ids'] if v in videos]
            pairs=[(v,n) for n in range(int(group['copies'])) for v in selected] if group['order']=='round' else [(v,n) for v in selected for n in range(int(group['copies']))]
            for index,(video,copy) in enumerate(pairs):
                when=''
                if group['schedule_type']!='now' and group.get('start_time'):
                    start=datetime.strptime(group['start_time'],'%Y-%m-%d %H:%M')
                    when=(start+timedelta(minutes=index*group['interval'])).strftime('%Y-%m-%d %H:%M')
                result.append({'key':group['id']+':'+video['id']+':'+str(copy),'group':group,'video':video,'copy':copy+1,'time':when})
        if len(result)>3000:raise ValueError('单次草稿条目过多，请拆成多个分组或批次')
        return result

    def payload(self,ctx,item):
        problem=(ctx['settings'].get('profile_ref') or {}).get('problem')
        if problem:raise ValueError(problem)
        group=item['group'];video=item['video'];self.validate_group(group,strict=False)
        if group['schedule_type']!='now':self.validate_schedule_time(group['schedule_type'],item.get('time') or group.get('start_time'))
        if not video['exists']:raise ValueError('视频文件不存在：'+video['name'])
        binding=ctx['binding'];options={'CAT_shortTitle':group.get('short_title',group.get('title','')),'postFlag':1 if group.get('original') else 0,'tagInfo':tag_info(group)}
        if group.get('location'):options['CAT_location']=group['location']
        if group.get('mount_required') and ctx.get('mount_source','channels_drama')!='plugin':
            if not binding:raise ValueError('请先匹配并确认挂载剧集')
            drama=binding['drama']
            if binding.get('source',ctx.get('mount_source','channels_drama'))!=ctx.get('mount_source','channels_drama'):raise ValueError('挂载关联类型不一致，请重新匹配')
            options['CAT_extReading']=component(ctx.get('mount_source','channels_drama'),drama)
        # Channels uses the common title as description only when description
        # is empty; CAT_shortTitle remains an independent platform field.
        payload={'uid':ctx['account']['uid'],'videoPath':video['path'],'title':group.get('video_title',''),'desc':group.get('desc','') or group.get('video_title',''),'tags':group.get('tags',[]),
            'scheduleType':group['schedule_type'],'autoReset':False,'platformOptions':options}
        if item['time']:payload['scheduleTime']=item['time']
        if item['time'] and datetime.strptime(item['time'],'%Y-%m-%d %H:%M').date()>(datetime.now(SHANGHAI)+timedelta(days=30)).date():
            raise ValueError('视频号定时最多选择未来30天，请调整整批开始时间、份数或间隔')
        if group.get('comment'):payload['comment']={'content':group['comment'],'isTop':bool(group.get('comment_top'))}
        selected_cover=ctx.get('sheep_cover',{}) if video.get('sheep') else ctx['cover']
        if group.get('cover_mode')=='custom':
            payload['cover']=str(self.covers().path(group.get('custom_cover_id','')))
        elif group.get('cover_mode')!='none' and selected_cover.get('exists'):payload['cover']=selected_cover['path']
        return payload

    def check(self,task_id):
        ctx=self.load(task_id);issues=[]
        self.connection_status(task_id)
        if ctx['mount_source']!='plugin' and any(g.get('mount_required') and g['video_ids'] for g in ctx['settings']['groups']):
            mount=self.dramas(task_id)
            if mount['status'] in ('auto','bound'):ctx['binding']=mount['binding']
            else:issues.append({'group_id':'','message':mount.get('message') or '请确认挂载剧集'})
        items=self.expanded(ctx)
        if not items:issues.append({'group_id':'','message':'请至少选择一个视频'})
        for g in ctx['settings']['groups']:
            if not g['video_ids']:continue
            try:
                for item in (i for i in items if i['group']['id']==g['id']):self.payload(ctx,item)
            except ValueError as exc:issues.append({'group_id':g['id'],'message':str(exc)})
        return {'ok':not issues,'issues':issues,'count':len(items),'binding':ctx['binding']}

    def start(self,task_id):
        with RUN_LOCK:
            if self.execution(task_id)['running'] or self.publication(task_id)['running']:raise ValueError('本任务正在处理，请勿重复启动')
            run={'mode':'running','target':'draft'}
            thread=threading.Thread(target=self._run,args=(task_id,run),daemon=True,name='V3-local-drafts')
            run['thread']=thread;RUNS[task_id]=run;thread.start()
        return {'accepted':True}

    def _run(self,task_id,run):
        import time
        state=self.read('execution',task_id,{'items':[]})
        old={i['key']:i for i in state['items']};state['state']='running';state['error']='';state['started_at']=stamp()
        self.write('execution',task_id,state)
        try:
            ctx=self.load(task_id)
            if self.read('settings',task_id) is None:
                self.write('settings',task_id,ctx['settings'])
            self.connection_status(task_id)
            # Revalidate the saved ID under this account once per batch.
            mount=None
            if ctx['mount_source']!='plugin' and any(g.get('mount_required') and g['video_ids'] for g in ctx['settings']['groups']):
                mount=self.dramas(task_id)
                if mount['status'] in ('bound','auto'):ctx['binding']=mount['binding']
                else:ctx['binding']=None
            expanded=self.expanded(ctx)
            state['items']=[]
            for item in expanded:
                record=old.get(item['key'],{'key':item['key'],'name':item['video']['name'],'group_id':item['group']['id'],'group_name':item['group']['name'],'copy':item['copy'],'time':item['time'],'status':'pending'})
                state['items'].append(record)
            self.write('execution',task_id,state)
            for item,record in zip(expanded,state['items']):
                while run['mode']=='paused':time.sleep(.2)
                if run['mode']=='stopped':break
                try:
                    payload=self.payload(ctx,item)
                    payload_hash=fingerprint(payload)
                    if record.get('draft_id') and record.get('payload_hash')!=payload_hash:
                        record.update(status='needs_help',error='参数已变化，原草稿保留。请在小V猫核对原草稿，或新建分组生成新版本。');continue
                    record['payload']=payload
                    expected=record.get('accepted_payload') or payload
                    title='V3草稿_'+task_id[:10]+'_'+hashlib.sha256(item['key'].encode()).hexdigest()[:16]
                    with self.client_factory(ctx['settings']['port'],writable=True) as client:
                        if record.get('status') in ('creating','uncertain','checking'):
                            found=client.find_draft(title)
                            if not found:
                                record.update(status='uncertain',error='尚未查到创建结果，为防重复暂不重建；稍后重新检查或人工查看本地草稿箱');continue
                            record['draft_id']=found['draftId']
                        if not record.get('draft_id'):
                            record.update(status='creating',payload_hash=payload_hash,draft_title=title,error='',video_id=item['video']['id'],mount_source=ctx['mount_source'])
                            self.write('execution',task_id,state)
                            created=client.call('vcat_create_draft',{**payload,'draftTitle':title})
                            record['draft_id']=created['draftId'];record['submitted_at']=stamp()
                        record['status']='checking';self.write('execution',task_id,state)
                        detail=client.call('vcat_list_drafts',{'draftId':record['draft_id']})
                        checks=verify_draft(detail,expected)
                        record.update(status='ready' if all(checks.values()) else 'needs_help',checks=checks,
                            error='' if all(checks.values()) else '草稿实际参数不一致，请核对后重新读取',payload_hash=payload_hash)
                except DraftOutcomeUnknown as exc:record.update(status='uncertain',error=str(exc))
                except (ValueError,RuntimeError,OSError) as exc:record.update(status='needs_help',error=str(exc)[:800])
                finally:self.write('execution',task_id,state)
            state['state']='stopped' if run['mode']=='stopped' else ('ready' if state['items'] and all(i['status']=='ready' for i in state['items']) else 'needs_help')
        except Exception as exc:state.update(state='needs_help',error=str(exc)[:800])
        finally:self.write('execution',task_id,state)


def verify_draft(detail,payload):
    from urllib.parse import unquote
    def path(value):return unquote(str(value or '')).replace('file:///','').replace('file://','').replace('\\','/').casefold()
    uid=payload['uid'];actual=detail.get('platformOptionsByUid',{}).get(uid,{})
    accounts=detail.get('accounts',[])
    checks={'account':len(accounts)==1 and accounts[0].get('uid')==uid,'video':path(detail.get('content',{}).get('videoPath'))==path(payload['videoPath']),
        'description':actual.get('CAT_desc','')==payload.get('desc',''),'topics':actual.get('topics',[])==payload.get('tags',[])}
    if payload.get('cover'):checks['cover']=path(actual.get('CAT_cover'))==path(payload['cover'])
    if payload.get('title'):checks['video_title']=detail.get('content',{}).get('title')==payload['title']
    for key,value in payload.get('platformOptions',{}).items():checks[key]=actual.get(key)==value
    for key in ('CAT_location','CAT_extReading'):
        checks[key]=actual.get(key)==payload.get('platformOptions',{}).get(key)
    timing=actual.get('CAT_timing',{})
    checks['time_mode']=timing.get('type')=={'now':1,'timing':2,'localTiming':3}[payload['scheduleType']]
    if payload.get('scheduleTime'):
        try:checks['time']=datetime.fromisoformat(str(timing['time']).replace('Z','+00:00')).astimezone(SHANGHAI).strftime('%Y-%m-%d %H:%M')==payload['scheduleTime']
        except (ValueError,KeyError):checks['time']=False
        checks['no_immediate_fallback']=timing.get('autoReset') is False
    if payload.get('comment'):checks['comment']=actual.get('CAT_comment')==payload['comment']
    return checks
