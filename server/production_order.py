"""One persistent account/drama card order for production and FFmpeg dispatch."""
from datetime import datetime


def ordered_tasks(conn):
    columns={r[1] for r in conn.execute('PRAGMA table_info(production_tasks)')}
    if not columns:return []
    names=['id']+[key for key in ('manual_order','planned_publish_at','created_at','release_status','cleanup_status') if key in columns]
    rows=[dict(zip(names,row)) for row in conn.execute('SELECT '+','.join(names)+' FROM production_tasks')]
    rows=[r for r in rows if r.get('cleanup_status','active')=='active']
    return sorted(rows,key=lambda r:(r.get('release_status')=='registered',int(r.get('manual_order') or 0) if int(r.get('manual_order') or 0)>0 else 10**12,str(r.get('planned_publish_at') or '')[:10] or '9999-12-31',str(r.get('created_at') or ''),r['id']))


def move_task(conn,task_id,target_id,placement):
    if placement not in ('before','after'):raise ValueError('请选择有效的放置位置')
    conn.execute('BEGIN IMMEDIATE')
    order=[r['id'] for r in ordered_tasks(conn) if r.get('release_status')!='registered']
    if task_id not in order or target_id not in order:raise ValueError('只能调整当前未登记发布的任务，请刷新列表')
    if task_id!=target_id:
        order.remove(task_id);index=order.index(target_id)+(placement=='after');order.insert(index,task_id)
    stamp=datetime.now().isoformat(timespec='seconds')
    for index,identity in enumerate(order,1):conn.execute('UPDATE production_tasks SET manual_order=?,updated_at=? WHERE id=?',(index,stamp,identity))
    conn.commit()
    return {'order':[r['id'] for r in ordered_tasks(conn)]}
