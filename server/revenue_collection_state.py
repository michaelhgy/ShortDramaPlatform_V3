"""Durable revenue collection state and date-based accounting for V3."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import uuid

SHANGHAI = timezone(timedelta(hours=8))


def clock():
    return datetime.now(SHANGHAI)


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS v3_revenue_pending_queries (attempt_id TEXT PRIMARY KEY)')
    from server.revenue_collectors import initialize as initialize_bindings
    initialize_bindings(conn)
    # execute, rather than executescript: never commit a caller's partial unit.
    conn.execute("""CREATE TABLE IF NOT EXISTS v3_revenue_backfills (
        account_id TEXT NOT NULL, theater_id TEXT NOT NULL, adapter_key TEXT NOT NULL,
        anchor_date TEXT NOT NULL, boundary_date TEXT NOT NULL DEFAULT '',
        complete INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(account_id,theater_id,adapter_key))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS v3_revenue_cumulative_snapshots (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL, theater_id TEXT NOT NULL,
        adapter_key TEXT NOT NULL, source_period TEXT NOT NULL,
        observation_date TEXT NOT NULL, raw_amount TEXT NOT NULL,
        credited_amount TEXT NOT NULL, attempt_id TEXT NOT NULL, collected_at TEXT NOT NULL,
        UNIQUE(account_id,theater_id,adapter_key,source_period,observation_date))""")


def backfill_plan(conn, account, adapter, anchor_date):
    key = (account['id'], account['theater_id'], adapter)
    conn.execute("""INSERT OR IGNORE INTO v3_revenue_backfills
        (account_id,theater_id,adapter_key,anchor_date) VALUES(?,?,?,?)""", (*key, anchor_date))
    state = conn.execute("""SELECT * FROM v3_revenue_backfills
        WHERE account_id=? AND theater_id=? AND adapter_key=?""", key).fetchone()
    return state if not state['complete'] else None


def pending_attempts(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_revenue_pending_queries'").fetchone():
        return set()
    return {r[0] for r in conn.execute('SELECT attempt_id FROM v3_revenue_pending_queries')}


def recheck_days(spec=None):
    """Per-collector policy; the history empty-streak limit is independent."""
    return max(1, int((spec or {}).get('empty_recheck_days', 7)))


def recent_empty(day, moment, spec=None):
    age = (moment.astimezone(SHANGHAI).date() - date.fromisoformat(day)).days
    return 1 <= age <= recheck_days(spec)


def retry_due(row, moment, spec=None):
    interval = max(1, int((spec or {}).get('recheck_interval_minutes', 60)))
    try:
        last = datetime.fromisoformat(row['collected_at'])
        last = last.replace(tzinfo=SHANGHAI) if last.tzinfo is None else last
    except (TypeError, ValueError):
        return True
    return moment.astimezone(SHANGHAI) >= last.astimezone(SHANGHAI) + timedelta(minutes=interval)


def completed(conn, account, adapter, day, *, collected_at=None, spec=None):
    row = conn.execute("""SELECT * FROM v2_revenue_collection_attempts
        WHERE account_id=? AND theater_id=? AND adapter_key=? AND revenue_date=?
          AND collection_status IN ('success','no_data')
          AND id NOT IN (SELECT attempt_id FROM v3_revenue_pending_queries)
        ORDER BY CASE collection_status WHEN 'success' THEN 0 ELSE 1 END,
                 collected_at DESC,rowid DESC LIMIT 1""",
        (account['id'], account['theater_id'], adapter, day)).fetchone()
    moment = collected_at or clock()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SHANGHAI)
    if (row and row['collection_status'] == 'no_data' and recent_empty(day, moment, spec)
            and retry_due(row, moment, spec)):
        return None
    return row


def cumulative_delta(conn, account, adapter, period, day, amount, attempt_id, now, baseline_periods=()):
    key = (account['id'], account['theater_id'], adapter, period)
    previous = conn.execute("""SELECT * FROM v3_revenue_cumulative_snapshots
        WHERE account_id=? AND theater_id=? AND adapter_key=? AND source_period=?
        ORDER BY observation_date DESC,collected_at DESC LIMIT 1""", key).fetchone()
    # Relabelling a previously unknown period is not a new earning. Keep all
    # old evidence and reuse its baseline instead of crediting the total twice.
    if previous is None and baseline_periods:
        placeholders = ','.join('?' for _ in baseline_periods)
        previous = conn.execute(f"""SELECT * FROM v3_revenue_cumulative_snapshots
            WHERE account_id=? AND theater_id=? AND adapter_key=? AND source_period IN ({placeholders})
            ORDER BY observation_date DESC,collected_at DESC LIMIT 1""", (*key[:3], *baseline_periods)).fetchone()
    if previous and day < previous['observation_date']:
        raise ValueError('采集日期早于已保存累计快照，未入账')
    baseline = Decimal(previous['raw_amount']) if previous else Decimal('0')
    if previous is None and (period == 'unknown' or 'unknown' in baseline_periods):
        # Old successful attempts stored the source's raw cumulative value.
        legacy = conn.execute("""SELECT amount FROM v2_revenue_collection_attempts
            WHERE account_id=? AND theater_id=? AND adapter_key=?
              AND collection_status='success' AND amount IS NOT NULL
              AND (period_end='unknown' OR period_end IS NULL OR period_end='')
            ORDER BY collected_at DESC,rowid DESC LIMIT 1""", key[:3]).fetchone()
        if legacy:
            baseline = Decimal(legacy['amount'])
    delta = amount - baseline
    if delta < 0:
        raise ValueError('累计金额低于上次快照，周期重置或金额修订待核对；未入账、未改基线')
    same_day_credit = (Decimal(previous['credited_amount'])
                       if previous and previous['source_period'] == period and previous['observation_date'] == day else Decimal('0'))
    conn.execute("""INSERT INTO v3_revenue_cumulative_snapshots
        (id,account_id,theater_id,adapter_key,source_period,observation_date,
         raw_amount,credited_amount,attempt_id,collected_at) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(account_id,theater_id,adapter_key,source_period,observation_date)
        DO UPDATE SET raw_amount=excluded.raw_amount,credited_amount=excluded.credited_amount,
          attempt_id=excluded.attempt_id,collected_at=excluded.collected_at""",
        (uuid.uuid4().hex,*key,day,format(amount,'f'),format(same_day_credit+delta,'f'),attempt_id,now))
    total = sum((Decimal(r[0]) for r in conn.execute("""SELECT credited_amount
        FROM v3_revenue_cumulative_snapshots WHERE account_id=? AND theater_id=?
        AND adapter_key=? AND observation_date=?""", (*key[:3],day))), Decimal('0'))
    return delta, total


def write_day(conn, account, adapter, day, amount, attempt_id, request_id, now, metadata):
    if metadata.get('method') == 'cumulative_delta':
        metadata = dict(metadata, components=[dict(r) for r in conn.execute("""SELECT source_period,
            raw_amount,credited_amount,attempt_id,collected_at FROM v3_revenue_cumulative_snapshots
            WHERE account_id=? AND theater_id=? AND adapter_key=? AND observation_date=?
            ORDER BY source_period""", (account['id'],account['theater_id'],adapter,day))])
    text = format(amount, 'f')
    conn.execute("""INSERT INTO v2_daily_revenues
        (id,account_id,theater_id,revenue_date,amount,quality,source_attempt_id,created_at,updated_at)
        VALUES(?,?,?,?,?,'direct',?,?,?) ON CONFLICT(account_id,revenue_date) DO UPDATE SET
        amount=excluded.amount,theater_id=excluded.theater_id,source_attempt_id=excluded.source_attempt_id,
        updated_at=excluded.updated_at""",
        (uuid.uuid4().hex,account['id'],account['theater_id'],day,text,attempt_id,now,now))
    conn.execute("""INSERT INTO v3_revenue_account_periods
        (id,account_id,theater_id,period_label,period_start,period_end,period_type,date_precision,
         amount,data_state,freshness_state,settlement_state,include_in_analysis,source_kind,
         source_attempt_id,collection_run_id,collected_at,raw_result_json)
        VALUES(?,?,?,?,?,?,'day','day',?,?,'collected','unknown',1,?,?,?,?,?)
        ON CONFLICT(account_id,theater_id,period_label,period_type,source_kind) DO UPDATE SET
        amount=excluded.amount,data_state=excluded.data_state,include_in_analysis=1,
        freshness_state=excluded.freshness_state,source_attempt_id=excluded.source_attempt_id,
        collection_run_id=excluded.collection_run_id,collected_at=excluded.collected_at,
        raw_result_json=excluded.raw_result_json""",
        (uuid.uuid4().hex,account['id'],account['theater_id'],day,day,day,text,
         'confirmed_zero' if amount == 0 else 'record','theater_collector',attempt_id,request_id,now,
         json.dumps(dict(metadata,adapter_key=adapter),ensure_ascii=False)))
