"""Low frequency, dependency-free Windows metrics for FFmpeg diagnostics.

Process I/O is logical I/O, not physical disk throughput. GPU/disk counters are
machine-wide. Missing counters are returned as errors, never as zero usage.
"""
from __future__ import annotations
import csv
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


class Memory(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('faults', w.DWORD)] + [(n, ctypes.c_size_t) for n in
        ('peak_rss', 'rss', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]


class IO(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class MemoryStatus(ctypes.Structure):
    _fields_ = [('length', w.DWORD), ('load_percent', w.DWORD)] + [(n, ctypes.c_ulonglong) for n in
        ('physical_total', 'physical_available', 'pagefile_total', 'pagefile_available', 'virtual_total', 'virtual_available', 'extended_available')]


def _ticks(value):
    return ((value.dwHighDateTime << 32) | value.dwLowDateTime) / 10_000_000


class ResourceSampler:
    def __init__(self, paths=()):
        self.paths = tuple(dict.fromkeys(str(Path(p).anchor) for p in paths if p))
        self.previous = {}
        self.gpu_at = -1e9
        self.gpu = {'status': 'not_sampled'}
        self.nvidia = shutil.which('nvidia-smi')
        self.disk_query = None
        self.disk_counters = {}
        self.disk_error = None
        if os.name == 'nt':
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
            self.kernel.OpenProcess.restype = w.HANDLE
            self.kernel.CloseHandle.argtypes = [w.HANDLE]
            self.kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
            self.kernel.GetProcessIoCounters.argtypes = [w.HANDLE, ctypes.POINTER(IO)]
            self.kernel.GetProcessHandleCount.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
            self.psapi = ctypes.WinDLL('psapi', use_last_error=True)
            self.psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(Memory), w.DWORD]

    def process(self, pid):
        if os.name != 'nt':
            return {'status': 'unavailable', 'reason': 'Windows process counters required', 'pid': pid}
        handle = self.kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            return {'status': 'unavailable', 'pid': pid, 'winerror': ctypes.get_last_error()}
        result = {'pid': pid, 'status': 'ok'}
        try:
            memory = Memory(); memory.cb = ctypes.sizeof(memory)
            io = IO(); count = w.DWORD()
            created, exited, kernel, user = (w.FILETIME() for _ in range(4))
            if self.psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
                result.update(rss_bytes=memory.rss, private_bytes=memory.private, page_faults=memory.faults)
            else: result['memory_error'] = ctypes.get_last_error()
            if self.kernel.GetProcessTimes(handle, *[ctypes.byref(x) for x in (created, exited, kernel, user)]):
                result['cpu_seconds'] = _ticks(kernel) + _ticks(user)
            else: result['cpu_error'] = ctypes.get_last_error()
            if self.kernel.GetProcessIoCounters(handle, ctypes.byref(io)):
                result.update(read_bytes=io.read_bytes, write_bytes=io.write_bytes)
            else: result['io_error'] = ctypes.get_last_error()
            if self.kernel.GetProcessHandleCount(handle, ctypes.byref(count)):
                result['handles'] = count.value
            else: result['handles_error'] = ctypes.get_last_error()
            now = time.monotonic(); previous = self.previous.get(pid)
            if previous and now > previous[0]:
                delta = now - previous[0]
                for field, label in [('cpu_seconds', 'cpu_percent_one_core'), ('read_bytes', 'read_bytes_per_second'), ('write_bytes', 'write_bytes_per_second')]:
                    if field in result and field in previous[1]:
                        result[label] = round(max(0, result[field] - previous[1][field]) / delta * (100 if field == 'cpu_seconds' else 1), 3)
            self.previous[pid] = (now, result.copy())
            # Avoid retaining a different FFmpeg PID for every completed stage.
            if len(self.previous) > 8:
                self.previous = {p: v for p, v in self.previous.items() if p in (pid, os.getpid(), 'system')}
            return result
        finally:
            self.kernel.CloseHandle(handle)

    def physical_disk(self):
        if os.name != 'nt': return {'status': 'unavailable', 'reason': 'Windows PDH required'}
        if self.disk_error: return {'status': 'unavailable', 'reason': self.disk_error}
        try:
            if self.disk_query is None:
                self.pdh = ctypes.WinDLL('pdh')
                self.pdh.PdhOpenQueryW.argtypes = [w.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(w.HANDLE)]
                self.pdh.PdhAddEnglishCounterW.argtypes = [w.HANDLE, w.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(w.HANDLE)]
                self.pdh.PdhCollectQueryData.argtypes = [w.HANDLE]
                self.pdh.PdhGetFormattedCounterValue.argtypes = [w.HANDLE, w.DWORD, ctypes.c_void_p, ctypes.c_void_p]
                self.pdh.PdhCloseQuery.argtypes = [w.HANDLE]
                query = w.HANDLE()
                code = self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(query))
                if code: raise OSError(f'PdhOpenQuery status={code:#x}')
                self.disk_query = query
                for name, counter in [('bytes_per_second', 'Disk Bytes/sec'), ('queue_length', 'Current Disk Queue Length'), ('seconds_per_transfer', 'Avg. Disk sec/Transfer')]:
                    handle = w.HANDLE()
                    code = self.pdh.PdhAddEnglishCounterW(query, '\\PhysicalDisk(_Total)\\' + counter, 0, ctypes.byref(handle))
                    if code: raise OSError(f'{counter}: status={code:#x}')
                    self.disk_counters[name] = handle
                self.pdh.PdhCollectQueryData(query)
                return {'status': 'warming_up', 'scope': 'all_local_physical_disks'}
            code = self.pdh.PdhCollectQueryData(self.disk_query)
            if code: raise OSError(f'PdhCollectQuery status={code:#x}')
            class Value(ctypes.Structure):
                _fields_ = [('status', w.DWORD), ('value', ctypes.c_double)]
            result = {'status': 'ok', 'scope': 'all_local_physical_disks'}
            for name, handle in self.disk_counters.items():
                value = Value()
                code = self.pdh.PdhGetFormattedCounterValue(handle, 0x200, None, ctypes.byref(value))
                if code or value.status not in (0, 1):
                    result[name + '_error'] = f'{code:#x}/{value.status:#x}'
                else: result[name] = round(value.value, 6)
            return result
        except Exception as exc:
            self.disk_error = str(exc)
            return {'status': 'unavailable', 'reason': str(exc)}

    def gpu_sample(self):
        now = time.monotonic()
        if now - self.gpu_at < 15:
            return {**self.gpu, 'age_seconds': round(now - self.gpu_at, 3)}
        self.gpu_at = now
        if not self.nvidia:
            self.gpu = {'status': 'unavailable', 'reason': 'nvidia-smi not found'}
            return self.gpu
        fields = ['index', 'name', 'driver_version', 'pstate', 'temperature.gpu', 'utilization.gpu', 'utilization.memory', 'memory.used', 'memory.total', 'clocks.current.graphics', 'clocks.current.memory', 'power.draw', 'clocks_event_reasons.active']
        try:
            args = [self.nvidia, '--query-gpu=' + ','.join(fields), '--format=csv,noheader,nounits']
            p = subprocess.run(args, capture_output=True, text=True, timeout=2,
                               **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            if p.returncode:
                # Older drivers may not expose the newer clock-event field.
                detail = p.stderr.strip()[-500:]
                fields = fields[:-1]
                args[1] = '--query-gpu=' + ','.join(fields)
                p = subprocess.run(args, capture_output=True, text=True, timeout=2,
                    **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
                if p.returncode: raise OSError(p.stderr.strip()[-500:])
                self.gpu = {'clock_event_counter_error': detail}
            else: self.gpu = {}
            self.gpu = {**self.gpu, 'status': 'ok', 'scope': 'whole_machine', 'devices': [dict(zip(fields, row)) for row in csv.reader(p.stdout.splitlines(), skipinitialspace=True)]}
        except Exception as exc:
            self.gpu = {'status': 'unavailable', 'reason': str(exc)[-500:]}
        return {**self.gpu, 'age_seconds': 0}

    def sample(self, child_pid=None):
        result = {'parent': self.process(os.getpid()), 'python_threads': threading.active_count()}
        if child_pid: result['ffmpeg'] = self.process(child_pid)
        if os.name == 'nt':
            memory = MemoryStatus(); memory.length = ctypes.sizeof(memory)
            if self.kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
                result['system_memory'] = {'status':'ok', **{name: getattr(memory, name) for name in ('load_percent', 'physical_total', 'physical_available')}}
            else: result['system_memory'] = {'status':'unavailable', 'winerror':ctypes.get_last_error()}
            idle, kernel, user = (w.FILETIME() for _ in range(3))
            if self.kernel.GetSystemTimes(*[ctypes.byref(x) for x in (idle, kernel, user)]):
                values = (_ticks(idle), _ticks(kernel) + _ticks(user)); old = self.previous.get('system')
                if old and values[1] > old[1]:
                    result['system_cpu_percent'] = round(100 * (1 - (values[0] - old[0]) / (values[1] - old[1])), 2)
                    result['system_cpu_status'] = 'ok'
                else: result['system_cpu_status'] = 'warming_up'
                self.previous['system'] = values
            else: result['system_cpu_status'] = 'unavailable'; result['system_cpu_error'] = ctypes.get_last_error()
        else:
            result['system_cpu_status'] = 'unavailable'
            result['system_memory'] = {'status':'unavailable', 'reason':'Windows counters required'}
        drives = []
        for anchor in self.paths:
            try:
                drive_type = self.kernel.GetDriveTypeW(str(anchor)) if os.name == 'nt' else None
                if drive_type == 4:
                    drives.append({'drive': anchor, 'drive_type': drive_type, 'capacity_status': 'network_drive_not_queried', 'reason': 'avoid blocking on a disconnected share'})
                    continue
                total, used, free = shutil.disk_usage(anchor)
                drives.append({'drive': anchor, 'total_bytes': total, 'free_bytes': free, 'drive_type': drive_type})
            except OSError as exc: drives.append({'drive': anchor, 'error': str(exc)})
        result.update(drives=drives, physical_disk=self.physical_disk(), gpu=self.gpu_sample())
        return result

    def close(self):
        if self.disk_query is not None:
            self.pdh.PdhCloseQuery(self.disk_query)
            self.disk_query = None
