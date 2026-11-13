"""Select bounded attempt evidence from summary files; never query business state."""
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

from .diagnostic_report import load_records, measures, profile

MAX_DETAILS = 200
MAX_BASELINES = 12


def record_key(row):
    meta = row['metadata']
    value = [meta.get('job_id'), meta.get('attempt'), meta.get('session_id')]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode('utf8')).hexdigest()


def session(row):
    return row['metadata'].get('session_id') or ''


def options(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise ValueError('诊断导出条件格式不正确')
    scope = value.get('scope', 'recent')
    if scope not in ('recent', 'selected', 'all'):
        raise ValueError('请选择最近一轮、指定任务或全部历史')
    limit = value.get('limit', 30)
    if type(limit) is not int or not 1 <= limit <= MAX_DETAILS:
        raise ValueError('详细日志数量必须为1至200的整数')
    baseline = value.get('include_baseline', True)
    if type(baseline) is not bool:
        raise ValueError('正常对照样本设置不正确')
    keys = value.get('attempt_keys', [])
    if not isinstance(keys, list) or any(not isinstance(k, str) or not re.fullmatch(r'[a-f0-9]{64}', k) for k in keys):
        raise ValueError('指定任务记录不正确，请重新打开弹窗选择')
    keys = list(dict.fromkeys(keys))
    if scope == 'selected' and not 1 <= len(keys) <= MAX_DETAILS:
        raise ValueError('请勾选1至200条任务记录')
    result = {'scope': scope, 'limit': limit, 'include_baseline': baseline, 'attempt_keys': keys}
    if 'session_id' in value:
        if value['session_id'] is not None and not isinstance(value['session_id'], str):
            raise ValueError('运行批次不正确')
        result['session_id'] = value['session_id'] or ''
    return result


def catalog(root):
    rows, errors = load_records(root)
    latest = session(rows[-1]) if rows else ''
    return {'items': [{'key': record_key(r), 'name': r['metadata'].get('name') or r['metadata']['job_id'],
                      'attempt': r['metadata'].get('attempt'), 'session_id': session(r),
                      'started_at': r.get('started_at', ''), 'status': r.get('status', 'unknown')}
                     for r in reversed(rows)],
            'latest_session_id': latest, 'latest_session_count': sum(session(r) == latest for r in rows),
            'total': len(rows), 'read_error_count': len(errors)}


def select(rows, request):
    scope = request['scope']
    latest = request.get('session_id', session(rows[-1]) if rows else '')
    if scope == 'recent':
        summary = [r for r in rows if session(r) == latest]
        if rows and not summary:
            raise ValueError('所选运行批次已无可用记录，请重新打开弹窗')
        newest = list(reversed(summary))
        running = [r for r in newest if r.get('status') == 'running']
        primary = (running + [r for r in newest if r.get('status') != 'running'])[:request['limit']]
    elif scope == 'selected':
        lookup = {record_key(r): r for r in rows}
        if any(k not in lookup for k in request['attempt_keys']):
            raise ValueError('部分指定记录已不可用，请重新打开弹窗选择；本次未扩大导出范围')
        primary = [lookup[k] for k in request['attempt_keys']]
        summary = primary
    else:
        summary = rows
        primary = rows
    primary = sorted(primary, key=lambda r: r.get('started_at', ''))
    keys = {record_key(r) for r in primary}
    baselines = []
    if scope != 'all' and request['include_baseline']:
        groups = {}
        for r in reversed(primary):
            groups.setdefault(profile(r), r.get('started_at', ''))
            groups[profile(r)] = min(groups[profile(r)], r.get('started_at', ''))
        for group, first in groups.items():
            # Earliest completed matching records from the same process session.
            candidates = [r for r in rows if profile(r) == group and r.get('status') == 'done'
                          and r.get('started_at', '') < first and record_key(r) not in keys and measures(r)['encode_fps']]
            for r in candidates[:3]:
                if len(baselines) == MAX_BASELINES:
                    break
                baselines.append(r)
                keys.add(record_key(r))
    details = sorted(primary + baselines, key=lambda r: r.get('started_at', ''))
    if scope == 'selected':
        summary = details
    summary = sorted(summary, key=lambda r: r.get('started_at', ''))
    info = {'scope': scope, 'label': {'recent': '最近一轮运行', 'selected': '指定任务', 'all': '全部历史'}[scope],
            'limit': request['limit'] if scope == 'recent' else None,
            'include_baseline': request['include_baseline'] and scope != 'all',
            'summary_attempts': len(summary), 'primary_attempts': len(primary),
            'baseline_attempts': len(baselines), 'detailed_attempts': len(details),
            'omitted_detail_attempts': len(summary) - len(details), 'discovered_attempts': len(rows),
            'summary_keys': [record_key(r) for r in summary], 'detail_keys': [record_key(r) for r in details],
            'baseline_keys': [record_key(r) for r in baselines],
            'statuses': dict(Counter(r.get('status', 'unknown') for r in summary))}
    return summary, details, info


def detail_folders(root, rows):
    root = Path(root).resolve()
    folders, missing = [], []
    for r in rows:
        meta = r['metadata']
        job, attempt = str(meta.get('job_id') or ''), meta.get('attempt')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', job) or type(attempt) is not int or attempt < 1:
            missing.append(record_key(r)); continue
        folder = root / job[:12] / f'a{attempt}'
        if folder.is_symlink() or not folder.resolve().is_relative_to(root):
            missing.append(record_key(r)); continue
        try:
            saved = json.loads((folder / 'performance-summary.json').read_text(encoding='utf-8-sig'))
            if record_key(saved) != record_key(r):
                missing.append(record_key(r)); continue
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            missing.append(record_key(r)); continue
        folders.append(folder)
    return list(dict.fromkeys(folders)), missing


def _time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError, AttributeError):
        return None


def select_operations(operations, summary):
    sessions = {session(r) for r in summary if session(r)}
    windows = []
    for r in summary:
        start = _time(r.get('started_at'))
        end = _time(r.get('updated_at')) or start
        if start and end:
            windows.append((start - timedelta(minutes=2), end + timedelta(minutes=2)))
    merged = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    starts = [start for start, _ in merged]
    indexes, ids = set(), set()
    for index, r in enumerate(operations):
        if not isinstance(r, dict):
            continue
        identity = r.get('session_id')
        at = _time(r.get('at'))
        position = bisect_right(starts, at) - 1 if at else -1
        in_window = position >= 0 and at <= merged[position][1]
        if (identity and identity in sessions) or (not identity and in_window):
            indexes.add(index)
            if r.get('operation_id'):
                ids.add(r['operation_id'])
    # Keep starts/finishes paired, even when one side is just outside the time range.
    return [r for index, r in enumerate(operations) if isinstance(r, dict)
            and (index in indexes or r.get('operation_id') in ids)]
