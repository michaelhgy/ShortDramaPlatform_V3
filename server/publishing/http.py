"""HTTP routes for preparation, native publication and plugin local drafts."""
import re
import json
import sqlite3
from http import HTTPStatus
from urllib.parse import parse_qs,urlparse
from .service import PublishingService


def handle(handler,method,path,payload=None):
    if not path.startswith('/api/v2/publishing/'):return False
    from server import v2_file_service as files
    from server.cover_editor import CoverStore
    service=PublishingService(files.connection,files.get_task_details,cover_resolver=CoverStore(files.WORKSPACE,files.connection).cover_info)
    payload=payload or {}
    def reply(status,value):
        body=json.dumps(value,ensure_ascii=False).encode('utf-8')
        handler.send_response(status)
        handler.send_header('Content-Type','application/json; charset=utf-8')
        handler.send_header('Content-Length',str(len(body)))
        handler.send_header('Cache-Control','no-store')
        handler.end_headers();handler.wfile.write(body)
    try:
        cover_match=re.fullmatch(r'/api/v2/publishing/covers/([a-f0-9]{64})\.jpg',path)
        if method=='GET' and cover_match:
            image=service.covers().path(cover_match.group(1)).read_bytes()
            handler.send_response(HTTPStatus.OK)
            handler.send_header('Content-Type','image/jpeg')
            handler.send_header('Content-Length',str(len(image)))
            handler.send_header('Cache-Control','private, max-age=31536000, immutable')
            handler.end_headers();handler.wfile.write(image);return True
        if method=='GET' and path=='/api/v2/publishing/progress-index':
            from .progress import progress_index
            reply(HTTPStatus.OK,progress_index(service));return True
        match=re.fullmatch(r'/api/v2/publishing/tasks/([a-f0-9]+)(?:/([a-z-]+))?',path)
        if not match:raise ValueError('发布准备入口不存在')
        task_id,action=match.groups()
        if method=='GET':
            if action=='execution':result=service.execution(task_id)
            elif action=='publication':result=service.refresh_publication(task_id)
            elif action=='progress':result=service.progress(task_id)
            elif action=='address-book':result=service.address_book(task_id)
            elif action=='profiles':result=service.profile_library(task_id)
            elif action=='history':result=service.profile_history(task_id)
            elif action=='context':result=service.context(task_id,include_videos=False)
            elif not action:result=service.load(task_id)
            else:raise ValueError('发布准备读取入口不存在')
        elif method=='POST':
            if not isinstance(payload,dict):raise ValueError('发布设置内容无效')
            if action=='cover-import':result=service.import_cover(task_id,payload)
            elif action=='settings':result=service.save(task_id,payload)
            elif action=='profile-save':result=service.profile_save(task_id,payload)
            elif action=='profile-delete':result=service.profile_delete(task_id,payload)
            elif action=='profile-capture':result=service.profile_capture(task_id,payload)
            elif action=='profile-preview':result=service.profile_preview(task_id,payload)
            elif action=='connection':result=service.connection_status(task_id)
            elif action=='addresses':result=service.addresses(task_id,payload.get('query',''))
            elif action=='address-save':result=service.save_address(task_id,payload.get('address'),payload.get('default',False))
            elif action=='address-delete':result=service.delete_address(task_id,payload.get('checksum'),payload.get('scope','account'))
            elif action=='dramas':result=service.dramas(task_id,str(payload.get('query') or ''))
            elif action=='binding':result=service.bind(task_id,payload.get('drama'),payload.get('confirmed',False),payload.get('account_only',False),payload.get('mount_source'))
            elif action=='history-delete':
                key=payload.get('key')
                if key not in ('title','video_title','short_title','desc','tags','comment','repost_source'):raise ValueError('历史记录类型无效')
                values=service.read('history',key,service.read('history','title',[]) if key=='short_title' else [])
                service.write('history',key,[v for v in values if v!=payload.get('value')]);result={'deleted':True}
            elif action=='check':result=service.check(task_id)
            elif action=='drafts':result=service.start(task_id)
            elif action=='publish':result=service.publish(task_id)
            elif action=='continue':result=service.continue_publication(task_id,payload.get('keys'))
            elif action=='schedule-retry-preview':result=service.schedule_retry_preview(task_id,payload)
            elif action=='schedule-retry':result=service.schedule_retry(task_id,payload)
            elif action=='republish-prepare':result=service.prepare_republish(task_id)
            elif action=='republish-ready':result=service.confirm_republish(task_id)
            elif action=='republish':result=service.republish(task_id,selected_keys=payload.get('keys'))
            elif action=='task-operation':result=service.manage_publication_tasks(task_id,payload.get('operation'),payload.get('keys'))
            elif action in ('open-draft','adopt-draft'):result=service.draft_assist(task_id,payload.get('key'),action,payload.get('confirmed',False))
            elif action in ('pause','resume','stop'):result=service.action(task_id,action)
            else:raise ValueError('发布操作入口不存在')
        else:raise ValueError('不支持的操作')
        reply(HTTPStatus.OK,result)
    except (ValueError,RuntimeError,OSError) as exc:
        reply(HTTPStatus.BAD_REQUEST,{'error':str(exc)})
    except sqlite3.Error:
        reply(HTTPStatus.SERVICE_UNAVAILABLE,{'error':'发布设置暂时不可用，请稍后重试'})
    return True
