"""Local build acceleration only. Installed update verification never uses it."""
import hashlib
import json
import os
from pathlib import Path


class HashCache:
    def __init__(self, path):
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text(encoding='utf8'))
            self.entries = data['entries'] if isinstance(data, dict) and data.get('schema') == 1 and isinstance(data.get('entries'), dict) else {}
        except (OSError, ValueError, KeyError):
            self.entries = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def stamp(path):
        st = path.stat()
        return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

    def digest(self, path):
        path = Path(path).resolve()
        before = self.stamp(path)
        key = str(path)
        entry = self.entries.get(key, {})
        if (isinstance(entry, dict) and entry.get('stamp') == before
                and isinstance(entry.get('sha256'), str) and len(entry['sha256']) == 64
                and all(c in '0123456789abcdef' for c in entry['sha256'])):
            self.hits += 1
            return entry['sha256']
        with path.open('rb') as stream:
            value = hashlib.file_digest(stream, 'sha256').hexdigest()
        if before != self.stamp(path):
            raise ValueError('File changed during hashing: ' + str(path))
        self.entries[key] = {'stamp': before, 'sha256': value}
        self.misses += 1
        return value

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_name(self.path.name + f'.{os.getpid()}.tmp')
        pending.write_text(json.dumps({'schema': 1, 'entries': self.entries}, ensure_ascii=False), encoding='utf8')
        os.replace(pending, self.path)
