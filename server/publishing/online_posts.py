"""Controlled reads of Xiao V's online works list; never start a sync task."""
from __future__ import annotations

import json
import math
import random
import threading
import time
from contextlib import closing
from datetime import date, datetime, time as day_time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_PAGE_INTERVAL_SECONDS = 2.0
PAGE_INTERVAL_SETTING = 'work_page_interval_seconds'


class PublicationRangeError(RuntimeError):
    pass


def validate_page_interval(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.1 <= value <= 60:
        raise ValueError('作品每页最大等待时间必须为0.1至60秒')
    return float(value)


def configured_page_interval(connection):
    with closing(connection()) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v2_settings'").fetchone():
            return DEFAULT_PAGE_INTERVAL_SECONDS
        row = conn.execute('SELECT value_json FROM v2_settings WHERE key=?', (PAGE_INTERVAL_SETTING,)).fetchone()
    return validate_page_interval(json.loads(row[0])) if row else DEFAULT_PAGE_INTERVAL_SECONDS


def publication_window(start, end):
    """Inclusive calendar dates in the platform's Shanghai business timezone."""
    try:
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError()
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        zone = ZoneInfo('Asia/Shanghai')
        if first.isoformat() != start or last.isoformat() != end or first > last or last > datetime.now(zone).date():
            raise ValueError()
        return (datetime.combine(first, day_time.min, zone).timestamp(),
                datetime.combine(last + timedelta(days=1), day_time.min, zone).timestamp())
    except (ValueError, TypeError, OverflowError):
        raise ValueError('作品发布时间范围无效，结束日期最晚为今天') from None


class PagePacer:
    """One process-wide gate, including requests crossing account boundaries.

    A configured 2 seconds means a fresh uniform wait in [1, 2] seconds
    after the preceding request finishes. Time already spent locally counts.
    """
    def __init__(self, *, sleeper=time.sleep, clock=time.monotonic, uniform=random.uniform):
        self.lock = threading.Lock()
        self.sleeper, self.clock, self.uniform = sleeper, clock, uniform
        self.last_finished = None

    def run(self, request, interval, *, progress=None, should_stop=None):
        from server.collection_progress import checkpoint
        interval = validate_page_interval(interval)
        with self.lock:
            checkpoint(should_stop)
            if self.last_finished is not None:
                remaining = self.uniform(interval / 2, interval) - (self.clock() - self.last_finished)
                if remaining > 0:
                    if progress: progress(f"分页间隔等待约 {remaining:.1f} 秒，避免连续请求")
                    if should_stop:
                        while remaining > 0:
                            checkpoint(should_stop)
                            step = min(remaining, .2)
                            self.sleeper(step)
                            remaining -= step
                    else:
                        self.sleeper(remaining)
            checkpoint(should_stop)
            try:
                return request()
            finally:
                self.last_finished = self.clock()


ONLINE_PAGE_PACER = PagePacer()


def read_online_posts(client, uid, *, page_interval_seconds=DEFAULT_PAGE_INTERVAL_SECONDS, pacer=None, progress=None, should_stop=None, published_start=None, published_end=None):
    from server.collection_progress import checkpoint
    interval = validate_page_interval(page_interval_seconds)
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('需要账号UID')
    if not getattr(client, 'account_data', False):
        raise ValueError('在线作品读取仅允许由数据采集任务触发')
    window = publication_window(published_start, published_end) if published_start is not None or published_end is not None else None
    gate = pacer or ONLINE_PAGE_PACER
    rows, seen, cursors = [], set(), set()
    expected, params, last_time = None, {}, None
    if window and progress:
        progress(f'按发布时间读取 {published_start} 至 {published_end} 的作品，达到范围下界后停止翻页')
    for page in range(1, 501):
        checkpoint(should_stop)
        def request():
            if progress: progress(f'正在请求第 {page} 页作品，已读取 {len(seen)} 条')
            return client._online_posts_page(uid, params)
        response = gate.run(request, interval,
                            progress=progress, should_stop=should_stop)
        if not isinstance(response, dict) or not isinstance(response.get('list'), list):
            raise RuntimeError('在线作品分页格式无效，保留原数据')
        total = response.get('total')
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise RuntimeError('在线作品总数无效，保留原数据')
        if expected is not None and expected != total:
            raise RuntimeError('在线读取期间作品总数变化，保留原数据')
        expected = total
        reached_boundary = False
        for item in response['list']:
            if not isinstance(item, dict) or item.get('uid') != uid or not item.get('postId'):
                raise RuntimeError('在线作品账号或编号无效，保留原数据')
            post_id = str(item['postId'])
            if post_id in seen:
                raise RuntimeError('在线作品分页重复，保留原数据')
            seen.add(post_id)
            if window:
                # Scheduled/unpublished items cannot establish a published history boundary.
                if item.get('publishStatus') != 'published':
                    continue
                timestamp = item.get('postUnix')
                if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp <= 0:
                    raise PublicationRangeError('作品真实发布时间缺失，无法确认日期范围，保留原数据')
                sticky = item.get('isSticky') is True or item.get('isSticky') == 1
                if not sticky:
                    if last_time is not None and timestamp > last_time:
                        raise PublicationRangeError('作品未按发布时间从新到旧返回，无法安全截断，保留原数据')
                    last_time = timestamp
                    if timestamp < window[0]:
                        reached_boundary = True
                if not window[0] <= timestamp < window[1]:
                    continue
            rows.append(item)
        if len(seen) > expected:
            raise RuntimeError('在线作品条数超过总数，保留原数据')
        if progress: progress(f'第 {page} 页已返回，累计读取 {len(seen)} / {expected} 条作品'+(f'，范围内 {len(rows)} 条' if window else ''))
        more = response.get('hasMore')
        if not isinstance(more, bool):
            raise RuntimeError('在线作品缺少分页结束标记，保留原数据')
        if not more:
            if len(seen) != expected:
                raise RuntimeError('在线作品分页不完整，保留原数据')
            if window and progress:
                progress(f'作品列表已结束，{published_start} 至 {published_end} 范围内共 {len(rows)} 条')
            return rows
        if window and reached_boundary:
            if progress:
                progress(f'第 {page} 页已到 {published_start} 之前，停止后续翻页；范围内 {len(rows)} 条')
            return rows
        cursor = response.get('nextState')
        if not response['list'] or not isinstance(cursor, dict) or not cursor:
            raise RuntimeError('在线作品分页没有继续条件，保留原数据')
        fingerprint = json.dumps(cursor, sort_keys=True, ensure_ascii=True)
        if fingerprint in cursors:
            raise RuntimeError('在线作品翻页条件未推进，保留原数据')
        cursors.add(fingerprint)
        params = cursor
    raise RuntimeError('在线作品分页超过500页，保留原数据')
