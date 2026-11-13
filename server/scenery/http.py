import os,re
from http import HTTPStatus
from .service import get_library
from server.template_library_http import stream_video


def handle(handler,method,path,payload=None):
    base='/api/v3/scenery'
    if not path.startswith(base):return False
    try:
        lib=get_library();payload=payload or {}
        if method=='GET' and path==base:value=lib.snapshot()
        elif method=='POST' and path==base+'/scan':
            lib.clean_exhausted();value=lib.scan()
        elif method=='POST' and path==base+'/open':
            folder=lib.original if payload.get('kind')=='original' else lib.ready
            folder.mkdir(parents=True,exist_ok=True);os.startfile(str(folder));value={'opened':True}
        elif (match:=re.fullmatch(base+r'/originals/([a-f0-9]{64})(/media)?',path)) and method=='GET':
            if match[2]:stream_video(handler,lib.raw(match[1])[1]);return True
            value=lib.details(match[1])
        elif (match:=re.fullmatch(base+r'/assets/([a-f0-9]{32})/media',path)) and method=='GET':
            a=next((a for a in lib.ready_assets() if a['id']==match[1] and a['valid']),None)
            if not a:raise ValueError('素材已清理或文件发生变化')
            from pathlib import Path
            stream_video(handler,Path(a['path']));return True
        elif method=='POST' and path==base+'/jobs':value=lib.create(payload.get('source_id'),payload.get('crops'),payload.get('request_id'))
        elif method=='POST' and path==base+'/jobs/batch':value=lib.create_batch(payload.get('items'))
        elif (match:=re.fullmatch(base+r'/originals/([a-f0-9]{64})/delete',path)) and method=='POST':value=lib.delete_original(match[1])
        elif (match:=re.fullmatch(base+r'/assets/([a-f0-9]{32})/delete',path)) and method=='POST':value=lib.delete_asset(match[1])
        elif method=='POST' and path in (base+'/pause',base+'/resume'):value=lib.action(path.rsplit('/',1)[1])
        elif (match:=re.fullmatch(base+r'/jobs/([a-f0-9]{32})/(retry|cancel)',path)) and method=='POST':value=lib.action(match[2],match[1])
        else:raise ValueError('风景处理接口不存在')
        handler._json(HTTPStatus.OK,value)
    except Exception as exc:handler._json(HTTPStatus.BAD_REQUEST,{'error':str(exc)})
    return True
