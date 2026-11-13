"""Per-task mount choices and distinct native component payloads."""
import json

SOURCES=('mini_drama','channels_drama','plugin')


def validate_source(value):
    if value not in SOURCES:raise ValueError('请选择小程序、视频号或插件挂载方式')
    return value


def task_mount(conn,task_id):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v3_catalog_task_mounts'").fetchone():return {}
    row=conn.execute('SELECT source,external_id,content FROM v3_catalog_task_mounts WHERE task_id=?',(task_id,)).fetchone()
    return {'source':row['source'],'external_id':row['external_id'],'snapshot':json.loads(row['content'])} if row else {}


def resolve_source(settings,mount):
    return validate_source(settings.get('mount_source') or mount.get('source') or 'channels_drama')


def binding_key(drama_id,source,scope):
    return drama_id+(':' if source=='channels_drama' else ':'+source+':')+scope


def component(source,drama):
    if source=='mini_drama':return {'type':5,'urlType':12,'drama':drama,'_mergeObjectDesc':{'component':{'id':drama['id'],'type':4}}}
    if source=='channels_drama':return {'type':8,'drama':drama,'_mergeObjectDesc':{'component':{'id':drama['id'],'type':8,'title':drama['name']}}}
    return None
