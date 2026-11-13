"""Read diagnostics without taking the composition lock or opening business DBs."""
from datetime import datetime
import os
from pathlib import Path
import threading

from .diagnostic_report import analyze, export_bundle, load_operations, load_records
from .diagnostic_selection import options, select, detail_folders, select_operations

_export_lock = threading.Lock()


def export_diagnostics(workspace: Path, data_root: Path, conditions=None):
    request = options(conditions)
    if not _export_lock.acquire(blocking=False):
        raise ValueError('正在导出合成诊断，请等待当前导出完成')
    try:
        source = Path(data_root).resolve() / 'fg'
        unreadable = []
        all_rows, errors = load_records(source, unreadable_sources=unreadable)
        rows, details, selection = select(all_rows, request)
        folders, missing = detail_folders(source, details)
        selection['missing_detail_keys'] = missing
        evidence = []
        if request['scope'] != 'all':
            selected_parents = {f"{str(r['metadata']['job_id'])[:12]}/a{r['metadata'].get('attempt')}" for r in details}
            for path in unreadable:
                if path.parent.relative_to(source).as_posix() in selected_parents or (not all_rows and request['scope'] == 'recent'):
                    evidence.append(path)
            evidence = evidence[:3]
        selection['unreadable_summary_files'] = [str(p.relative_to(source)) for p in evidence]
        folder = Path(workspace).resolve() / '诊断输出' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        folder.mkdir(parents=True, exist_ok=False)
        report = folder / '合成诊断报告.md'
        bundle = folder / '合成诊断日志.zip'
        try:
            operations, operation_errors = load_operations(source)
            if request['scope'] != 'all': operations = select_operations(operations, rows)
            errors += operation_errors
            result = export_bundle(source, bundle, allow_missing=True,
                                   attempt_dirs=None if request['scope'] == 'all' else folders,
                                   summary_rows=rows, operation_rows=operations, selection=selection, evidence_paths=evidence)
            warnings = []
            if not rows:
                warnings.append('所选范围尚未发现新版合成诊断记录；报告中已注明。')
            if missing:
                warnings.append(f'{len(missing)}条所选记录仅剩摘要，详细日志缺失或已属于其他运行批次，未混入其他任务文件。')
            if evidence:
                warnings.append(f'另附{len(evidence)}份损坏摘要原文，不收集其余未选任务的详细日志。')
            if errors or result['read_errors']:
                warnings.append(f"有 {len(errors) + len(result['read_errors'])} 项记录未能完整读取，详见报告及压缩包清单。")
            scope_text = (f"导出范围：{selection['label']}；简要统计 {len(rows)} 条，详细记录 {len(details)} 条"
                          f"（所选 {selection['primary_attempts']} 条，正常对照 {selection['baseline_attempts']} 条）。\n\n"
                          f"本范围另有 {selection['omitted_detail_attempts']} 条仅保留摘要，未附详细日志；"
                          f"所选详细记录中 {len(missing)} 条的原始详细日志不可用。全部范围条件与记录清单见ZIP内 export-selection.json。\n\n")
            preface = (scope_text + f'导出时间：{datetime.now().astimezone().isoformat(timespec="seconds")}\n\n'
                       f'日志来源：{source}\n\n'
                       '本次只读取日志；不会暂停合成。正在运行的任务仅包含读取时已产生的记录；'
                       '报告与日志包按顺序读取，运行中内容可能略有差异，未结束记录不代表失败。\n\n')
            all_errors = [*errors, *[f"{e['path']}: {e['error']}" for e in result['read_errors']]]
            report.write_text(preface + analyze(rows, all_errors, operations, detail_rows=details), encoding='utf8')
        except Exception as exc:
            # Preserve partial output, and make its incomplete status visible to operators.
            try:
                (folder / '导出失败.txt').write_text(f'本次导出未完成，请勿作为完整诊断包。\n{exc}\n', encoding='utf8')
            except OSError:
                pass  # Disk-full/permission failure must not hide the original error or output path.
            raise RuntimeError(f'导出未完成：{exc}。已生成的文件保留在：{folder}') from exc
        opened = False
        try:
            os.startfile(str(folder))
            opened = True
        except (OSError, AttributeError):
            warnings.append('未能自动打开文件夹，请按下方路径手动打开。')
        return {'directory': str(folder), 'report_path': str(report), 'bundle_path': str(bundle),
                'attempts': len(details), 'summary_attempts': len(rows), 'selection': selection,
                'files': result['files'], 'opened': opened, 'warnings': warnings}
    finally:
        _export_lock.release()
