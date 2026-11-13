import json
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest
from server.ffmpeg_finals import diagnostic_export as exporter
from server.ffmpeg_finals.http import handle


def seed(root):
    attempt = root / 'fg' / 'job' / 'a1'
    attempt.mkdir(parents=True)
    row = {'metadata': {'job_id': 'job', 'attempt': 1, 'name': '隔离合成', 'session_id': 'test'},
           'started_at': '2026-11-05T12:00:00', 'status': 'running', 'stages': [], 'context': {}}
    (attempt / 'performance-summary.json').write_text(json.dumps(row), encoding='utf8')
    (attempt / 'compose.log').write_text('frame=123', encoding='utf8')
    for name in ('source.mp4', 'business.db', 'plan.json'):
        (attempt / name).write_bytes(b'must not export')
    return attempt


def test_export_real_files_fixed_location_and_no_state_change(tmp_path):
    data = tmp_path / 'data'
    attempt = seed(data)
    before = {p: p.read_bytes() for p in data.rglob('*') if p.is_file()}
    with patch.object(exporter.os, 'startfile', create=True) as opener:
        result = exporter.export_diagnostics(tmp_path / 'workspace', data)
    assert result['attempts'] == 1 and result['files'] == 5 and result['opened']
    folder = Path(result['directory'])
    assert folder.parent == tmp_path / 'workspace' / '诊断输出'
    opener.assert_called_once_with(str(folder))
    text = Path(result['report_path']).read_text(encoding='utf8')
    assert '隔离合成' in text and 'running' in text and '未结束记录不代表失败' in text
    with zipfile.ZipFile(result['bundle_path']) as archive:
        assert set(archive.namelist()) == {'job/a1/performance-summary.json', 'job/a1/compose.log', 'bundle-manifest.json',
                                             'diagnostics/composition-history.jsonl', 'diagnostics/scheduler-events.jsonl', 'diagnostics/export-selection.json'}
        assert json.loads(archive.read('bundle-manifest.json'))['read_errors'] == []
    assert before == {p: p.read_bytes() for p in data.rglob('*') if p.is_file()}


def test_empty_log_export_explicit_and_unique_folders(tmp_path):
    with patch.object(exporter.os, 'startfile', create=True):
        first = exporter.export_diagnostics(tmp_path / 'workspace', tmp_path / 'data')
        second = exporter.export_diagnostics(tmp_path / 'workspace', tmp_path / 'data')
    assert first['directory'] != second['directory']
    assert first['attempts'] == 0 and first['files'] == 3
    assert '尚未发现' in first['warnings'][0]
    assert not (tmp_path / 'data').exists()
    assert '尚未发现新版诊断记录' in Path(first['report_path']).read_text(encoding='utf8')
    assert zipfile.is_zipfile(first['bundle_path'])


def test_folder_open_failure_keeps_success_and_manual_path(tmp_path):
    with patch.object(exporter.os, 'startfile', create=True, side_effect=OSError('denied')):
        result = exporter.export_diagnostics(tmp_path / 'workspace', tmp_path / 'data')
    assert not result['opened'] and Path(result['report_path']).is_file()
    assert any('手动打开' in w for w in result['warnings'])


def test_corrupt_record_warning_preserves_original_evidence(tmp_path):
    attempt = seed(tmp_path / 'data')
    (attempt / 'performance-summary.json').write_text('{broken', encoding='utf8')
    with patch.object(exporter.os, 'startfile', create=True):
        result = exporter.export_diagnostics(tmp_path / 'workspace', tmp_path / 'data')
    assert any('未能完整读取' in w for w in result['warnings'])
    assert '无法读取的记录' in Path(result['report_path']).read_text(encoding='utf8')
    with zipfile.ZipFile(result['bundle_path']) as archive:
        assert archive.read('job/a1/performance-summary.json') == b'{broken'


def test_export_failure_is_visible_and_lock_released(tmp_path):
    with patch.object(exporter, 'export_bundle', side_effect=OSError('disk full')):
        with pytest.raises(RuntimeError, match='导出未完成.*disk full'):
            exporter.export_diagnostics(tmp_path / 'workspace', tmp_path / 'data')
    failures = list((tmp_path / 'workspace').rglob('导出失败.txt'))
    assert len(failures) == 1 and '未完成' in failures[0].read_text(encoding='utf8')
    assert exporter._export_lock.acquire(blocking=False)
    exporter._export_lock.release()


def test_concurrent_export_rejected_without_writing(tmp_path):
    with exporter._export_lock:
        with pytest.raises(ValueError, match='正在导出'):
            exporter.export_diagnostics(tmp_path / 'workspace', tmp_path / 'data')
    assert not (tmp_path / 'workspace').exists()


class Handler:
    def _json(self, status, value):
        self.status, self.value = status, value


def test_endpoint_uses_configured_paths_without_initializing_composer(tmp_path):
    workspace, data = tmp_path / 'workspace', tmp_path / 'data'
    seed(data)
    from server import v2_file_service as service
    handler = Handler()
    with patch.object(service, 'require_configured_paths', return_value=(workspace, data)), \
         patch('server.ffmpeg_finals.http.get_composer', side_effect=AssertionError('must not initialize/recover jobs')), \
         patch.object(exporter.os, 'startfile', create=True):
        assert handle(handler, 'POST', '/api/v3/final-composition/diagnostics/export', {'root': 'ignored', 'output': 'ignored'})
    assert handler.status == 200 and handler.value['attempts'] == 1
    assert Path(handler.value['directory']).parent == workspace / '诊断输出'


def test_endpoint_error_is_readable_and_does_not_start_composer():
    from server import v2_file_service as service
    handler = Handler()
    with patch.object(service, 'require_configured_paths', side_effect=RuntimeError('需要配置数据盘')), \
         patch('server.ffmpeg_finals.http.get_composer', side_effect=AssertionError('unexpected recovery')):
        assert handle(handler, 'POST', '/api/v3/final-composition/diagnostics/export', {})
    assert handler.status == 400 and handler.value['error'] == '需要配置数据盘'


def test_unreadable_log_is_reported_in_report_manifest_and_ui(tmp_path):
    attempt = seed(tmp_path / 'data')
    blocked = attempt / 'compose.log'
    real_open = Path.open

    def open_except_blocked(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError('log temporarily locked')
        return real_open(path, *args, **kwargs)

    with patch.object(Path, 'open', open_except_blocked), patch.object(exporter.os, 'startfile', create=True):
        result = exporter.export_diagnostics(tmp_path / 'workspace', tmp_path / 'data')
    assert result['attempts'] == 1 and result['files'] == 4
    assert any('未能完整读取' in w for w in result['warnings'])
    assert 'log temporarily locked' in Path(result['report_path']).read_text(encoding='utf8')
    with zipfile.ZipFile(result['bundle_path']) as archive:
        manifest = json.loads(archive.read('bundle-manifest.json'))
        assert len(manifest['read_errors']) == 1
        assert 'log temporarily locked' in manifest['read_errors'][0]['error']
    assert blocked.read_bytes() == b'frame=123'
