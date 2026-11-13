"""Automatic video ownership and one continuous schedule for a task."""
import copy
import uuid
import re
from datetime import datetime,timedelta

KINDS={'普通视频':'normal','正剧视频':'normal','羊':'sheep','羊视频':'sheep','羊头视频':'sheep'}


def prepare_settings(settings,videos,location=None):
    value=copy.deepcopy(settings)
    groups=value.get('groups') or []
    for group in groups:
        group.setdefault('kind',KINDS.get(group.get('name'),'custom'))
        group.setdefault('cover_mode','auto')
        group.setdefault('cover_source','custom' if group['cover_mode']=='custom' else 'auto')
        group.setdefault('custom_cover_id','')
        group.setdefault('short_title',group.get('title',''))
        group.setdefault('video_title','')
    # The first workbench used an unnamed default group and inferred "manual"
    # from it. That inference is not evidence of a user's ownership adjustment.
    if (not value.get('assignment_confirmed') and len(groups)==1
            and groups[0]['kind']=='custom' and re.fullmatch(r'分组\s*\d+',groups[0].get('name',''))):
        selected=[v for v in videos if v['id'] in groups[0].get('video_ids',[])]
        groups[0]['kind']='sheep' if selected and all(v['sheep'] for v in selected) else 'normal'
        value['assignment_mode']='auto'
    mode=value.get('assignment_mode') or ('manual' if any(g['kind']=='custom' for g in groups) else 'auto')
    if mode not in ('auto','manual'):raise ValueError('视频分组方式无效')
    if mode=='auto':
        prototype=copy.deepcopy(groups[0]) if groups else None
        for sheep,kind,name in ((False,'normal','正剧视频'),(True,'sheep','羊视频')):
            ids=[v['id'] for v in videos if bool(v['sheep'])==sheep]
            matches=[g for g in groups if g['kind']==kind]
            if len(matches)>1:raise ValueError('存在重复的自动分组，请在特殊调整中核对')
            group=matches[0] if matches else None
            if group is None and ids:
                group={'id':uuid.uuid4().hex,'name':name,'kind':kind,'video_ids':[],
                    'cover_mode':'auto','title':'','desc':'','tags':[],'schedule_type':'now','start_time':'','interval':3,
                    'copies':1,'order':'round','location':location,'mount_required':not sheep,'tag_type':0,'original':False,'comment':'','comment_top':False}
                if prototype:
                    group.update({k:copy.deepcopy(v) for k,v in prototype.items() if k not in ('id','name','kind','video_ids','mount_required')})
                group.setdefault('short_title',group.get('title',''))
                group.setdefault('video_title','')
                groups.append(group)
            if group is not None:group.update(name=name,video_ids=ids)
        for g in groups:
            if g['kind']=='custom':g['video_ids']=[]
    value['assignment_mode']=mode
    normal=next((g for g in groups if g['kind']=='normal'),None)
    sheep=next((g for g in groups if g['kind']=='sheep'),None)
    # Preserve explicitly different old addresses until the operator enables sync.
    sync=value.get('sync_location',not (normal and sheep and normal.get('location')!=sheep.get('location')))
    if not isinstance(sync,bool):raise ValueError('地址同步选项无效')
    value['sync_location']=sync
    source=normal if normal is not None else sheep
    if sync and source is not None:
        for g in groups:
            if g['kind'] in ('normal','sheep'):g['location']=copy.deepcopy(source.get('location'))
    group_order=value.get('group_order','normal_first')
    if group_order not in ('normal_first','sheep_first'):raise ValueError('两组发布顺序无效')
    first='normal' if group_order=='normal_first' else 'sheep'
    groups.sort(key=lambda g:0 if g['kind']==first else 1 if g['kind'] in ('normal','sheep') else 2)
    first_group=groups[0] if groups else {}
    schedule=value.get('schedule') or {k:first_group.get(k,default) for k,default in [('schedule_type','now'),('start_time',''),('interval',3)]}
    value.update(groups=groups,schedule=schedule,group_order=group_order)
    return schedule_groups(value)


def schedule_groups(settings):
    value=copy.deepcopy(settings)
    schedule=value.get('schedule')
    if not schedule:return value  # Legacy in-process callers.
    mode=schedule.get('schedule_type','now');start=schedule.get('start_time','');interval=schedule.get('interval',3)
    if mode not in ('now','timing','localTiming'):raise ValueError('请选择有效的时间方式')
    if isinstance(interval,bool) or not isinstance(interval,(int,float)) or int(interval)!=interval or not 0<=interval<=10080:raise ValueError('发布间隔须为0–10080的整数分钟')
    base=None
    if start and mode!='now':
        try:base=datetime.strptime(start,'%Y-%m-%d %H:%M')
        except ValueError:raise ValueError('开始日期和时间格式无效') from None
    offset=0
    for group in value['groups']:
        group.update(schedule_type=mode,interval=interval,start_time=(base+timedelta(minutes=offset*interval)).strftime('%Y-%m-%d %H:%M') if base else '')
        offset+=len(group['video_ids'])*int(group.get('copies',1))
    if offset>3000:raise ValueError('单次草稿条目过多，请减少份数或分批处理')
    return value
