"""Actual delivered updater acceptance in a fresh V3-owned directory only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.v3_update_core import digest, verify, registry_location, version


def accept(base, target, output, runtime_proof=None):
    version(base); version(target)
    output = Path(output).resolve()
    if not (output.is_relative_to(ROOT/'packaging/work') or output.is_relative_to(ROOT/'local-test-output')):
        raise ValueError('验收目录只能位于V3的packaging/work或local-test-output，不允许正式安装目录')
    output.mkdir(parents=True, exist_ok=False)
    install = output/'installation'
    registered = registry_location()
    if registered and install == registered[0].resolve(): raise ValueError('禁止验收正式安装目录')
    update = ROOT/'packaging/updates'/(base+'_to_'+target)
    manifest = json.loads((update/'manifest.json').read_text(encoding='utf8'))
    delivery = update/'交付'
    info = json.loads((delivery/'更新信息.json').read_text(encoding='utf8'))
    exe = delivery/info['file']
    target_exe_hash=manifest['target_files']['ShortDramaPlatformV3.exe']['sha256']
    target_inventory_hash = hashlib.sha256(json.dumps(manifest['target_files'], sort_keys=True).encode()).hexdigest()
    skip_runtime=False
    if runtime_proof:
        proof=json.loads(Path(runtime_proof).read_text(encoding='utf8'))
        if (proof.get('status')!='PASS' or proof.get('target')!=target or proof.get('target_exe_sha256')!=target_exe_hash
                or proof.get('target_inventory_sha256') != target_inventory_hash
                or proof.get('runtime', {}).get('status') != 'ok'
                or proof.get('runtime', {}).get('version', {}).get('release_id') != target):
            raise ValueError('不能复用其他目标或未通过的运行检查')
        skip_runtime=True
    if digest(exe) != info['sha256']: raise ValueError('交付EXE指纹不一致')
    report = {'status': 'RUNNING', 'base': base, 'target': target, 'updater_sha256': info['sha256'], 'target_exe_sha256':target_exe_hash,
              'target_inventory_sha256': target_inventory_hash, 'production_installation_updated': False, 'business_database_accessed': False}
    def save():
        (output/'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    def run(args, name, expected=0):
        env = dict(os.environ, PYTHONUTF8='1', V2_WORKSPACE_ROOT=str(output/'unused-business-root'))
        env.pop('PYTHONPATH', None)
        with (output/(name+'.log')).open('w', encoding='utf8') as log:
            result = subprocess.run(list(map(str, args)), cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=600, **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
        if result.returncode != expected: raise RuntimeError('验收阶段失败：'+name)
    save()
    try:
        # No hard links: unknown future program writes cannot change a released baseline.
        shutil.copytree(ROOT/'packaging/releases'/base/'ShortDramaPlatformV3', install)
        sentinel = install/'user-owned-evidence.txt'; sentinel.write_bytes(b'KEEP_UNCHANGED')
        unchanged = {n:(install/n).stat().st_mtime_ns for n in manifest['base_files'] if n not in manifest['changed']+manifest['removed']}
        run([exe, '--silent', '--install-dir', install, '--result', output/'first.json'], 'first')
        first = json.loads((output/'first.json').read_text(encoding='utf8'))
        if first['status'] != 'updated': raise ValueError('实际更新未成功')
        verify(install, manifest['target_files'])  # Full hashes, deliberately no builder cache.
        if sentinel.read_bytes()!=b'KEEP_UNCHANGED': raise ValueError('未知用户文件被修改')
        if any((install/n).stat().st_mtime_ns!=stamp for n,stamp in unchanged.items()): raise ValueError('未变化文件被重新写入')
        run([exe, '--silent', '--install-dir', install, '--result', output/'repeat.json'], 'repeat')
        if json.loads((output/'repeat.json').read_text(encoding='utf8'))['status']!='already_current': raise ValueError('重复更新保护失败')
        wrong = output/'wrong-version'; wrong.mkdir()
        shutil.copy2(install/'ShortDramaPlatformV3.exe', wrong/'ShortDramaPlatformV3.exe')
        meta = json.loads((install/'build-metadata.json').read_text(encoding='utf8'))
        meta.update(version='2000.01.01.1', release_id='2000.01.01.1')
        (wrong/'build-metadata.json').write_text(json.dumps(meta), encoding='utf8')
        original = digest(wrong/'ShortDramaPlatformV3.exe')
        run([exe, '--silent', '--install-dir', wrong, '--result', output/'wrong.json'], 'wrong', expected=1)
        if json.loads((output/'wrong.json').read_text(encoding='utf8'))['status']!='error' or digest(wrong/'ShortDramaPlatformV3.exe')!=original:
            raise ValueError('错误版本保护失败')
        if not skip_runtime:
            run([install/'ShortDramaPlatformV3.exe', '--runtime-probe', '--probe-output', output/'runtime.json'], 'runtime')
            runtime = json.loads((output/'runtime.json').read_text(encoding='utf8'))
            if runtime['status']!='ok' or runtime['version']['release_id']!=target: raise ValueError('冻结程序运行检查失败')
            report['runtime'] = runtime
        report.update(status='PASS', target_files_verified=len(manifest['target_files']),
                      unchanged_files_preserved=len(unchanged), repeated_update='already_current', wrong_version_rejected=True,
                      runtime_skipped_same_target=skip_runtime, delivery_bytes=info['bytes'])
        save()
        # Existing delivery evidence is never overwritten by a verification rerun.
    except Exception as exc:
        report.update(status='FAIL', error=str(exc)); save(); raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-version', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime-proof', type=Path, help='PASS acceptance report for the identical target executable')
    args = parser.parse_args()
    report = accept(args.base_version, args.version, args.output, args.runtime_proof)
    print(json.dumps({'status':report['status'], 'target':args.version, 'report':str(args.output/'acceptance.json')}, ensure_ascii=False))


if __name__=='__main__': main()
