"""Real generated-media verification for V3 diagnostics; never opens business databases."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.ffmpeg_diagnostics import AttemptDiagnostics, phase, plan_metadata
from server.ffmpeg_templates.renderer import sha
from tools import verify_ffmpeg_insertions as fixture
from tools.analyze_composition_diagnostics import analyze, load_records, load_operations


def verify(root):
    real_renderer = fixture.FinalRenderer
    history = root / 'fg/diagnostics'
    summaries = []
    class LoggedRenderer:
        def __init__(self, folder, progress, cache_root=None):
            self.folder = Path(folder); self.progress = progress; self.cache_root = cache_root
        def render(self, job):
            name = self.folder.name
            folder = root / 'fg' / name / 'a1'
            metadata = plan_metadata(job, job_id=name, attempt=1, session_id='isolated-real-media',
                                     name=name, sequence=len(summaries) + 1)
            with AttemptDiagnostics(folder, history, metadata, interval=1):
                renderer = real_renderer(folder, self.progress, cache_root=self.cache_root)
                renderer._hardware = self._hardware
                self.encoder = renderer.encoder
                with phase('render'): output = renderer.render(job)
                with phase('output_hash', bytes=output.stat().st_size): digest = sha(output)
                target = root / (name + '-published.mp4')
                with phase('publish_copy', bytes=output.stat().st_size): shutil.copy2(output, target)
                with phase('publish_hash', bytes=target.stat().st_size): assert sha(target) == digest
            summary = json.loads((folder / 'performance-summary.json').read_text(encoding='utf8'))
            assert summary['status'] == 'done' and summary['resource_sample_count'] > 0
            assert any(p.get('frame', 0) > 0 and 'speed' in p for p in summary['processes'])
            assert any(s['stage'] == 'ffmpeg:decode_check' for s in summary['stages'])
            assert summary['context']['acceleration']['transfer'] == 'cpu'
            assert not summary['diagnostic_errors'], summary['diagnostic_errors']
            summaries.append(summary)
            return output
    with patch.object(fixture, 'FinalRenderer', LoggedRenderer):
        fixture.verify(root)
    rows, errors = load_records(root / 'fg'); operations, other = load_operations(root / 'fg')
    assert len(rows) == 3 and not errors and not other
    (root / '诊断分析报告.md').write_text(analyze(rows, errors, operations), encoding='utf8')
    result = {'attempts': len(rows), 'resource_samples': [s['resource_sample_count'] for s in summaries],
              'outputs': len(list(root.glob('*-published.mp4'))), 'report': str(root / '诊断分析报告.md')}
    (root / 'diagnostic-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args().output)
