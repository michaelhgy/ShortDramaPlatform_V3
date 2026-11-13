"""Fill account-day history from Xiao V cache first; refresh the platform only for gaps."""
from __future__ import annotations

import math
from datetime import date, timedelta

# A business inference, rather than an account-registration timestamp.
ZERO_RUN_DAYS = 7
WINDOW_DAYS = 90
DAILY_FIELDS = ('view', 'fansAdd', 'fansNet', 'fansReduce', 'like', 'favorite', 'comment', 'forward')
OPTIONAL_FIELDS = ('fansTotal',)


def numeric(value):
    if isinstance(value, bool) or value is None or value == '':
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def complete(row):
    return isinstance(row, dict) and all(numeric(row.get(key)) is not None and (key == 'fansNet' or numeric(row.get(key)) >= 0) for key in DAILY_FIELDS)


def dates(start, end):
    current = date.fromisoformat(start)
    finish = date.fromisoformat(end)
    while current <= finish:
        yield current.isoformat()
        current += timedelta(days=1)


def ranges(days):
    """Only query missing dates, grouping adjacent dates, at most 90 per request."""
    result = []
    for day in sorted(set(days)):
        if result and (date.fromisoformat(day) - date.fromisoformat(result[-1][1])).days == 1 and (date.fromisoformat(day) - date.fromisoformat(result[-1][0])).days < WINDOW_DAYS:
            result[-1][1] = day
        else:
            result.append([day, day])
    return result


def infer_start(rows):
    """Find the oldest observed activity and require a contiguous all-zero lead-in."""
    active = sorted(day for day, row in rows.items() if complete(row)
                    and any(numeric(row.get(key)) != 0 for key in DAILY_FIELDS))
    if not active:
        return None
    first = active[0]
    before = date.fromisoformat(first) - timedelta(days=ZERO_RUN_DAYS)
    proof = list(dates(before.isoformat(), (date.fromisoformat(first)-timedelta(days=1)).isoformat()))
    if not all(complete(rows.get(day)) and all(numeric(rows[day].get(key)) == 0 for key in DAILY_FIELDS) for day in proof):
        return None
    return {'startDate': first, 'zeroDates': proof, 'rule': 'consecutive_zero_days', 'zeroRunDays': ZERO_RUN_DAYS}


def collect_daily(client, uid, existing, end, at, *, refresh=False, progress=None, should_stop=None, save_partial=None, reset_online=False):
    """No assumed cache coverage; empty/failed reads never become zero days."""
    if reset_online or ((existing or {}).get('dailyCollection') or {}).get('resetPending'):
        return reset_daily(client, uid, existing, end, at, progress=progress, should_stop=should_stop, save_partial=save_partial)
    from server.publishing.vcat import discard_home_visits
    from server.collection_progress import checkpoint, CollectionStopped
    payload = discard_home_visits(dict(existing or {}))
    saved = {r['date']: dict(r) for r in payload.get('daily', [])
             if isinstance(r, dict) and isinstance(r.get('date'), str) and r['date'] <= end}
    boundary = (payload.get('dailyCollection') or {}).get('boundary')
    if boundary and boundary.get('rule') not in ('consecutive_zero_days', 'lookback_limit'):
        boundary = None
    current = dict(saved)
    queried = []
    refresh_state = 'not_needed'
    failures = []
    oldest_checked = None
    scan_start = (date.fromisoformat(end)-timedelta(days=WINDOW_DAYS-1)).isoformat()
    unchecked = {day for day in dates(scan_start, end) if not complete(current.get(day))}

    def infer_boundary(*, fallback=False):
        # This is an available-data boundary, never an inferred registration date.
        observed = {day: row for day, row in current.items() if scan_start <= day <= end}
        inferred = infer_start(observed)
        if inferred or not fallback or unchecked or not observed:
            return inferred
        if progress:
            progress(f'已核对最近{WINDOW_DAYS}天，未确认连续{ZERO_RUN_DAYS}天全零；采用可查询的最早日期 {min(observed)} 作为起始日')
        return {'startDate': min(observed), 'rule': 'lookback_limit',
                'lookbackDays': WINDOW_DAYS, 'scanStartDate': scan_start, 'scanEndDate': end}

    def merge(response):
        nonlocal payload
        response = discard_home_visits(response)
        payload.update({key: value for key, value in response.items() if key not in ('daily', 'dailyCollection')})
        for row in response.get('daily') or []:
            day = row.get('date') if isinstance(row, dict) else None
            if not isinstance(day, str) or day > end:
                continue
            try:
                date.fromisoformat(day)
            except ValueError:
                continue
            old = current.get(day, {})
            # A complete past day is immutable; partial facts retain known values.
            if complete(old):
                continue
            fresh = {**old, 'date': day}
            for key in (*DAILY_FIELDS, *OPTIONAL_FIELDS):
                if (numeric(old.get(key)) is None or (key != 'fansNet' and numeric(old.get(key)) < 0)) and numeric(row.get(key)) is not None and (key == 'fansNet' or numeric(row.get(key)) >= 0):
                    fresh[key] = row[key]
                elif key not in fresh:
                    fresh[key] = None
            fresh['_collectedAt'] = at
            current[day] = fresh

    def read(windows):
        nonlocal oldest_checked
        for start, finish in windows:
            checkpoint(should_stop)
            if progress: progress(f'读取小V猫已有日数据：{start} 至 {finish}，只查询缺失日期')
            oldest_checked = min(oldest_checked or start, start)
            queried.append({'startDate':start, 'endDate':finish, 'source':'xiaovcat_local'})
            try:
                response = client.call('vcat_get_account_stats', {'uid':uid, 'startDate':start, 'endDate':finish, 'includeIncome':False})
                # A response must actually include the requested day; never invent it.
                filtered = dict(response)
                filtered['daily'] = [r for r in response.get('daily') or [] if isinstance(r,dict) and isinstance(r.get('date'),str) and start <= r['date'] <= finish]
                merge(filtered)
                unchecked.difference_update(dates(start, finish))
                if save_partial:
                    save_partial({**payload, 'daily': [current[d] for d in sorted(current)],
                                  'dailyCollection': {**(payload.get('dailyCollection') or {}), 'state': 'partial'}})
                if progress: progress(f'{start} 至 {finish} 已返回 {len(filtered["daily"])} 天记录，正在核对完整性')
            except CollectionStopped:
                raise
            except Exception:
                unchecked.update(dates(start, finish))
                failures.append({'startDate':start,'endDate':finish})

    def missing():
        start = boundary['startDate'] if boundary else scan_start
        return [day for day in dates(start, end) if not complete(current.get(day))]

    # An established start plus complete V3 days needs neither a cache query nor a platform refresh.
    if boundary and not missing():
        payload['dailyCollection'] = {**(payload.get('dailyCollection') or {}), 'state':'complete',
                                      'boundary':boundary, 'checkedThrough':end, 'missingDates':[]}
        if progress: progress(f'已完整保存 {boundary["startDate"]} 至 {end}，无需外部请求')
        return payload, {'state':'up_to_date','startDate':boundary['startDate'],'endDate':end,
                         'localQueries':[], 'platformRefresh':'not_needed','missingDates':[]}
    read(ranges(missing()))
    if boundary is None:
        boundary = infer_boundary(fallback=not missing())
    needs_platform = boundary is None or bool(missing())
    if needs_platform and refresh:
        checkpoint(should_stop)
        if progress: progress('小V猫本地仍有缺口，正在主动获取官方账号数据；返回后补读缺失日期')
        try:
            result = client.call('vcat_refresh_account_stats', {'uids':[uid]})
            refresh_state = 'success' if any(r.get('uid') == uid and r.get('success') is True for r in result.get('results', [])) else 'unconfirmed'
        except CollectionStopped:
            raise
        except Exception:
            refresh_state = 'failed'
        # Refresh has no date parameter; query only still-missing dates afterwards.
        read(ranges(missing()))
        if boundary is None:
            boundary = infer_boundary()
    if boundary is None and (not refresh or refresh_state in ('success', 'not_needed')):
        boundary = infer_boundary(fallback=True)
    gaps = missing()
    state = 'complete' if boundary and not gaps else 'partial'
    metadata = {'state':state,'boundary':boundary,'checkedThrough':end,'missingDates':gaps,
                'queryFailures':failures,'platformRefresh':refresh_state,'checkedAt':at,'oldestQueriedDate':oldest_checked}
    payload['daily'] = [current[day] for day in sorted(current)]
    payload['dailyCollection'] = metadata
    return payload, {'state':state,'startDate':boundary['startDate'] if boundary else None,'endDate':end,
                     'localQueries':queried,'platformRefresh':refresh_state,'missingDates':gaps,
                     'boundaryConfirmed':bool(boundary),'queryFailures':failures}


def reset_daily(client, uid, existing, end, at, *, progress=None, should_stop=None, save_partial=None):
    """Refresh online first and rebuild coverage; failed reads retain saved facts."""
    from server.publishing.vcat import discard_home_visits
    from server.collection_progress import checkpoint, CollectionStopped
    original = discard_home_visits(dict(existing or {}))
    old_rows = {row['date']: dict(row) for row in original.get('daily', []) if isinstance(row, dict) and isinstance(row.get('date'), str)}

    def retained(fresh, pending=True):
        rows = dict(old_rows)
        for row in fresh.get('daily', []):
            day = row['date']
            if complete(row):
                rows[day] = {**rows.get(day, {}), **{key: value for key, value in row.items() if value is not None}}
            elif not complete(rows.get(day)):
                old = rows.get(day, {})
                rows[day] = {**row, **{key: value for key, value in old.items() if value is not None}}
        return {**original, **fresh, 'daily': [rows[day] for day in sorted(rows)],
                'dailyCollection': {**fresh.get('dailyCollection', {}), 'resetPending': pending, 'mode': 'reset_online'}}

    pending = retained({'daily': [], 'dailyCollection': {'state': 'partial', 'boundary': None, 'checkedThrough': end, 'missingDates': [], 'checkedAt': at}})
    if save_partial:
        save_partial(pending)
    checkpoint(should_stop)
    if progress:
        progress('强制获取在线每日数据：正在请求小V猫刷新官方；原数据保留，返回后最多反推90天确认起始日')
    try:
        response = client.call('vcat_refresh_account_stats', {'uids': [uid]})
        confirmed = any(row.get('uid') == uid and row.get('success') is True for row in response.get('results', []))
    except CollectionStopped:
        raise
    except Exception:
        confirmed = False
    if not confirmed:
        pending['dailyCollection']['platformRefresh'] = 'failed'
        return pending, {'state': 'partial', 'startDate': None, 'endDate': end, 'localQueries': [], 'platformRefresh': 'failed', 'missingDates': [], 'boundaryConfirmed': False, 'resetError': '在线刷新未成功确认，原有每日数据已保留，请重试'}
    checkpoint(should_stop)
    if progress:
        progress('在线刷新已完成，正在重新读取每日数据，最多反推90天确认起始日')
    def save_fresh(value):
        value = {**value, 'dailyCollection': {**value.get('dailyCollection', {}), 'platformRefresh': 'success'}}
        if save_partial:
            save_partial(retained(value))
    fresh, info = collect_daily(client, uid, {}, end, at, refresh=False, progress=progress, should_stop=should_stop, save_partial=save_fresh)
    fresh['dailyCollection']['platformRefresh'] = 'success'
    fresh['dailyCollection']['resetAt'] = at
    info['platformRefresh'] = 'success'
    return retained(fresh, pending=info['state'] != 'complete'), info
