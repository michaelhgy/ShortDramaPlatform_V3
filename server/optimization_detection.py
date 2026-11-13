"""Persist account detection cadence; never call Xiao V Cat from a timer directly."""
from __future__ import annotations

import json
import random
import time
from contextlib import closing
from datetime import datetime

from server import operations_collection as ops

DEFAULTS = {'enabled': False, 'min_minutes': 50, 'max_minutes': 70, 'paused_reason': ''}


class OptimizationDetection:
    def __init__(self, connection, *, clock=time.time, uniform=random.uniform):
        self.connection, self.clock, self.uniform = connection, clock, uniform
        with closing(connection()) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS v3_optimization_detection_settings(
                    id INTEGER PRIMARY KEY CHECK(id=1), payload_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS v3_optimization_detection_accounts(
                    uid TEXT PRIMARY KEY, account_id TEXT NOT NULL, next_due REAL NOT NULL,
                    requested_at REAL NOT NULL DEFAULT 0, last_attempt TEXT NOT NULL DEFAULT '',
                    last_success TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '');
            """)
            conn.commit()

    def settings(self):
        with closing(self.connection()) as conn:
            row = conn.execute('SELECT payload_json FROM v3_optimization_detection_settings WHERE id=1').fetchone()
        saved = json.loads(row[0]) if row else {}
        return {key: saved.get(key, value) for key, value in DEFAULTS.items()}

    def records(self):
        with closing(self.connection()) as conn:
            return {r['uid']: dict(r) for r in conn.execute('SELECT * FROM v3_optimization_detection_accounts')}

    def state(self):
        return {**self.settings(), 'accounts': list(self.records().values())}

    def _next(self, settings=None):
        cfg = settings or self.settings()
        return self.clock() + self.uniform(cfg['min_minutes'], cfg['max_minutes']) * 60

    def save(self, payload, available):
        if not isinstance(payload, dict) or type(payload.get('enabled')) is not bool:
            raise ValueError('请选择是否开启自动检测')
        low, high = payload.get('min_minutes'), payload.get('max_minutes')
        if any(type(x) is not int or not 1 <= x <= 1440 for x in (low, high)) or low > high:
            raise ValueError('随机检测间隔需为1至1440分钟，最小值不能大于最大值')
        previous = self.settings()
        cfg = {'enabled': payload['enabled'], 'min_minutes': low, 'max_minutes': high,
               'paused_reason': ''}
        changed = (low, high) != (previous['min_minutes'], previous['max_minutes'])
        with closing(self.connection()) as conn:
            conn.execute('INSERT INTO v3_optimization_detection_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json', (ops.dump(cfg),))
            for aid, account in available.items():
                uid = account['uid']
                conn.execute("""INSERT INTO v3_optimization_detection_accounts(uid,account_id,next_due) VALUES(?,?,?)
                    ON CONFLICT(uid) DO UPDATE SET account_id=excluded.account_id,
                    next_due=CASE WHEN ? THEN excluded.next_due ELSE next_due END""",
                    (uid, aid, self._next(cfg), changed or not previous['enabled']))
            conn.commit()
        return self.state()

    def request(self, ids, available):
        if not isinstance(ids, list) or not ids or any(not isinstance(a, str) or a not in available for a in ids):
            raise ValueError('请先选择需要立即检测的有效账号')
        with closing(self.connection()) as conn:
            for aid in dict.fromkeys(ids):
                uid = available[aid]['uid']
                conn.execute("""INSERT INTO v3_optimization_detection_accounts(uid,account_id,next_due,requested_at) VALUES(?,?,?,?)
                    ON CONFLICT(uid) DO UPDATE SET account_id=excluded.account_id,requested_at=excluded.requested_at""",
                    (uid, aid, self._next(), self.clock()))
            conn.commit()

    def due_ids(self, available):
        cfg, records, now = self.settings(), self.records(), self.clock()
        automatic = set(available) if cfg['enabled'] and not cfg['paused_reason'] else set()
        missing = [(a['uid'], aid, self._next(cfg)) for aid, a in available.items() if aid in automatic and a['uid'] not in records]
        if missing:
            with closing(self.connection()) as conn:
                conn.executemany('INSERT OR IGNORE INTO v3_optimization_detection_accounts(uid,account_id,next_due) VALUES(?,?,?)', missing)
                conn.commit()
            records = self.records()
        return [aid for aid, a in available.items() if (r := records.get(a['uid'])) and
                (r['requested_at'] > 0 or aid in automatic and r['next_due'] <= now)]

    def due(self, uid):
        row = self.records().get(uid)
        return not row or not row['last_success'] and not row['last_attempt'] or row['requested_at'] > 0 or row['next_due'] <= self.clock()

    def defer(self, aid, uid, *, message='', success=False, attempted=False):
        at = datetime.fromtimestamp(self.clock(), ops.SH).strftime('%Y-%m-%d %H:%M:%S')
        with closing(self.connection()) as conn:
            conn.execute("""INSERT INTO v3_optimization_detection_accounts(uid,account_id,next_due,requested_at,last_attempt,last_success,last_error)
                VALUES(?,?,?,0,?,?,?) ON CONFLICT(uid) DO UPDATE SET account_id=excluded.account_id,
                next_due=excluded.next_due,requested_at=0,
                last_attempt=CASE WHEN ? THEN excluded.last_attempt ELSE last_attempt END,
                last_success=CASE WHEN ? THEN excluded.last_success ELSE last_success END,last_error=excluded.last_error""",
                (uid, aid, self._next(), at if attempted else '', at if success else '', message, attempted, success))
            conn.commit()

    def pause(self):
        cfg = self.settings()
        cfg['paused_reason'] = '检测遇到访问限制，自动检测已暂停；处理后可手动检测，或重新保存自动检测设置'
        with closing(self.connection()) as conn:
            conn.execute('INSERT INTO v3_optimization_detection_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json', (ops.dump(cfg),))
            # Queued manual requests must not bypass an access-limit pause.
            conn.execute('UPDATE v3_optimization_detection_accounts SET requested_at=0')
            conn.commit()
