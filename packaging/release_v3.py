"""Fixed V3 light-release entry. Explicit base, bounded logs, resumable stages.

No registry lookup, automatic base selection, cleanup or business-service launch.
Use an approved source checkout/snapshot; this tool does not guess release scope.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.v3_update_core import version


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inputs(root):
    result = {}
    for folder in ('src', 'server', 'packaging', 'public', 'tools'):
        for base, dirs, files in os.walk(root / folder, followlinks=False):
            dirs[:] = [d for d in dirs if d not in ('node_modules', '__pycache__', 'releases', 'updates', 'work', 'output', 'experiments', '.git')
                       and not (Path(base) / d).is_symlink() and not (Path(base) / d).is_junction()]
            for name in files:
                p = Path(base) / name
                if p.suffix in ('.py', '.ts', '.tsx', '.js', '.cjs', '.json', '.spec', '.iss', '.html', '.css'):
                    if p.name == 'version.iss' or p.relative_to(root).as_posix() == 'public/cover-editor.html':
                        continue  # Explicit deterministic builder outputs, not handwritten inputs.
                    result[p.relative_to(root).as_posix()] = digest(p)
    for name in ('package.json', 'package-lock.json', 'tsconfig.json', 'tsconfig.release.json', 'vite.config.ts'):
        result[name] = digest(root / name)
    for p in sorted((root / 'docs').rglob('*.md')) + sorted(root.glob('requirements*.txt')) + [root / 'index.html']:
        if p.is_file(): result[p.relative_to(root).as_posix()] = digest(p)
    return result


def artifact_hashes(paths):
    result = {}
    for path in map(Path, paths):
        if path.is_dir():
            files = sorted(p for p in path.rglob('*') if p.is_file())
            if not files: raise RuntimeError('阶段输出目录为空：' + str(path))
            for p in files: result[str(p.resolve())] = digest(p)
        else:
            result[str(path.resolve())] = digest(path)
    return result


class Stages:
    def __init__(self, work, signature, resume=False):
        self.work = Path(work)
        self.path = self.work / 'state.json'
        if self.path.exists():
            if not resume:
                raise ValueError('发布工作目录已存在；检查日志后用 --resume，不覆盖历史记录')
            self.state = json.loads(self.path.read_text(encoding='utf8'))
            if self.state['input_signature'] != signature:
                raise ValueError('源码或发布参数已变化，不能复用旧检查结果；请用新的工作目录')
        else:
            self.work.mkdir(parents=True, exist_ok=True)
            self.state = {'input_signature': signature, 'stages': {}}
        self.save()

    def save(self):
        pending = self.path.with_suffix('.pending')
        pending.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding='utf8')
        os.replace(pending, self.path)

    def run(self, name, command, cwd, artifacts=()):
        if self.state['stages'].get(name, {}).get('status') == 'PASS':
            completed = self.state['stages'][name]
            if artifact_hashes(completed.get('artifact_roots', [])) != completed.get('artifacts', {}):
                raise RuntimeError('已完成阶段输出丢失或变化：'+name+'；保留证据，禁止盲目跳过')
            print('复用已完成阶段：' + name, flush=True)
            return
        started = time.monotonic()
        # Keep failed logs too. Never overwrite a previous attempt.
        attempt = 1
        while (self.work / f'{name}-{attempt}.log').exists(): attempt += 1
        log = self.work / f'{name}-{attempt}.log'
        env = dict(os.environ, PYTHONUTF8='1')
        env.pop('PYTHONPATH', None)
        with log.open('w', encoding='utf8') as stream:
            result = subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        self.state['stages'][name] = {**self.state['stages'].get(name, {}), 'status': 'PASS' if result.returncode == 0 else 'FAIL',
                                    'seconds': round(time.monotonic()-started, 2), 'log': str(log.resolve())}
        if result.returncode==0:
            try:
                self.state['stages'][name]['artifacts'] = artifact_hashes(artifacts)
                self.state['stages'][name]['artifact_roots'] = [str(Path(p).resolve()) for p in artifacts]
            except Exception:
                self.state['stages'][name]['status'] = 'FAIL'; self.save(); raise
        self.save()
        if result.returncode:
            raise RuntimeError('阶段失败：' + name + '；仅查看该日志：' + str(log))
        print('完成：' + name, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-version', required=True, action='append', help='Only explicitly requested baselines; repeat only when needed')
    p.add_argument('--version', required=True)
    p.add_argument('--source-root', type=Path, default=ROOT)
    p.add_argument('--work-dir', type=Path)
    p.add_argument('--existing-target', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--clean-program-cache', action='store_true', help='Fresh PyInstaller analysis when dependencies, Python, spec or cache trust changes')
    p.add_argument('--plan-only', action='store_true')
    p.add_argument('--test', action='append', default=[], help='Feature-specific backend test file; update/version tests are always included')
    p.add_argument('--feature-receipt', type=Path, help='PASS receipt with nonempty input_hashes, exact current-source match; reuses only feature tests')
    p.add_argument('--scope-confirmed', action='store_true', help='Caller confirms this source contains exactly the approved release scope')
    args = p.parse_args()
    source = args.source_root.resolve()
    target = ROOT / 'packaging/releases' / args.version / 'ShortDramaPlatformV3'
    version(args.version)
    bases = list(dict.fromkeys(args.base_version))
    for base in bases:
        if version(base) >= version(args.version): p.error('基础版本必须早于目标版本')
        meta = ROOT / 'packaging/releases' / base / 'ShortDramaPlatformV3/build-metadata.json'
        if not meta.is_file() or json.loads(meta.read_text(encoding='utf8')).get('version') != base:
            p.error('缺少匹配的已发布基础构建：' + base)
    if source != ROOT and not source.is_relative_to(ROOT):
        p.error('发布源码必须在V3项目内，不能指向V2或未知外部目录')
    identity = json.loads((source / 'packaging/version.json').read_text(encoding='utf8'))
    if identity['release_id'] != args.version: p.error('目标版本必须与已确认源码的统一版本配置一致')
    plan = {'base_versions': bases, 'target': args.version, 'product_version': identity['product_version'],
            'source': str(source), 'existing_target': args.existing_target, 'clean_program_cache': args.clean_program_cache,
            'stages': ['src类型', '更新/版本检查', '按需功能检查', '前端一次构建', '主程序一次构建', '显式基线升级包', '实际EXE隔离升级及一次运行检查'],
            'no_default_media_regression': True, 'no_registry_base_detection': True, 'no_cleanup': True}
    if args.plan_only:
        print(json.dumps(plan, ensure_ascii=False, indent=2)); return
    if not args.scope_confirmed: p.error('先确认发布源码范围，再传 --scope-confirmed；脏工作区请使用固定源码快照')
    if sys.version_info[:3] != (3, 12, 10): p.error('使用Windows CPython3.12.10')
    if target.exists() and not (args.existing_target or args.resume): p.error('目标构建已存在；需明确 --existing-target，不覆盖')
    hashes = inputs(source)
    tests = list(dict.fromkeys(['server/tests/test_v3_updates.py', 'server/tests/test_product_version.py'] + args.test))
    if args.feature_receipt:
        receipt = json.loads(args.feature_receipt.read_text(encoding='utf8'))
        proof = receipt.get('input_hashes')
        if receipt.get('status') != 'PASS' or not isinstance(proof, dict) or not proof:
            p.error('功能验证凭据必须为PASS并有非空input_hashes，不接受只凭旧测试数字')
        if proof != hashes: p.error('功能验证必须覆盖本次完整源码输入且指纹一致，不能复用局部或已变化的记录')
        if not receipt.get('scope') or not receipt.get('checks'): p.error('功能凭据必须说明scope及checks')
    elif not args.test and not args.existing_target:
        p.error('请提供本功能定向 --test 或匹配当前代码的 --feature-receipt；不默认全量重测')
    signature_data = {'plan': plan, 'hashes': hashes, 'tests': tests,
                      'feature_receipt': digest(args.feature_receipt) if args.feature_receipt else None,
                      'runner_hashes': {n: digest(ROOT/'packaging'/n) for n in ('release_v3.py', 'verify_v3_release.py', 'build_v3_update.py', 'release_hash_cache.py')},
                      'python': sys.version, 'python_executable': sys.executable,
                      'installed_python_dependencies': sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions())}
    signature = hashlib.sha256(json.dumps(signature_data, sort_keys=True).encode()).hexdigest()
    work = args.work_dir or ROOT / 'packaging/work/releases' / args.version
    work=Path(work).resolve()
    if not (work.is_relative_to(ROOT/'packaging/work') or work.is_relative_to(ROOT/'local-test-output')):
        p.error('发布工作目录只能在V3的packaging/work或local-test-output下')
    lock = ROOT/'packaging/work/release-active.lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    try:
        handle = lock.open('x')
    except FileExistsError:
        p.error('该发布正在运行或中断锁尚未核对；禁止并发发布')
    try:
        handle.write(str(os.getpid())); handle.close()
        stages = Stages(work, signature, args.resume)
        (Path(work) / 'inputs.json').write_text(json.dumps(signature_data, ensure_ascii=False, indent=2), encoding='utf8')
        node = shutil.which('node'); npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not node or not npm: raise RuntimeError('缺少现有Node/npm运行环境')
        stages.run('types', [node, source/'node_modules/typescript/bin/tsc', '--noEmit', '-p', source/'tsconfig.release.json'], source)
        stages.run('backend', [sys.executable, '-m', 'pytest', '-q', *tests], source)
        if not args.existing_target:
            stages.run('frontend-tests', [npm, 'test'], source)
            stages.run('frontend-build', [npm, 'run', 'build'], source, [source/'dist'])
            stages.run('program', [sys.executable, source/'packaging/build_v3.py', '--version', args.version, *([] if args.clean_program_cache else ['--incremental']), '--release-root', ROOT/'packaging/releases'], source, [target/'ShortDramaPlatformV3.exe',target/'build-metadata.json'])
        if inputs(source) != hashes: raise RuntimeError('构建期间源码漂移；停止交付，保留证据')
        if not target.is_dir(): raise RuntimeError('缺少目标程序目录')
        compiled = json.loads((target/'build-metadata.json').read_text(encoding='utf8'))
        if compiled.get('version') != args.version or compiled.get('product_version') != identity['product_version']:
            raise RuntimeError('目标程序身份不匹配')
        if compiled.get('release_input_hashes') != hashes:
            raise RuntimeError('目标完整发布输入与当前源码不一致；旧构建不能作为新流程的未知凭据')
        if not compiled.get('source_hashes'): raise RuntimeError('目标缺少编译源码清单，禁止复用未知构建')
        for name, value in compiled.get('source_hashes', {}).items():
            if digest(source/name) != value: raise RuntimeError('目标程序源码身份不匹配：' + name)
        cache = ROOT/'packaging/work/inventory-cache.json'
        first_proof = None
        for index, base in enumerate(bases):
            stages.run('update-'+base, [sys.executable, ROOT/'packaging/build_v3_update.py', '--base-version', base, '--version', args.version,
                                       '--existing-target', '--inventory-cache', cache], ROOT, [ROOT/'packaging/updates'/(base+'_to_'+args.version)/'manifest.json', ROOT/'packaging/updates'/(base+'_to_'+args.version)/'交付'])
            stage_name = 'accept-' + base
            previous = stages.state['stages'].get(stage_name, {})
            output = Path(previous['output']) if previous.get('status') == 'PASS' else Path(work)/stage_name
            attempt = 1
            if previous.get('status') != 'PASS':
                while output.exists():
                    output = Path(work)/(stage_name + '-attempt-' + str(attempt)); attempt += 1
                stages.state['stages'][stage_name] = {'status': 'PENDING', 'output': str(output)}
                stages.save()
            command = [sys.executable, ROOT/'packaging/verify_v3_release.py', '--base-version', base, '--version', args.version,
                       '--output', output]
            if first_proof: command.extend(['--runtime-proof', first_proof])
            stages.run(stage_name, command, ROOT, [output/'acceptance.json'])
            stages.state['stages'][stage_name]['output'] = str(output); stages.save()
            if first_proof is None: first_proof = output/'acceptance.json'
        if inputs(source)!=hashes: raise RuntimeError('验收期间源码漂移，停止交付')
        stages.state['status'] = 'PASS'; stages.save()
        print(json.dumps({'status':'PASS', 'version':args.version, 'bases':bases, 'report':str(stages.path.resolve())}, ensure_ascii=False))
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__': main()
