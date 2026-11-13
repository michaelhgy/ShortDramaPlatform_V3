import copy
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from server import v2_file_service as files
from server.account_import import AccountImport, PREVIEWS, RUNS, PREVIEW_TTL


class Cat:
    accounts_data = []
    def __init__(self, writable=False): assert writable is False
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def accounts(self, *, resolve_groups=False):
        assert resolve_groups is True
        return copy.deepcopy(self.accounts_data)


class Avatars:
    calls = []
    fail = False
    def sync_avatar(self, account, entry):
        self.calls.append((account['id'],entry['avatar']))
        if self.fail: raise OSError('offline')
        return True


class AccountImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.old=files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH
        files.WORKSPACE=self.root/'workspace';files.DATA_ROOT=self.root/'data';files.DATABASE_INITIALIZED_PATH=None
        self.theater=files.create_theater({'name':'剧场A'})
        self.stopped=files.create_theater({'name':'停用剧场','status':'停用'})
        self.existing=files.create_account({'nickname':'本地保留名','channel_id':'old','theater_id':self.theater['id'],'status':'观察','notes':'保留'})
        files.create_account({'nickname':'冲突昵称','channel_id':'different','theater_id':self.theater['id']})
        Cat.accounts_data=[self.remote('old','平台新名字'),self.remote('new','新账号',loginStatus='登录失效'),self.remote('conflict','冲突昵称'),self.remote('second','第二账号')]
        PREVIEWS.clear();RUNS.clear();Avatars.calls=[];Avatars.fail=False
        self.service=AccountImport(files.WORKSPACE,files.connection,Cat,Avatars())
    def tearDown(self):
        self.assertFalse(any(r['status'] in ('queued','running') for r in RUNS.values()))
        PREVIEWS.clear();RUNS.clear()
        files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH=self.old
        self.temp.cleanup()
    def remote(self, uid, name, **extra):
        return dict(uid=uid,nickname=name,platform='Channels',platformName='视频号',avatar='https://example.test/'+uid,
                    groupName='运营分组',tags=[],fansTotal=None,loginStatus='登录有效',cookie='never-export',**extra) if not extra else {
                    **self.remote(uid,name),**extra}
    def item(self,uid,name='新账号',theater=None,**extra):
        return {'uid':uid,'nickname':name,'theater_id':theater or self.theater['id'],**extra}
    def run_import(self, items, preview=None):
        preview=preview or self.service.preview();run=self.service.start(preview['token'],items)
        deadline=time.monotonic()+5
        while self.service.status(run['id'])['status'] in ('queued','running') and time.monotonic()<deadline:time.sleep(.01)
        return self.service.status(run['id'])
    def test_preview_preserves_resolved_default_and_custom_groups(self):
        Cat.accounts_data = [self.remote('new', '新账号', groupName='默认分组'),
                             self.remote('second', '第二账号', groupName='兔子')]
        preview = self.service.preview()
        self.assertEqual(['默认分组', '兔子'], [a['groupName'] for a in preview['items']])
        self.assertEqual(2, len(files.list_accounts()['items']))
        self.assertTrue(all('cookie' not in a and 'groupId' not in a for a in preview['items']))

    def wait_avatar_sync(self, preview=None):
        run = self.service.start_avatar_sync((preview or self.service.preview())['token'])
        deadline = time.monotonic() + 5
        while self.service.status(run['id'])['status'] in ('queued','running') and time.monotonic() < deadline:
            time.sleep(.01)
        return self.service.status(run['id'])

    def test_avatar_sync_existing_only_and_business_fields_unchanged(self):
        before = files.list_accounts()['items']
        preview = self.service.preview()
        run = self.wait_avatar_sync(preview)
        self.assertEqual(('avatars', 'completed', 1, 0), (run['kind'], run['status'], run['avatars'], run['created']))
        self.assertEqual(before, files.list_accounts()['items'])
        self.assertEqual([(self.existing['id'], 'https://example.test/old')], Avatars.calls)
        self.assertEqual(run['id'], self.service.start_avatar_sync(preview['token'])['id'])

    def test_avatar_sync_failure_does_not_change_accounts_and_allows_new_preview_retry(self):
        Avatars.fail = True
        before = files.list_accounts()['items']
        run = self.wait_avatar_sync()
        self.assertEqual((1, 1, 'failed'), (run['avatar_failed'], run['completed'], run['results'][0]['status']))
        self.assertEqual(before, files.list_accounts()['items'])
        Avatars.fail = False
        self.assertEqual(1, self.wait_avatar_sync()['avatars'])

    def test_avatar_sync_rechecks_current_uid_after_preview(self):
        preview = self.service.preview()
        with closing(files.connection()) as conn:
            conn.execute("UPDATE accounts SET channel_id='changed' WHERE id=?", (self.existing['id'],))
            conn.commit()
        with self.assertRaisesRegex(ValueError, '没有已存在'):
            self.service.start_avatar_sync(preview['token'])
        self.assertEqual([], Avatars.calls)

    def test_avatar_sync_expired_or_unknown_preview_does_not_write(self):
        with self.assertRaises(ValueError): self.service.start_avatar_sync('missing')
        preview = self.service.preview()
        PREVIEWS[preview['token']]['created'] = time.monotonic() - PREVIEW_TTL - 1
        with self.assertRaises(ValueError): self.service.start_avatar_sync(preview['token'])
        self.assertEqual([], Avatars.calls)

    def test_preview_is_readonly_filters_platform_and_removes_private_fields(self):
        Cat.accounts_data += [self.remote('new','重复账号'),{**self.remote('other','其他平台'),'platform':'Douyin'}]
        before=files.list_accounts();result=self.service.preview()
        self.assertEqual(before,files.list_accounts());self.assertEqual(4,result['total']);self.assertEqual(1,result['existing_count'])
        self.assertEqual(3,result['new_count']);self.assertEqual(1,result['conflict_count']);self.assertNotIn('cookie',result['items'][0])
        self.assertNotIn('cookie',PREVIEWS[result['token']]['accounts']['old'])
    def test_existing_uid_is_skipped_despite_name_change_and_no_theater(self):
        before=files.get_account(self.existing['id']);run=self.run_import([{'uid':'old','nickname':'想覆盖','theater_id':''}])
        self.assertEqual(1,run['skipped']);self.assertEqual(before,files.get_account(self.existing['id']));self.assertEqual([],Avatars.calls)
    def test_invalid_login_can_import_with_blank_optional_fields_and_normal_business_status(self):
        run=self.run_import([self.item('new')]);self.assertEqual(1,run['created']);self.assertEqual(1,run['avatars'])
        record=next(a for a in files.list_accounts()['items'] if a['channel_id']=='new')
        self.assertEqual('正常',record['status'])
        for key in ('sub_theater_name','reporting_date','registration_date','notes'):self.assertEqual('',record[key])
        self.assertEqual(self.theater['id'],record['theater_id'])
    def test_nickname_collision_isolated_and_editable(self):
        run=self.run_import([self.item('conflict','冲突昵称'),self.item('second','第二账号')])
        self.assertEqual((1,1),(run['created'],run['failed']))
        fixed=self.run_import([self.item('conflict','冲突昵称（新）')]);self.assertEqual(1,fixed['created'])
    def test_duplicate_names_in_batch_do_not_create_duplicate_records(self):
        run=self.run_import([self.item('new','同一昵称'),self.item('second','同一昵称')]);self.assertEqual((1,1),(run['created'],run['failed']))
    def test_missing_disabled_and_unknown_theaters_fail_individually(self):
        rows=[self.item('new',theater='missing'),self.item('second','第二账号',theater=self.stopped['id'])]
        run=self.run_import(rows);self.assertEqual(2,run['failed']);self.assertEqual(2,len(files.list_accounts()['items']))
    def test_inline_created_theater_is_immediately_usable(self):
        preview=self.service.preview();new=files.create_theater({'name':'窗口内新增剧场','default_commission_rate':40,'default_tax_rate':6})
        run=self.run_import([self.item('new',theater=new['id'])],preview);self.assertEqual(1,run['created'])
    def test_fresh_uid_check_skips_account_added_after_preview(self):
        preview=self.service.preview();added=files.create_account({'nickname':'其他窗口添加','channel_id':'new','theater_id':self.theater['id']})
        run=self.run_import([self.item('new')],preview);self.assertEqual(1,run['skipped']);self.assertEqual('其他窗口添加',files.get_account(added['id'])['nickname'])
    def test_unknown_uid_duplicate_uid_and_expired_preview_rejected(self):
        preview=self.service.preview()
        with self.assertRaises(ValueError):self.service.start(preview['token'],[self.item('untrusted')])
        with self.assertRaises(ValueError):self.service.start(preview['token'],[self.item('new'),self.item('new')])
        PREVIEWS[preview['token']]['created']=time.monotonic()-PREVIEW_TTL-1
        with self.assertRaises(ValueError):self.service.start(preview['token'],[self.item('new')])
    def test_repeated_submission_is_idempotent_and_avatar_url_not_client_controlled(self):
        preview=self.service.preview();run=self.run_import([self.item('new',avatar='http://untrusted.test/')],preview)
        again=self.service.start(preview['token'],[self.item('new')]);self.assertEqual(run['id'],again['id'])
        self.assertEqual(3,len(files.list_accounts()['items']));self.assertEqual('https://example.test/new',Avatars.calls[0][1])
    def test_avatar_failure_keeps_successful_account(self):
        Avatars.fail=True;run=self.run_import([self.item('new')]);self.assertEqual('completed',run['status']);self.assertEqual(1,run['avatar_failed']);self.assertEqual(1,run['created'])
    def test_commit_failure_does_not_report_unsaved_success(self):
        preview=self.service.preview()
        class FailCommit:
            def __init__(self):self.conn=files.connection()
            def execute(self,*args):return self.conn.execute(*args)
            def commit(self):raise OSError('disk full')
            def close(self):self.conn.close()
        self.service.connection=FailCommit
        run=self.run_import([self.item('new')],preview);self.assertEqual('error',run['status']);self.assertEqual([],run['results']);self.assertEqual(0,run['created']);self.assertEqual(2,len(files.list_accounts()['items']))


if __name__=='__main__':unittest.main()
