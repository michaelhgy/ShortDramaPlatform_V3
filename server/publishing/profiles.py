"""Reusable publishing rules; only managed custom cover images travel with profiles."""
import copy
import json
import threading
import uuid
from datetime import datetime

LOCK=threading.RLock()
SCOPES=('schedule','copies','text','declaration','location_mount','cover')
COVER=('cover_mode','cover_source','custom_cover_id')
TEXT=('video_title','desc','tags','short_title','comment','comment_top')
DECLARATION=('tag_type','original','repost_source','shoot_region_codes')
GROUP_DEFAULTS={'copies':1,'order':'round','mount_required':True,'video_title':'','desc':'','tags':[],'short_title':'','comment':'','comment_top':False,
    'tag_type':0,'original':False,'repost_source':'','shoot_region_codes':[],'cover_mode':'auto','cover_source':'auto','custom_cover_id':''}
LABELS={'cover_mode':'使用封面','cover_source':'封面来源','custom_cover_id':'自定义封面图片','schedule_type':'时间方式','interval':'作品间隔','group_order':'两组顺序','copies':'每视频份数','order':'复制排列',
    'video_title':'视频标题','desc':'简介','tags':'话题','short_title':'短标题','comment':'追评','comment_top':'置顶追评',
    'tag_type':'视频声明','original':'原创','repost_source':'转载来源','shoot_region_codes':'拍摄地点','location':'地址','mount_required':'需要挂载','sync_location':'正剧与羊同步地址'}


def base_config():
    return {'schedule':{'schedule_type':'timing','interval':3},'group_order':'normal_first','sheep_inherit':True,
        'groups':{'normal':copy.deepcopy(GROUP_DEFAULTS),'sheep':{**copy.deepcopy(GROUP_DEFAULTS),'mount_required':False}},
        'location':{'mode':'account','checksum':'','sync':True}}


def separate_mounts(config):
    """Read legacy shared switches without rewriting saved task snapshots."""
    value=copy.deepcopy(config);legacy=value.pop('mount_required',True)
    for kind in ('normal','sheep'):
        group=value.setdefault('groups',{}).setdefault(kind,{})
        group.setdefault('mount_required',bool(legacy) if kind=='normal' else False)
        group.setdefault('cover_mode','auto')
        group.setdefault('cover_source','custom' if group['cover_mode']=='custom' else 'auto')
        group.setdefault('custom_cover_id','')
    value.setdefault('location',{}).setdefault('sync',True)
    return value


def initial_book():
    daily=base_config();multiple=base_config();multiple['groups']['normal']['copies']=2;multiple['schedule']['interval']=5
    return {'items':[{'id':'builtin-daily','name':'日常发布','revision':1,'config':daily},
        {'id':'builtin-multiple','name':'多份循环','revision':1,'config':multiple}],
        'software_default_id':None,'account_defaults':{}}


def effective_group(config,kind):
    group=copy.deepcopy(config['groups'][kind])
    if kind=='sheep' and config['sheep_inherit']:
        group.update({key:copy.deepcopy(config['groups']['normal'][key]) for key in (*TEXT,*DECLARATION)})
    return group


def selected_scopes(value):
    if not isinstance(value,list) or not value or any(s not in SCOPES for s in value):raise ValueError('请至少选择一项有效的应用范围')
    return list(dict.fromkeys(value))


def group_values(config,kind,scopes,location):
    source=effective_group(config,kind);result={}
    if 'cover' in scopes:result.update({key:source[key] for key in COVER})
    if 'copies' in scopes:result.update({key:source[key] for key in ('copies','order')})
    if 'text' in scopes:result.update({key:source[key] for key in TEXT})
    if 'declaration' in scopes:result.update({key:source[key] for key in DECLARATION})
    if 'location_mount' in scopes:result.update(location=copy.deepcopy(location),mount_required=source['mount_required'])
    return copy.deepcopy(result)


def format_value(key,value):
    if key=='custom_cover_id':return '已保存图片 '+value[:8] if value else '未选择'
    if key=='cover_mode':return {'none':'不使用','auto':'使用自带','drama':'使用自带','custom':'使用自定义'}.get(value,str(value))
    if key=='cover_source':return '使用自定义' if value=='custom' else '使用自带'
    if key=='location':return (value or {}).get('name') or (value or {}).get('fullAddress') or '不显示位置'
    if isinstance(value,bool):return '开启' if value else '关闭'
    if isinstance(value,list):return '、'.join(map(str,value)) or '空'
    maps={'schedule_type':{'now':'立即模式','timing':'平台定时','localTiming':'本机定时'},
        'group_order':{'normal_first':'正剧→羊','sheep_first':'羊→正剧'},'order':{'round':'整组循环','consecutive':'同视频连续'},
        'tag_type':{0:'无需声明',1:'AI生成',2:'营销广告',3:'虚构剧情',5:'自行拍摄',7:'转载',8:'个人观点'}}
    return str(maps.get(key,{}).get(value,value)) if value not in (None,'') else '空'


class PublishProfiles:
    def __init__(self,service):self.service=service

    def book(self):
        book=self.service.read('publish_profiles','library') or initial_book()
        for p in book['items']:
            if 'mount_required' in p['config'] or 'sync' not in p['config'].get('location',{}):p['revision']+=1
            p['config']=separate_mounts(p['config'])
        return book

    def public(self,uid):
        book=self.book()
        return {'items':book['items'],'software_default_id':book.get('software_default_id'),
            'account_default_id':book.get('account_defaults',{}).get(uid)}

    def default(self,uid):
        book=self.book();key=book.get('account_defaults',{}).get(uid) or book.get('software_default_id')
        return next((p for p in book['items'] if p['id']==key),None)

    def find(self,key):
        result=next((p for p in self.book()['items'] if p['id']==key),None)
        if not result:raise ValueError('方案不存在或已被删除，请刷新后选择')
        return result

    def validate_config(self,value):
        if not isinstance(value,dict):raise ValueError('发布方案内容无效')
        result=base_config();schedule=value.get('schedule') or {}
        if not isinstance(schedule,dict) or not isinstance(value.get('groups') or {},dict) or not isinstance(value.get('location') or {},dict):raise ValueError('方案排期、分组或地址内容无效')
        result['schedule']={'schedule_type':schedule.get('schedule_type','timing'),'interval':schedule.get('interval',3)}
        result['group_order']=value.get('group_order','normal_first')
        if result['group_order'] not in ('normal_first','sheep_first'):raise ValueError('两组发布顺序无效')
        result['sheep_inherit']=bool(value.get('sheep_inherit',True))
        location=value.get('location') or {};mode=location.get('mode','account')
        if mode not in ('account','none','public'):raise ValueError('方案地址方式无效')
        checksum=str(location.get('checksum') or '') if mode=='public' else ''
        sync=location.get('sync',True)
        if not isinstance(sync,bool):raise ValueError('地址同步选项无效')
        result['location']={'mode':mode,'checksum':checksum,'sync':sync}
        if mode=='public' and not any(a['poiCheckSum']==checksum for a in self.service.public_addresses()):raise ValueError('指定的公共地址已不存在，请重新选择')
        for kind in ('normal','sheep'):
            source=(value.get('groups') or {}).get(kind) or {}
            if not isinstance(source,dict):raise ValueError('方案分组内容无效')
            group={key:copy.deepcopy(source.get(key,default)) for key,default in GROUP_DEFAULTS.items()}
            group['mount_required']=source.get('mount_required',bool(value.get('mount_required',True)) if kind=='normal' else False)
            if not isinstance(group['mount_required'],bool):raise ValueError('挂载选项无效')
            if any(not isinstance(group[k],str) for k in ('video_title','desc','short_title','comment','repost_source')):raise ValueError('方案文案须为文字')
            self.service.validate_group({**group,**result['schedule'],'location':None},strict=False)
            result['groups'][kind]=group
        return result

    def save(self,uid,payload):
        name=str(payload.get('name') or '').strip()
        if not name or len(name)>50:raise ValueError('方案名称须为1–50字')
        config=self.validate_config(payload.get('config'))
        with LOCK:
            book=self.book();key=payload.get('id') or uuid.uuid4().hex
            old=next((p for p in book['items'] if p['id']==key),None)
            if payload.get('id') and not old:raise ValueError('方案已被删除，请另存为新方案')
            if old and payload.get('revision')!=old['revision']:raise ValueError('方案已在其他窗口更新，请刷新后重试')
            if any(p['name'].casefold()==name.casefold() and p['id']!=key for p in book['items']):raise ValueError('已有同名方案，请换一个名称')
            if not old and len(book['items'])>=100:raise ValueError('方案较多，请先整理不再使用的方案')
            changed=not old or old['name']!=name or old['config']!=config
            profile={'id':key,'name':name,'config':config,'revision':(old['revision']+1 if changed else old['revision']) if old else 1,
                'updated_at':datetime.now().isoformat(timespec='seconds')}
            book['items']=[profile if p['id']==key else p for p in book['items']] if old else book['items']+[profile]
            if payload.get('software_default') is True:book['software_default_id']=key
            elif payload.get('software_default') is False and book.get('software_default_id')==key:book['software_default_id']=None
            if payload.get('account_default') is True:book.setdefault('account_defaults',{})[uid]=key
            elif payload.get('account_default') is False and book.get('account_defaults',{}).get(uid)==key:book['account_defaults'].pop(uid,None)
            self.service.write('publish_profiles','library',book)
        return {'profile':profile,'library':self.public(uid)}

    def delete(self,uid,key,revision):
        with LOCK:
            book=self.book();profile=self.find(key)
            if revision!=profile['revision']:raise ValueError('方案已更新，请刷新后重试')
            book['items']=[p for p in book['items'] if p['id']!=key]
            if book.get('software_default_id')==key:book['software_default_id']=None
            book['account_defaults']={uid:pid for uid,pid in book.get('account_defaults',{}).items() if pid!=key}
            self.service.write('publish_profiles','library',book)
        return {'library':self.public(uid)}

    def capture(self,settings,ctx):
        result=base_config();result['schedule']={key:settings['schedule'][key] for key in ('schedule_type','interval')}
        result['group_order']=settings.get('group_order','normal_first')
        by_kind={g.get('kind'):g for g in settings['groups']}
        normal=by_kind.get('normal') or by_kind.get('sheep') or next(iter(settings['groups']),{})
        sheep=by_kind.get('sheep') or normal
        for kind,g in (('normal',normal),('sheep',sheep)):
            result['groups'][kind]={key:copy.deepcopy(g.get(key,g.get('title','') if key=='short_title' else default)) for key,default in GROUP_DEFAULTS.items()}
            result['groups'][kind]['mount_required']=by_kind.get(kind,{}).get('mount_required',kind=='normal')
        result['sheep_inherit']=all(result['groups']['normal'][k]==result['groups']['sheep'][k] for k in (*TEXT,*DECLARATION))
        address=normal.get('location')
        if not address:result['location']={'mode':'none','checksum':''}
        elif address.get('poiCheckSum')==(ctx.get('default_address') or {}).get('poiCheckSum'):result['location']={'mode':'account','checksum':''}
        else:result['location']={'mode':'public','checksum':address['poiCheckSum']}
        result['location']['sync']=settings.get('sync_location',True)
        return result

    def apply(self,settings,profile,ctx,scopes=None):
        scopes=selected_scopes(list(SCOPES) if scopes is None else scopes);config=profile['config'];value=copy.deepcopy(settings);changes=[]
        location=None
        if 'location_mount' in scopes:
            mode=config['location']['mode']
            if mode=='account':location=ctx.get('default_address')
            elif mode=='public':
                location=next((a for a in ctx.get('public_addresses',[]) if a['poiCheckSum']==config['location']['checksum']),None)
                if not location:raise ValueError('此方案指定的公共地址已被删除，请修改方案地址后再应用')
        root={}
        if 'location_mount' in scopes:
            sync=config['location'].get('sync',True);root['sync_location']=sync
            if value.get('sync_location',True)!=sync:changes.append({'label':LABELS['sync_location'],'before':format_value('sync_location',value.get('sync_location',True)),'after':format_value('sync_location',sync)})
            value['sync_location']=sync
        if 'schedule' in scopes:
            schedule_root={**config['schedule'],'group_order':config['group_order']};root.update(schedule_root)
            for key,target in schedule_root.items():
                old=value.get('group_order','normal_first') if key=='group_order' else value['schedule'].get(key)
                if old!=target:changes.append({'label':LABELS[key],'before':format_value(key,old),'after':format_value(key,target)})
            value['schedule'].update(config['schedule']);value['group_order']=config['group_order']
        baseline={'root':root,'groups':{kind:group_values(config,kind,scopes,location) for kind in ('normal','sheep')}}
        for group in value['groups']:
            kind=group.get('kind')
            if kind not in baseline['groups']:continue
            for key,target in baseline['groups'][kind].items():
                old=group.get(key,GROUP_DEFAULTS.get(key))
                if old!=target:changes.append({'label':('正剧' if kind=='normal' else '羊')+' · '+LABELS[key],'before':format_value(key,old),'after':format_value(key,target)})
                group[key]=copy.deepcopy(target)
        value['profile_ref']={'id':profile['id'],'name':profile['name'],'revision':profile['revision'],'scopes':scopes,'baseline':baseline}
        return {'settings':value,'changes':changes,'has_special_groups':any(g.get('kind')=='custom' for g in value['groups'])}

    @staticmethod
    def restore_new_groups(settings,saved):
        value=copy.deepcopy(settings);baseline=(value.get('profile_ref') or {}).get('baseline',{}).get('groups',{})
        old={g['id'] for g in saved.get('groups',[])}
        allowed=set(GROUP_DEFAULTS)|{'location','mount_required'}
        for g in value['groups']:
            if g['id'] not in old and g.get('kind') in baseline:g.update({k:copy.deepcopy(v) for k,v in baseline[g['kind']].items() if k in allowed})
        return value

    def state(self,settings):
        ref=settings.get('profile_ref')
        if not ref:return None
        profile=next((p for p in self.book()['items'] if p['id']==ref.get('id')),None);baseline=ref.get('baseline') or {};modified=False
        for key,target in baseline.get('root',{}).items():
            old=settings.get(key) if key in ('group_order','sync_location') else settings.get('schedule',{}).get(key)
            modified|=old!=target
        for g in settings['groups']:
            for key,target in baseline.get('groups',{}).get(g.get('kind'),{}).items():modified|=g.get(key,GROUP_DEFAULTS.get(key))!=target
        return {'id':ref.get('id'),'name':profile['name'] if profile else ref.get('name','已删除方案'),'modified':bool(modified),
            'deleted':profile is None,'update_available':bool(profile and profile['revision']!=ref.get('revision'))}
