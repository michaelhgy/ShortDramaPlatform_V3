"""Temporary fixtures only: no real packaging, installation, cleanup or business data."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]

def load(name):
    spec = importlib.util.spec_from_file_location('release_test_' + name, ROOT/'packaging'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

cache_module = load('release_hash_cache')
release = load('release_v3')
audit_module = load('audit_release_storage')
verifier = load('verify_v3_release')
builder = load('build_v3_update')


def test_cache_hit_change_and_persist(tmp_path):
    f = tmp_path/'file'; f.write_bytes(b'first')
    c = cache_module.HashCache(tmp_path/'cache.json')
    assert c.digest(f) == hashlib.sha256(b'first').hexdigest()
    assert c.digest(f) == c.digest(f)
    assert (c.misses, c.hits) == (1, 2)
    c.save()
    c = cache_module.HashCache(c.path)
    assert c.digest(f) == hashlib.sha256(b'first').hexdigest()
    assert c.hits == 1
    f.write_bytes(b'changed-size')
    assert c.digest(f) == hashlib.sha256(b'changed-size').hexdigest()
    assert c.misses == 1


@pytest.mark.parametrize('data', ['broken', '[]', '{"schema":1,"entries": []}'])
def test_corrupt_cache_falls_back(tmp_path, data):
    p=tmp_path/'cache'; p.write_text(data)
    c=cache_module.HashCache(p)
    f=tmp_path/'f'; f.write_bytes(b'x')
    assert c.digest(f) == hashlib.sha256(b'x').hexdigest()
    assert c.misses == 1


@pytest.mark.parametrize('entry', [[], 'bad', {'stamp': None, 'sha256': 'z'*64}])
def test_corrupt_entry_falls_back(tmp_path, entry):
    f=tmp_path/'f'; f.write_bytes(b'x')
    c=cache_module.HashCache(tmp_path/'cache')
    if isinstance(entry, dict): entry['stamp'] = c.stamp(f)
    c.entries[str(f.resolve())] = entry
    assert c.digest(f) == hashlib.sha256(b'x').hexdigest()
    assert c.misses == 1


def test_changed_during_hash_rejected(tmp_path, monkeypatch):
    f=tmp_path/'f'; f.write_bytes(b'x')
    c=cache_module.HashCache(tmp_path/'cache')
    monkeypatch.setattr(c, 'stamp', Mock(side_effect=[[1], [2]]))
    with pytest.raises(ValueError, match='changed during'): c.digest(f)


def test_cached_inventory_matches_default(tmp_path):
    (tmp_path/'ShortDramaPlatformV3.exe').write_bytes(b'one')
    c=cache_module.HashCache(tmp_path/'unused-cache')
    assert builder.inventory(tmp_path) == builder.inventory(tmp_path, c)
    assert builder.inventory(tmp_path) == builder.inventory(tmp_path, c)
    assert (c.hits, c.misses) == (1, 1)


def test_stage_resume_artifacts_and_signature(tmp_path, monkeypatch):
    run=Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(release.subprocess, 'run', run)
    artifact=tmp_path/'dist'; artifact.mkdir(); (artifact/'index.html').write_text('ok')
    stages=release.Stages(tmp_path/'work', 'signature')
    stages.run('build', ['fake'], tmp_path, [artifact])
    resumed=release.Stages(tmp_path/'work', 'signature', True)
    resumed.run('build', ['fake'], tmp_path, [artifact])
    assert run.call_count == 1
    (artifact/'extra').write_text('changed')
    with pytest.raises(RuntimeError, match='输出丢失或变化'): resumed.run('build', ['fake'], tmp_path)
    with pytest.raises(ValueError, match='源码或发布参数'): release.Stages(tmp_path/'work', 'other', True)
    with pytest.raises(ValueError, match='发布工作目录已存在'): release.Stages(tmp_path/'work', 'signature')


def test_failed_stage_retry_keeps_log(tmp_path, monkeypatch):
    monkeypatch.setattr(release.subprocess, 'run', Mock(side_effect=[SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)]))
    stages=release.Stages(tmp_path, 'same')
    with pytest.raises(RuntimeError, match='阶段失败'): stages.run('check', ['fake'], tmp_path)
    stages.run('check', ['fake'], tmp_path)
    assert (tmp_path/'check-1.log').exists() and (tmp_path/'check-2.log').exists()
    assert stages.state['stages']['check']['status'] == 'PASS'


def test_stage_missing_output_not_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(release.subprocess, 'run', Mock(return_value=SimpleNamespace(returncode=0)))
    stages=release.Stages(tmp_path, 'same')
    with pytest.raises(FileNotFoundError): stages.run('build', ['fake'], tmp_path, [tmp_path/'missing'])
    assert stages.state['stages']['build']['status'] == 'FAIL'


def test_audit_read_only_and_links(tmp_path):
    f=tmp_path/'packaging/releases/2026.01.01.1/build/work'; f.parent.mkdir(parents=True); f.write_bytes(b'cache')
    protected=tmp_path/'packaging/releases/2026.01.01.1/ShortDramaPlatformV3/app'; protected.parent.mkdir(); protected.write_bytes(b'app')
    original={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report=audit_module.audit(tmp_path)
    assert report['read_only'] and not report['errors']
    assert report['totals']['build_cache_candidate']['bytes'] == 5
    assert report['totals']['protected_release']['bytes'] == 3
    assert original == {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert audit_module.category(('local-test-output','check','installation','app')) == 'temporary_copy_candidate'
    try: (tmp_path/'packaging/work').symlink_to(protected.parent, target_is_directory=True)
    except OSError: return  # Creating Windows symlinks may require a privilege not held by pytest.
    report=audit_module.audit(tmp_path)
    assert str(tmp_path/'packaging/work') in report['links_skipped']
    assert report['totals']['protected_release']['files'] == 1


def test_plan_only_no_process_or_write(tmp_path, monkeypatch, capsys):
    base='2026.01.01.1'; target='2026.01.02.1'
    meta=tmp_path/'packaging/releases'/base/'ShortDramaPlatformV3/build-metadata.json'
    meta.parent.mkdir(parents=True); meta.write_text(json.dumps({'version':base}))
    identity=tmp_path/'packaging/version.json'; identity.write_text(json.dumps({'release_id':target,'product_version':'3.0.0'}))
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    monkeypatch.setattr(release,'ROOT',tmp_path)
    monkeypatch.setattr(sys,'argv',['release_v3.py','--base-version',base,'--version',target,'--source-root',str(tmp_path),'--plan-only'])
    spawn=Mock(side_effect=AssertionError('must not spawn'))
    monkeypatch.setattr(release.subprocess,'run',spawn)
    release.main()
    assert json.loads(capsys.readouterr().out)['no_cleanup']
    assert not spawn.called
    assert before == {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_accept_rejects_production_path(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='不允许正式安装目录'):
        verifier.accept('2026.01.01.1','2026.01.02.1',tmp_path/'production-install')
    assert not (tmp_path/'production-install').exists()


def test_runtime_proof_requires_complete_target(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    monkeypatch.setattr(verifier,'registry_location',lambda:None)
    folder=tmp_path/'packaging/updates/2026.01.01.1_to_2026.01.02.1'
    (folder/'交付').mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps({'target_files':{'ShortDramaPlatformV3.exe':{'sha256':'a'*64}}}))
    (folder/'交付/更新信息.json').write_text(json.dumps({'file':'fake.exe'}))
    proof=tmp_path/'proof.json'; proof.write_text(json.dumps({'status':'PASS','target':'2026.01.02.1','target_exe_sha256':'a'*64,'runtime':{'status':'ok'}}))
    with pytest.raises(ValueError,match='不能复用其他目标'):
        verifier.accept('2026.01.01.1','2026.01.02.1',tmp_path/'local-test-output/verify',proof)

def test_pipeline_two_bases_build_once_and_resume(tmp_path, monkeypatch):
    bases=['2026.01.01.1','2026.01.02.1']; target='2026.01.03.1'
    for base in bases:
        meta=tmp_path/'packaging/releases'/base/'ShortDramaPlatformV3/build-metadata.json'
        meta.parent.mkdir(parents=True); meta.write_text(json.dumps({'version':base}))
    (tmp_path/'packaging/version.json').write_text(json.dumps({'release_id':target,'product_version':'3.0.0'}))
    (tmp_path/'x').write_bytes(b'code')
    monkeypatch.setattr(release,'ROOT',tmp_path)
    monkeypatch.setattr(release,'inputs',lambda root:{'x':release.digest(tmp_path/'x')})
    tools=('release_v3.py','verify_v3_release.py','build_v3_update.py','release_hash_cache.py')
    for name in tools: (tmp_path/'packaging'/name).write_text('tool')
    monkeypatch.setattr(release.shutil,'which',lambda name:name)
    calls=[]
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ['run','build']:
            (tmp_path/'dist').mkdir(); (tmp_path/'dist/index.html').write_text('built')
        elif len(command)>1 and command[1].endswith('build_v3.py'):
            folder=tmp_path/'packaging/releases'/target/'ShortDramaPlatformV3'; folder.mkdir(parents=True)
            (folder/'ShortDramaPlatformV3.exe').write_bytes(b'exe')
            (folder/'build-metadata.json').write_text(json.dumps({'version':target,'product_version':'3.0.0',
                'release_input_hashes':release.inputs(tmp_path),'source_hashes':release.inputs(tmp_path)}))
        elif len(command)>1 and command[1].endswith('build_v3_update.py'):
            base=command[command.index('--base-version')+1]
            folder=tmp_path/'packaging/updates'/(base+'_to_'+target); (folder/'交付').mkdir(parents=True)
            (folder/'manifest.json').write_text('{}'); (folder/'交付/fake.exe').write_bytes(b'update')
        elif len(command)>1 and command[1].endswith('verify_v3_release.py'):
            folder=Path(command[command.index('--output')+1]); folder.mkdir(parents=True)
            (folder/'acceptance.json').write_text('{"status":"PASS"}')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(release.subprocess,'run',fake_run)
    args=['release_v3.py','--base-version',bases[0],'--base-version',bases[1],'--version',target,
          '--source-root',str(tmp_path),'--scope-confirmed','--test','server/tests/feature.py']
    monkeypatch.setattr(sys,'argv',args)
    release.main()
    assert sum(len(c)>1 and c[1].endswith('build_v3.py') for c in calls)==1
    assert sum(len(c)>1 and c[1].endswith('build_v3_update.py') for c in calls)==2
    accepts=[c for c in calls if len(c)>1 and c[1].endswith('verify_v3_release.py')]
    assert len(accepts)==2 and '--runtime-proof' not in accepts[0] and '--runtime-proof' in accepts[1]
    assert not (tmp_path/'packaging/work/release-active.lock').exists()
    previous=len(calls)
    monkeypatch.setattr(sys,'argv',args+['--resume'])
    release.main()
    assert len(calls)==previous
