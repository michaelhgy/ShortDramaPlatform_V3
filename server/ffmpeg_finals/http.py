import re
from http import HTTPStatus
from .service import get_composer


def handle(handler,method,path,payload=None):
    root='/api/v3/final-composition'
    if not path.startswith(root):return False
    try:
        if (method=='POST' and path==root+'/diagnostics/export') or (method=='GET' and path==root+'/diagnostics/catalog'):
            from server.v2_file_service import require_configured_paths
            workspace,data_root=require_configured_paths()
            if method=='GET':
                from .diagnostic_selection import catalog
                value=catalog(data_root/'fg')
            else:
                from .diagnostic_export import export_diagnostics
                value=export_diagnostics(workspace,data_root,payload)
            handler._json(HTTPStatus.OK,value)
            return True
        composer=get_composer();payload=payload or {}
        if method=='GET' and path==root:value=composer.snapshot()
        elif method=='POST' and path==root+'/automatic':value=composer.set_automatic(payload.get('enabled'))
        elif method=='POST' and path==root+'/order':
            from contextlib import closing
            from server.production_order import move_task
            with closing(composer.lib.business_connection()) as conn:value=move_task(conn,str(payload.get('task_id')or''),str(payload.get('target_id')or''),str(payload.get('placement')or''))
            composer.wake.set()
        elif method=='POST' and path==root+'/regenerate':value=composer.regenerate(task_id=str(payload.get('task_id') or ''))
        elif method=='POST' and (match:=re.fullmatch(re.escape(root)+r'/jobs/([a-f0-9]{32})/regenerate',path)):
            value=composer.regenerate(identity=match[1])
        elif method=='POST' and path==root+'/batches':value=composer.create(str(payload.get('task_id') or ''))
        elif method=='POST' and path in (root+'/pause',root+'/resume'):value=composer.action(path.rsplit('/',1)[1])
        elif method=='POST' and (match:=re.fullmatch(re.escape(root)+r'/jobs/([a-f0-9]{32})/(retry|cancel)',path)):
            value=composer.action(match[2],match[1])
        else:handler._json(HTTPStatus.NOT_FOUND,{'error':'成片操作不存在'});return True
        handler._json(HTTPStatus.OK,value)
    except Exception as exc:handler._json(HTTPStatus.BAD_REQUEST,{'error':str(exc)})
    return True
