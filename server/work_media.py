"""Local work covers and current playback URLs; no video downloads or refreshes."""
from __future__ import annotations

import hashlib
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ASSET_ID = re.compile(r"[a-f0-9]{64}")


def playback_url(value):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in ('http', 'https') and parsed.hostname else ''
    except ValueError:
        return ''


def local_cover_url(asset_id):
    return '/api/v3/work-covers/' + asset_id if isinstance(asset_id, str) and ASSET_ID.fullmatch(asset_id) else ''


def legacy_cover_identity(uid, post):
    url = playback_url(post.get('coverUrl'))
    if not url:
        return ''
    parsed = urlsplit(url)
    # Signed addresses change on every query; the cover's content key does not.
    query = sorted((k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                   if k.lower() not in {'token', 'sign', 't', 'expire', 'expires', 'auth_key'})
    source = post.get('coverKey') or urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ''))
    return hashlib.sha256((str(uid) + '\0' + str(post['postId']) + '\0' + source).encode()).hexdigest()


def cover_identity(uid, post):
    # A published work's cover is fixed; transport URLs and coverKey are not versions.
    return hashlib.sha256(('work-cover\0' + str(uid) + '\0' + str(post['postId'])).encode()).hexdigest()


class WorkMediaCache:
    def __init__(self, root, downloader=None):
        self.root = Path(root)
        if downloader is None:
            from server.drama_catalog import download_image
            downloader = download_image
        self.downloader = downloader
        self._validated = {}

    def path(self, asset_id):
        if not isinstance(asset_id, str) or not ASSET_ID.fullmatch(asset_id):
            raise ValueError('作品封面编号无效')
        return self.root / (asset_id + '.png')

    def valid(self, asset_id):
        if not local_cover_url(asset_id):
            return False
        return self._valid_path(self.path(asset_id))

    def _valid_path(self, path):
        try:
            stat = path.stat()
            fingerprint = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            if not path.is_file() or not stat.st_size:
                return False
            # Decode once per unchanged local file, with no CDN validation request.
            if self._validated.get(path) == fingerprint:
                return True
            with Image.open(path) as image:
                image.load()
                if not image.width or not image.height:
                    return False
            self._validated[path] = fingerprint
            return True
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            return False

    def prepare(self, uid, posts, previous=(), *, download=True, progress=None, should_stop=None):
        old = {str(p['postId']): p for p in previous}

        def one(post):
            item = dict(post)
            prior = old.get(str(item['postId']), {})
            previous_id = prior.get('coverLocalId')
            item.pop('coverLocalId', None)
            # Most updates stop here, before parsing any remote URL or comparing keys.
            if self.valid(previous_id):
                item['coverLocalId'] = previous_id
                return item, None
            asset_id = cover_identity(uid, item)
            if self.valid(asset_id):
                item['coverLocalId'] = asset_id
                return item, None
            # Find an unlinked cache from the old URL-based scheme without moving it.
            legacy_id = legacy_cover_identity(uid, item)
            if self.valid(legacy_id):
                item['coverLocalId'] = legacy_id
                return item, None
            if not playback_url(item.get('coverUrl')):
                return item, None
            target = self.path(asset_id)
            if not download or (should_stop and should_stop()):
                return item, None
            temporary = None
            try:
                data = self.downloader(item['coverUrl'])
                self.root.mkdir(parents=True, exist_ok=True)
                temporary = self.root / (uuid.uuid4().hex + '.tmp')
                temporary.write_bytes(data)
                if not self._valid_path(temporary):
                    raise ValueError('作品封面图片无效')
                self._validated.pop(temporary, None)
                temporary.replace(target)
                item['coverLocalId'] = asset_id
                return item, None
            except Exception:
                return item, {'uid': uid, 'post_id': str(item['postId']), 'stage': 'cover',
                              'message': '作品封面下载失败，暂未取得可用的本地在线视频封面'}
            finally:
                if temporary:
                    self._validated.pop(temporary, None)
                    if temporary.exists():
                        temporary.unlink()

        # Only image CDN downloads run concurrently; official data pages keep their own gate.
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = [None] * len(posts)
            futures = {pool.submit(one, post): i for i, post in enumerate(posts)}
            for done, future in enumerate(as_completed(futures), 1):
                results[futures[future]] = future.result()
                if progress and (done == 1 or done % 10 == 0 or done == len(posts)):
                    progress(f'作品列表已完整返回，正在整理本地封面 {done} / {len(posts)}；已有封面直接复用')
        return [r for r, _ in results], [e for _, e in results if e]
