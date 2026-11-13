"""Replace only explicitly marked legacy demo notices; acquisition and real caches stay untouched."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'src/data/optimizationNoticeRules.json').read_text(encoding='utf-8'))


def plan_replacement(conn: sqlite3.Connection) -> list[dict]:
    result = []
    cursor = conn.execute("SELECT id,source_kind,punish_state,payload_json FROM v3_video_post_punishments WHERE source_kind IN ('development_seed','simulation_ui') ORDER BY id")
    for notice_id, source, state, payload in cursor:
        try:
            meta = json.loads(payload or '{}')
        except (ValueError, TypeError):
            continue
        if not isinstance(meta, dict) or meta.get('noticeMappingVersion') == CONFIG['version']:
            continue
        text = meta.get('notice', '')
        legacy = (source == 'development_seed' and meta.get('generated') is True and isinstance(text, str) and text.startswith('开发场景：'))
        legacy_ui = source == 'simulation_ui' and meta.get('simulation') is True and not text
        if not (legacy or legacy_ui):
            continue
        number = int(hashlib.sha256(notice_id.encode()).hexdigest(), 16) % len(CONFIG['rules'])
        rule = CONFIG['rules'][number]
        updated = {**meta, 'notice': rule['analysis'], 'simplifiedReason': rule['tag'],
                   'noticeRuleId': rule['id'], 'noticeMappingVersion': CONFIG['version']}
        updated.pop('severity', None)
        result.append({'id': notice_id, 'source': source, 'old_state': state, 'old_payload': payload,
                       'new_payload': json.dumps(updated, ensure_ascii=False, separators=(',', ':')), 'tag': rule['tag']})
    return result


def apply_replacement(conn: sqlite3.Connection, plan: list[dict]) -> None:
    """The caller owns the transaction, so an exception rolls back the entire batch."""
    for item in plan:
        cursor = conn.execute("""UPDATE v3_video_post_punishments SET payload_json=?,punish_state=''
            WHERE id=? AND source_kind=? AND payload_json=? AND punish_state=?""",
            (item['new_payload'], item['id'], item['source'], item['old_payload'], item['old_state']))
        if cursor.rowcount != 1:
            raise RuntimeError(f"notice changed since planning: {item['id']}")


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--expected-count', type=int)
    args = parser.parse_args()
    database = args.db.resolve(strict=True)
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as readonly:
        readonly.execute('PRAGMA query_only=ON')
        plan = plan_replacement(readonly)
        summary = {'version': CONFIG['version'], 'rows': len(plan), 'sources': dict(Counter(item['source'] for item in plan)),
                   'tags': dict(Counter(item['tag'] for item in plan)), 'applied': False}
        if not args.apply:
            print(json.dumps(summary, ensure_ascii=False))
            return
        if args.expected_count is None or len(plan) != args.expected_count:
            raise RuntimeError('expected count is required and must match the current dry run')
        if not args.backup or args.backup.exists() or args.backup.resolve() == database:
            raise RuntimeError('a new, separate backup path is required')
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(args.backup) as destination:
            readonly.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('backup integrity check failed')
    with sqlite3.connect(database, timeout=10) as conn:
        conn.execute('BEGIN IMMEDIATE')
        current = plan_replacement(conn)
        if current != plan:
            raise RuntimeError('notice records changed during backup; no changes applied')
        apply_replacement(conn, current)
        if plan_replacement(conn):
            raise RuntimeError('replacement validation failed')
    summary.update(applied=True, backup=str(args.backup.resolve()))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
