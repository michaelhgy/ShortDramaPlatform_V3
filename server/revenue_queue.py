"""Unified queue adapter. Reuses the revenue engine; never calls Xiao V."""
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
import threading
import uuid

from server import revenue_collection_state as state
from server import revenue_collectors as collectors
from server import revenue_query_settings as settings

START_LOCK = threading.Lock()


def account_states(conn, yesterday, *, collected_at=None):
    moment = collected_at or state.clock()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=state.SHANGHAI)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'theaters', 'v3_account_revenue_collectors', 'v2_revenue_collection_attempts'} <= tables:
        return {}
    from server import v2_revenue_service as service
    result = {}
    pending_ids = state.pending_attempts(conn)
    for account in service._accounts(conn, None, None):
        key = account['revenue_collector_id']
        spec = settings.effective_spec(conn, collectors.definition(key))
        enabled = bool(spec and settings.current(conn, key)['enabled'])
        available = bool(enabled and str(account['channel_id'] or '').strip())
        history = conn.execute('SELECT * FROM v3_revenue_backfills WHERE account_id=? AND theater_id=? AND adapter_key=?',
            (account['id'], account['theater_id'], key)).fetchone() if key else None
        mode = 'daily' if spec and spec['date_precision'] == 'day' else 'cumulative' if spec else 'unknown'
        start = history['boundary_date'] if history and history['complete'] else ''
        attempts = list(conn.execute('SELECT revenue_date,collection_status,collected_at,id,period_end FROM v2_revenue_collection_attempts WHERE account_id=? AND theater_id=? AND adapter_key=? ORDER BY collected_at DESC,rowid DESC',
            (account['id'], account['theater_id'], key))) if key else []
        complete_days = {r['revenue_date'] for r in attempts if r['collection_status'] in ('success','no_data') and r['id'] not in pending_ids}
        query_due, rechecks = True, []
        if mode == 'daily':
            successes = {r['revenue_date'] for r in attempts if r['collection_status'] == 'success' and r['id'] not in pending_ids}
            latest_empty = {}
            for row in attempts:
                if (row['collection_status'] == 'no_data' and row['id'] not in pending_ids
                        and row['revenue_date'] not in successes and state.recent_empty(row['revenue_date'], moment, spec)):
                    latest_empty.setdefault(row['revenue_date'], row)
            rechecks = sorted(latest_empty)
            due_rechecks = [day for day in rechecks if state.retry_due(latest_empty[day], moment, spec)]
            if start:
                count = (date.fromisoformat(yesterday)-date.fromisoformat(start)).days+1
                missing_dates = [(date.fromisoformat(start)+timedelta(days=i)).isoformat() for i in range(max(0,count))
                    if (date.fromisoformat(start)+timedelta(days=i)).isoformat() not in complete_days]
                missing = len(missing_dates)
            else:
                missing = None
            status = 'backfill' if not history or not history['complete'] else 'missing' if missing or rechecks else 'complete'
            query_due = status == 'backfill' or bool(missing or due_rechecks)
            if start:
                missing_dates = sorted(set(missing_dates + due_rechecks))
            if status == 'backfill':
                message = '历史待补齐'
            elif missing:
                message = f'待补查 {missing} 天'
                if rechecks:
                    message += f'，另有 {len(rechecks)} 天暂无数据，待复查'
            elif rechecks:
                message = f'{len(rechecks)} 天暂无数据，' + ('待复查' if due_rechecks else '间隔未到，稍后复查')
            else:
                message = '截至昨日已查询，无待补查日期'
        else:
            today = (date.fromisoformat(yesterday)+timedelta(days=1)).isoformat()
            anchor = history['anchor_date'] if history and not history['complete'] else None
            periods = service._cumulative_periods(spec,today,anchor) if spec else []
            missing_periods = [period for period in periods if not service._cumulative_completed(
                conn, account, key, period, today, historical=service._cumulative_is_historical(spec,period,today), collected_at=moment, spec=spec)]
            latest_periods = {}
            for row in attempts:
                if row['collection_status'] in ('success', 'no_data') and row['id'] not in pending_ids:
                    latest_periods.setdefault(row['period_end'], row)
            rechecks = [period for period in periods if period in latest_periods
                        and latest_periods[period]['collection_status'] == 'no_data'
                        and period not in missing_periods]
            query_due = bool(missing_periods)
            ready = bool(periods and not missing_periods and not rechecks)
            historical_missing = any(service._cumulative_is_historical(spec,p,today) for p in missing_periods) if spec else False
            status, missing = ('complete' if ready else 'backfill' if historical_missing else 'missing'), None
            labels = ['当前累计' if p == 'unknown' else p + '累计' for p in missing_periods]
            message = ('本轮累计已查询，间隔后可更新' if ready else
                       '待查询：' + '、'.join(labels) if labels else
                       '累计暂无数据，间隔未到，稍后复查' if rechecks else '累计收益待更新')
        if not spec:
            status, message = 'unconfigured', '未配置收益采集器'
        elif not enabled:
            status, message = 'disabled', '收益采集器已停用'
        elif not str(account['channel_id'] or '').strip():
            status, message = 'unconfigured', '未填写视频号ID'
        latest_success = next((r['collected_at'] for r in attempts if r['collection_status'] in ('success','no_data') and r['id'] not in pending_ids), '')
        result[account['id']] = dict(available=available, mode=mode, state=status,
            collector_name=spec['name'] if spec else '', message=message, missing_days=missing,
            recheck_days=len(rechecks), query_due=query_due,
            last_success=latest_success, first_missing=missing_dates[0] if mode=='daily' and start and missing_dates else '')
    return result


def collect_account(connection, account_id, progress, should_stop, *, outcome=None):
    """Claim the same run registry as the legacy manual and automatic entrances."""
    from server import v2_revenue_service as service
    from server.collection_progress import checkpoint, CollectionStopped
    moment = state.clock()
    yesterday = (moment.date()-timedelta(days=1)).isoformat()
    with closing(connection()) as conn:
        meta = account_states(conn, yesterday, collected_at=moment).get(account_id)
        if not meta or not meta['available']:
            return 'failed', (meta or {}).get('message', '账号收益采集器待配置')
        if meta['state'] == 'complete' or not meta.get('query_due', True):
            return 'skipped', meta['message']+'，已跳过重复查询'
        account = service._accounts(conn,None,[account_id])[0]
        adapter = account['revenue_collector_id']
        history = conn.execute('SELECT * FROM v3_revenue_backfills WHERE account_id=? AND theater_id=? AND adapter_key=?',
            (account_id,account['theater_id'],adapter)).fetchone()
        # Start from the first missing date; completed dates remain reusable.
        start = meta.get('first_missing') or yesterday
        with START_LOCK:
            active = conn.execute("SELECT id FROM v2_revenue_collection_runs WHERE status IN ('queued','running') LIMIT 1").fetchone()
            if active:
                return 'partial', '已有收益任务正在查询，本项未重复发起；原任务结束后可继续'
            run_id, now = uuid.uuid4().hex, moment.isoformat(timespec='seconds')
            conn.execute("INSERT INTO v2_revenue_collection_runs(id,status,start_date,end_date,created_at,started_at,updated_at) VALUES(?,'running',?,?,?,?,?)",
                (run_id,start,yesterday,now,now,now))
            conn.commit()
        streak, counts = 0, {'success':0,'no_data':0,'failed':0,'pending':0,'skipped':0,'zero':0}
        saved_amount, source_amount, source_period = Decimal('0.00'), None, ''
        queried_dates = []
        def report(item):
            nonlocal streak, saved_amount, source_amount, source_period
            checkpoint(should_stop)
            status = item['status']
            if status == 'failed':
                from server.collection_progress import access_limited, CollectionAccessLimited
                if access_limited(item.get('message','')):
                    raise CollectionAccessLimited(item['message'])
            if status == 'verification_required':
                progress(item['message'])
                if outcome is not None:
                    outcome['verification_id'] = item['verification_id']
                return
            day = item.get('date','')
            if status == 'running':
                progress(f'正在查询 {day}'+('，补齐历史收益' if meta['state']=='backfill' else '，补查缺失收益'))
                return
            if status in counts:
                counts[status] += 1
            if status in ('success', 'no_data', 'failed', 'pending'):
                queried_dates.append(day)
            if status == 'success':
                saved_amount += Decimal(item['amount'])
                source_amount, source_period = item.get('raw_amount'), item.get('source_period', '')
            if status == 'success' and item.get('amount') == '0.00':
                counts['zero'] += 1
            streak = item.get('empty_streak', streak)
            if status == 'skipped':
                progress(f'{day} 已保存收益或尚未到复查间隔，已跳过；本轮跳过 {counts["skipped"]} 天')
                return
            label = ('收益 '+item['amount']+' 元') if status == 'success' else '无收益记录' if status == 'no_data' else '待更新／待确认' if status=='pending' else '查询失败'
            suffix = f'；连续无收益 {streak}/7 天' if meta['state']=='backfill' and streak else ''
            progress(f'{day}：{label}'+suffix+(('；'+item['message']) if item.get('message') else ''))
            conn.execute('UPDATE v2_revenue_collection_runs SET completed_units=completed_units+1,success_units=success_units+?,no_data_units=no_data_units+?,failed_units=failed_units+?,current_account=?,current_theater=?,updated_at=? WHERE id=?',
                (int(status=='success'),int(status=='no_data'),int(status=='failed'),account['nickname'],account['theater_name'],state.clock().isoformat(timespec='seconds'),run_id))
            conn.commit()
        try:
            checkpoint(should_stop)
            ranges = []
            if meta['mode'] == 'daily' and history:
                begin = start if history['complete'] else (date.fromisoformat(history['anchor_date'])+timedelta(days=1)).isoformat()
                cursor = date.fromisoformat(begin)
                while cursor <= date.fromisoformat(yesterday):
                    end = min(cursor+timedelta(days=89), date.fromisoformat(yesterday))
                    ranges.append((cursor.isoformat(),end.isoformat(),False))
                    cursor = end+timedelta(days=1)
            if meta['mode'] != 'daily' or not history or not history['complete']:
                # Newer missing dates were already queried above, including failures.
                # Resume history at its saved anchor so the same date is never
                # requested a second time in this run.
                anchor = history['anchor_date'] if meta['mode'] == 'daily' and history else yesterday
                ranges.append((anchor,anchor,True))
            result = {'backfills': []}
            for begin, end, initial in ranges:
                result = service.collect_supported_theaters(conn,begin,end,account_ids=[account_id],
                    progress_callback=report,skip_completed=True,initial_backfill=initial,
                    collection_run_id=run_id,collected_at=moment,should_stop=should_stop,report_cached=True)
                if any(item['status'] == 'verification_required' for item in result['items']):
                    break
            remaining = account_states(conn, yesterday, collected_at=moment).get(account_id, {})
            coverage_pending = remaining.get('state') in ('backfill', 'missing')
            unfinished = any(not item['complete'] for item in result['backfills']) or remaining.get('state') == 'backfill' 
            if outcome is not None:
                outcome.update(pending_days=counts['pending']+remaining.get('recheck_days', 0),failed_days=counts['failed'],
                    history_pending=unfinished,empty_days=counts['no_data'],saved_days=counts['success'],skipped_days=counts['skipped'],
                    mode=meta['mode'],collector_id=adapter,collector_name=meta['collector_name'],
                    saved_amount=format(saved_amount,'f'),source_amount=source_amount,source_period=source_period,
                    query_start=min(queried_dates) if queried_dates else '',query_end=max(queried_dates) if queried_dates else '')
            notes = []
            if any(item['status'] == 'verification_required' for item in result['items']):
                notes.append('等待人工验证码，验证后继续')
            if counts['failed']: notes.append(f'{counts["failed"]} 天查询失败，可重试')
            if counts['pending']: notes.append(f'{counts["pending"]} 天待更新，下次继续查询')
            if unfinished: notes.append('历史尚未补齐，下次继续')
            elif coverage_pending and not (counts['pending'] or counts['failed']):
                notes.append(remaining.get('message') or '所需收益结果尚未完整，下次继续')
            message = f'保存收益 {counts["success"]} 天（其中0收益 {counts["zero"]} 天），无收益记录 {counts["no_data"]} 天，跳过 {counts["skipped"]} 天'
            message += ('；'+'；'.join(notes)) if notes else '；本轮已完成'
            status = ('failed' if counts['failed'] and not (counts['success']+counts['no_data']+counts['pending'])
                      else 'partial' if notes else 'success' if counts['success']+counts['no_data'] else 'skipped')
            conn.execute("UPDATE v2_revenue_collection_runs SET status='completed',total_units=completed_units,error_message=?,finished_at=?,updated_at=? WHERE id=?",
                ('；'.join(notes),state.clock().isoformat(timespec='seconds'),state.clock().isoformat(timespec='seconds'),run_id))
            conn.commit()
            return status, message
        except BaseException as exc:
            conn.rollback()
            stopped = isinstance(exc,CollectionStopped)
            if stopped and adapter == 'pingyue':
                from server.pingyue_collector import SESSIONS, REGISTRY_LOCK, defer_waiting
                from server.revenue_query_settings import current
                config = current(conn, adapter)
                with REGISTRY_LOCK:
                    session = SESSIONS.get((config['source_url'], config['extract_code']))
                if session:
                    defer_waiting(session.challenge_id)
            conn.execute('UPDATE v2_revenue_collection_runs SET status=?,error_message=?,finished_at=?,updated_at=? WHERE id=?',
                ('stopped' if stopped else 'failed','已停止，已保存结果保留' if stopped else str(exc),state.clock().isoformat(timespec='seconds'),state.clock().isoformat(timespec='seconds'),run_id))
            conn.commit()
            raise
