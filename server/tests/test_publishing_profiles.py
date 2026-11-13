import copy
import json
import unittest
from unittest.mock import patch
from server.tests import test_publishing as fixtures
from server.publishing.profiles import PublishProfiles,base_config


class PublishingProfileTests(unittest.TestCase):
    setUp=fixtures.PublishingTests.setUp
    tearDown=fixtures.PublishingTests.tearDown
    connect=fixtures.PublishingTests.connect
    config=fixtures.PublishingTests.config

    def make(self,name='测试方案',**options):
        return self.service.profile_save('task-a',{'name':name,'config':base_config(),**options})['profile']

    def apply(self,profile,settings=None,scopes=None,task='task-a'):
        value=self.service.profile_preview(task,{'id':profile['id'],'settings':settings or self.service.load(task)['settings'],**({'scopes':scopes} if scopes is not None else {})})
        return self.service.save(task,value['settings'])

    def test_examples_are_read_only_and_do_not_replace_existing_base_defaults(self):
        result=self.service.load('task-a')
        self.assertEqual(2,len(result['profile_library']['items']));self.assertIsNone(result['profile_library']['software_default_id'])
        self.assertEqual('now',result['settings']['schedule']['schedule_type'])
        self.assertIsNone(self.service.read('publish_profiles','library'))

    def test_sync_addresses_is_saved_normalized_and_does_not_change_manual_groups_or_defaults(self):
        a={'poiCheckSum':'a','name':'A','_searchQuery':{'query':'A'}}
        b={'poiCheckSum':'b','name':'B','_searchQuery':{'query':'B'}}
        self.service.save_address('task-a',a,True);settings=self.service.load('task-a')['settings']
        special=copy.deepcopy(settings['groups'][0]);special.update(id='custom',kind='custom',name='人工组',video_ids=[],location=b)
        settings.update(sync_location=True,assignment_mode='manual',assignment_confirmed=True);settings['groups'].append(special)
        settings['groups'][0]['location']=None
        ctx=self.service.save('task-a',settings)
        self.assertEqual([None,None,b],[g['location'] for g in ctx['settings']['groups']]);self.assertEqual(a,ctx['default_address'])
        settings=ctx['settings'];settings['sync_location']=False;settings['groups'][0]['location']=a;settings['groups'][1]['location']=b
        ctx=self.service.save('task-a',settings);self.assertEqual([a,b,b],[g['location'] for g in ctx['settings']['groups']])
        self.assertFalse(ctx['settings']['sync_location'])

    def test_profile_captures_and_applies_sync_only_with_address_scope(self):
        self.config();config=base_config();config['location']['sync']=False
        profile=self.make(config=config);ctx=self.apply(profile)
        self.assertFalse(ctx['settings']['sync_location']);self.assertFalse(self.service.profile_capture('task-a',{'settings':ctx['settings']})['config']['location']['sync'])
        config['location']['sync']=True;updated=self.service.profile_save('task-a',{**profile,'config':config})['profile']
        preview=self.service.profile_preview('task-a',{'id':updated['id'],'scopes':['copies']})
        self.assertFalse(preview['settings']['sync_location'])
        result=self.apply(updated,scopes=['location_mount']);self.assertTrue(result['settings']['sync_location']);self.assertFalse(result['profile_state']['modified'])

    def test_legacy_different_locations_stay_independent_without_database_rewrite(self):
        self.config();saved=self.service.read('settings','task-a');saved.pop('sync_location',None)
        saved['groups'][0]['location']={'poiCheckSum':'a','name':'A','_searchQuery':{'query':'A'}}
        saved['groups'][1]['location']=None;self.service.write('settings','task-a',saved)
        ctx=self.service.load('task-a');self.assertFalse(ctx['settings']['sync_location'])
        self.assertEqual(saved,self.service.read('settings','task-a'));self.assertIsNone(ctx['settings']['groups'][1]['location'])

    def test_mount_defaults_and_capture_are_independent_for_normal_and_sheep(self):
        ctx=self.service.load('task-a');normal,sheep=ctx['settings']['groups']
        self.assertTrue(normal['mount_required']);self.assertFalse(sheep['mount_required'])
        normal['mount_required']=False;sheep['mount_required']=True
        config=self.service.profile_capture('task-a',{'settings':ctx['settings']})['config']
        self.assertFalse(config['groups']['normal']['mount_required']);self.assertTrue(config['groups']['sheep']['mount_required'])
        self.assertNotIn('mount_required',config)

    def test_no_mount_payload_omits_component_even_when_an_association_is_saved(self):
        config=base_config();config['schedule']['schedule_type']='now'
        profile=self.make(config=config);ctx=self.apply(profile)
        ctx['binding']={'drama':{'id':'mount-a','name':'测试剧','usable':True}}
        values=[self.service.payload(ctx,i)['platformOptions'] for i in self.service.expanded(ctx)]
        self.assertIn('CAT_extReading',values[0]);self.assertNotIn('CAT_extReading',values[1])
        config['groups']['normal']['mount_required']=False;config['groups']['sheep']['mount_required']=True
        result=self.service.profile_save('task-a',{**profile,'config':config});ctx=self.apply(result['profile'])
        ctx['binding']={'drama':{'id':'mount-a','name':'测试剧','usable':True}}
        values=[self.service.payload(ctx,i)['platformOptions'] for i in self.service.expanded(ctx)]
        self.assertNotIn('CAT_extReading',values[0]);self.assertIn('CAT_extReading',values[1])

    def test_legacy_profile_switch_is_read_compatibly_without_changing_existing_task(self):
        ctx=self.config();settings=copy.deepcopy(self.service.load('task-a')['settings'])
        profile=self.make();raw=self.service.read('publish_profiles','library')
        for p in raw['items']:
            for g in p['config']['groups'].values():g.pop('mount_required',None)
            p['config']['mount_required']=True
        self.service.write('publish_profiles','library',raw)
        book=self.service.profile_library('task-a');found=next(p for p in book['items'] if p['id']==profile['id'])
        self.assertEqual(profile['revision']+1,found['revision'])
        self.assertTrue(found['config']['groups']['normal']['mount_required']);self.assertFalse(found['config']['groups']['sheep']['mount_required'])
        self.assertEqual(raw,self.service.read('publish_profiles','library'));self.assertEqual(settings,self.service.load('task-a')['settings'])

    def test_profile_history_shares_saved_task_text_and_remembers_only_successful_saves(self):
        ctx=self.config();ctx['settings']['groups'][0]['desc']='工作台历史';self.service.save('task-a',ctx['settings'])
        config=base_config();config['groups']['normal'].update(video_title='方案标题',desc='方案简介',tags=['话题一','话题二'],short_title='方案独立短标题',comment='方案追评',tag_type=7,repost_source='方案转载来源')
        self.make(config=config)
        history=self.service.profile_history('task-b');self.assertIn('工作台历史',history['desc']);self.assertIn('方案简介',history['desc'])
        for key,text in [('video_title','方案标题'),('tags','话题一 话题二'),('short_title','方案独立短标题'),('comment','方案追评'),('repost_source','方案转载来源')]:self.assertIn(text,history[key])
        config['groups']['normal']['desc']='失败不要记住'
        with self.assertRaisesRegex(ValueError,'同名'):self.make(config=config)
        self.assertNotIn('失败不要记住',self.service.profile_history('task-a')['desc'])

    def test_software_and_account_defaults_are_separate(self):
        first=self.make(software_default=True)
        cfg=base_config();cfg['groups']['normal']['copies']=3
        second=self.make('账号专用',config=cfg,account_default=True)
        self.assertEqual(second['id'],self.service.load('task-a')['profile_state']['id'])
        self.assertEqual(first['id'],self.service.load('task-b')['profile_state']['id'])
        self.assertEqual(3,self.service.load('task-a')['settings']['groups'][0]['copies'])

    def test_saved_task_is_not_overwritten_by_new_default_or_profile_edit(self):
        self.config();saved=self.service.load('task-a')['settings'];profile=self.make(software_default=True)
        self.assertEqual(saved,self.service.load('task-a')['settings'])
        applied=self.apply(profile);old=copy.deepcopy(applied['settings'])
        updated={**profile,'config':copy.deepcopy(profile['config'])};updated['config']['groups']['normal']['copies']=8
        self.service.profile_save('task-a',updated)
        result=self.service.load('task-a');self.assertEqual(old,result['settings']);self.assertTrue(result['profile_state']['update_available'])

    def test_partial_application_preserves_clock_identity_text_and_manual_groups(self):
        ctx=self.config();settings=ctx['settings'];settings['assignment_mode']='manual';settings['assignment_confirmed']=True
        settings['schedule']={'schedule_type':'timing','start_time':'2030-01-01 19:37','interval':1}
        settings['groups'][0]['desc']='保留简介';special=copy.deepcopy(settings['groups'][0]);special.update(id='special',kind='custom',name='人工特殊组',video_ids=[]);settings['groups'].append(special)
        profile=self.make();before=copy.deepcopy(settings)
        result=self.service.profile_preview('task-a',{'id':profile['id'],'settings':settings,'scopes':['schedule','copies']})
        value=result['settings'];self.assertEqual('2030-01-01 19:37',value['schedule']['start_time'])
        self.assertEqual('保留简介',value['groups'][0]['desc']);self.assertEqual(before['groups'][0]['video_ids'],value['groups'][0]['video_ids'])
        actual=next(g for g in value['groups'] if g['id']=='special')
        self.assertEqual({k:v for k,v in special.items() if k not in ('schedule_type','start_time','interval')},
            {k:v for k,v in actual.items() if k not in ('schedule_type','start_time','interval')});self.assertTrue(result['has_special_groups'])
        self.assertEqual(before,settings);self.assertEqual(before['account_id'],value['account_id'])

    def test_capture_and_save_never_store_files_accounts_exact_dates_or_executions(self):
        ctx=self.config();ctx['settings']['schedule']['start_time']='2030-01-01 19:37';ctx['settings']['groups'][0]['shoot_date']='2026-01-01'
        cfg=self.service.profile_capture('task-a',{'settings':ctx['settings']})['config']
        raw=json.dumps(cfg);self.assertNotIn('19:37',raw);self.assertNotIn('2026-01-01',raw);self.assertNotIn('video-a',raw);self.assertNotIn('account-a',raw)
        cfg['groups']['normal'].update(video_ids=['poison'],cover='secret.png',shoot_date='2000-01-01')
        saved=self.make(config=cfg);self.assertNotIn('poison',json.dumps(saved));self.assertNotIn('secret.png',json.dumps(saved))

    def test_profile_address_policy_does_not_change_account_defaults(self):
        address={'poiCheckSum':'a','name':'A地址','_searchQuery':{'query':'A'}};other={**address,'poiCheckSum':'b','name':'B地址'}
        self.service.save_address('task-a',address,True);self.service.save_address('task-b',other,True)
        profile=self.make();a=self.apply(profile);b=self.apply(profile,task='task-b')
        self.assertEqual(address,a['settings']['groups'][0]['location']);self.assertEqual(other,b['settings']['groups'][0]['location'])
        config=base_config();config['location']={'mode':'public','checksum':'b'};fixed=self.make('固定公共地址',config=config)
        result=self.apply(fixed);self.assertEqual(other,result['settings']['groups'][0]['location']);self.assertEqual(address,result['default_address'])

    def test_deleted_public_address_does_not_silently_apply_a_different_place(self):
        address={'poiCheckSum':'a','name':'A地址','_searchQuery':{'query':'A'}};self.service.save_address('task-a',address)
        config=base_config();config['location']={'mode':'public','checksum':'a','sync':False};profile=self.make(config=config,software_default=True)
        self.service.delete_address('task-a','a','public')
        with self.assertRaisesRegex(ValueError,'公共地址'):self.service.profile_preview('task-a',{'id':profile['id']})
        ctx=self.service.load('task-b');self.assertIn('problem',ctx['settings']['profile_ref']);self.assertFalse(ctx['settings']['sync_location'])
        with self.assertRaisesRegex(ValueError,'公共地址'):self.service.payload(ctx,self.service.expanded(ctx)[0])

    def test_delete_clears_default_references_but_keeps_task_snapshot(self):
        profile=self.make(software_default=True,account_default=True);result=self.apply(profile);settings=copy.deepcopy(result['settings'])
        self.service.profile_delete('task-a',profile)
        result=self.service.load('task-a');self.assertEqual(settings,result['settings']);self.assertTrue(result['profile_state']['deleted'])
        self.assertIsNone(result['profile_library']['account_default_id']);self.assertIsNone(result['profile_library']['software_default_id'])

    def test_profile_operations_leave_existing_execution_and_drafts_untouched(self):
        execution={'state':'ready','items':[{'key':'old','draft_id':987,'status':'ready','accepted_payload':{'original':'kept'}}]}
        self.service.write('execution','task-a',execution)
        profile=self.make();self.apply(profile);self.service.profile_delete('task-a',profile)
        self.assertEqual(execution,self.service.read('execution','task-a'))
        self.assertEqual([],fixtures.FakeCat.calls)

    def test_newly_detected_sheep_video_uses_applied_snapshot_not_edited_library(self):
        self.rows=self.rows[:1];config=base_config();config['groups']['sheep']['copies']=4
        profile=self.make(config=config);self.apply(profile)
        edited={**profile,'config':copy.deepcopy(config)};edited['config']['groups']['sheep']['copies']=9;self.service.profile_save('task-a',edited)
        self.rows.append({'id':'video-b','output_path':str(self.sheep),'sequence_no':2})
        result=self.service.load('task-a');self.assertEqual(4,result['settings']['groups'][1]['copies']);self.assertFalse(result['profile_state']['modified'])

    def test_managed_edits_mark_task_without_treating_exact_start_as_profile_change(self):
        profile=self.make();ctx=self.apply(profile);settings=ctx['settings'];settings['schedule']['start_time']='2030-01-01 19:37'
        self.assertFalse(PublishProfiles(self.service).state(settings)['modified'])
        settings['groups'][0]['desc']='任务独立修改';self.assertTrue(PublishProfiles(self.service).state(settings)['modified'])

    def test_name_revision_and_empty_scope_guards(self):
        profile=self.make()
        with self.assertRaisesRegex(ValueError,'同名'):self.make()
        with self.assertRaisesRegex(ValueError,'更新'):self.service.profile_save('task-a',{**profile,'revision':0})
        with self.assertRaises(ValueError):self.service.profile_preview('task-a',{'id':profile['id'],'scopes':[]})
        for config in ({'schedule':[1]}, {'groups':{'normal':[1]}}, {'groups':{'normal':{'desc':[]}}}):
            with self.assertRaises(ValueError):self.make('非法方案',config=config)
        with patch.object(self.service,'execution',return_value={'running':True}):
            with self.assertRaisesRegex(ValueError,'停止'):self.service.profile_preview('task-a',{'id':profile['id']})
