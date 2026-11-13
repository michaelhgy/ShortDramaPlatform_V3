"""Global exact-text label assignments; never alter source notices or platform state."""
import hashlib
import json
import re
from server import operations_collection as ops

KEY = 'optimization_analysis_labels'


class MappingConflict(ValueError):
    pass


def normalize(text):
    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.I).replace('&nbsp;', ' ')
    text = re.sub(r'^\s*作品分析\s*[:：]\s*', '', text)
    return re.sub(r'[\s\ufeff]+', '', text)


def analysis_key(text):
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()


def configuration(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_publish_documents'").fetchone()
    row = conn.execute("SELECT content FROM v3_publish_documents WHERE kind='settings' AND key=?", (KEY,)).fetchone() if exists else None
    return json.loads(row[0]) if row else {'version': 0, 'mappings': []}


def groups(conn):
    config = configuration(conn)
    collected = {}

    def add(analysis, uid='', seen='', count=False):
        if not isinstance(analysis, str) or not normalize(analysis):
            return
        key = analysis_key(analysis)
        item = collected.setdefault(key, {'key': key, 'analysis': analysis, 'variants': set(),
            'record_count': 0, 'accounts': set(), 'last_seen_at': ''})
        item['variants'].add(analysis)
        if count:
            item['record_count'] += 1
            item['accounts'].add(uid)
            item['last_seen_at'] = max(item['last_seen_at'], seen)

    # Notices include unmatched identities and works later hidden/deleted. Grouping
    # does not need a work match, and cannot make an uncertain identity actionable.
    for row in conn.execute("""SELECT n.uid,n.detail_json,n.last_seen_at FROM v3_work_notices n
        WHERE EXISTS(SELECT 1 FROM accounts a WHERE a.channel_id=n.uid)"""):
        detail = json.loads(row['detail_json'])
        add(detail.get('reason'), row['uid'], row['last_seen_at'], True)
    # Retain saved mappings even if a source account is later retired.
    for mapping in config['mappings']:
        add(mapping['analysis'])
    result = []
    for item in collected.values():
        accounts = item.pop('accounts')
        item['account_count'] = len(accounts)
        item['variants'] = sorted(item['variants'])
        result.append(item)
    result.sort(key=lambda item: (-item['record_count'], item['key']))
    return {'configuration': config, 'groups': result}


def save_mapping(conn, payload):
    if not isinstance(payload, dict) or set(payload) != {'key', 'tag', 'expected_version'}:
        raise ValueError('作品分析归类参数无效')
    version = payload['expected_version']
    if type(version) is not int or version < 0:
        raise ValueError('作品分析设置版本无效，请刷新后重试')
    if not isinstance(payload['key'], str) or not re.fullmatch('[a-f0-9]{64}', payload['key']):
        raise ValueError('请选择已经收集到的作品分析')
    tag = payload['tag']
    if tag is not None and (not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 80):
        raise ValueError('标签不能为空，且不能超过80个字符')
    if tag is not None:
        tag = tag.strip()
    if not conn.in_transaction:
        conn.execute('BEGIN IMMEDIATE')
    current = groups(conn)
    config = current['configuration']
    if config['version'] != version:
        raise MappingConflict('作品分析归类已被其他窗口或用户修改，请刷新后核对再保存')
    group = next((g for g in current['groups'] if g['key'] == payload['key']), None)
    if group is None:
        raise ValueError('这条作品分析已经变化，请刷新后重新选择')
    mappings = [m for m in config['mappings'] if analysis_key(m['analysis']) != group['key']]
    if tag is not None:
        mappings.append({'analysis': group['analysis'], 'tag': tag, 'updated_at': ops.stamp()})
    value = {'version': version + 1, 'mappings': mappings}
    conn.execute("""INSERT INTO v3_publish_documents(kind,key,content,updated_at) VALUES('settings',?,?,?)
        ON CONFLICT(kind,key) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at""",
        (KEY, ops.dump(value), ops.stamp()))
    return groups(conn)
