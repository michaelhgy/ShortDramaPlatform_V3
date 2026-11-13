import copy
import json
import unittest
from contextlib import closing
from server.tests import test_publishing as fixtures
from server.publishing.service import RUNS
from server.drama_catalog import guard_legacy_drafts


class TypedCat(fixtures.FakeCat):
    by_source={}
    def worker(self,uid,method,params):
        if method!='getDramaComponent':return super().worker(uid,method,params)
        self.calls.append((method,params))
        mode='channels_drama' if params.get('sceneType')==3 else 'mini_drama'
        rows=copy.deepcopy(self.by_source[mode]);return {'list':rows,'totalCount':len(rows),'baseResp':{'errcode':0}}


class PublishingMountSourceTests(unittest.TestCase):
    tearDown=fixtures.PublishingTests.tearDown
    connect=fixtures.PublishingTests.connect
    wait=fixtures.PublishingTests.wait
    def setUp(self):
        fixtures.PublishingTests.setUp(self)
        with closing(self.connect()) as c:c.execute('CREATE TABLE v3_catalog_task_mounts(task_id TEXT PRIMARY KEY,source TEXT,external_id TEXT,content TEXT)');c.commit()
        self.service.client_factory=TypedCat
        TypedCat.calls=[];TypedCat.drafts={};TypedCat.next_id=1
        TypedCat.by_source={mode:[{'id':mode+'-id','name':'生恩如纸养恩如山','usable':True,'mediaCount':100,'miniAppName':'测试小程序' if mode=='mini_drama' else '', 'questFlag':{'test':1}}] for mode in ('mini_drama','channels_drama')}

    def choose(self,mode):
        value=self.service.load('task-a')['settings'];value['mount_source']=mode
        return self.service.save('task-a',value)

    def original(self,mode,drama=None):
        drama=drama or (TypedCat.by_source[mode][0] if mode!='plugin' else {})
        with closing(self.connect()) as c:c.execute('INSERT OR REPLACE INTO v3_catalog_task_mounts VALUES(?,?,?,?)',('task-a',mode,drama.get('id',''),json.dumps(drama)));c.commit()

    def test_default_reads_catalogue_selection_and_reuses_exact_id_even_with_duplicate_names(self):
        self.original('mini_drama');TypedCat.by_source['mini_drama'].append({**TypedCat.by_source['mini_drama'][0],'id':'other-mini','miniAppName':'其他小程序'})
        ctx=self.service.load('task-a');self.assertEqual('mini_drama',ctx['settings']['mount_source']);self.assertTrue(ctx['binding']['from_task'])
        result=self.service.dramas('task-a');self.assertEqual('bound',result['status']);self.assertEqual('mini_drama-id',result['binding']['drama']['id'])
        self.assertTrue(all('sceneType' not in p for name,p in TypedCat.calls if name=='getDramaComponent'))

    def test_override_is_remembered_without_modifying_original_snapshot_and_switching_back_restores_binding(self):
        self.original('mini_drama');self.service.dramas('task-a')
        self.choose('channels_drama');self.assertIsNone(self.service.load('task-a')['binding'])
        video=self.service.dramas('task-a');self.assertEqual('channels_drama-id',video['binding']['drama']['id'])
        self.choose('mini_drama');self.assertEqual('mini_drama-id',self.service.load('task-a')['binding']['drama']['id'])
        with closing(self.connect()) as c:self.assertEqual('mini_drama',c.execute('SELECT source FROM v3_catalog_task_mounts').fetchone()[0])

    def test_modes_generate_different_complete_components_and_keep_group_no_mount(self):
        for mode,outer,inner in [('mini_drama',5,4),('channels_drama',8,8)]:
            self.choose(mode);binding=self.service.dramas('task-a')['binding'];ctx=self.service.load('task-a');ctx['binding']=binding
            items=self.service.expanded(ctx);opts=self.service.payload(ctx,items[0])['platformOptions'];mount=opts['CAT_extReading']
            self.assertEqual(outer,mount['type']);self.assertEqual(inner,mount['_mergeObjectDesc']['component']['type']);self.assertEqual({'test':1},mount['drama']['questFlag'])
            self.assertEqual(12 if mode=='mini_drama' else None,mount.get('urlType'))
            self.assertNotIn('CAT_extReading',self.service.payload(ctx,items[1])['platformOptions'])

    def test_plugin_skips_native_queries_and_generates_local_drafts_with_no_component(self):
        self.original('plugin');ctx=self.service.load('task-a');self.assertEqual('plugin',ctx['settings']['mount_source'])
        self.assertIsNone(ctx['binding']);self.assertEqual('plugin',self.service.dramas('task-a')['status']);self.assertTrue(self.service.check('task-a')['ok'])
        self.service.start('task-a');result=self.wait();self.assertEqual('ready',result['state'])
        self.assertEqual(2,len(TypedCat.drafts));self.assertTrue(all('CAT_extReading' not in d['platformOptionsByUid']['uid-a'] for d in TypedCat.drafts.values()))
        self.assertFalse(any(name=='getDramaComponent' for name,p in TypedCat.calls))

    def test_stale_candidate_source_and_running_source_changes_are_rejected(self):
        self.choose('mini_drama')
        with self.assertRaisesRegex(ValueError,'已变化'):self.service.bind('task-a',TypedCat.by_source['channels_drama'][0],True,False,'channels_drama')
        value=self.service.load('task-a')['settings'];value['mount_source']='bad'
        with self.assertRaises(ValueError):self.service.save('task-a',value)
        import threading
        gate=threading.Event();thread=threading.Thread(target=lambda:gate.wait(2));thread.start();RUNS['task-a']={'thread':thread,'mode':'running'}
        try:
            value['mount_source']='plugin'
            with self.assertRaisesRegex(ValueError,'正在执行'):self.service.save('task-a',value)
        finally:gate.set();thread.join();RUNS.clear()

    def test_unavailable_original_does_not_auto_switch_to_another_same_name_id(self):
        self.original('mini_drama');TypedCat.by_source['mini_drama']=[{**TypedCat.by_source['mini_drama'][0],'id':'other-id'}]
        result=self.service.dramas('task-a');self.assertEqual('unavailable',result['status']);self.assertEqual('mini_drama-id',result['binding']['drama']['id'])

    def test_native_draft_runner_uses_the_correct_modes(self):
        for mode in ('mini_drama','channels_drama'):
            self.choose(mode);self.service.start('task-a');result=self.wait()
            if mode=='mini_drama':
                self.assertEqual('ready',result['state']);old=copy.deepcopy(TypedCat.drafts)
            else:
                self.assertEqual('needs_help',result['state']);self.assertEqual(old,TypedCat.drafts)

    def test_http_handoff_guard_accepts_supported_modes_but_not_invalid_choice(self):
        with closing(self.connect()) as c:
            c.execute("INSERT INTO production_tasks SELECT 'aabbcc',account_name,drama_name,planned_publish_at,release_status FROM production_tasks WHERE id='task-a'")
            for mode in ('mini_drama','channels_drama','plugin'):
                c.execute('INSERT OR REPLACE INTO v3_catalog_task_mounts VALUES(?,?,?,?)',('aabbcc',mode,'','{}'));guard_legacy_drafts(c,'/api/v2/publishing/tasks/aabbcc/drafts')
            c.execute('INSERT OR REPLACE INTO v3_publish_documents VALUES(?,?,?,?)',('settings','aabbcc',json.dumps({'mount_source':'bad'}),'now'))
            with self.assertRaises(ValueError):guard_legacy_drafts(c,'/api/v2/publishing/tasks/aabbcc/drafts')
