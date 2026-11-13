"""Attempt-scoped evidence for slow/stalled final composition, without database writes."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
import hashlib
from functools import wraps, lru_cache
import sys
import json
import logging
import os
from pathlib import Path
import platform
import threading
import time
import traceback
from server.runtime_metrics import ResourceSampler

_local = threading.local()
_log = logging.getLogger(__name__)
_file_lock = threading.RLock()


def _stamp():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def append_json(path, value, limit=8 * 1024 * 1024):
    """Bound both live traces and cross-attempt history; rotate diagnostic files only."""
    with _file_lock:
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size >= limit:
            for index in (2, 1):
                old = path.with_name(path.name + f'.{index}')
                if old.exists(): os.replace(old, path.with_name(path.name + f'.{index + 1}'))
            os.replace(path, path.with_name(path.name + '.1'))
        with path.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')


def current():
    return getattr(_local, 'attempt', None)


def event(kind, **values):
    attempt = current()
    if attempt: attempt.event(kind, **values)


@contextmanager
def phase(name, **details):
    attempt = current()
    if attempt:
        with attempt.phase(name, **details): yield
    else: yield


@lru_cache(maxsize=1)
def code_identity():
    if getattr(sys, 'frozen', False):
        path = Path(sys.executable)
        stat = path.stat()
        return {'kind': 'packaged', 'path': str(path), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    root = Path(__file__).parent
    paths = ['ffmpeg_process.py', 'ffmpeg_diagnostics.py', 'runtime_metrics.py',
             'ffmpeg_finals/service.py', 'ffmpeg_finals/pipeline.py', 'ffmpeg_finals/cached.py', 'ffmpeg_finals/renderer.py']
    return {'kind': 'source', 'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}}


class AttemptDiagnostics:
    def __init__(self, folder, history_root, metadata, *, interval=5, sampler_factory=None):
        self.folder = Path(folder)
        self.history = Path(history_root) / 'composition-history.jsonl'
        self.metadata = metadata
        self.interval = interval
        self.sampler_factory = sampler_factory or ResourceSampler
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.closed = False
        self.started = time.monotonic()
        self.started_at = _stamp()
        self.stage = 'initializing'
        self.stage_at = self.started
        self.stages = []
        self.resources = {}
        self.extremes = {}
        self.resource_first = None
        self.resource_last = None
        self.sample_count = 0
        self.metrics = {}
        self.errors = []
        self.status = 'running'
        self.failure_stage = None
        self.context = {}
        self.process_records = []
        self.record_index = None
        self.version = {}
        try:
            from server.product_version import get_product_version
            self.version = {**get_product_version(), 'code_identity': code_identity()}
        except Exception as exc: self.errors.append('version: ' + str(exc))

    def _io(self, operation):
        try: return operation()
        except Exception as exc:
            text = type(exc).__name__ + ': ' + str(exc)
            if text not in self.errors:
                self.errors.append(text)
                self.errors = self.errors[-20:]
                _log.warning('FFmpeg diagnostics write failed (%s): %s', self.folder, text)

    def event(self, kind, **values):
        with self.lock:
            if self.closed: return
            record = {'schema': 1, 'at': _stamp(), 'elapsed_seconds': round(time.monotonic() - self.started, 3),
                      'event': kind, 'job_id': self.metadata.get('job_id'), 'attempt': self.metadata.get('attempt'), **values}
            self._io(lambda: append_json(self.folder / 'diagnostics.jsonl', record))

    def _summary(self):
        return {'schema': 1, 'started_at': self.started_at, 'updated_at': _stamp(), 'status': self.status,
                'elapsed_seconds': round(time.monotonic() - self.started, 3), 'metadata': self.metadata,
                'version': self.version, 'python': platform.python_version(), 'platform': platform.platform(),
                'stage': self.failure_stage or ('completed' if self.status == 'done' else self.stage), 'stage_elapsed_seconds': round(time.monotonic() - self.stage_at, 3),
                'stages': self.stages, 'ffmpeg': self.metrics, 'processes': self.process_records,
                'context': self.context, 'resource_sample_count': self.sample_count,
                'resource_first': self.resource_first, 'resource_last': self.resource_last,
                'resource_peaks': self.resources, 'resource_extremes': self.extremes, 'diagnostic_errors': self.errors}

    def _write_summary(self):
        value = self._summary()
        def write():
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / 'performance-summary.json'
            pending = path.with_suffix('.json.tmp')
            pending.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
            os.replace(pending, path)
        self._io(write)
        return value

    def __enter__(self):
        self.previous = current(); _local.attempt = self
        self.event('attempt_started', metadata=self.metadata, version=self.version)
        self._write_summary()
        self.thread = threading.Thread(target=self._sample_loop, name='ffmpeg-diagnostics', daemon=True)
        try: self.thread.start()
        except Exception as exc:
            self.errors.append('sampler thread: ' + repr(exc)); self.thread = None
        return self

    def __exit__(self, kind, error, tb):
        if error:
            self.status = 'error'
            self.event('attempt_error', exception_type=kind.__name__, error=str(error),
                       traceback=''.join(traceback.format_exception(kind, error, tb))[-12000:])
        else: self.status = 'done'
        self.stop.set()
        if self.thread: self.thread.join(timeout=3)
        with self.lock:
            if self.thread and self.thread.is_alive(): self.errors.append('resource sampler did not stop within 3 seconds')
            value = self._write_summary()
            self.event('attempt_finished', status=self.status, seconds=value['elapsed_seconds'])
            self._io(lambda: append_json(self.history, value))
            self.closed = True
        _local.attempt = self.previous
        return False

    @contextmanager
    def phase(self, name, **details):
        start = time.monotonic()
        with self.lock:
            old = self.stage, self.stage_at
            self.stage, self.stage_at = name, start
            self.event('stage_started', stage=name, **details)
        error = None
        try: yield
        except BaseException as exc:
            error = str(exc)
            if self.failure_stage is None: self.failure_stage = name
            raise
        finally:
            with self.lock:
                row = {'stage': name, 'seconds': round(time.monotonic() - start, 3), 'status': 'error' if error else 'done', **details}
                if error: row['error'] = error[-2500:]
                self.stages.append(row)
                self.event('stage_finished', **row)
                self.stage, self.stage_at = old
                self._write_summary()

    def update_context(self, **values):
        with self.lock:
            self.context.update(values)
            self.event('context', **values)

    def progress_write(self, seconds):
        with self.lock:
            values = self.context.setdefault('progress_database_writes', {'count': 0, 'total_seconds': 0, 'max_seconds': 0})
            values['count'] += 1
            values['total_seconds'] = round(values['total_seconds'] + seconds, 6)
            values['max_seconds'] = round(max(values['max_seconds'], seconds), 6)
        if seconds >= 1: self.event('slow_progress_database_write', seconds=round(seconds, 3))

    def process_update(self, data):
        with self.lock:
            if data['event'] == 'process_started':
                self.process_at = time.monotonic()
                self.process_records.append({'stage': self.stage, **data})
                self.record_index = len(self.process_records) - 1
            self.metrics = dict(data)
            if self.record_index is not None:
                self.process_records[self.record_index].update(data)
            if data['event'] != 'process_progress': self.event(data['event'], stage=self.stage, metrics=data)

    def _sample_loop(self):
        sampler = None
        try:
            sampler = self.sampler_factory([self.folder, self.metadata.get('source_path'), self.metadata.get('target')])
            while True:
                with self.lock:
                    state = dict(self.metrics)
                    pid = state.get('pid') if state.get('event') not in ('process_finished', 'process_error') else None
                    stage = self.stage
                    now = time.monotonic()
                    state['sample_age_seconds'] = round(now - state.get('monotonic_at', now), 3)
                    if state.get('event') == 'process_progress':
                        state['no_frame_advance_seconds'] = round(state.get('no_frame_advance_seconds', 0) + state['sample_age_seconds'], 3)
                resource = sampler.sample(pid)
                with self.lock:
                    if self.closed: break
                    self.sample_count += 1
                    if self.resource_first is None: self.resource_first = resource
                    self.resource_last = resource
                    for owner in ('parent', 'ffmpeg'):
                        for field in ('rss_bytes', 'private_bytes', 'handles', 'cpu_percent_one_core'):
                            value = resource.get(owner, {}).get(field)
                            if isinstance(value, (int, float)):
                                key = owner + '_' + field
                                self.resources[key] = max(self.resources.get(key, 0), value)
                    measurements = [('system_cpu_percent', resource.get('system_cpu_percent'), 'max'),
                        ('available_memory_bytes', resource.get('system_memory', {}).get('physical_available'), 'min'),
                        ('disk_queue_length', resource.get('physical_disk', {}).get('queue_length'), 'max'),
                        ('disk_seconds_per_transfer', resource.get('physical_disk', {}).get('seconds_per_transfer'), 'max')]
                    for gpu in resource.get('gpu', {}).get('devices', []):
                        for source, target, mode in [('temperature.gpu','temperature_c','max'), ('memory.used','memory_used_mb','max')]:
                            try: measurements.append(('gpu_' + str(gpu.get('index')) + '_' + target, float(gpu[source]), mode))
                            except (KeyError, ValueError): pass
                        try:
                            if float(gpu['utilization.gpu']) >= 20:
                                measurements.append(('gpu_' + str(gpu['index']) + '_loaded_clock_mhz', float(gpu['clocks.current.graphics']), 'min'))
                        except (KeyError, ValueError): pass
                    for key, value, mode in measurements:
                        if not isinstance(value, (float, int)): continue
                        previous = self.extremes.get(key)
                        if previous is None or (value > previous['value'] if mode == 'max' else value < previous['value']):
                            self.extremes[key] = {'value': value, 'at': _stamp(), 'stage': stage}
                    self.event('resource_sample', stage=stage, metrics=state, resources=resource)
                    self._write_summary()
                if self.stop.wait(self.interval): break
        except Exception as exc:
            self.event('resource_sampler_error', error=repr(exc))
            with self.lock: self.errors.append('resource sampler: ' + repr(exc))
        finally:
            if sampler:
                try: sampler.close()
                except Exception: _log.exception('Resource sampler close failed')


def plan_metadata(plan, *, job_id, attempt, session_id, **extra):
    keys = ('task_id', 'material_id', 'name', 'account_name', 'drama_name', 'template_id', 'source_path', 'source_sha256', 'target', 'frames', 'source_frames', 'regeneration')
    value = {k: plan.get(k) for k in keys}
    insertions = plan.get('insertions') or {}
    value.update(job_id=job_id, attempt=attempt, session_id=session_id,
                 media_seconds=plan['frames'] / 30, insertions=[{k: s.get(k) for k in ('kind', 'slot', 'frames', 'sha256')} for s in insertions.get('segments', [])],
                 plan_sha256=hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest(), **extra)
    return value


_request_last = {}


def observe_snapshot(name):
    """Record slow reads plus one normal baseline per minute; never serialize payloads."""
    def decorate(function):
        @wraps(function)
        def observed(*args, **kwargs):
            start = time.monotonic(); error = None
            try:
                return function(*args, **kwargs)
            except BaseException as exc:
                error = repr(exc)
                raise
            finally:
                elapsed = time.monotonic() - start
                with _file_lock:
                    last = _request_last.get(name, -1e9)
                    should_write = error or elapsed >= 1 or start - last >= 60
                    if should_write: _request_last[name] = start
                if should_write:
                    try:
                        owner = sys.modules.get('server.v2_file_service')
                        root = getattr(owner, 'DATA_ROOT', None)
                        if root:
                            append_json(Path(root) / 'fg/diagnostics/runtime-observations.jsonl',
                                {'schema': 1, 'at': _stamp(), 'event': 'snapshot_read', 'name': name,
                                 'seconds': round(elapsed, 3), 'error': error, 'pid': os.getpid()})
                    except Exception:
                        _log.exception('Snapshot diagnostics write failed')
        return observed
    return decorate


@contextmanager
def operation(root, name, **identity):
    """Durable boundaries also cover batch preparation before an attempt exists."""
    start = time.monotonic()
    operation_id = f'{os.getpid()}-{threading.get_ident()}-{time.monotonic_ns()}'
    path = Path(root) / 'scheduler-events.jsonl'
    def write(kind, **values):
        try:
            append_json(path, {'schema': 1, 'at': _stamp(), 'event': kind, 'operation': name,
                'operation_id': operation_id, 'pid': os.getpid(), **identity, **values})
        except Exception: _log.exception('Scheduler diagnostics write failed')
    write('operation_started')
    error = None
    try: yield
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        write('operation_finished', seconds=round(time.monotonic() - start, 3), error=error)
