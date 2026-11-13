"""Video declaration payloads; IDs and fields match the native Channels UI."""
import re
from datetime import datetime,timedelta,timezone
from .regions import REGIONS

SHANGHAI=timezone(timedelta(hours=8))
SHORT_TITLE=re.compile(r'^[\u2103\u4E00-\u9FA5A-Za-z0-9《》"“”:：+?？%\s]+$')


def tag_info(group,strict=True):
    kind=group.get('tag_type',0)
    if type(kind) is not int or kind not in (0,1,2,3,5,7,8):raise ValueError('请选择有效的视频声明')
    result={'tagType':kind}
    if kind==7:
        source=str(group.get('repost_source') or '').strip()
        if len(source)>500:raise ValueError('转载来源最多500字')
        if strict and not source:raise ValueError('选择内容为转载时，请填写转载来源')
        result['repostSource']=source
    if kind==5:
        date=group.get('shoot_date') or ''
        codes=group.get('shoot_region_codes') or []
        if not isinstance(codes,list) or len(codes)>3:raise ValueError('拍摄地点无效，请重新选择')
        options=REGIONS
        for code in codes:
            region=next((r for r in options if type(code) is int and r['code']==code),None)
            if not region:raise ValueError('拍摄地点无效，请重新选择')
            options=region.get('sub',[])
        shoot={}
        if date:
            try:parsed=datetime.strptime(date,'%Y-%m-%d').replace(tzinfo=SHANGHAI)
            except (ValueError,TypeError):raise ValueError('请选择有效的拍摄日期') from None
            if parsed.date()>datetime.now(SHANGHAI).date():raise ValueError('拍摄日期不能晚于今天')
            shoot['postTimestamp']=str(int(parsed.timestamp()))
        if strict and (not date or not codes):raise ValueError('选择内容为自行拍摄时，请填写拍摄日期和地点')
        shoot.update(dict(zip(('countryCode','provinceCode','cityCode'),codes)))
        result['shootInfo']=shoot
    return result
