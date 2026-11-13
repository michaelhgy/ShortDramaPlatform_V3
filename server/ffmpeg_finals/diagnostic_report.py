"""Read V3 final-composition diagnostics; emit an evidence-based Chinese report.

Usage: python tools/analyze_composition_diagnostics.py <fg folder> --output <report.md>
Only the explicitly requested report is written; inputs and business state are read-only.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import statistics
import zipfile


LABELS = {'source_hash_validation': '素材完整性校验', 'source_metadata_and_insertions_validation': '素材信息及插片检查',
          'template_cache_validation': '模板缓存检查', 'encoder_probe': '编码能力检测',
          'output_hash': '成片校验值计算', 'publish_copy': '复制到成片目录', 'publish_hash': '复制件完整性校验',
          'publish_rename': '成片落盘改名', 'commit_completion': '任务完成写入',
          'project_running_state': '同步运行状态', 'project_completed_state': '同步完成状态',
          'output_metadata_validation': '成片规格检查', 'load_business_task': '读取业务任务'}


def load_records(root, *, unreadable_sources=None):
    root = Path(root)
    if (root / 'fg').is_dir(): root = root / 'fg'
    errors = []; found = {}
    paths = [root] if root.is_file() else [root / 'performance-summary.json', *root.glob('*/a*/performance-summary.json'),
        *root.glob('composition-history.jsonl*'), *root.glob('diagnostics/composition-history.jsonl*')]
    for path in dict.fromkeys(paths):
        if not path.is_file(): continue
        try:
            if 'jsonl' in path.name:
                rows = []
                for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
                    try: rows.append(json.loads(line))
                    except ValueError as exc: errors.append(f'{path.name}:{number}: {exc}')
            else: rows = [json.loads(path.read_text(encoding='utf-8-sig'))]
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('metadata'), dict):
                    errors.append(f'{path}: invalid summary record')
                    if unreadable_sources is not None and path.name == 'performance-summary.json': unreadable_sources.append(path)
                    continue
                meta = row['metadata']
                if not meta.get('job_id'): continue
                key = meta['job_id'], meta.get('attempt'), meta.get('session_id')
                if key not in found or str(row.get('updated_at', '')) > str(found[key].get('updated_at', '')):
                    found[key] = {**row, '_file': str(path)}
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f'{path}: {exc}')
            if unreadable_sources is not None and path.name == 'performance-summary.json': unreadable_sources.append(path)
    return sorted(found.values(), key=lambda r: r.get('started_at', '')), errors


def measures(row):
    stages = row.get('stages', [])
    encoded = [s for s in stages if s['stage'].startswith('ffmpeg:compose') and s.get('status') == 'done']
    seconds = sum(s['seconds'] for s in encoded)
    frames = sum(s.get('frames', 0) for s in encoded)
    return {'encode_seconds': seconds, 'encode_fps': frames / seconds if seconds and frames else None,
            'copy_seconds': sum(s['seconds'] for s in stages if s['stage'] == 'publish_copy'),
            'decode_seconds': sum(s['seconds'] for s in stages if s['stage'] == 'ffmpeg:decode_check')}


def profile(row):
    m = row['metadata']; c = row.get('context', {}); source = c.get('source', {})
    a = c.get('acceleration', {})
    return (m.get('session_id'), m.get('template_id'), c.get('encoder'), a.get('transfer'), a.get('reason'),
            source.get('source_width'), source.get('source_height'), source.get('source_codec_name'), source.get('source_original_fps', source.get('source_fps')),
            bool(any(s.get('kind') == 'insertion' for s in m.get('insertions', []))))


def analyze(rows, errors=(), operations=(), *, detail_rows=None):
    out = ['# V3 连续合成诊断', '', f'读取到 {len(rows)} 条尝试记录。', '',
           '本报告按实际阶段耗时和相同运行条件比较；异常信号属于证据或排查方向，不自动认定为唯一根因。', '',
           '| 顺序 | 视频 / 尝试 | 状态 | 视频时长秒 | 总耗时秒 | 编码帧/秒 | 完整校验秒 | 复制秒 |',
           '|---|---|---|---:|---:|---:|---:|---:|']
    groups = defaultdict(list)
    for row in rows:
        m = row['metadata']; v = measures(row)
        title = str(m.get('name') or m['job_id']).replace('|', '/')
        fps = f"{v['encode_fps']:.1f}" if v['encode_fps'] is not None else '未取得'
        out.append(f"| {m.get('sequence', '—')} | {title} / {m.get('attempt')} | {row.get('status')} | {m.get('media_seconds', 0):.1f} | {row.get('elapsed_seconds', 0):.2f} | {fps} | {v['decode_seconds']:.2f} | {v['copy_seconds']:.2f} |")
        if row.get('status') == 'done' and v['encode_fps']:
            groups[profile(row)].append((row, v))
    out += ['', '## 连续运行趋势', '']
    compared = 0
    for group in groups.values():
        if len(group) < 6: continue
        compared += 1
        early = statistics.median(x[1]['encode_fps'] for x in group[:3])
        late = statistics.median(x[1]['encode_fps'] for x in group[-3:])
        drop = (1 - late / early) * 100
        label = '发现明显下降信号' if drop >= 20 else '未达到20%的下降提示线'
        out.append(f"- 同会话、模板、输入格式及加速方式，共 {len(group)} 条：前3条编码中位速度 {early:.1f} 帧/秒，后3条 {late:.1f} 帧/秒，变化 {-drop:+.1f}%；{label}。")
    if not compared:
        out.append('- 同条件完成记录不足6条，无法形成前后各3条的趋势对比；下表仍可定位每条的耗时。')
    out += ['', '## 每条证据与检查方向', '']
    for row in rows if detail_rows is None else detail_rows:
        m = row['metadata']; c = row.get('context', {}); v = measures(row)
        out.append(f"### {m.get('name') or m['job_id']} / 尝试 {m.get('attempt')}")
        out.append('')
        stages = [s for s in row.get('stages', []) if s['stage'] != 'render']
        for stage in sorted(stages, key=lambda s: s['seconds'], reverse=True)[:3]:
            name = stage['stage']; label = LABELS.get(name, '视频完整解码校验' if name == 'ffmpeg:decode_check' else name)
            speed = f"，{stage['bytes'] / stage['seconds'] / 1e6:.1f} MB/秒" if stage.get('bytes') and stage['seconds'] else ''
            out.append(f"- 耗时阶段：{label} {stage['seconds']:.3f} 秒{speed}，状态 {stage.get('status')}。")
        out.append(f"- 加速方式：编码 {c.get('encoder', '未取得')}；画面合成 {json.dumps(c.get('acceleration', {}), ensure_ascii=False)}。")
        out.append(f"- 领取任务耗时 {m.get('dispatch_seconds', 0):.3f} 秒；领取时等待项 {m.get('waiting_candidates', '未取得')}；自动排队耗时 {m.get('loop_timing', {}).get('automatic_tick_seconds', '未取得')} 秒。")
        if m.get('gap_since_previous_seconds') is not None:
            out.append(f"- 距离上一条任务结束 {m['gap_since_previous_seconds']:.3f} 秒（包含空闲、暂停、排队准备等，不能直接认定为调度故障）。")
        writes = c.get('progress_database_writes', {})
        if writes.get('max_seconds', 0) >= 1:
            out.append(f"- 进度数据库写入出现等待：最长 {writes['max_seconds']:.3f} 秒，累计 {writes.get('total_seconds', 0):.3f} 秒。")
        for process in row.get('processes', []):
            if process.get('error') or process.get('no_frame_advance_seconds', 0) >= 10:
                out.append(f"- FFmpeg 证据：阶段 {process.get('stage')}，停止推进 {process.get('no_frame_advance_seconds', 0):.1f} 秒，错误 {process.get('error', '未报告')}。")
        if row.get('status') == 'running':
            out.append(f"- 本条没有完成收口：最后记录阶段 {row.get('stage')}，更新时间 {row.get('updated_at')}。可能仍在运行或进程曾退出，需结合进程与事件日志确认。")
        first = row.get('resource_first') or {}; last = row.get('resource_last') or {}
        for field, label, unit in [('private_bytes', '主程序私有内存', 1024 * 1024), ('handles', '主程序句柄数', 1)]:
            a = first.get('parent', {}).get(field); b = last.get('parent', {}).get(field)
            if a is not None and b is not None:
                suffix = ' MB' if unit > 1 else ''
                out.append(f'- {label}：开始 {a / unit:.1f}{suffix}，末次 {b / unit:.1f}{suffix}（单条变化不等于泄漏）。')
        for key, entry in row.get('resource_extremes', {}).items():
            out.append(f"- 资源极值：{key} = {entry['value']}，发生在 {entry.get('at')} / {entry.get('stage')}。")
        for owner in ('gpu', 'physical_disk'):
            if last.get(owner, {}).get('status') == 'unavailable':
                out.append(f"- 指标未取得：{owner}，原因 {last[owner].get('reason', '未提供')}。")
        out.append(f"- 资源采样 {row.get('resource_sample_count', 0)} 次；逐时刻 CPU、磁盘延迟/队列、显卡温度/频率/占用及缺失原因见同目录 diagnostics.jsonl。")
        if row.get('diagnostic_errors'):
            out.append('- 诊断自身错误：' + '; '.join(row['diagnostic_errors']))
        out.append(f"- 记录来源：`{row.get('_file', '')}`。")
        out.append('')
    if operations:
        out += ['## 排队准备与页面刷新', '']
        finished = {r.get('operation_id') for r in operations if r.get('event') == 'operation_finished'}
        unfinished = [r for r in operations if r.get('event') == 'operation_started' and r.get('operation_id') not in finished]
        for r in unfinished[-10:]:
            out.append(f"- 未找到结束记录：{r.get('operation')}，开始 {r.get('at')}，任务 {r.get('task_id', '未提供')}。可能仍在处理、曾退出或旧日志已轮转，需核对时间及进程。")
        for r in sorted((r for r in operations if r.get('seconds') is not None), key=lambda r:r['seconds'], reverse=True)[:10]:
            out.append(f"- {r.get('operation') or r.get('name')}：{r['seconds']:.3f} 秒，时间 {r.get('at')}，错误 {r.get('error') or '无'}。")
        out.append('')
    if errors: out += ['## 无法读取的记录', '', *['- ' + str(e) for e in errors], '']
    if not rows: out += ['尚未发现新版诊断记录。旧日志不会补出过去未采集的资源数据；需要运行包含本次改动的版本。', '']
    return '\n'.join(out)


def load_operations(root):
    root = Path(root)
    if (root / 'fg').is_dir(): root = root / 'fg'
    if root.is_file(): root = root.parent
    if (root / 'diagnostics').is_dir(): root = root / 'diagnostics'
    rows = []; errors = []
    for pattern in ('scheduler-events.jsonl*', 'runtime-observations.jsonl*'):
        for path in root.glob(pattern):
            try:
                for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
                    try: rows.append(json.loads(line))
                    except ValueError as exc: errors.append(f'{path.name}:{number}: {exc}')
            except OSError as exc: errors.append(str(exc))
    return rows, errors


def export_bundle(root, output, *, allow_missing=False, attempt_dirs=None, summary_rows=(), operation_rows=(), selection=None, evidence_paths=()):
    root = Path(root)
    if (root / 'fg').is_dir(): root = root / 'fg'
    if not root.is_dir() and not (allow_missing and not root.exists()): raise ValueError('打包需要 fg 或 diagnostics 目录')
    output = Path(output)
    if output.exists(): raise ValueError('诊断包已存在，请使用新文件名，避免覆盖历史证据')
    allowed = {'performance-summary.json', 'check.json', 'encoder_check.json', 'hardware_check.json', 'acceleration_fallback.json'}
    paths = ([*root.glob('diagnostics/*'), *root.glob('*/a*/*')] if attempt_dirs is None
             else [p for folder in attempt_dirs for p in folder.glob('*')] + list(evidence_paths))
    if root.name == 'diagnostics': paths += list(root.glob('*'))
    if (root / 'performance-summary.json').is_file(): paths += list(root.glob('*'))
    manifest = []; errors = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in dict.fromkeys(paths):
            if path.is_symlink() or not path.is_file(): continue
            if path.name not in allowed and not (path.name.startswith(('diagnostics.jsonl', 'composition-history.jsonl', 'runtime-observations.jsonl', 'scheduler-events.jsonl', 'progress.jsonl')) or path.name.endswith(('.log', '.command.json', '.ffgraph'))): continue
            try:
                # A bounded tail retains recent incidents without copying large logs.
                size = path.stat().st_size
                with path.open('rb') as stream:
                    if size > 8 * 1024 * 1024: stream.seek(-8 * 1024 * 1024, 2)
                    content = stream.read(8 * 1024 * 1024)
                name = path.relative_to(root).as_posix()
                if size > len(content) and 'jsonl' in path.name:
                    content = content.partition(b'\n')[2]  # discard a partial first line
                archive.writestr(name, content)
                manifest.append({'path':name, 'source_bytes':size, 'included_bytes':len(content), 'tail_only':size > len(content)})
            except OSError as exc: errors.append({'path':str(path), 'error':str(exc)})
        if selection is not None:
            generated = {
                'diagnostics/composition-history.jsonl': ''.join(json.dumps({k:v for k,v in row.items() if k != '_file'}, ensure_ascii=False) + '\n' for row in summary_rows),
                'diagnostics/scheduler-events.jsonl': ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in operation_rows),
                'diagnostics/export-selection.json': json.dumps(selection, ensure_ascii=False, indent=2),
            }
            if attempt_dirs is None:
                generated = {'diagnostics/export-selection.json': generated['diagnostics/export-selection.json']}
            for name, content in generated.items():
                data = content.encode('utf8')
                archive.writestr(name, data)
                manifest.append({'path':name, 'included_bytes':len(data), 'generated':True, 'tail_only':False})
        archive.writestr('bundle-manifest.json', json.dumps({'schema':1, 'files':manifest, 'read_errors':errors, 'selection':selection},ensure_ascii=False,indent=2))
    return {'files':len(manifest), 'read_errors':errors, 'path':str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, help='可选：同时导出日志ZIP，排除视频、素材和数据库')
    args = parser.parse_args()
    if not args.root.exists(): parser.error('日志路径不存在')
    rows, errors = load_records(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    operations, operation_errors = load_operations(args.root)
    errors += operation_errors
    args.output.write_text(analyze(rows, errors, operations), encoding='utf8')
    bundle = export_bundle(args.root, args.bundle) if args.bundle else None
    print(json.dumps({'attempts': len(rows), 'read_errors': len(errors), 'report': str(args.output), 'bundle':bundle}, ensure_ascii=True))


if __name__ == '__main__': main()
