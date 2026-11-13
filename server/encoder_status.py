"""Read an attempt's encoder evidence without probing hardware or changing jobs."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re


@lru_cache(maxsize=512)
def _read_check(path: Path, modified: int, size: int) -> dict | None:
    # Metadata keys invalidate the cache when the renderer finishes its write.
    with path.open(encoding='utf-8-sig') as stream:
        value = json.loads(stream.read(16_385))
    if not isinstance(value, dict):
        return None
    encoder = value.get('encoder')
    if encoder == 'h264_nvenc':
        return {'encoder': encoder, 'warning': None}
    if encoder != 'libx264':
        return None
    diagnostic = value.get('diagnostic')
    diagnostic = diagnostic.strip() if isinstance(diagnostic, str) else ''
    incompatible = 'driver does not support the required nvenc api version' in diagnostic.lower()
    minimum = re.search(r'minimum required nvidia driver.*?\bis\s+(\d+(?:\.\d+)*)', diagnostic, re.I)
    if incompatible:
        reason = 'NVIDIA 驱动不兼容当前编码组件，显卡编码检测未通过。'
        version = f'至 {minimum.group(1)} 或更新版本' if minimum else '至兼容当前编码组件的版本'
        action = f'请更新 NVIDIA 驱动{version}，完成后重启电脑，再运行新任务确认。'
    else:
        reason = ('显卡编码检测未通过，具体原因见检测详情。' if diagnostic
                  else '本次未启用显卡编码，检测记录未提供具体原因。')
        action = '请检查本机 NVIDIA 显卡及驱动是否可用，再运行新任务确认。'
    return {'encoder': encoder, 'warning': {
        'reason': reason, 'action': action, 'diagnostic': diagnostic[:3000],
    }}


def job_encoder_status(root: Path, job: dict) -> dict | None:
    """Never attribute an earlier attempt's fallback to a waiting/retried job."""
    if job.get('status') not in ('running', 'done', 'error') or not job.get('attempt'):
        return None
    path = root / job['id'][:12] / f"a{job['attempt']}" / 'encoder_check.json'
    try:
        stat = path.stat()
        if stat.st_size > 16_384:
            return None
        return _read_check(path, stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, UnicodeError):
        # Missing historical logs and an in-progress JSON write are not job errors.
        return None
