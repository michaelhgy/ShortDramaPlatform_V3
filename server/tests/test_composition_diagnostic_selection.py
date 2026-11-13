from datetime import datetime, timedelta
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest
from server.ffmpeg_finals.diagnostic_export import export_diagnostics
from server.ffmpeg_finals.diagnostic_report import load_records
from server.ffmpeg_finals.diagnostic_selection import catalog, options, record_key, select, select_operations


def write_attempt(root, index, *, session='current', day=5, template='template', status='done'):
    identity = f'{index:012x}' + 'a' * 20
    stamp = (datetime(2026, 11, day, 0, 0) + timedelta(minutes=index)).isoformat()
    row = {'metadata': {'job_id': identity, 'attempt': 1, 'session_id': session, 'name': f'诊断任务{index}',
                        'template_id': template, 'sequence': index, 'media_seconds': 600},
           'started_at': stamp, 'updated_at': stamp, 'status': status,
           'context': {'encoder': 'h264_nvenc', 'acceleration': {'transfer': 'vulkan'},
                       'source': {'source_width': 720, 'source_height': 1280, 'source_codec_name': 'h264', 'source_fps': '30/1'}},
           'stages': [{'stage': 'ffmpeg:compose', 'seconds': 60, 'frames': 18000, 'status': 'done'}]}
    folder = root / identity[:12] / 'a1'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'performance-summary.json').write_text(json.dumps(row), encoding='utf8')
    (folder / 'compose.log').write_text(f'{session}-detail-{index}', encoding='utf8')
    return row, folder


def run_export(tmp_path, request=None):
    with patch('server.ffmpeg_finals.diagnostic_export.os.startfile', create=True):
        return export_diagnostics(tmp_path / 'workspace', tmp_path / 'data', request)


def test_default_500_attempts_keeps_only_latest_30_plus_3_matching_baselines(tmp_path):
    root = tmp_path / 'data/fg'
    old, _ = write_attempt(root, 800, session='old', day=3)
    for index in range(500):
        write_attempt(root, index, status='running' if index == 400 else 'done')
    shared = root / 'diagnostics'; shared.mkdir()
    (shared / 'composition-history.jsonl').write_text(json.dumps(old) + '\n', encoding='utf8')
    ops = [{'at': '2026-11-03T00:00:00', 'session_id': 'old', 'event': 'snapshot_read', 'name': 'old-only-marker'},
           {'at': '2026-11-05T08:00:00', 'session_id': 'current', 'event': 'snapshot_read', 'name': 'current-only-marker'}]
    (shared / 'scheduler-events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in ops), encoding='utf8')
    blocked = root / f'{800:012x}/a1/compose.log'
    original_open = Path.open

    def guard(path, *args, **kwargs):
        assert path != blocked, 'unselected old task detail must never be read'
        return original_open(path, *args, **kwargs)

    with patch.object(Path, 'open', guard):
        result = run_export(tmp_path)
    selection = result['selection']
    assert result['summary_attempts'] == 500 and result['attempts'] == 33
    assert selection['primary_attempts'] == 30 and selection['baseline_attempts'] == 3
    assert selection['omitted_detail_attempts'] == 467
    assert not selection['missing_detail_keys']
    with zipfile.ZipFile(result['bundle_path']) as archive:
        logs = [name for name in archive.namelist() if name.endswith('/compose.log')]
        assert len(logs) == 33
        indexes = {int(name.split('/')[0], 16) for name in logs}
        assert indexes == {0, 1, 2, 400, *range(471, 500)}
        history = [json.loads(line) for line in archive.read('diagnostics/composition-history.jsonl').splitlines()]
        assert len(history) == 500 and all(row['metadata']['session_id'] == 'current' for row in history)
        operations = archive.read('diagnostics/scheduler-events.jsonl')
        assert b'old-only-marker' not in operations and b'current-only-marker' in operations
        assert len(archive.namelist()) == len(set(archive.namelist()))
        manifest = json.loads(archive.read('bundle-manifest.json'))
        assert manifest['selection']['detailed_attempts'] == 33
    report = Path(result['report_path']).read_text(encoding='utf8')
    assert report.count('### ') == 33
    assert '简要统计 500 条，详细记录 33 条' in report
    assert '467 条仅保留摘要' in report


def test_selected_records_baseline_stays_in_same_session_and_can_be_disabled(tmp_path):
    root = tmp_path / 'data/fg'
    for index in range(5):
        row, _ = write_attempt(root, index, session='old', day=3)
    write_attempt(root, 100)
    key = record_key(row)
    request = {'scope': 'selected', 'attempt_keys': [key], 'include_baseline': False}
    result = run_export(tmp_path, request)
    assert result['attempts'] == result['summary_attempts'] == 1
    assert result['selection']['baseline_attempts'] == 0
    with zipfile.ZipFile(result['bundle_path']) as archive:
        assert [n for n in archive.namelist() if n.endswith('compose.log')] == [f'{4:012x}/a1/compose.log']
        assert b'current' not in archive.read('diagnostics/composition-history.jsonl')
    result = run_export(tmp_path, {**request, 'include_baseline': True})
    assert result['attempts'] == result['summary_attempts'] == 4
    assert result['selection']['baseline_attempts'] == 3


def test_all_is_explicit_and_keeps_retained_shared_history_without_duplicate_entries(tmp_path):
    root = tmp_path / 'data/fg'
    for index in range(40):
        write_attempt(root, index)
    shared = root / 'diagnostics'; shared.mkdir()
    original = b'{"retained-original":"yes"}\n'
    (shared / 'scheduler-events.jsonl').write_bytes(original)
    result = run_export(tmp_path, {'scope': 'all', 'include_baseline': False})
    assert result['attempts'] == result['summary_attempts'] == 40
    with zipfile.ZipFile(result['bundle_path']) as archive:
        assert len([n for n in archive.namelist() if n.endswith('/compose.log')]) == 40
        assert archive.read('diagnostics/scheduler-events.jsonl') == original
        assert len(archive.namelist()) == len(set(archive.namelist()))


@pytest.mark.parametrize('conditions', [
    {'scope': 'other'}, {'limit': 0}, {'limit': 201}, {'limit': 3.5}, {'limit': True},
    {'include_baseline': 'false'}, {'scope': 'selected'}, {'scope': 'selected', 'attempt_keys': ['../arbitrary']},
    {'scope': 'selected', 'attempt_keys': ['a' * 64]}, {'scope': 'recent', 'session_id': 'missing'},
])
def test_invalid_or_missing_selection_never_falls_back_to_all_or_creates_output(tmp_path, conditions):
    write_attempt(tmp_path / 'data/fg', 1)
    with pytest.raises(ValueError):
        run_export(tmp_path, conditions)
    assert not (tmp_path / 'workspace').exists()


def test_older_session_summary_never_attaches_newer_session_details_in_reused_folder(tmp_path):
    root = tmp_path / 'data/fg'
    old, folder = write_attempt(root, 1, session='old', day=3)
    write_attempt(root, 1, session='current', day=5)
    shared = root / 'diagnostics'; shared.mkdir()
    (shared / 'composition-history.jsonl').write_text(json.dumps(old) + '\n', encoding='utf8')
    result = run_export(tmp_path, {'scope': 'selected', 'attempt_keys': [record_key(old)], 'include_baseline': False})
    assert len(result['selection']['missing_detail_keys']) == 1
    assert any('详细日志缺失' in warning for warning in result['warnings'])
    with zipfile.ZipFile(result['bundle_path']) as archive:
        assert not any(n.endswith('/compose.log') for n in archive.namelist())
        assert 'old' in archive.read('diagnostics/composition-history.jsonl').decode('utf8')
        assert b'current-detail' not in b''.join(archive.read(n) for n in archive.namelist())


def test_baselines_are_bounded_across_many_profiles(tmp_path):
    rows = []
    for index in range(30):
        row, _ = write_attempt(tmp_path, index, template=f'group-{index // 5}')
        rows.append(row)
    for index in range(6):
        row, _ = write_attempt(tmp_path, 40 + index, template=f'group-{index}')
        rows.append(row)
    summary, details, info = select(rows, options({'limit': 6}))
    assert info['primary_attempts'] == 6 and info['baseline_attempts'] == 12
    assert len(details) == 18 and len(summary) == 36


def test_pinned_latest_session_and_read_only_catalog(tmp_path):
    root = tmp_path / 'data/fg'
    old, _ = write_attempt(root, 1, session='old', day=3)
    write_attempt(root, 20)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    value = catalog(root)
    assert value['total'] == 2 and value['latest_session_count'] == 1 and value['latest_session_id'] == 'current'
    assert value['items'][0]['name'] == '诊断任务20'
    assert value['items'][1]['key'] == record_key(old)
    result = run_export(tmp_path, {'scope': 'recent', 'session_id': 'old', 'include_baseline': False})
    assert result['summary_attempts'] == 1
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_operation_time_filter_keeps_pairs_without_unrelated_sessions():
    summary = [{'metadata': {'session_id': 's'}, 'started_at': '2026-11-05T10:00:00', 'updated_at': '2026-11-05T10:10:00'}]
    operations = [
        {'at': '2026-11-04T00:00:00', 'operation_id': 'pair', 'event': 'operation_started'},
        {'at': '2026-11-05T10:01:00', 'operation_id': 'pair', 'event': 'operation_finished'},
        {'at': '2026-11-05T10:02:00', 'session_id': 'other', 'name': 'wrong-session'},
        {'at': '2026-11-05T10:03:00', 'name': 'snapshot'},
        {'at': '2026-11-04T00:00:00', 'name': 'unrelated'}, None,
    ]
    assert select_operations(operations, summary) == [operations[0], operations[1], operations[3]]


def test_catalog_http_never_initializes_or_recovers_jobs(tmp_path):
    from server import v2_file_service as service
    from server.ffmpeg_finals.http import handle
    write_attempt(tmp_path / 'data/fg', 1)

    class Handler:
        def _json(self, status, value):
            self.status, self.value = status, value

    handler = Handler()
    with patch.object(service, 'require_configured_paths', return_value=(tmp_path / 'workspace', tmp_path / 'data')), \
         patch('server.ffmpeg_finals.http.get_composer', side_effect=AssertionError('must not recover')):
        assert handle(handler, 'GET', '/api/v3/final-composition/diagnostics/catalog')
    assert handler.status == 200 and handler.value['total'] == 1
    assert not (tmp_path / 'workspace').exists()


def test_http_export_forwards_selected_conditions_and_rejects_unknown_keys(tmp_path):
    from server import v2_file_service as service
    from server.ffmpeg_finals.http import handle
    first, _ = write_attempt(tmp_path / 'data/fg', 1)
    write_attempt(tmp_path / 'data/fg', 2)

    class Handler:
        def _json(self, status, value):
            self.status, self.value = status, value

    handler = Handler()
    with patch.object(service, 'require_configured_paths', return_value=(tmp_path / 'workspace', tmp_path / 'data')), \
         patch('server.ffmpeg_finals.http.get_composer', side_effect=AssertionError('must not recover')), \
         patch('server.ffmpeg_finals.diagnostic_export.os.startfile', create=True):
        assert handle(handler, 'POST', '/api/v3/final-composition/diagnostics/export',
                      {'scope': 'selected', 'attempt_keys': [record_key(first)], 'include_baseline': False})
        assert handler.status == 200 and handler.value['attempts'] == 1
        with zipfile.ZipFile(handler.value['bundle_path']) as archive:
            assert f'{1:012x}/a1/compose.log' in archive.namelist()
            assert f'{2:012x}/a1/compose.log' not in archive.namelist()
        prior_outputs = set((tmp_path / 'workspace').rglob('*'))
        assert handle(handler, 'POST', '/api/v3/final-composition/diagnostics/export',
                      {'scope': 'selected', 'attempt_keys': ['f' * 64]})
        assert handler.status == 400 and '已不可用' in handler.value['error']
        assert prior_outputs == set((tmp_path / 'workspace').rglob('*'))
