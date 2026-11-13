"""Read the current business database for the operations cockpit; no collection.

Sources are deliberately combined. The newest snapshot for each business key
wins, so multiple collection batches never multiply the same daily metric.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from math import isfinite
from server.drama_catalog import account_metadata
from server.optimization_analysis import configuration as analysis_configuration
import json


def rating_revenue_data(conn, current_periods):
    """Keep confirmed financial history separate from the latest query result; read only."""
    query_time = """julianday(CASE
        WHEN substr(collected_at,-1) IN ('Z','z') OR substr(collected_at,-6,1) IN ('+','-') THEN collected_at
        WHEN length(collected_at)=10 THEN collected_at||'T00:00:00+08:00'
        ELSE replace(collected_at,' ','T')||'+08:00' END)"""
    successful = [dict(r) for r in conn.execute('''SELECT d.* FROM v3_revenue_account_periods d
        WHERE data_state IN ('record','confirmed_zero','zero','cached_only') AND amount IS NOT NULL
            AND source_kind<>'legacy_v2' AND freshness_state NOT IN ('legacy_unverified','legacy_unknown','expired')
            AND EXISTS(SELECT 1 FROM accounts a WHERE a.id=d.account_id)''')]
    periods = {r['id']: r for r in successful}
    periods.update({r['id']: r for r in current_periods})
    prototypes = {(r['account_id'], r['theater_id'], r['period_end']): r for r in current_periods
                  if r['period_type']=='day' and r['period_start']==r['period_end']
                  and r['source_kind']!='legacy_v2' and r['freshness_state']!='legacy_unverified'}
    # The successful daily table survives a later failed attempt; do not erase its saved amount.
    for row in conn.execute('''SELECT d.*,a.adapter_key,a.collected_at
        FROM v2_daily_revenues d JOIN v2_revenue_collection_attempts a ON a.id=d.source_attempt_id
        WHERE a.collection_status='success' AND EXISTS(SELECT 1 FROM accounts c WHERE c.id=d.account_id)'''):
        prototype=prototypes.get((row['account_id'],row['theater_id'],row['revenue_date']))
        if not prototype:
            continue
        try:
            current_meta=json.loads(prototype['raw_result_json'] or '{}')
        except (ValueError, TypeError):
            current_meta={}
        if not isinstance(current_meta, dict):
            current_meta={}
        try:
            current_amount=float(prototype['amount'])
        except (TypeError, ValueError):
            current_amount=None
        waiting=(current_meta.get('income_updated') is False or current_meta.get('finalized') is False
                 or current_meta.get('update_status') in ('pending','待更新'))
        unknown_zero=(current_amount==0
                      and prototype['data_state']!='confirmed_zero'
                      and current_meta.get('income_updated') is not True and current_meta.get('finalized') is not True
                      and not (prototype['source_kind']=='development_seed' and current_meta.get('generated') is True))
        if not waiting and not unknown_zero and prototype['data_state'] in ('record','confirmed_zero','zero','cached_only') and current_amount is not None and isfinite(current_amount) and current_amount>=0:
            continue
        recovered=dict(prototype)
        recovered.update(id='saved-success:'+row['id'],amount=row['amount'],collected_at=row['collected_at'],
                         source_attempt_id=row['source_attempt_id'],data_state='record')
        metadata={'recovered_successful_query':True}
        if row['adapter_key']=='development_seed':
            metadata['generated']=True
            if float(row['amount'])==0:
                recovered['data_state']='confirmed_zero'
        recovered['raw_result_json']=json.dumps(metadata,ensure_ascii=False)
        periods[recovered['id']]=recovered
    queries=[dict(r) for r in conn.execute(f'''WITH ranked AS (
        SELECT id,account_id,theater_id,revenue_date,collection_status,collected_at,error_message,
            adapter_key,data_kind,period_type,ROW_NUMBER() OVER(PARTITION BY account_id,theater_id,revenue_date
                ORDER BY {query_time} DESC,collected_at DESC,id DESC) AS position
        FROM v2_revenue_collection_attempts d WHERE EXISTS(SELECT 1 FROM accounts a WHERE a.id=d.account_id)
        ) SELECT * FROM ranked WHERE position=1''')]
    from server.revenue_collection_state import pending_attempts
    pending = pending_attempts(conn)
    for row in queries:
        row.pop('position')
        if row['id'] in pending:
            row['collection_status'] = 'pending'
    return {'periods':list(periods.values()),'queries':queries}


def dashboard_data(connection, *, allow_legacy_snapshots=False):
    with closing(connection()) as conn:
        conn.execute('BEGIN')
        accounts = [dict(r) for r in conn.execute('''
            SELECT a.id,a.nickname,a.channel_id,a.theater_id,a.status,a.notes,t.name AS theater_name
            FROM accounts a JOIN theaters t ON t.id=a.theater_id ORDER BY a.nickname,a.id
        ''')]
        from server.operations_collection import login_statuses
        saved_logins = login_statuses(conn)
        accounts = [{**account_metadata(conn, a), **saved_logins.get(a['channel_id'], {})} for a in accounts]
        dramas = [
            {'id': r['id'], 'name': r['current_name'], 'cover_url': f"/api/v2/dramas/{r['id']}/cover"}
            for r in conn.execute('''SELECT d.id,d.current_name,p.cover_path
                FROM dramas d JOIN drama_profiles p ON p.drama_id=d.id WHERE p.cover_path<>'' ''')
            if Path(r['cover_path']).is_file()
        ]
        theaters = [dict(r) for r in conn.execute('SELECT id,name,status FROM theaters ORDER BY name,id')]

        def latest(table, keys, order, eligibility='1=1'):
            query = f'''WITH ranked AS (
                SELECT d.*,ROW_NUMBER() OVER(PARTITION BY {keys} ORDER BY {order},d.id DESC) AS position
                FROM {table} d WHERE ({eligibility}) AND EXISTS(SELECT 1 FROM accounts a WHERE a.id=d.account_id)
            ) SELECT * FROM ranked WHERE position=1'''
            result = []
            for row in conn.execute(query):
                value = dict(row)
                value.pop('position')
                result.append(value)
            return result

        daily = latest('v3_video_account_daily', 'd.account_id,d.stat_date', 'd.fetched_at DESC')
        # Matrix cards retain a successful complete day even after a later failed read.
        daily_latest = latest('v3_video_account_daily', 'd.account_id', 'd.stat_date DESC,d.fetched_at DESC',
            """d.stat_date<date('now','+8 hours')
                AND d.data_state IN ('record','confirmed_zero','zero','cached_only')
                AND d.fans_net IS NOT NULL AND d.view>=0 AND d.like_count>=0 AND d.comment_count>=0""")
        # Failed collection is not a new zero-count work; keep its last usable snapshot.
        posts = latest('v3_video_posts', 'd.uid,d.post_id', "CASE WHEN d.data_state IN ('record','confirmed_zero','zero','cached_only') AND d.view IS NOT NULL AND d.view>=0 THEN 0 ELSE 1 END ASC,d.snapshot_date DESC,d.fetched_at DESC")
        revenue = latest('v3_revenue_account_periods', 'd.account_id,d.theater_id,d.period_type,d.period_label', 'd.collected_at DESC')
        # Export IDs may not have an associated work; preserve them as risk records.
        punishments = latest('v3_video_post_punishments', 'd.account_id,d.post_id_or_export_id', 'd.snapshot_date DESC,d.fetched_at DESC')
        from server.operations_collection import publication_dashboard, real_dashboard_rows
        history, collection = publication_dashboard(conn)
        from server.work_history import dashboard as work_dashboard, settings as action_settings
        works, pending_notices, action_log = work_dashboard(conn)
        profiles = latest('v3_video_accounts', 'd.account_id', 'd.snapshot_date DESC,d.fetched_at DESC')
        if not allow_legacy_snapshots:
            # Explicit live-mode cutover: leave all old evidence in storage, but
            # never mix simulation snapshots into the real operating dashboard.
            real = real_dashboard_rows(conn)
            profiles, daily, posts = real['video_accounts'], real['video_account_daily'], real['video_posts']
            daily_latest = []
            for aid in {r['account_id'] for r in daily}:
                usable = [r for r in daily if r['account_id'] == aid and r['data_state'] != 'incomplete']
                if usable: daily_latest.append(max(usable, key=lambda r: r['stat_date']))
            def real_revenue(row):
                meta = json.loads(row.get('raw_result_json') or '{}')
                return row.get('source_kind') not in ('simulation_ui', 'development_seed', 'legacy_v2') and not meta.get('generated') and not meta.get('simulation')
            revenue = [r for r in revenue if real_revenue(r)]
            punishments = []  # Only the durable, V3-attributed events below drive optimization.
        rating = rating_revenue_data(conn, revenue)
        if not allow_legacy_snapshots:
            rating['periods'] = [r for r in rating['periods'] if real_revenue(r)]
            rating['queries'] = [r for r in rating['queries'] if r.get('adapter_key') != 'development_seed']
        return {
            'schema': 'v3-operations-dashboard-1',
            'today': datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
            'latest_date': max((r['stat_date'] for r in daily), default=''),
            'accounts': accounts, 'theaters': theaters, 'dramas': dramas,
            'video_accounts': profiles,
            'publication_history': history, 'collection': collection,
            'work_history': works, 'pending_optimizations': pending_notices,
            'optimization_action_settings': action_settings(conn), 'optimization_action_log': action_log,
            'optimization_analysis_configuration': analysis_configuration(conn),
            'video_account_daily': daily, 'video_posts': posts,
            'account_daily_latest': daily_latest,
            'video_post_punishments': punishments,
            'revenue_account_periods': revenue,
            'revenue_rating': rating,
            'coverage': {
                'account_days': len(daily),
                'failed_account_days': sum(r['data_state'] == 'failed' for r in daily),
                'failed_revenue_periods': sum(r['data_state'] == 'failed' for r in revenue),
                'unclassified_risks': sum('simplifiedReason' not in r['payload_json'] for r in punishments),
            },
        }
