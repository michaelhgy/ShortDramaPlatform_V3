"""Read FFmpeg frame progress without blocking forever on a stalled child."""
from __future__ import annotations

import queue
import logging
import subprocess
import threading
import time


def run_progress(command, log, on_progress, *, stall_seconds=120, popen_options=None, observer=None):
    """Return (exit code, last frame); stop only this child on failure/cancellation.

    FFmpeg must write -progress pipe:1. Heartbeats with an unchanged frame do
    not count as work. The timeout also covers a stall before the first frame.
    """
    if observer is None:
        from server.ffmpeg_diagnostics import current
        attempt = current()
        observer = attempt.process_update if attempt else None
    started = time.monotonic()
    stats = {}
    frame = high_water = 0
    last_advance = started
    last_notify = started
    def notify(kind, **extra):
        if observer:
            moment = time.monotonic()
            record = {'event': kind, 'pid': process.pid, 'frame': frame,
                      'elapsed_seconds': round(moment - started, 3),
                      'no_frame_advance_seconds': round(moment - last_advance, 3),
                      'monotonic_at': moment, **stats, **extra}
            try: observer(record)
            except Exception:
                logging.getLogger(__name__).exception('FFmpeg diagnostic observer failed')
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log,
                               **(popen_options or {}))
    notify('process_started', executable=str(command[0]))
    messages = queue.Queue()

    def read():
        try:
            for line in iter(process.stdout.readline, b''):
                messages.put(line)
        finally:
            messages.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    eof = False
    try:
        while True:
            try:
                raw = messages.get(timeout=min(.25, stall_seconds))
                if raw is None:
                    eof = True
                else:
                    key, _, value = raw.decode('ascii', 'replace').strip().partition('=')
                    if key == 'frame':
                        try:
                            frame = int(value)
                        except ValueError:
                            continue
                        if frame > high_water:
                            high_water = frame
                            last_advance = time.monotonic()
                    elif key in ('fps', 'speed', 'out_time_us', 'total_size', 'dup_frames', 'drop_frames'):
                        stats[key] = value
                    elif key == 'progress':
                        notify('process_progress', progress=value)
                        last_notify = time.monotonic()
                        on_progress(frame, value == 'end')
            except queue.Empty:
                pass
            if time.monotonic() - last_notify >= 1:
                notify('process_progress')
                last_notify = time.monotonic()
            if eof and process.poll() is not None:
                return process.returncode, frame
            if time.monotonic() - last_advance >= stall_seconds:
                raise RuntimeError(f'FFmpeg连续{stall_seconds:g}秒没有新增输出帧（停在第{high_water}帧），已停止本次处理；日志和中间文件已保留')
    except BaseException as error:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        notify('process_error', error=str(error), returncode=process.poll())
        raise
    finally:
        reader.join(timeout=5)
        process.stdout.close()
        notify('process_finished', returncode=process.poll())
