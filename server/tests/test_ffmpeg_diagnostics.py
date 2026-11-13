import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from server.ffmpeg_diagnostics import AttemptDiagnostics, current, phase, append_json
from server.ffmpeg_process import run_progress
from server.runtime_metrics import ResourceSampler
from tools.analyze_composition_diagnostics import analyze, load_records


class FakeSampler:
    def __init__(self, paths): self.closed = False
    def sample(self, pid=None):
        return {'parent': {'private_bytes': 100, 'handles': 10}, 'gpu': {'status': 'unavailable', 'reason': 'test device missing'}}
    def close(self): self.closed = True


def recorder(root, **kwargs):
    return AttemptDiagnostics(root / 'fg/job/a1', root / 'fg/diagnostics',
        {'job_id': 'job', 'attempt': 1, 'session_id': 'session', 'media_seconds': 2}, interval=.03,
        sampler_factory=FakeSampler, **kwargs)


def events(attempt):
    return [json.loads(line) for line in (attempt.folder / 'diagnostics.jsonl').read_text(encoding='utf8').splitlines()]


def test_stall_before_first_frame_still_has_samples_error_and_closed_thread(tmp_path):
    attempt = recorder(tmp_path)
    with pytest.raises(RuntimeError, match='第0帧'), attempt:
        with phase('ffmpeg:compose', frames=60):
            run_progress([sys.executable, '-u', '-c', 'import time;time.sleep(30)'], subprocess.DEVNULL,
                         lambda *args: None, stall_seconds=.3)
    summary = json.loads((attempt.folder / 'performance-summary.json').read_text(encoding='utf8'))
    assert summary['status'] == 'error'
    assert summary['resource_sample_count'] >= 2
    assert summary['stages'][0]['stage'] == 'ffmpeg:compose'
    assert summary['stages'][0]['status'] == 'error'
    assert any(e['event'] == 'resource_sample' for e in events(attempt))
    assert any(e['event'] == 'process_error' and e['metrics']['frame'] == 0 for e in events(attempt))
    assert '第0帧' in next(e['error'] for e in events(attempt) if e['event'] == 'attempt_error')
    assert not attempt.thread.is_alive()
    assert current() is None


def test_ffmpeg_speed_stats_exit_and_nonzero_error_retained(tmp_path):
    attempt = recorder(tmp_path)
    script = "print('frame=12\\nfps=24.0\\nspeed=0.8x\\nout_time_us=400000\\ntotal_size=1234\\ndup_frames=2\\ndrop_frames=1\\nprogress=end',flush=True)"
    with attempt:
        with phase('ffmpeg:compose', frames=12):
            code, frame = run_progress([sys.executable, '-u', '-c', script], subprocess.DEVNULL, lambda *a: None)
            assert (code, frame) == (0, 12)
    summary = json.loads((attempt.folder / 'performance-summary.json').read_text(encoding='utf8'))
    process = summary['processes'][0]
    assert process['fps'] == '24.0' and process['speed'] == '0.8x'
    assert process['out_time_us'] == '400000' and process['returncode'] == 0
    assert process['dup_frames'] == '2' and process['drop_frames'] == '1'


def test_logging_failure_cannot_fail_successful_work(tmp_path):
    attempt = recorder(tmp_path)
    with patch('server.ffmpeg_diagnostics.append_json', side_effect=OSError('disk full')):
        with attempt:
            with phase('publish_copy', bytes=100): pass
    result = json.loads((attempt.folder / 'performance-summary.json').read_text(encoding='utf8'))
    assert result['status'] == 'done'
    assert any('disk full' in e for e in result['diagnostic_errors'])
    assert not attempt.thread.is_alive()


def test_copy_failure_preserves_stage_trace_and_no_false_success(tmp_path):
    attempt = recorder(tmp_path)
    with pytest.raises(OSError, match='network write'), attempt:
        with phase('publish_copy', bytes=123): raise OSError('network write')
    summary = json.loads((attempt.folder / 'performance-summary.json').read_text(encoding='utf8'))
    assert summary['status'] == 'error'
    assert summary['stage'] == 'publish_copy'
    assert summary['stages'][0]['stage'] == 'publish_copy'
    assert summary['stages'][0]['bytes'] == 123
    assert summary['stages'][0]['error'] == 'network write'
    assert any('network write' in r.get('traceback', '') for r in events(attempt))


def test_sampler_failure_is_explicit_and_work_continues(tmp_path):
    class BrokenSampler(FakeSampler):
        def sample(self, pid=None): raise OSError('GPU counter missing')
    attempt = recorder(tmp_path); attempt.sampler_factory = BrokenSampler
    with attempt: time.sleep(.06)
    summary = json.loads((attempt.folder / 'performance-summary.json').read_text(encoding='utf8'))
    assert summary['status'] == 'done'
    assert summary['resource_sample_count'] == 0
    assert any('GPU counter missing' in e for e in summary['diagnostic_errors'])
    assert any(e['event'] == 'resource_sampler_error' for e in events(attempt))


def test_rotation_only_keeps_bounded_diagnostic_backups(tmp_path):
    log = tmp_path / 'history.jsonl'
    for number in range(20): append_json(log, {'number': number, 'text': 'a' * 100}, limit=120)
    assert {p.name for p in tmp_path.iterdir()} == {'history.jsonl', 'history.jsonl.1', 'history.jsonl.2', 'history.jsonl.3'}
    assert json.loads(log.read_text())['number'] == 19


def row(number, fps=100, session='same', template='same'):
    return {'schema': 1, 'started_at': f'2026-11-04T01:00:{number:02d}+08:00', 'updated_at': str(number), 'status': 'done',
            'metadata': {'job_id': str(number), 'attempt': 1, 'session_id': session, 'template_id': template, 'media_seconds': 10, 'sequence': number},
            'context': {'encoder': 'h264_nvenc', 'acceleration': {'transfer': 'vulkan'}, 'source': {'source_width': 720}},
            'stages': [{'stage': 'ffmpeg:compose', 'seconds': 300 / fps, 'frames': 300, 'status': 'done'}]}


def test_trend_compares_normalized_work_and_never_mixes_templates_or_sessions():
    rows = [row(i, 100 if i < 3 else 50) for i in range(6)]
    report = analyze(rows)
    assert '发现明显下降信号' in report and '-50.0%' in report
    rows = [row(i, 100 if i < 3 else 50, template=str(i % 2)) for i in range(6)]
    assert '不足6条' in analyze(rows)
    rows = [row(i, session=str(i % 2)) for i in range(6)]
    assert '不足6条' in analyze(rows)


def test_missing_or_corrupt_records_are_visible_and_history_deduplicates(tmp_path):
    folder = tmp_path / 'job/a1'; folder.mkdir(parents=True)
    (folder / 'performance-summary.json').write_text(json.dumps(row(1)), encoding='utf8')
    history = tmp_path / 'diagnostics/composition-history.jsonl'; history.parent.mkdir()
    history.write_text(json.dumps(row(1)) + '\npartial-write', encoding='utf8')
    rows, errors = load_records(tmp_path)
    assert len(rows) == 1 and len(errors) == 1
    assert '无法读取' in analyze(rows, errors)
    assert '尚未发现新版诊断记录' in analyze([])


def test_windows_counters_return_real_metrics_and_release_pdh():
    if sys.platform != 'win32': pytest.skip('Windows counters')
    sampler = ResourceSampler([]); sampler.nvidia = None
    try:
        result = sampler.sample()
        assert result['parent']['status'] == 'ok'
        assert result['parent']['rss_bytes'] > 0 and result['parent']['handles'] > 0
        assert result['gpu']['status'] == 'unavailable'
        assert result['physical_disk']['status'] in ('warming_up', 'unavailable')
    finally: sampler.close()
    assert sampler.disk_query is None


@pytest.fixture
def composer_env():
    from server.tests.test_ffmpeg_finals import FinalTests
    env = FinalTests(); env.setUp()
    try: yield env
    finally: env.tearDown()


def test_composer_success_records_actual_publish_phases(composer_env):
    env = composer_env
    with patch('server.ffmpeg_diagnostics.ResourceSampler', FakeSampler):
        env.composer.create(env.task['id']); env.composer.run_next()
    paths = list(env.composer.root.glob('*/a1/performance-summary.json'))
    assert len(paths) == 1
    summary = json.loads(paths[0].read_text(encoding='utf8'))
    names = {r['stage'] for r in summary['stages']}
    assert {'render', 'output_hash', 'publish_copy', 'publish_hash', 'commit_completion'} <= names
    assert summary['metadata']['waiting_candidates'] == 2
    assert summary['metadata']['dispatch_seconds'] >= 0
    assert summary['status'] == 'done'
    assert (env.composer.root / 'diagnostics/composition-history.jsonl').is_file()


def test_composer_failure_keeps_error_evidence_and_failure_state(composer_env):
    env = composer_env
    def fail(*args): raise RuntimeError('deliberate render failure')
    env.composer.render = fail
    env.composer.create(env.task['id']); env.composer.run_next()
    job = next(j for j in env.composer.snapshot()['jobs'] if j['status'] == 'error')
    assert 'deliberate render failure' in job['error']
    summary = json.loads(next(env.composer.root.glob('*/a1/performance-summary.json')).read_text(encoding='utf8'))
    assert summary['status'] == 'error'
    assert next(s for s in summary['stages'] if s['stage'] == 'render')['status'] == 'error'

def test_bundle_excludes_media_database_and_rejects_overwriting(tmp_path):
    import zipfile
    from tools.analyze_composition_diagnostics import export_bundle
    root = tmp_path / 'fg'; attempt = root / 'job/a1'; attempt.mkdir(parents=True)
    for name in ['performance-summary.json', 'diagnostics.jsonl', 'compose.log', 'compose.command.json', 'final.mp4', 'state.db', 'plan.json']:
        (attempt / name).write_text('{}', encoding='utf8')
    archive = tmp_path / 'logs.zip'
    result = export_bundle(root, archive)
    assert result['files'] == 4
    with zipfile.ZipFile(archive) as value:
        assert 'job/a1/diagnostics.jsonl' in value.namelist()
        assert not any(name.endswith(('.mp4', '.db')) for name in value.namelist())
        assert 'bundle-manifest.json' in value.namelist()
    with pytest.raises(ValueError, match='已存在'): export_bundle(root, archive)


def test_slow_and_unfinished_preparation_is_reported():
    report = analyze([], operations=[
        {'event':'operation_started','operation':'source_hash','operation_id':'unfinished','at':'now'},
        {'event':'snapshot_read','name':'production_summary','seconds':8,'at':'now'}])
    assert '未找到结束记录' in report and 'production_summary：8.000' in report


def test_snapshot_logging_failure_preserves_real_result(tmp_path):
    from server.ffmpeg_diagnostics import observe_snapshot
    from server import v2_file_service as service
    with patch.object(service,'DATA_ROOT',tmp_path), patch('server.ffmpeg_diagnostics.append_json',side_effect=OSError('write denied')):
        @observe_snapshot('test_unique_snapshot')
        def snapshot(): return {'ok':True}
        assert snapshot() == {'ok':True}
