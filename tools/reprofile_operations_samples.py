"""Replace only development_seed statistics using paired historical observations.

Explicit CLI; never collects from a platform or edits media/catalog identities.
The reference database is read-only. The caller owns the write transaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import statistics
import uuid
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

SOURCE = 'development_seed'
MODEL = 'qingning-paired-observations-v1'
BEIJING = timezone(timedelta(hours=8))
TABLES = ['v3_video_accounts', 'v3_video_account_daily', 'v3_video_posts', 'v3_video_post_daily',
          'v3_video_account_diagnostics', 'v3_video_post_punishments',
          'v3_revenue_account_periods', 'v3_revenue_details']


def key(value):
    return uuid.uuid5(uuid.NAMESPACE_URL, MODEL + ':' + value).hex


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def money(value):
    return format(Decimal(value) / 100, '.2f')


def insert_many(conn, table, rows):
    if not rows:
        return
    columns = list(rows[0])
    conn.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                     [tuple(row[c] for c in columns) for row in rows])


def summarize(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    return dict(count=len(values), zero=sum(v == 0 for v in values), median=statistics.median(values),
                p90=values[int((len(values)-1)*.9)], p99=values[int((len(values)-1)*.99)],
                maximum=max(values), total=round(sum(values), 2))


def load_reference(path):
    """Do not use drama_views, or interpret first observation as a real publish date."""
    profiles = defaultdict(list)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        rows = list(conn.execute('''SELECT d.account_id,d.source_video_id,d.revenue_date,d.video_views,d.gross_revenue
            FROM v2_revenue_video_details d JOIN accounts a ON a.id=d.account_id
            JOIN theaters t ON t.id=a.theater_id
            WHERE a.created_at<'2026-10-01' AND t.name LIKE '%青柠%'
            ORDER BY d.account_id,d.source_video_id,d.revenue_date'''))
        grouped = defaultdict(list)
        for row in rows:
            if row['video_views'] < 0 or cents(row['gross_revenue']) < 0:
                raise ValueError('参考记录含负播放或负收益，未修改目标数据库。')
            grouped[(row['account_id'], row['source_video_id'])].append(row)
        for (aid, vid), observations in grouped.items():
            first = date.fromisoformat(observations[0]['revenue_date'])
            points = {(date.fromisoformat(r['revenue_date'])-first).days:
                      (int(r['video_views']), cents(r['gross_revenue'])) for r in observations}
            profiles[aid].append(dict(account=aid, video=vid, first=str(first), points=points))
    if not profiles:
        raise ValueError('参考库中没有最早一批青柠账号的视频播放与收益明细，未修改目标数据库。')
    return dict(profiles), dict(accounts=len(profiles), videos=len(grouped), observation_rows=len(rows),
        views=summarize([int(r['video_views']) for r in rows]),
        revenue=summarize([float(r['gross_revenue']) for r in rows]))


def protected_digest(conn):
    queries = {t: f'SELECT * FROM {t} ORDER BY id' for t in ['accounts', 'theaters', 'dramas', 'drama_profiles']}
    queries['avatars'] = 'SELECT * FROM v3_catalog_avatars ORDER BY account_id'
    for table in TABLES:
        queries[table] = f"SELECT * FROM {table} WHERE source_kind<>'{SOURCE}' ORDER BY id"
    queries['original_attempts'] = f"SELECT * FROM v2_revenue_collection_attempts WHERE adapter_key<>'{SOURCE}' ORDER BY id"
    queries['original_totals'] = f'''SELECT d.* FROM v2_daily_revenues d WHERE NOT EXISTS
        (SELECT 1 FROM v2_revenue_collection_attempts a WHERE a.id=d.source_attempt_id AND a.adapter_key='{SOURCE}') ORDER BY d.id'''
    queries['original_details'] = 'SELECT * FROM v2_revenue_video_details ORDER BY id'
    return {name: hashlib.sha256(packed([tuple(r) for r in conn.execute(sql)]).encode()).hexdigest()
            for name, sql in queries.items()}


def reprofile(conn, profiles, end, days=60):
    if not 7 <= days <= 90:
        raise ValueError('天数须为7—90。')
    if not profiles or not any(profiles.values()):
        raise ValueError('没有可用参考样本，未执行替换。')
    originals = {t: [dict(r) for r in conn.execute(f'SELECT * FROM {t} WHERE source_kind=? ORDER BY id', (SOURCE,))] for t in TABLES}
    posts = originals['v3_video_posts']
    before_work_views = summarize([r['view'] for r in posts])
    if not posts or any(not originals[t] for t in TABLES if t != 'v3_video_post_punishments'):
        raise ValueError('目标库缺少现有开发数据，未执行替换。')
    before = protected_digest(conn)
    foreign_before = {tuple(r) for r in conn.execute('PRAGMA foreign_key_check')}
    accounts = {r['id']: dict(r) for r in conn.execute('SELECT a.*,t.name AS theater_name FROM accounts a JOIN theaters t ON t.id=a.theater_id')}
    if any(p['account_id'] not in accounts for p in posts):
        raise ValueError('开发作品有无法关联的账号，未修改。')
    if conn.execute('''SELECT count(*) FROM v2_revenue_video_details d JOIN v2_revenue_collection_attempts a
        ON a.id=d.attempt_id WHERE a.adapter_key=?''', (SOURCE,)).fetchone()[0]:
        raise ValueError('开发采集记录被原始视频明细引用，不能安全替换。')
    rng = random.Random(20261101)
    start = end-timedelta(days=days-1)
    dates = [start+timedelta(days=i) for i in range(days)]
    stamp = datetime.now(BEIJING).isoformat(timespec='microseconds')
    template = {t: originals[t][0] for t in TABLES if originals[t]}
    output = {t: [] for t in TABLES}
    runs = {domain: key(f'run:{domain}:{end}:{days}') for domain in ['video', 'revenue']}
    by_account = defaultdict(list)
    for post in posts:
        by_account[post['account_id']].append(post)
    all_profiles = [p for group in profiles.values() for p in group]
    donors = sorted(profiles)
    post_times = {}
    totals = defaultdict(lambda: defaultdict(int))
    revenue = defaultdict(int)
    assumptions = dict(interactions='synthetic_not_calibrated', fans='synthetic_not_calibrated',
                       risk='existing_synthetic_assignments_retained', drama_views='unused')
    account_plan = []
    metric_names = ['view', 'like_count', 'comment_count', 'forward_count', 'favorite_count', 'fans_add']
    for ai, (aid, works) in enumerate(sorted(by_account.items())):
        account = accounts[aid]
        inactive = account['status'] == '停用'
        last_publish = end-timedelta(days=rng.randint(10, min(30, days-1))) if inactive and days>10 else end
        first_publish = min(start+timedelta(days=rng.randint(0, max(0, days//4))), last_publish)
        slots = [first_publish+timedelta(days=i) for i in range((last_publish-first_publish).days+1)]
        weights = [0 if rng.random()<.28 else rng.gammavariate(.6, 1) for _ in slots]
        if not any(weights):
            weights[0] = 1
        donor = aid if aid in profiles else donors[ai % len(donors)]
        chosen_days = rng.choices(slots, weights=weights, k=len(works))
        if not inactive and ai % 3 == 0:
            chosen_days[0] = end  # Current-month visual data, without forcing every account to post daily.
        used_times = set()
        for post, published in zip(sorted(works, key=lambda p:p['post_id']), chosen_days):
            profile = rng.choice(profiles[donor] if rng.random()<.85 else all_profiles)
            gain = rng.uniform(.7, 1.35)
            latest_second = 23*3600
            if published == datetime.now(BEIJING).date():
                now = datetime.now(BEIJING)
                latest_second = max(1,now.hour*3600+now.minute*60+now.second)
            earliest_second = min(8*3600,latest_second-1)
            second = earliest_second + int(rng.random()*(latest_second-earliest_second))
            while (published, second) in used_times:
                second += 1
            used_times.add((published, second))
            published_at = datetime.combine(published, datetime.min.time())+timedelta(seconds=second)
            post_times[post['post_id']] = str(published_at)
            meta = json.loads(post['payload_json'] or '{}')
            meta.update(generated=True, model=MODEL, reference_account_id=profile['account'],
                        reference_video_id=profile['video'], reference_first_observed_date=profile['first'],
                        simulated_publish_date=True, sample_scale=gain, assumptions=assumptions)
            cumulative = defaultdict(int)
            # Keep observed calendar spacing; never compress a long data gap into consecutive days.
            last_age = min((end-published).days, max(profile['points'])+7)
            for age in range(last_age+1):
                day = published+timedelta(days=age)
                measured = age in profile['points']
                views, amount = profile['points'].get(age, (0, 0))
                views, amount = round(views*gain), round(amount*gain)
                if not measured and age>max(profile['points']) and rng.random()<.25:
                    views = rng.randint(0, 3)  # Small synthetic tail, never inferred revenue.
                metrics = dict(view=views, like_count=round(views*rng.uniform(.002,.03)),
                    comment_count=round(views*rng.uniform(0,.0015)), forward_count=round(views*rng.uniform(0,.006)),
                    favorite_count=round(views*rng.uniform(0,.004)), fans_add=round(views*rng.uniform(.0001,.002)))
                for name, value in metrics.items():
                    totals[(aid, day)][name] += value
                    cumulative[name] += value
                revenue[(aid, day)] += amount
                row = dict(template['v3_video_post_daily'])
                row.update(id=key(f'post-day:{post["post_id"]}:{day}'), post_id=post['post_id'], uid=account['channel_id'],
                    account_id=aid, stat_date=str(day), **metrics, metric_grain='daily',
                    data_state='record' if views else 'confirmed_zero', freshness_state='simulated',
                    collection_run_id=runs['video'], fetched_at=stamp,
                    payload_json=packed(dict(generated=True,model=MODEL,paired_observation=measured,synthetic_gap=not measured)))
                output['v3_video_post_daily'].append(row)
                if account['theater_name'] != '触摸剧场':
                    detail = dict(template['v3_revenue_details'])
                    detail.update(id=key(f'detail:{post["post_id"]}:{day}'),account_id=aid,theater_id=account['theater_id'],
                        detail_date=str(day),source_video_id=post['post_id'],source_drama_name=meta.get('drama_name',''),
                        video_views=views,drama_views=0,gross_revenue=money(amount),source_rank=0,
                        matched_drama_id=meta.get('drama_id',''),match_status='matched',data_state='record' if amount else 'confirmed_zero',
                        freshness_state='simulated',include_in_analysis=1,source_attempt_id='',collection_run_id=runs['revenue'],
                        collected_at=stamp,raw_result_json=packed(dict(generated=True,model=MODEL,paired_observation=measured,drama_views_unused=True)))
                    output['v3_revenue_details'].append(detail)
            post.update(uid=account['channel_id'],account_name=account['nickname'],post_time=str(published_at),
                view=cumulative['view'],like_count=cumulative['like_count'],comment_count=cumulative['comment_count'],
                forward_count=cumulative['forward_count'],love_count=cumulative['favorite_count'],fans_add=cumulative['fans_add'],
                full_view=round(rng.uniform(.08,.65),4),view_time=round(rng.uniform(10,70),2),snapshot_date=str(end),
                collection_run_id=runs['video'],fetched_at=stamp,payload_json=packed(meta))
            output['v3_video_posts'].append(post)
        account_plan.append(dict(account_id=aid,donor_account_id=donor,works=len(works),inactive=inactive,
                                 first_publish=str(min(chosen_days)),last_publish=str(max(chosen_days))))

    # Previous month is still unsettled in this development scenario, so recent windows work at month rollover.
    unsettled_start = (end.replace(day=1)-timedelta(days=1)).replace(day=1)
    attempts, legacy_totals = [], []
    existing_daily = {(r['account_id'],r['revenue_date']): dict(r) for r in conn.execute('SELECT * FROM v2_daily_revenues')}
    developer_attempts = {r[0] for r in conn.execute('SELECT id FROM v2_revenue_collection_attempts WHERE adapter_key=?',(SOURCE,))}
    views_rank = sorted(by_account, key=lambda aid: -sum(totals[(aid,d)]['view'] for d in dates))
    for aid in sorted(by_account):
        account = accounts[aid]
        fans = rng.randint(20, 2800)
        rank = views_rank.index(aid)/len(views_rank)
        tier = '头部爆款' if rank<.1 else '腰部主力' if rank<.55 else '新锐测试'
        months = defaultdict(int)
        for day in dates:
            metrics = totals[(aid,day)]
            adds = metrics['fans_add']
            reduces = min(fans+adds, rng.randint(0,3)+(1 if account['status']=='停用' else 0))
            fans += adds-reduces
            row = dict(template['v3_video_account_daily'])
            row.update(id=key(f'account-day:{aid}:{day}'),uid=account['channel_id'],account_id=aid,stat_date=str(day),
                **{k:metrics[k] for k in metric_names if k!='fans_add'},fans_total=fans,fans_add=adds,fans_net=adds-reduces,
                fans_reduce=reduces,data_state='record' if metrics['view'] else 'confirmed_zero',freshness_state='simulated',
                collection_run_id=runs['video'],fetched_at=stamp,payload_json=packed(dict(generated=True,model=MODEL,assumptions=assumptions)))
            output['v3_video_account_daily'].append(row)
            amount = revenue[(aid,day)]
            months[day.replace(day=1)] += amount
            if account['theater_name']=='触摸剧场':
                continue
            attempt_id = key(f'attempt:{aid}:{day}')
            attempts.append(dict(id=attempt_id,request_id=runs['revenue'],account_id=aid,theater_id=account['theater_id'],
                adapter_key=SOURCE,revenue_date=str(day),collection_status='success',amount=money(amount),error_message='',
                collected_at=stamp,data_kind='account_daily_total',period_end=str(day),period_type='day'))
            previous = existing_daily.get((aid,str(day)))
            if not previous or previous['source_attempt_id'] in developer_attempts:
                legacy_totals.append(dict(id=previous['id'] if previous else key(f'legacy-total:{aid}:{day}'),account_id=aid,
                    theater_id=account['theater_id'],revenue_date=str(day),amount=money(amount),quality='direct',
                    source_attempt_id=attempt_id,created_at=previous['created_at'] if previous else stamp,updated_at=stamp))
            row = dict(template['v3_revenue_account_periods'])
            row.update(id=key(f'period:{aid}:{day}'),account_id=aid,theater_id=account['theater_id'],period_label=str(day),
                period_start=str(day),period_end=str(day),period_type='day',date_precision='day',amount=money(amount),
                data_state='record' if amount else 'confirmed_zero',freshness_state='simulated',settlement_state='unsettled' if day>=unsettled_start else 'settled',
                include_in_analysis=int(day>=unsettled_start),source_attempt_id=attempt_id,collection_run_id=runs['revenue'],
                collected_at=stamp,raw_result_json=packed(dict(generated=True,model=MODEL)))
            output['v3_revenue_account_periods'].append(row)
        if account['theater_name']=='触摸剧场':
            for first, amount in sorted(months.items()):
                last = min(end, (first.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1))
                row = dict(template['v3_revenue_account_periods'])
                row.update(id=key(f'month:{aid}:{first}'),account_id=aid,theater_id=account['theater_id'],period_label=first.strftime('%Y-%m'),
                    period_start=str(max(first,start)),period_end=str(last),period_type='month_cumulative',date_precision='month',
                    amount=money(amount),data_state='record' if amount else 'confirmed_zero',freshness_state='simulated',
                    settlement_state='unsettled' if first>=unsettled_start else 'settled',include_in_analysis=int(first>=unsettled_start),
                    source_attempt_id='',collection_run_id=runs['revenue'],collected_at=stamp,raw_result_json=packed(dict(generated=True,model=MODEL)))
                output['v3_revenue_account_periods'].append(row)
        snapshot = dict(template['v3_video_accounts'])
        snapshot.update(id=key(f'account:{aid}:{end}'),uid=account['channel_id'],account_id=aid,account_name=account['nickname'],
            login_status='已停用' if account['status']=='停用' else '登录有效',fans_total=fans,group_name=tier,
            snapshot_date=str(end),data_state='record',freshness_state='simulated',fetched_at=stamp,
            payload_json=packed(dict(generated=True,model=MODEL,tier=tier,assumptions=assumptions)))
        output['v3_video_accounts'].append(snapshot)
        diag = dict(template['v3_video_account_diagnostics'])
        diag.update(id=key(f'diagnostic:{aid}:{end}'),uid=account['channel_id'],account_id=aid,account_name=account['nickname'],
            snapshot_date=str(end),data_state='record',freshness_state='simulated',last_verify_time=stamp,fetched_at=stamp,
            payload_json=packed(dict(generated=True,model=MODEL,risk_calibrated=False)))
        output['v3_video_account_diagnostics'].append(diag)
    for row in originals['v3_video_post_punishments']:
        if row['post_id_or_export_id'] not in post_times:
            raise ValueError('存在无法关联作品的开发风险记录，未替换。')
        meta = json.loads(row['payload_json'] or '{}')
        meta.update(model=MODEL,risk_calibrated=False,detectedDate=post_times[row['post_id_or_export_id']][:10])
        row.update(publish_time=post_times[row['post_id_or_export_id']],snapshot_date=str(end),fetched_at=stamp,payload_json=packed(meta))
        output['v3_video_post_punishments'].append(row)
    for diag in output['v3_video_account_diagnostics']:
        count = sum(r['account_id']==diag['account_id'] for r in output['v3_video_post_punishments'])
        diag.update(abnormal_post_count=count,abnormal=int(count>9),video_status='需关注' if count>9 else '正常')

    # All preparation and preconditions above run before deleting anything.
    for table in reversed(TABLES):
        conn.execute(f'DELETE FROM {table} WHERE source_kind=?',(SOURCE,))
    conn.execute('''DELETE FROM v2_daily_revenues WHERE source_attempt_id IN
        (SELECT id FROM v2_revenue_collection_attempts WHERE adapter_key=?)''',(SOURCE,))
    conn.execute('DELETE FROM v2_revenue_collection_attempts WHERE adapter_key=?',(SOURCE,))
    for domain, rid in runs.items():
        conn.execute('''INSERT INTO v3_analytics_collection_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET source_captured_at=excluded.source_captured_at,finished_at=excluded.finished_at''',
            (rid,domain,SOURCE,'local_empirical_resampling','v3_snapshot',str(start),str(end),MODEL,0,stamp,'completed','{}','',stamp,stamp))
    for table, rows in output.items():
        insert_many(conn,table,rows)
    insert_many(conn,'v2_revenue_collection_attempts',attempts)
    insert_many(conn,'v2_daily_revenues',legacy_totals)
    if protected_digest(conn)!=before:
        raise ValueError('原始历史记录或账号/剧场/封面资料发生变化，事务应回滚。')
    if {tuple(r) for r in conn.execute('PRAGMA foreign_key_check')}-foreign_before:
        raise ValueError('引入了新的外键问题，事务应回滚。')
    work_daily = defaultdict(int)
    account_daily = defaultdict(int)
    for row in output['v3_video_post_daily']:
        work_daily[row['post_id']] += row['view']
        account_daily[(row['account_id'],row['stat_date'])] += row['view']
    if any(row['view']!=work_daily[row['post_id']] for row in posts):
        raise ValueError('作品累计播放与分日不一致，事务应回滚。')
    if any(row['view']!=account_daily[(row['account_id'],row['stat_date'])] for row in output['v3_video_account_daily']):
        raise ValueError('账号日播放与作品日播放不一致，事务应回滚。')
    return dict(model=MODEL,start=str(start),end=str(end),accounts=len(by_account),counts={t:len(v) for t,v in output.items()},
        before_work_views=before_work_views,
        work_views=summarize([r['view'] for r in posts]),daily_account_views=summarize([r['view'] for r in output['v3_video_account_daily']]),
        daily_revenue=summarize([float(r['amount']) for r in output['v3_revenue_account_periods'] if r['period_type']=='day']),
        total_generated_revenue=money(sum(revenue.values())),protected_records_unchanged=True,new_foreign_key_errors=0,
        assumptions=assumptions,account_plan=account_plan)


def main():
    parser = argparse.ArgumentParser(description='备份后以青柠历史视频播放与收益成组调整V3开发数据，不改原始采集或媒体')
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--end-date',type=date.fromisoformat,default=datetime.now(BEIJING).date())
    parser.add_argument('--days',type=int,default=60)
    args=parser.parse_args()
    if not args.database.is_file() or not args.reference.is_file() or args.database.resolve()==args.reference.resolve():
        parser.error('须指定现有目标库和独立的造数前参考备份。')
    profiles,reference_stats = load_reference(args.reference)
    conn=sqlite3.connect(args.database,timeout=30);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA foreign_keys=ON')
    backup=args.database.with_name(args.database.name+'.before-empirical-reprofile-'+datetime.now(BEIJING).strftime('%Y%m%d-%H%M%S-%f'))
    try:
        with closing(sqlite3.connect(backup)) as destination:
            conn.backup(destination)
        conn.execute('BEGIN IMMEDIATE')
        result=reprofile(conn,profiles,args.end_date,args.days)
        conn.commit()
        result.update(backup=str(backup),reference=str(args.reference),reference_stats=reference_stats)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='account_plan'},ensure_ascii=True))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__=='__main__':
    main()
