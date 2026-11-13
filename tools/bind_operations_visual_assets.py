"""Replace development account identities and work artwork using local catalog data.

No media is edited. Statistics are regrouped within the same theater when there
are fewer imported identities than generated profiles. The CLI backs up first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

SOURCE = 'development_seed'
TABLES = ['v3_video_accounts', 'v3_video_account_daily', 'v3_video_posts', 'v3_video_post_daily',
          'v3_video_account_diagnostics', 'v3_video_post_punishments', 'v3_revenue_account_periods', 'v3_revenue_details']


def identifier(text):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'v3-visual-assets:'+text).hex


def json_value(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def insert(conn, table, row):
    columns = list(row)
    conn.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", list(row.values()))


def regroup(rows, keys, fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    result = []
    for group in groups.values():
        row = dict(group[0])
        if len(group) > 1:
            for field in fields:
                values = [r[field] for r in group if r[field] is not None]
                if field == 'amount':
                    row[field] = format(sum((Decimal(str(v)) for v in values), Decimal(0)), '.2f') if values else None
                else:
                    row[field] = sum(values) if values else 0
            states = [r.get('data_state') for r in group]
            row['data_state'] = 'record' if 'record' in states else 'confirmed_zero' if 'confirmed_zero' in states else states[0]
            field = 'payload_json' if 'payload_json' in row else 'raw_result_json'
            original = json.loads(row.get(field) or '{}')
            original['visual_merged_rows'] = [dict(id=r['id'], state=r.get('data_state'), account_id=r.get('_original_account')) for r in group]
            row[field] = json_value(original)
        result.append({k: v for k, v in row.items() if not k.startswith('_')})
    return result


def bind(conn):
    accounts = {r['id']: dict(r) for r in conn.execute('SELECT * FROM accounts')}
    fake = sorted((a for a in accounts.values() if a['channel_id'].startswith('dev-channels-')), key=lambda a: a['id'])
    if not fake:
        return {'changed': False, 'reason': 'no generated identities remain'}
    profiles = {r[0] for r in conn.execute('SELECT DISTINCT account_id FROM v3_video_account_daily WHERE source_kind=?', (SOURCE,))}
    candidates = [accounts[r['account_id']] for r in conn.execute('SELECT account_id,path FROM v3_catalog_avatars')
                  if r['account_id'] in accounts and r['account_id'] not in profiles and Path(r['path']).is_file()
                  and not accounts[r['account_id']]['channel_id'].startswith('dev-')]
    candidates.sort(key=lambda a: a['id'])
    if not candidates:
        raise ValueError('没有尚未绑定统计、且有本地头像的真实账号，未修改数据库。')
    by_theater = defaultdict(list)
    for source in fake:
        by_theater[source['theater_id']].append(source)
    destinations = defaultdict(list)
    groups = sorted(by_theater)
    if len(candidates) < len(groups):
        raise ValueError('有头像的账号不足以保留所有剧场分布，未修改数据库。')
    assigned = 0
    while assigned < min(len(candidates), len(fake)):
        for tid in groups:
            if assigned >= min(len(candidates), len(fake)):
                break
            if len(destinations[tid]) < len(by_theater[tid]):
                target = dict(candidates[assigned])
                target['theater_id'] = tid
                destinations[tid].append(target)
                assigned += 1
    mapping = {aid: accounts[aid] for aid in profiles if aid in accounts and not accounts[aid]['channel_id'].startswith('dev-')}
    for tid, sources in by_theater.items():
        for i, source in enumerate(sources):
            mapping[source['id']] = destinations[tid][i % len(destinations[tid])]
    covers = [dict(r) for r in conn.execute('''SELECT d.id,d.current_name,p.cover_path
        FROM dramas d JOIN drama_profiles p ON p.drama_id=d.id WHERE p.cover_path<>'' ORDER BY d.id''') if Path(r['cover_path']).is_file()]
    if not covers:
        raise ValueError('资料库没有可用封面的剧集，未修改数据库。')
    rows = {t: [dict(r) for r in conn.execute(f'SELECT * FROM {t} WHERE source_kind=? ORDER BY id', (SOURCE,))] for t in TABLES}
    attempts = [dict(r) for r in conn.execute('SELECT * FROM v2_revenue_collection_attempts WHERE adapter_key=?', (SOURCE,))]
    revenues = [dict(r) for r in conn.execute('''SELECT d.* FROM v2_daily_revenues d
        JOIN v2_revenue_collection_attempts a ON a.id=d.source_attempt_id WHERE a.adapter_key=?''', (SOURCE,))]
    totals_before = {t: sum(Decimal(str(r.get('view', r.get('amount') or r.get('gross_revenue') or 0))) for r in rows[t]) for t in TABLES}
    stamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='microseconds')
    post_assets = {}
    offsets = {aid: i for i, aid in enumerate(sorted(mapping))}
    for i, row in enumerate(sorted(rows['v3_video_posts'], key=lambda r: r['post_id'])):
        cover = covers[(i // 4) % len(covers)]
        meta = json.loads(row['payload_json'] or '{}')
        episode = int(meta.get('episode') or 1)
        meta.update(drama_id=cover['id'], drama_name=cover['current_name'], file_name=f"{cover['current_name']}-{episode}.mp4", visual_catalog_binding=True)
        row['payload_json'] = json_value(meta)
        row['post_time'] = (datetime.fromisoformat(row['post_time'])+timedelta(minutes=offsets[row['account_id']])).isoformat(sep=' ')
        post_assets[row['post_id']] = (cover, row['post_time'])
    for table, values in rows.items():
        for row in values:
            original_id = row['account_id']
            target = mapping[original_id]
            row['_original_account'] = original_id
            row['account_id'] = target['id']
            if 'uid' in row:
                row['uid'] = target['channel_id']
            if 'account_name' in row:
                row['account_name'] = target['nickname']
            if 'theater_id' in row:
                row['theater_id'] = target['theater_id']
            if 'fetched_at' in row:
                row['fetched_at'] = stamp
            if 'collected_at' in row:
                row['collected_at'] = stamp
            if table == 'v3_video_post_punishments' and row['post_id_or_export_id'] in post_assets:
                row['publish_time'] = post_assets[row['post_id_or_export_id']][1]
            if table == 'v3_revenue_details' and row['source_video_id'] in post_assets:
                cover = post_assets[row['source_video_id']][0]
                row['source_drama_name'], row['matched_drama_id'] = cover['current_name'], cover['id']
    rows['v3_video_account_daily'] = regroup(rows['v3_video_account_daily'], ['account_id','stat_date','source_kind'],
        ['view','fans_total','fans_add','fans_net','fans_reduce','like_count','favorite_count','comment_count','forward_count'])
    rows['v3_revenue_account_periods'] = regroup(rows['v3_revenue_account_periods'], ['account_id','theater_id','period_label','period_type','source_kind'], ['amount'])
    rows['v3_video_accounts'] = regroup(rows['v3_video_accounts'], ['account_id','snapshot_date','source_kind'], ['fans_total'])
    rows['v3_video_account_diagnostics'] = regroup(rows['v3_video_account_diagnostics'], ['account_id','snapshot_date','source_kind'], ['abnormal_post_count'])
    for row in rows['v3_video_account_diagnostics']:
        row['abnormal'] = int(row['abnormal_post_count'] > 9)
    totals_after = {t: sum(Decimal(str(r.get('view', r.get('amount') or r.get('gross_revenue') or 0))) for r in rows[t]) for t in TABLES}
    if totals_before != totals_after:
        raise ValueError('归并后统计总量不一致，整批回滚。')
    # All mutations start after preparation and validation.
    for tid in destinations:
        for target in destinations[tid]:
            conn.execute('UPDATE accounts SET theater_id=?,updated_at=? WHERE id=?', (tid,stamp,target['id']))
    conn.execute('''DELETE FROM v2_daily_revenues WHERE source_attempt_id IN
        (SELECT id FROM v2_revenue_collection_attempts WHERE adapter_key=?)''', (SOURCE,))
    for row in attempts:
        target = mapping[row['account_id']]
        conn.execute('UPDATE v2_revenue_collection_attempts SET account_id=?,theater_id=? WHERE id=?',
                     (target['id'],target['theater_id'],row['id']))
    summary = defaultdict(list)
    for row in revenues:
        target = mapping[row['account_id']]
        row['account_id'], row['theater_id'] = target['id'], target['theater_id']
        summary[(target['id'],row['revenue_date'])].append(row)
    for (aid, day), values in summary.items():
        total = format(sum((Decimal(r['amount']) for r in values),Decimal(0)),'.2f')
        attempt_id = identifier(f'aggregate-attempt:{aid}:{day}')
        template = dict(next(r for r in attempts if r['id']==values[0]['source_attempt_id']))
        template.update(id=attempt_id,account_id=aid,theater_id=values[0]['theater_id'],amount=total,collection_status='success',error_message='',collected_at=stamp)
        insert(conn,'v2_revenue_collection_attempts',template)
        row = dict(values[0]); row.update(amount=total,source_attempt_id=attempt_id,updated_at=stamp)
        insert(conn,'v2_daily_revenues',row)
    for table, values in rows.items():
        conn.execute(f'DELETE FROM {table} WHERE source_kind=?',(SOURCE,))
        for row in values:
            insert(conn,table,{k:v for k,v in row.items() if not k.startswith('_')})
    for source in fake:
        aid = source['id']
        conn.execute('UPDATE v2_change_events SET account_id=? WHERE account_id=?',(mapping[aid]['id'],aid))
        # Abort if a newly-created, unreviewed dependency appeared during planning.
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            if table in ('accounts','v2_change_events'):
                continue
            if 'account_id' in {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}:
                if conn.execute(f'SELECT 1 FROM {table} WHERE account_id=? LIMIT 1',(aid,)).fetchone():
                    raise ValueError(f'虚构账号仍被 {table} 引用，未删除且整批回滚。')
        conn.execute('DELETE FROM accounts WHERE id=?',(aid,))
    return {'changed':True, 'removed_generated_accounts':len(fake), 'real_accounts':conn.execute('SELECT count(*) FROM accounts').fetchone()[0],
            'bound_profiles':len(set(t['id'] for t in mapping.values())), 'imported_accounts':assigned,
            'catalog_dramas_used':len({v[0]['id'] for v in post_assets.values()}), 'works':len(post_assets),
            'after_rows':{t: len(v) for t,v in rows.items()}, 'preserved_totals':{t:str(v) for t,v in totals_after.items()},
            'account_mapping':{aid: {'account_id':t['id'],'nickname':t['nickname'],'channel_id':t['channel_id'],'theater_id':t['theater_id']} for aid,t in mapping.items()}}


def main():
    parser=argparse.ArgumentParser(description='为开发数据绑定真实账号外观和已有剧集封面，不处理媒体文件')
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if not args.database.is_file(): parser.error('数据库必须已存在。')
    conn=sqlite3.connect(args.database,timeout=30);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA foreign_keys=ON')
    backup=args.database.with_name(args.database.name+'.before-visual-bind-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    try:
        with sqlite3.connect(backup) as target: conn.backup(target)
        conn.execute('BEGIN IMMEDIATE')
        result=bind(conn)
        conn.commit()
        result['backup']=str(backup)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='account_mapping'},ensure_ascii=True))
    except Exception:
        conn.rollback();raise
    finally:
        conn.close()


if __name__=='__main__': main()
