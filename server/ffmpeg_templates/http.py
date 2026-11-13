import re
from http import HTTPStatus
from .service import get_maker
from .config import RANGES
from .renderer import STICKERS,EFFECTS,BORDERS,read


def handle(handler,method,path,payload=None):
    if not path.startswith('/api/v3/template-generation'):return False
    try:
        maker=get_maker();base='/api/v3/template-generation';payload=payload or {}
        if method=='GET' and path==base+'/config':
            from .parameter_info import field_info
            from .fullscreen_layers import sticker_catalog
            inventory=read(STICKERS/'sources/usable_catalog.json')
            value={'config':maker.config(),'limits':RANGES,'suggested_ranges':RANGES,'fields':field_info(),'profile':'1080×2400 / 30fps',
                   'library':{'effects':len(read(EFFECTS/'catalog.json')['assets']),'borders':len(read(BORDERS/'catalog.json')['assets']),'fullscreen_stickers':len(sticker_catalog())}}
        elif method=='POST' and path==base+'/config':value={'config':maker.save_config(payload.get('config'))}
        elif method=='GET' and path==base:value=maker.snapshot()
        elif method=='POST' and path==base+'/batches':value=maker.create(payload.get('count'),payload.get('request_id'))
        elif method=='POST' and path in [base+'/pause',base+'/resume']:value=maker.pause(path.endswith('/pause'))
        elif (match:=re.fullmatch(re.escape(base)+r'/jobs/([a-f0-9]{32})/(retry|cancel|preview)',path)):
            job,action=match.groups()
            if method=='GET' and action=='preview':
                from server.template_library_http import stream_video
                stream_video(handler,maker.preview(job));return True
            if method!='POST' or action not in {'retry','cancel'}:raise ValueError('不支持的模板操作')
            value=getattr(maker,action)(job)
        else:handler._json(HTTPStatus.NOT_FOUND,{'error':'模板制作接口不存在'});return True
        handler._json(HTTPStatus.OK,value)
    except Exception as exc:
        handler._json(HTTPStatus.BAD_REQUEST,{'error':str(exc)})
    return True
