import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from tools import v3_update_core as core

spec=importlib.util.spec_from_file_location('v3_update_builder',Path(__file__).resolve().parents[2]/'packaging/build_v3_update.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class Interrupted(BaseException):pass


class V3UpdateTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.base=self.root/'base';self.target=self.root/'target';self.install=self.root/'installed'
        common={core.MAIN:b'old executable','_internal/unchanged.dll':b'fixed runtime','_internal/tools/library.mkv':b'fixed video',
                '_internal/dist/index.html':b'old index','_internal/dist/assets/old.js':b'old script','使用手册/index.html':b'old manual'}
        for root,version in ((self.base,'2026.10.25.1'),(self.target,'2026.10.25.2')):
            for name,body in common.items():self.put(root/name,body)
            self.put(root/'build-metadata.json',json.dumps({'product':core.PRODUCT,'version':version}).encode())
        self.put(self.target/core.MAIN,b'new executable')
        self.put(self.target/'_internal/dist/index.html',b'new index')
        (self.target/'_internal/dist/assets/old.js').unlink()
        self.put(self.target/'_internal/dist/assets/new.js',b'new script')
        self.put(self.target/'使用手册/index.html',b'new manual')
        shutil.copytree(self.base,self.install)
        self.put(self.install/'用户数据/账号.db',b'never modify business data')
        self.bundle=self.root/'payload.zip';self.manifest=builder.make_manifest(self.base,self.target)
        builder.payload(self.manifest,self.target,self.bundle);self.hash=core.digest(self.bundle)

    def put(self,path,body):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    def apply(self,**kwargs):return core.apply(self.install,self.bundle,self.hash,**kwargs)
    def assert_base(self):core.verify(self.install,self.manifest['base_files'])
    def assert_target(self):core.verify(self.install,self.manifest['target_files'])
    def journals(self):return [core.read(p) for p in (self.install/'.v3-updates').glob('*/journal.json')]

    def test_update_adds_replaces_removes_files_and_preserves_business_and_fixed_resources(self):
        fixed=self.install/'_internal/tools/library.mkv';before=(fixed.stat().st_mtime_ns,fixed.read_bytes())
        value=self.apply();self.assertEqual('updated',value['status']);self.assert_target()
        self.assertFalse((self.install/'_internal/dist/assets/old.js').exists())
        self.assertEqual(before,(fixed.stat().st_mtime_ns,fixed.read_bytes()))
        self.assertEqual(b'never modify business data',(self.install/'用户数据/账号.db').read_bytes())
        self.assertEqual(b'old executable',(Path(value['backup'])/core.MAIN).read_bytes())
        self.assertEqual('committed',self.journals()[0]['state'])

    def test_already_current_is_checked_and_does_not_repeat_transaction(self):
        self.apply();self.assertEqual('already_current',self.apply()['status']);self.assertEqual(1,len(self.journals()))

    def test_same_version_but_changed_file_is_not_accepted(self):
        self.apply();self.put(self.install/'_internal/dist/index.html',b'corrupt')
        with self.assertRaisesRegex(core.UpdateError,'文件缺失或已变化'):self.apply()

    def test_wrong_version_and_wrong_product_are_rejected(self):
        for product,version in ((core.PRODUCT,'2026.10.20.1'),('ShortDramaPlatform V2','2026.10.25.1')):
            self.put(self.install/'build-metadata.json',json.dumps({'product':product,'version':version}).encode())
            with self.assertRaises(core.UpdateError):self.apply()
            self.assertEqual(b'old executable',(self.install/core.MAIN).read_bytes())

    def test_missing_base_and_modified_fixed_files_require_full_install(self):
        p=self.install/'_internal/tools/library.mkv';p.unlink()
        with self.assertRaisesRegex(core.UpdateError,'完整安装包'):self.apply()
        self.assertFalse((self.install/'.v3-updates').exists())

    def test_new_destination_conflict_is_preserved(self):
        p=self.install/'_internal/dist/assets/new.js';self.put(p,b'user-owned')
        with self.assertRaisesRegex(core.UpdateError,'位置已被占用'):self.apply()
        self.assertEqual(b'user-owned',p.read_bytes());self.assert_base()

    def test_tampered_bundle_is_rejected_before_backup(self):
        with self.bundle.open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(core.UpdateError,'更新包校验失败'):self.apply()
        self.assert_base();self.assertFalse((self.install/'.v3-updates').exists())

    def test_corrupt_payload_with_matching_container_hash_does_not_modify_install(self):
        with zipfile.ZipFile(self.bundle,'r') as a:contents={n:a.read(n) for n in a.namelist()}
        name='files/'+core.MAIN;contents[name]=b'x'*len(contents[name])
        self.bundle.unlink()
        with zipfile.ZipFile(self.bundle,'x') as a:
            for name,body in contents.items():a.writestr(name,body)
        self.hash=core.digest(self.bundle)
        with self.assertRaisesRegex(core.UpdateError,'更新文件校验失败'):self.apply()
        self.assert_base()

    def test_failure_after_partial_replacement_restores_old_version(self):
        def fault(stage):
            if stage.startswith('file:'):raise RuntimeError('injected write failure')
        with self.assertRaisesRegex(core.UpdateError,'原程序已恢复'):self.apply(hook=fault)
        self.assert_base();self.assertFalse((self.install/'_internal/dist/assets/new.js').exists())
        self.assertEqual('rolled_back',self.journals()[0]['state'])

    def test_crash_mid_update_is_recovered_before_next_attempt(self):
        def fault(stage):
            if stage.startswith('file:'):raise Interrupted()
        with self.assertRaises(Interrupted):self.apply(hook=fault)
        self.assertEqual('applying',self.journals()[0]['state'])
        self.assertEqual('updated',self.apply()['status']);self.assert_target()
        self.assertEqual({'rolled_back','committed'},{j['state'] for j in self.journals()})

    def test_crash_after_activation_still_has_a_valid_executable_backup(self):
        def fault(stage):
            if stage=='activated':raise Interrupted()
        with self.assertRaises(Interrupted):self.apply(hook=fault)
        self.assertEqual('updated',self.apply()['status']);self.assert_target()

    def test_unchanged_main_executable_backup_is_retained(self):
        self.put(self.target/core.MAIN,(self.base/core.MAIN).read_bytes());self.bundle.unlink()
        self.manifest=builder.make_manifest(self.base,self.target);builder.payload(self.manifest,self.target,self.bundle);self.hash=core.digest(self.bundle)
        value=self.apply();self.assertTrue((Path(value['backup'])/core.MAIN).is_file());self.assert_target()

    def test_running_program_is_not_terminated_or_modified(self):
        with patch.object(core,'running_in',return_value=[123]):
            with self.assertRaisesRegex(core.UpdateError,'仍在运行'):self.apply()
        self.assert_base();self.assertFalse((self.install/'.v3-updates').exists())

    def test_concurrent_update_is_rejected(self):
        with core.exclusive(self.install):
            with self.assertRaisesRegex(core.UpdateError,'已有更新程序'):self.apply()
        self.assert_base()

    def test_low_disk_space_is_rejected_without_replacement(self):
        with patch.object(core.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)):
            with self.assertRaisesRegex(core.UpdateError,'空间不足'):self.apply()
        self.assert_base()

    def test_unsafe_paths_and_reserved_windows_names_are_rejected(self):
        for name in ('../outside','/absolute','C:/drive','_internal/../x','_internal\\x','_internal/name:ads','用户数据/a.db','_internal/NUL.txt','_internal/folder./a'):
            with self.subTest(name=name),self.assertRaises(core.UpdateError):core.relative(name)

    def test_duplicate_case_paths_and_wrong_diff_are_rejected(self):
        m=copy.deepcopy(self.manifest);m['target_files']['_internal/DIST/index.html']=m['target_files']['_internal/dist/index.html']
        with self.assertRaises(core.UpdateError):core.validate_manifest(m)
        m=copy.deepcopy(self.manifest);m['removed']=[]
        with self.assertRaisesRegex(core.UpdateError,'差异清单'):core.validate_manifest(m)

    def test_new_runtime_or_changed_library_requires_complete_installer(self):
        self.put(self.target/'_internal/unchanged.dll',b'new runtime')
        with self.assertRaisesRegex(core.UpdateError,'完整安装包'):builder.make_manifest(self.base,self.target)

    def test_base_zip_may_change_with_frozen_python_imports(self):
        self.put(self.target/'_internal/base_library.zip',b'changed stdlib zip')
        self.assertIn('_internal/base_library.zip',builder.make_manifest(self.base,self.target)['changed'])

    def test_developer_modified_files_after_crash_are_not_overwritten(self):
        def fault(stage):
            if stage=='blocked':raise Interrupted()
        with self.assertRaises(Interrupted):self.apply(hook=fault)
        self.put(self.install/'使用手册/index.html',b'external change')
        with self.assertRaisesRegex(core.UpdateError,'不能自动覆盖'):self.apply()
        self.assertEqual(b'external change',(self.install/'使用手册/index.html').read_bytes())


if __name__=='__main__':unittest.main()
