import base64
import copy
import io
import json
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from PIL import Image
from server import v2_file_service as files
from server.cover_editor import CoverStore
from server.drama_catalog import Catalogue, JOBS, all_drama_metadata, drama_metadata, snapshot, task_metadata, validate_mount, initialize


def picture(color='red'):
    stream = io.BytesIO(); Image.new('RGB', (77,103), color).save(stream, format='PNG')
    return stream.getvalue()


class Cat:
    pages = {}; calls = []; login = '登录有效'
    def __init__(self, writable=False):
        assert writable is False
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def accounts(self): return [{'uid':'uid-a','platform':'Channels','loginStatus':self.login,'avatar':''}]
    def worker(self, uid, method, params):
        assert method == 'getDramaComponent'
        self.calls.append(copy.deepcopy(params))
        source = 'channels_drama' if params.get('sceneType') == 3 else 'mini_drama'
        response = copy.deepcopy(self.pages.get((source,params['page']), {'list':[],'totalCount':0,'baseResp':{'errcode':0}}))
        if isinstance(response, Exception): raise response
        return response


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.previous = files.WORKSPACE, files.DATA_ROOT, files.DATABASE_INITIALIZED_PATH
        files.WORKSPACE=self.root/'workspace'; files.DATA_ROOT=self.root/'data'; files.DATABASE_INITIALIZED_PATH=None
        self.theater=files.create_theater({'name':'测试剧场'})
        self.account=files.create_account({'nickname':'测试账号','channel_id':'uid-a','theater_id':self.theater['id']})
        self.account2=files.create_account({'nickname':'另一个账号','channel_id':'uid-b','theater_id':self.theater['id']})
        self.catalogue=Catalogue(files.WORKSPACE,files.connection,Cat,lambda url: picture())
        JOBS.clear(); Cat.calls=[]; Cat.pages={}; Cat.login='登录有效'
    def tearDown(self):
        self.assertFalse(any(j['status'] in ('queued','running','stopping') for j in JOBS.values()))
        JOBS.clear()
        files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH=self.previous
        self.temp.cleanup()
    def item(self, id='remote-a', name='生恩如纸 养恩如山', **values):
        return {'id':id,'name':name,'mediaCount':104,'usable':True,'coverUrl':'https://example.test/image',**values}
    def ingest(self, items, source='mini_drama', mode='all', account=None):
        return self.catalogue.ingest(account or self.account,source,items,mode)
    def count(self):
        with closing(files.connection()) as c:return c.execute('SELECT COUNT(*) FROM dramas').fetchone()[0]
    def run_sync(self, sources=['mini_drama'], mode='all'):
        job=self.catalogue.start([self.account['id']],sources,mode)
        deadline=time.monotonic()+8
        while snapshot(job['id'])['status'] in ('queued','running','stopping') and time.monotonic()<deadline: time.sleep(.01)
        return snapshot(job['id'])
    def test_usable_mode_imports_only_usable_all_adds_unusable(self):
        records=[self.item(),self.item('no','不可挂载剧',usable=False,unusableReason='未版权保护')]
        stats,_=self.ingest(records,mode='usable');self.assertEqual(1,self.count());self.assertEqual(1,stats['skipped'])
        self.ingest(records);self.assertEqual(2,self.count())
        result=self.catalogue.items(self.account['id'],'mini_drama')
        self.assertEqual(2,result['total']);self.assertEqual('未版权保护',next(r for r in result['items'] if r['external_id']=='no')['reason'])
    def test_unique_history_name_associates_both_sources_no_duplicates(self):
        drama=files.create_drama({'current_name':'本地保留名称','history_names':['生恩如纸，养恩如山'],'theater_id':self.theater['id']})
        self.ingest([self.item(miniAppName='绿泡泡短剧')])
        self.ingest([self.item('video-id')],source='channels_drama')
        self.assertEqual(1,self.count())
        record=files.get_drama(drama['id'])
        self.assertEqual('本地保留名称',record['current_name']);self.assertEqual(104,record['official_total_episodes']);self.assertEqual(2,len(record['platform_sources']))
    def test_changes_refresh_external_fields_but_preserve_omitted_values(self):
        self.ingest([self.item(miniAppName='绿泡泡短剧',questFlag=7)])
        self.ingest([{'id':'remote-a','name':'平台改名','mediaCount':105,'usable':True}])
        row=files.list_dramas()['items'][0]
        self.assertEqual('生恩如纸 养恩如山',row['current_name']);self.assertEqual(105,row['official_total_episodes'])
        self.assertEqual('绿泡泡短剧',row['platform_sources'][0]['miniAppName']);self.assertEqual(7,row['platform_sources'][0]['questFlag'])
        self.ingest([{'id':'remote-a','name':'平台改名','mediaCount':'invalid','miniAppName':'','coverUrl':'','usable':True}])
        preserved=files.list_dramas()['items'][0]
        self.assertEqual(105,preserved['official_total_episodes']);self.assertEqual('绿泡泡短剧',preserved['platform_sources'][0]['miniAppName'])
    def test_deleted_drama_is_not_offered_and_new_fetch_recreates_valid_link(self):
        self.ingest([self.item()]);drama=files.list_dramas()['items'][0]
        files.delete_drama(drama['id'])
        self.assertEqual([],self.catalogue.eligibility([self.account['id']],'mini_drama')['items'])
        self.assertIsNone(self.catalogue.items(self.account['id'],'mini_drama')['items'][0]['drama_id'])
        self.ingest([self.item()]);new=files.list_dramas()['items'][0]
        self.assertNotEqual(drama['id'],new['id']);self.assertEqual(1,self.count())
    def test_same_remote_on_multiple_accounts_links_once_but_availability_is_independent(self):
        self.ingest([self.item()]);self.ingest([self.item(usable=False,unusableReason='当前账号不可挂载')],account=self.account2)
        self.assertEqual(1,self.count())
        a=self.catalogue.eligibility([self.account['id'],self.account2['id']],'mini_drama')['items']
        self.assertEqual([self.account['id']],[r['account_id'] for r in a])
    def test_same_name_other_theater_does_not_merge_or_abort(self):
        other=files.create_theater({'name':'另一个剧场'})
        existing=files.create_drama({'current_name':'生恩如纸 养恩如山','theater_id':other['id']})
        self.ingest([self.item()]);self.assertEqual(2,self.count())
        linked=self.catalogue.items(self.account['id'],'mini_drama')['items'][0]
        self.assertNotEqual(existing['id'],linked['drama_id']);self.assertIn('测试剧场',linked['current_name'])
        self.ingest([self.item('video-id')],source='channels_drama');self.assertEqual(2,self.count())
    def test_cover_fills_empty_original_only_and_preserves_sheep_and_versions(self):
        _,covers=self.ingest([self.item()]);self.assertEqual('filled',self.catalogue.fill_cover(covers[0]))
        drama=files.list_dramas()['items'][0]['id'];store=CoverStore(files.WORKSPACE,files.connection)
        first=store.snapshot(drama);self.assertEqual(first['project']['drama']['original'],first['project']['sheep']['original'])
        store.replace_original(drama,{'filename':'mine.png','content_base64':base64.b64encode(picture('green')).decode()},'drama')
        before=store.snapshot(drama);self.assertEqual('existing',self.catalogue.fill_cover(covers[0]));self.assertEqual(before,store.snapshot(drama))
    def test_manual_replacement_during_download_wins(self):
        _,covers=self.ingest([self.item()]);drama=files.list_dramas()['items'][0]['id'];store=CoverStore(files.WORKSPACE,files.connection)
        def download(url):
            store.replace_original(drama,{'filename':'manual.png','content_base64':base64.b64encode(picture('blue')).decode()},'drama')
            return picture('red')
        self.catalogue.downloader=download
        self.assertEqual('existing',self.catalogue.fill_cover(covers[0]))
        path=store.cover_info(drama)['cover']['path']
        self.assertEqual((0,0,255,255),Image.open(path).getpixel((0,0)))
    def test_official_count_conflict_keeps_both_does_not_flip_main_count(self):
        self.ingest([self.item()]);self.ingest([self.item('video-id',mediaCount=103)],source='channels_drama')
        record=files.list_dramas()['items'][0];self.assertTrue(record['episode_count_conflict']);self.assertEqual(0,record['official_total_episodes'])
        self.assertEqual({103,104},{r['mediaCount'] for r in record['platform_sources']})
    def test_mount_snapshot_persists_and_failed_theater_or_unusable_rejected(self):
        self.ingest([self.item()]);drama=files.list_dramas()['items'][0]
        payload={'source_id':'fixture-task','account_name':'测试账号','drama_name':drama['current_name'],'mount_source':'mini_drama','mount_external_id':'remote-a','planned_publish_at':'2026-10-27'}
        task=files.create_task(payload)
        self.ingest([self.item(name='平台新名称',mediaCount=105)])
        with closing(files.connection()) as conn:
            saved=task_metadata(conn,task['id']);self.assertEqual(104,saved['mount_snapshot']['mediaCount'])
            with self.assertRaises(ValueError):validate_mount(conn,payload,'另一个账号',drama['current_name'])
        with self.assertRaises(ValueError):files.create_task({**payload,'source_id':'other','mount_source':'plugin','planned_publish_at':'2026-10-27'})
    def test_plugin_and_cross_theater_validation(self):
        drama=files.create_drama({'current_name':'手工剧','theater_id':self.theater['id']})
        task=files.create_task({'source_id':'plugin','account_name':'测试账号','drama_name':drama['current_name'],'mount_source':'plugin','planned_publish_at':'2026-10-27'})
        self.assertEqual('plugin',task['mount_source'])
        other=files.create_theater({'name':'他处'});wrong=files.create_drama({'current_name':'其他剧','theater_id':other['id']})
        with self.assertRaises(ValueError):files.create_task({'source_id':'wrong','account_name':'测试账号','drama_name':wrong['current_name'],'mount_source':'plugin','planned_publish_at':'2026-10-27'})
        with self.assertRaisesRegex(ValueError,'计划日期'):files.create_task({'source_id':'missing-day','account_name':'测试账号','drama_name':drama['current_name'],'mount_source':'plugin'})
    def test_pagination_short_first_page_continues_and_sources_use_correct_parameters(self):
        for source in ('mini_drama','channels_drama'):
            Cat.pages[(source,1)]={'list':[self.item(source+'-1','第一页',coverUrl='')],'totalCount':2}
            Cat.pages[(source,2)]={'list':[self.item(source+'-2','第二页',coverUrl='')],'totalCount':2}
        job=self.run_sync(['mini_drama','channels_drama']);self.assertEqual('completed',job['status']);self.assertEqual(4,job['fetched']);self.assertEqual(2,self.count())
        self.assertTrue(any(p.get('sceneType')==3 for p in Cat.calls));self.assertTrue(any('sceneType' not in p for p in Cat.calls))
    def test_repeated_page_stops_partial_and_empty_refresh_does_not_remove(self):
        item=self.item(coverUrl='')
        for page in (1,2):Cat.pages[('mini_drama',page)]={'list':[item],'totalCount':100}
        job=self.run_sync();self.assertEqual('partial',job['status']);self.assertEqual(1,self.count())
        Cat.pages={};job=self.run_sync();self.assertEqual('completed',job['status']);self.assertEqual(1,self.count())
    def test_thousands_records_incremental_and_catalog_paginates_24(self):
        for page in range(1,77):
            Cat.pages[('mini_drama',page)]={'list':[self.item(str(n),'目录剧'+str(n),coverUrl='') for n in range((page-1)*20,min(page*20,1503))],'totalCount':1503}
        job=self.run_sync();self.assertEqual('completed',job['status']);self.assertEqual(1503,job['fetched']);self.assertEqual(1503,self.count())
        page=self.catalogue.items(self.account['id'],'mini_drama',page=2);self.assertEqual(24,len(page['items']));self.assertEqual(1503,page['total'])
        self.assertEqual(1,self.catalogue.items(self.account['id'],'mini_drama',query='目录剧1502')['total'])
    def test_complete_refresh_hides_absent_only_for_scanned_account_and_source(self):
        self.ingest([self.item('a', '掉链接剧', coverUrl=''), self.item('b', '仍可挂载', coverUrl='')])
        self.ingest([self.item('a', '掉链接剧', coverUrl='')], account=self.account2)
        self.ingest([self.item('a', '掉链接剧', coverUrl='')], source='channels_drama')
        drama_id = next(r['drama_id'] for r in self.catalogue.items(self.account['id'], 'mini_drama')['items'] if r['external_id'] == 'a')
        Cat.pages[('mini_drama',1)] = {'list':[self.item('b', '仍可挂载', coverUrl='')], 'totalCount':1}
        job = self.run_sync(mode='usable')
        self.assertEqual('completed', job['status']); self.assertEqual(1, job['removed'])
        for usable_only in (False, True):
            self.assertEqual(['b'], [r['external_id'] for r in self.catalogue.items(self.account['id'], 'mini_drama', usable_only=usable_only)['items']])
        self.assertEqual(['b'], [r['external_id'] for r in self.catalogue.eligibility([self.account['id']], 'mini_drama')['items']])
        self.assertEqual(1, self.catalogue.items(self.account2['id'], 'mini_drama')['total'])
        self.assertEqual(1, self.catalogue.items(self.account['id'], 'channels_drama')['total'])
        self.assertEqual(2, self.count())
        with closing(files.connection()) as conn:
            row = conn.execute('SELECT present,usable FROM v3_catalog_availability WHERE account_id=? AND source=? AND external_id=?', (self.account['id'], 'mini_drama', 'a')).fetchone()
            self.assertEqual((0,0), tuple(row))
            with self.assertRaises(ValueError):
                validate_mount(conn, {'mount_source':'mini_drama','mount_external_id':'a'}, self.account['nickname'], '掉链接剧')
        Cat.pages[('mini_drama',1)] = {'list':[self.item('a', '掉链接剧', coverUrl=''), self.item('b', '仍可挂载', coverUrl='')], 'totalCount':2}
        self.assertEqual('completed', self.run_sync()['status'])
        restored = next(r for r in self.catalogue.items(self.account['id'], 'mini_drama')['items'] if r['external_id'] == 'a')
        self.assertEqual(drama_id, restored['drama_id']); self.assertEqual(2, self.count())

    def test_confirmed_empty_directory_hides_entries_but_preserves_local_drama(self):
        self.ingest([self.item(coverUrl='')])
        job = self.run_sync()
        self.assertEqual('completed', job['status']); self.assertEqual(1, job['removed'])
        self.assertEqual(0, self.catalogue.items(self.account['id'], 'mini_drama')['total'])
        self.assertEqual([], self.catalogue.eligibility([self.account['id']], 'mini_drama')['items'])
        self.assertEqual(1, self.count())

    def test_incomplete_or_invalid_scan_never_prunes_previous_catalogue(self):
        cases = [
            {('mini_drama',1): {'list':[], 'totalCount':1}},
            {('mini_drama',1): {'list':[]}},
            {('mini_drama',1): {'list':[], 'totalCount':-1}},
            {('mini_drama',1): {'list':[{'id':'broken'}], 'totalCount':1}},
            {('mini_drama',1): {'list':[self.item('new',coverUrl='')], 'totalCount':3}, ('mini_drama',2): {'list':[], 'totalCount':3}},
            {('mini_drama',1): {'list':[self.item('new',coverUrl='')], 'totalCount':3}, ('mini_drama',2): {'list':[], 'totalCount':2}},
            {('mini_drama',1): {'list':[self.item('new',coverUrl='')], 'totalCount':3}, ('mini_drama',2): RuntimeError('中断')},
        ]
        self.ingest([self.item('old', '旧剧', coverUrl='')])
        for pages in cases:
            with self.subTest(pages=pages):
                Cat.pages = pages
                job = self.run_sync()
                self.assertEqual('partial', job['status']); self.assertEqual(0, job['removed'])
                self.assertIn('old', [r['external_id'] for r in self.catalogue.items(self.account['id'], 'mini_drama')['items']])
        Cat.login = '登录失效'
        self.assertEqual('partial', self.run_sync()['status'])
        self.assertIn('old', [r['external_id'] for r in self.catalogue.items(self.account['id'], 'mini_drama')['items']])

    def test_out_of_range_page_returns_last_page(self):
        self.ingest([self.item(str(i), '剧'+str(i), coverUrl='') for i in range(27)])
        result = self.catalogue.items(self.account['id'], 'mini_drama', page=100)
        self.assertEqual(2, result['page']); self.assertEqual(3, len(result['items']))

    def test_old_availability_schema_adds_presence_without_losing_rows(self):
        self.ingest([self.item(coverUrl='')])
        with closing(files.connection()) as conn:
            conn.execute('ALTER TABLE v3_catalog_availability DROP COLUMN present')
            initialize(conn); initialize(conn); conn.commit()
            self.assertEqual(1, conn.execute('SELECT present FROM v3_catalog_availability').fetchone()[0])
        self.assertEqual(1, self.catalogue.items(self.account['id'], 'mini_drama')['total'])

    def test_current_version_startup_repairs_missing_presence_with_all_tables_present(self):
        self.ingest([self.item(coverUrl='')])
        with closing(files.connection()) as conn:
            before = [tuple(r) for r in conn.execute('SELECT account_id,source,external_id,usable,reason,checked_at FROM v3_catalog_availability')]
            conn.execute('ALTER TABLE v3_catalog_availability DROP COLUMN present'); conn.commit()
            self.assertEqual(files.SCHEMA_VERSION, conn.execute('PRAGMA user_version').fetchone()[0])
            self.assertTrue(files.FEATURE_TABLES <= {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        files.DATABASE_INITIALIZED_PATH = None
        with closing(files.connection()) as conn:
            self.assertEqual(1, conn.execute('SELECT present FROM v3_catalog_availability').fetchone()[0])
            self.assertEqual(before, [tuple(r) for r in conn.execute('SELECT account_id,source,external_id,usable,reason,checked_at FROM v3_catalog_availability')])
        self.assertEqual(1, self.catalogue.items(self.account['id'], 'mini_drama')['total'])

    def test_catalogue_open_repairs_cached_connection_schema_without_restart(self):
        self.ingest([self.item(coverUrl='')])
        with closing(files.connection()) as conn:
            conn.execute('ALTER TABLE v3_catalog_availability DROP COLUMN present'); conn.commit()
        self.assertIsNotNone(files.DATABASE_INITIALIZED_PATH)
        restored = Catalogue(files.WORKSPACE, files.connection, Cat, lambda url: picture())
        self.assertEqual(1, restored.items(self.account['id'], 'mini_drama')['total'])
        self.assertEqual(1, len(restored.eligibility([self.account['id']], 'mini_drama')['items']))
        statements = []
        def traced():
            conn = files.connection(); conn.set_trace_callback(statements.append); return conn
        Catalogue(files.WORKSPACE, traced, Cat)
        self.assertFalse(any(line.lstrip().upper().startswith(('ALTER', 'INSERT', 'CREATE', 'UPDATE', 'DELETE', 'BEGIN')) for line in statements))

    def test_concurrent_catalogue_open_repairs_missing_column_once(self):
        from concurrent.futures import ThreadPoolExecutor
        self.ingest([self.item(coverUrl='')])
        with closing(files.connection()) as conn:
            conn.execute('ALTER TABLE v3_catalog_availability DROP COLUMN present'); conn.commit()
        def open_catalogue(_):
            catalogue = Catalogue(files.WORKSPACE, files.connection, Cat)
            return catalogue.items(self.account['id'], 'mini_drama')['total']
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual([1,1,1,1], list(pool.map(open_catalogue, range(4))))

    def test_page_size_24_48_96_and_invalid_size(self):
        self.ingest([self.item(str(i), '剧'+str(i), coverUrl='') for i in range(101)])
        for size in (24,48,96):
            result = self.catalogue.items(self.account['id'], 'mini_drama', page=2, page_size=size)
            self.assertEqual(size, result['page_size'])
            self.assertEqual(min(size,101-size), len(result['items']))
        with self.assertRaises(ValueError): self.catalogue.items(self.account['id'], 'mini_drama', page_size=20)

    def test_database_write_error_is_reported_as_failure_not_empty_success(self):
        import sqlite3
        Cat.pages[('mini_drama',1)] = {'list':[self.item(coverUrl='')], 'totalCount':1}
        def broken(*args): raise sqlite3.OperationalError('no such column: present')
        self.catalogue.ingest = broken
        with self.assertLogs('server.drama_catalog', level='ERROR'):
            job = self.run_sync()
        self.assertEqual('partial', job['status']); self.assertEqual(0, job['fetched'])
        self.assertIn('获取未完成', job['message']); self.assertIn('目录保存失败', job['errors'][0])

    def test_avatar_cache_uses_account_id_preserves_business_fields_and_failure_old_image(self):
        self.assertTrue(self.catalogue.sync_avatar(self.account,{'avatar':'https://example.test/avatar'}))
        record=files.get_account(self.account['id']);self.assertIn('/avatar?',record['avatar_url']);self.assertEqual(self.theater['id'],record['theater_id'])
        self.assertFalse(self.catalogue.sync_avatar(self.account,{'avatar':'https://example.test/avatar'}))
        self.catalogue.downloader=lambda url: (_ for _ in ()).throw(OSError('offline'))
        with self.assertRaises(OSError):self.catalogue.sync_avatar(self.account,{'avatar':'https://example.test/new'})
        self.assertEqual(record['avatar_url'],files.get_account(self.account['id'])['avatar_url'])
    def test_parallel_identical_avatars_share_file_and_both_update(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(2)
        data = picture('blue')
        def download(url):
            barrier.wait(timeout=3)
            return data
        self.catalogue.downloader = download
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.catalogue.sync_avatar, a, {'avatar':'https://example.test/shared'}) for a in (self.account,self.account2)]
            self.assertEqual([True,True], [f.result() for f in futures])
        with closing(files.connection()) as conn:
            rows = conn.execute('SELECT path FROM v3_catalog_avatars').fetchall()
        self.assertEqual(2, len(rows))
        self.assertEqual(1, len({r['path'] for r in rows}))

    def test_avatar_update_emits_account_event_and_preserves_business_record(self):
        with closing(files.connection()) as conn:
            before = dict(conn.execute('SELECT * FROM accounts WHERE id=?', (self.account['id'],)).fetchone())
            last = conn.execute('SELECT COALESCE(MAX(id),0) FROM v2_change_events').fetchone()[0]
        self.catalogue.sync_avatar(self.account, {'avatar':'https://example.test/avatar'})
        with closing(files.connection()) as conn:
            after = dict(conn.execute('SELECT * FROM accounts WHERE id=?', (self.account['id'],)).fetchone())
            events = [dict(r) for r in conn.execute('SELECT change_type,account_id FROM v2_change_events WHERE id>?', (last,))]
        self.assertEqual(before, after)
        self.assertEqual([{'change_type':'account_changed', 'account_id':self.account['id']}], events)

    def test_avatar_download_race_does_not_attach_to_changed_account(self):
        self.catalogue.sync_avatar(self.account, {'avatar':'https://example.test/old'})
        old = files.get_account(self.account['id'])['avatar_url']
        def download(url):
            with closing(files.connection()) as conn:
                conn.execute("UPDATE accounts SET channel_id='changed-during-download' WHERE id=?", (self.account['id'],))
                conn.commit()
            return picture('blue')
        self.catalogue.downloader = download
        with self.assertRaisesRegex(ValueError, '平台ID已变化'):
            self.catalogue.sync_avatar(self.account, {'avatar':'https://example.test/new'})
        self.assertEqual(old, files.get_account(self.account['id'])['avatar_url'])

    def test_account_preview_uses_same_cached_avatar_as_account_api(self):
        from server.account_import import AccountImport
        from server.tests.test_account_import import Cat as PreviewCat
        self.catalogue.sync_avatar(self.account, {'avatar':'https://example.test/avatar'})
        saved = PreviewCat.accounts_data
        try:
            PreviewCat.accounts_data = [{'uid':'uid-a','nickname':'平台昵称','platform':'Channels','groupName':'默认分组','avatar':'https://example.test/different'}]
            item = AccountImport(files.WORKSPACE, files.connection, PreviewCat).preview()['items'][0]
            self.assertEqual(files.get_account(self.account['id'])['avatar_url'], item['localAvatar'])
            self.assertEqual('existing', item['match'])
        finally:
            PreviewCat.accounts_data = saved

    def test_production_details_and_summaries_return_actual_account_id(self):
        drama = files.create_drama({'current_name':'头像身份测试剧','theater_id':self.theater['id']})
        task = files.create_task({'source_id':'avatar-task','account_name':'测试账号','drama_name':drama['current_name'],'planned_publish_at':'2026-11-04'})
        self.assertEqual(self.account['id'], files.get_task_details(task['id'])['account_id'])
        self.assertEqual(self.account['id'], files.list_task_summaries()['items'][0]['account_id'])
        with closing(files.connection()) as conn:
            conn.execute("UPDATE production_tasks SET account_name='无法关联的旧昵称' WHERE id=?", (task['id'],))
            conn.commit()
        self.assertEqual('', files.get_task_details(task['id'])['account_id'])

    def test_stop_keeps_successful_page(self):
        self.ingest([self.item('old', coverUrl='')])
        Cat.pages[('mini_drama',1)]={'list':[self.item(coverUrl='')],'totalCount':100}
        original=self.catalogue.ingest
        def ingest(*args):
            result=original(*args)
            for job in JOBS.values():job['stop']=True
            return result
        self.catalogue.ingest=ingest
        job=self.run_sync();self.assertEqual('stopped',job['status']);self.assertEqual(1,self.count())
        self.assertEqual({'old', 'remote-a'}, {r['external_id'] for r in self.catalogue.eligibility([self.account['id']], 'mini_drama')['items']})


if __name__ == '__main__': unittest.main()
