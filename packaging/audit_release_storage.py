"""Read-only packaging storage audit. Never deletes, moves or follows links."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def category(parts):
    if parts[:2] == ('packaging', 'releases'):
        return 'protected_release' if len(parts) > 3 and parts[3] != 'build' else 'build_cache_candidate'
    if parts[:2] == ('packaging', 'updates'):
        return 'protected_delivery' if len(parts) > 3 and parts[3] == '交付' else 'update_work_review'
    if parts and parts[0] in ('local-test-output', 'artifacts'):
        if any(x in parts for x in ('acceptance-install', 'wrong-version-install', 'installation', 'wrong-version', 'build', '__pycache__')):
            return 'temporary_copy_candidate'
        return 'mixed_evidence_review'
    if parts[:2] in (('packaging', 'work'), ('packaging', 'output')): return 'build_cache_candidate'
    return 'review'


def audit(root=ROOT):
    root = Path(root).resolve()
    totals = defaultdict(lambda: {'bytes': 0, 'files': 0})
    groups = defaultdict(lambda: {'bytes': 0, 'files': 0})
    links, errors = [], []
    starts = ['packaging/releases', 'packaging/updates', 'packaging/work', 'packaging/output', 'local-test-output', 'artifacts']
    def walk(folder):
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if entry.is_symlink() or path.is_junction():
                        links.append(str(path)); continue
                    if entry.is_dir(follow_symlinks=False):
                        walk(path)
                    elif entry.is_file(follow_symlinks=False):
                        parts = path.relative_to(root).parts
                        size = entry.stat(follow_symlinks=False).st_size
                        kind = category(parts)
                        totals[kind]['bytes'] += size; totals[kind]['files'] += 1
                        # Disjoint immediate report groups; never add parent and child sizes together.
                        count = 4 if parts[:2] in (('packaging', 'releases'), ('packaging', 'updates')) else 2
                        key = '/'.join(parts[:count])
                        groups[key]['bytes'] += size; groups[key]['files'] += 1
        except OSError as exc:
            errors.append({'path': str(folder), 'error': str(exc)})
    for name in starts:
        path = root / name
        if path.is_symlink() or path.is_junction():
            links.append(str(path)); continue
        if path.is_dir(): walk(path)
    return {'created_at': datetime.now().astimezone().isoformat(), 'root': str(root),
            'read_only': True, 'size_basis': 'logical bytes; hard links may share physical disk space',
            'totals': dict(totals), 'groups': sorted(({'path': k, **v} for k, v in groups.items()), key=lambda x: -x['bytes']),
            'links_skipped': links, 'errors': errors,
            'policy': 'Never auto-delete released builds, deliveries, source snapshots, logs or failed evidence. Candidates require review and explicit cleanup authorization.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'report': str(args.output.resolve()), 'totals': result['totals'], 'errors': len(result['errors']), 'deleted_files': 0}, ensure_ascii=False))


if __name__ == '__main__': main()
