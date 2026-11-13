import copy
import unittest
from server.tests import test_publishing as fixtures
from server.publishing.vcat import PublishOutcomeUnknown,PublishRejected,VcatClient


class PublishCat(fixtures.FakeCat):
    tasks=[];unknown=False;missing=False;mismatch_first=False;reject_after=None;reject_message='发布异常，需要管理员扫码验证';cancel_reject=False
    def call(self,name,args):
        if name=='vcat_set_publish_priority':
            self.calls.append((name,copy.deepcopy(args)))
            next(row for row in self.tasks if row['localId']==args['localId'])['statusCode']=0
            return {'updated':True}
        if name=='vcat_cancel_publish_task':
            self.calls.append((name,copy.deepcopy(args)))
            if self.cancel_reject:raise PublishRejected('小V猫拒绝取消任务')
            next(row for row in self.tasks if row['localId']==args['localId'])['statusCode']=5
            return {'canceled':True}
        if name=='vcat_create_publish_task':
            self.calls.append((name,copy.deepcopy(args)))
            if self.reject_after is not None and len(self.tasks)>=self.reject_after:raise PublishRejected(self.reject_message)
            row={**copy.deepcopy(args),'localId':'task-'+str(len(self.tasks)+1),'batchSource':args['batchName']+'_10-26 20:00:00','status':'已发布','statusCode':'2'}
            if self.mismatch_first and not self.tasks:
                row['_source']={'formData':{'CAT_timing':{'type':2,'time':'2000-01-01T00:00:00Z','autoReset':False}}}
            if not self.missing:self.tasks.append(row)
            if self.unknown:raise PublishOutcomeUnknown('test unknown submission')
            return {'tasks':[{'localId':row['localId']}],'batchSource':row['batchSource']}
        if name=='vcat_list_publish_tasks':
            rows=[r for r in self.tasks if r['uid']==args['uid'] and r['batchSource'].startswith(args['batchSource'])]
            return {'list':copy.deepcopy(rows),'total':len(rows)}
        return super().call(name,args)
    def task_action(self,name,*arguments):
        self.calls.append((name,copy.deepcopy(arguments)))
        values,ids=arguments
        for row in self.tasks:
            if row['localId'] in ids:row['statusCode']=values['status']
        return {'updated':True}


class PublishingPublishTests(unittest.TestCase):
    connect=fixtures.PublishingTests.connect
    tearDown=fixtures.PublishingTests.tearDown
    def setUp(self):
        fixtures.PublishingTests.setUp(self);self.service.client_factory=PublishCat
        PublishCat.tasks=[];PublishCat.unknown=False;PublishCat.missing=False;PublishCat.mismatch_first=False;PublishCat.reject_after=None;PublishCat.cancel_reject=False;PublishCat.calls=[];PublishCat.drafts={};PublishCat.next_id=1
    def config(self):
        ctx=self.service.load('task-a');self.service.save('task-a',ctx['settings']);return ctx
    def wait(self,kind='publish'):
        import time
        for _ in range(500):
            state=self.service.execution('task-a',kind)
            if not state['running']:return state
            time.sleep(.01)
        self.fail('worker did not stop')
    def seed_task(self,key,status,payload=None):
        codes={'waiting':0,'publishing':1,'success':2,'paused':3,'failed':4,'canceled':5,'localTiming':6}
        local_id='local-'+key
        batch='V3-test-'+key
        record={'key':key,'name':key,'status':{'waiting':'submitted','publishing':'publishing','success':'success','paused':'paused','failed':'failed','canceled':'canceled','localTiming':'localTiming'}[status],
            'remote_state':status,'local_id':local_id,'batch_name':batch,'uid':'uid-a','payload':payload or {'scheduleType':'now'}}
        PublishCat.tasks.append({'uid':'uid-a','localId':local_id,'batchSource':batch+'_10-26 20:00:00','statusCode':codes[status]})
        state=self.service.publication('task-a');state['items'].append(record);self.service.write('publish_execution','task-a',state)
        return record
    def test_direct_publish_and_repeat_does_not_create_local_drafts_or_duplicate_queue_tasks(self):
        self.service.publish('task-a');state=self.wait();self.assertEqual(2,len(PublishCat.tasks));self.assertFalse(PublishCat.drafts)
        self.assertTrue(all(r['status']=='success' and r.get('local_id') for r in state['items']))
        self.assertTrue(all(r['start'] is True and r['autoReset'] is False for r in PublishCat.tasks))
        self.service.publish('task-a');self.wait();self.assertEqual(2,len(PublishCat.tasks))
    def test_plugin_action_routes_to_existing_local_drafts_without_real_publication(self):
        settings=self.service.load('task-a')['settings'];settings['mount_source']='plugin';self.service.save('task-a',settings)
        self.service.publish('task-a');self.wait('draft');self.assertEqual(2,len(PublishCat.drafts));self.assertFalse(PublishCat.tasks)
        self.assertTrue(all('CAT_extReading' not in d['platformOptionsByUid']['uid-a'] for d in PublishCat.drafts.values()))
    def test_uncertain_response_is_reconciled_and_not_resubmitted(self):
        PublishCat.unknown=True;self.service.publish('task-a');state=self.wait();self.assertEqual('uncertain',state['items'][0]['status']);self.assertEqual(1,len(PublishCat.tasks))
        self.service.refresh_publication('task-a');PublishCat.unknown=False;self.service.publish('task-a');self.wait();self.assertEqual(2,len(PublishCat.tasks))
        self.assertEqual(2,sum(n=='vcat_create_publish_task' for n,p in PublishCat.calls))
    def test_uncertain_missing_remote_task_never_blindly_retries(self):
        PublishCat.unknown=True;PublishCat.missing=True;self.service.publish('task-a');self.wait();self.service.publish('task-a');self.wait()
        self.assertEqual(1,sum(n=='vcat_create_publish_task' for n,p in PublishCat.calls))
    def test_account_level_rejection_stops_later_submission_and_continue_resubmits_after_fix(self):
        PublishCat.reject_after=1
        self.service.publish('task-a');state=self.wait()
        self.assertEqual(1,len(PublishCat.tasks));self.assertEqual(['success','rejected'],[item['status'] for item in state['items']])
        PublishCat.reject_after=None
        self.service.continue_publication('task-a');self.wait()
        self.assertEqual(2,len(PublishCat.tasks));self.assertTrue(all(item['status']=='success' for item in self.service.publication('task-a')['items']))
    def test_full_preflight_happens_before_any_queue_write(self):
        settings=self.service.load('task-a')['settings'];settings['groups'][1]['short_title']='短';self.service.write('settings','task-a',settings)
        self.service.publish('task-a');state=self.wait();self.assertEqual('needs_help',state['state']);self.assertFalse(PublishCat.tasks)
    def test_changed_parameters_preserve_existing_remote_tasks(self):
        self.service.publish('task-a');self.wait();settings=self.service.load('task-a')['settings'];settings['groups'][0]['desc']='changed';self.service.save('task-a',settings)
        self.service.publish('task-a');state=self.wait();self.assertEqual('needs_help',state['items'][0]['status']);self.assertEqual(2,len(PublishCat.tasks))
    def test_first_item_limit_then_resume_preserves_schedule_and_has_exactly_one_task_per_copy(self):
        from datetime import datetime,timedelta
        settings=self.service.load('task-a')['settings'];settings['schedule']={'schedule_type':'timing','start_time':(datetime.now()+timedelta(days=2)).strftime('%Y-%m-%d')+' 20:00','interval':3}
        settings['groups'][0]['copies']=3;self.service.save('task-a',settings)
        self.service.publish('task-a',limit=1);self.wait();self.assertEqual(1,len(PublishCat.tasks))
        self.service.publish('task-a');self.wait();self.assertEqual(4,len(PublishCat.tasks));self.assertEqual(4,len({r['batchName'] for r in PublishCat.tasks}))
        self.assertEqual(['20:00','20:03','20:06','20:09'],[r['scheduleTime'][-5:] for r in PublishCat.tasks])
    def test_adapter_requires_explicit_real_publishing_permission(self):
        client=VcatClient.__new__(VcatClient);client.writable=True;client.publishing=False
        with self.assertRaises(ValueError):client.call('vcat_create_publish_task',{})
    def test_cancel_adapter_requires_same_explicit_publishing_permission(self):
        client=VcatClient.__new__(VcatClient);client.writable=True;client.publishing=False
        with self.assertRaises(ValueError):client.call('vcat_cancel_publish_task',{'localId':'task-1'})
        client.publishing=True;client.setting={'writeModules':{'publish':True}};client.changed=False
        client.request=lambda method,params:{'result':{'content':[{'type':'text','text':'{"canceled":true}'}]}}
        self.assertEqual({'canceled':True},client.call('vcat_cancel_publish_task',{'localId':'task-1'}))
    def test_manually_deleted_queue_task_is_reported_and_never_recreated(self):
        self.service.publish('task-a');self.wait();removed=PublishCat.tasks.pop(0)
        state=self.service.refresh_publication('task-a');self.assertEqual('uncertain',state['items'][0]['status'])
        self.assertEqual(removed['localId'],state['items'][0]['local_id'])
        self.service.publish('task-a');self.wait()
        self.assertEqual(2,sum(n=='vcat_create_publish_task' for n,p in PublishCat.calls))
        self.assertEqual(1,len(PublishCat.tasks))
    def test_live_form_verification_detects_wrong_account_mount_location_and_timing(self):
        from server.publishing.publisher import verify_remote
        payload={'uid':'uid-a','videoPath':r'D:\video.mp4','desc':'test','tags':['topic'],'cover':r'D:\cover.png',
            'scheduleType':'timing','scheduleTime':'2026-10-28 20:00','platformOptions':{
                'CAT_extReading':{'type':5},'CAT_location':{'uid':'poi'},'CAT_shortTitle':'','tagInfo':{'tagType':0},'postFlag':0}}
        row={'uid':'uid-a','videoPath':'file://D:\\video.mp4','_source':{'formData':{
            **copy.deepcopy(payload['platformOptions']),'CAT_desc':'test','topics':['topic'],'CAT_cover':'file://D:\\cover.png',
            'CAT_timing':{'type':2,'time':'2026-10-28T12:00:00.000Z','autoReset':False}}}}
        self.assertTrue(all(verify_remote(row,payload).values()))
        row['uid']='other';form=row['_source']['formData'];form.pop('CAT_extReading');form['CAT_location']={'uid':'other'};form['CAT_timing']['type']=1;form['CAT_timing']['autoReset']=True
        checks=verify_remote(row,payload)
        for key in ('account','CAT_extReading','CAT_location','time_mode','no_immediate_fallback'):self.assertFalse(checks[key],key)
    def test_batch_identity_leaves_room_for_small_cat_timestamp_suffix(self):
        from server.publishing.publisher import batch_name
        name=batch_name('a'*32,'group:video:0')
        self.assertLessEqual(len(name+'_10-26 20:00:00'),50)
        self.assertNotEqual(name,batch_name('a'*32,'group:video:1'))
    def test_remote_parameter_warning_does_not_stop_later_items(self):
        self.config();PublishCat.mismatch_first=True
        self.service.publish('task-a');state=self.wait()
        self.assertEqual(2,len(PublishCat.tasks))
        self.assertEqual('needs_help',state['items'][0]['status'])
        self.assertEqual('success',state['items'][1]['status'])
    def test_listed_local_time_can_validate_form_time_with_version_offset(self):
        from server.publishing.publisher import verify_remote
        payload={'uid':'uid-a','videoPath':r'D:\video.mp4','desc':'x','tags':[],
            'scheduleType':'timing','scheduleTime':'2026-10-31 07:35','platformOptions':{}}
        row={'uid':'uid-a','timing':'2026-10-31 07:35:00','videoPath':r'D:\video.mp4',
            '_source':{'formData':{'CAT_desc':'x','topics':[],'CAT_timing':{'type':2,'time':'2026-10-31T11:35:00.000Z','autoReset':False}}}}
        checks=verify_remote(row,payload)
        self.assertTrue(checks['time'])
    def test_unsubmitted_pending_item_can_be_canceled_locally(self):
        self.config();ctx=self.service.load('task-a');item=self.service.expanded(ctx)[0]
        self.service.write('publish_execution','task-a',{'items':[{'key':item['key'],'name':item['video']['name'],'group_id':item['group']['id'],'group_name':item['group']['name'],'copy':item['copy'],'status':'pending','uid':'uid-a','batch_name':'V3-pending'}],'state':'needs_help'})
        result=self.service.manage_publication_tasks('task-a','cancel',[item['key']])
        self.assertEqual([item['key']],result['changed'])
        self.assertEqual('canceled',self.service.publication('task-a')['items'][0]['status'])
        self.assertFalse(PublishCat.tasks)
    def test_unsubmitted_pending_item_uses_continue_submission_not_remote_retry(self):
        self.config();ctx=self.service.load('task-a');item=self.service.expanded(ctx)[0]
        self.service.write('publish_execution','task-a',{'items':[{'key':item['key'],'name':item['video']['name'],'group_id':item['group']['id'],'group_name':item['group']['name'],'copy':item['copy'],'status':'pending','uid':'uid-a','batch_name':'V3-pending'}],'state':'needs_help'})
        result=self.service.continue_publication('task-a',[item['key']])
        self.wait();self.assertTrue(result['accepted'])
        self.assertEqual(1,len(PublishCat.tasks))
        self.assertEqual('success',self.service.publication('task-a')['items'][0]['status'])
    def test_pause_only_updates_waiting_tasks_and_skips_other_states(self):
        self.config();waiting=self.seed_task('waiting','waiting');local=self.seed_task('local','localTiming');success=self.seed_task('success','success')
        result=self.service.manage_publication_tasks('task-a','pause',[waiting['key'],local['key'],success['key']])
        self.assertEqual([waiting['key']],result['changed'])
        self.assertEqual({local['key'],success['key']},{item['key'] for item in result['skipped']})
        self.assertEqual(3,next(row['statusCode'] for row in PublishCat.tasks if row['localId']==waiting['local_id']))
        self.assertFalse(any(row['localId'] in (local['local_id'],success['local_id']) for row in PublishCat.tasks if row['statusCode']==3))
    def test_cancel_only_targets_active_queue_states_and_never_success(self):
        self.config();waiting=self.seed_task('waiting','waiting');publishing=self.seed_task('publishing','publishing');paused=self.seed_task('paused','paused');success=self.seed_task('success','success')
        result=self.service.manage_publication_tasks('task-a','cancel',[waiting['key'],publishing['key'],paused['key'],success['key']])
        self.assertEqual({waiting['key'],publishing['key'],paused['key']},set(result['changed']))
        self.assertEqual({success['key']},{item['key'] for item in result['skipped']})
        self.assertEqual(5,next(row['statusCode'] for row in PublishCat.tasks if row['localId']==publishing['local_id']))
        self.assertEqual(5,next(row['statusCode'] for row in PublishCat.tasks if row['localId']==paused['local_id']))
        self.assertEqual(2,next(row['statusCode'] for row in PublishCat.tasks if row['localId']==success['local_id']))
    def test_retry_requeues_only_eligible_tasks_and_blocks_expired_schedule(self):
        from datetime import datetime,timedelta
        from server.publishing.service import SHANGHAI
        self.config();paused=self.seed_task('paused','paused');future=(datetime.now(SHANGHAI)+timedelta(days=2)).strftime('%Y-%m-%d %H:%M')
        failed=self.seed_task('future-failed','failed',{'scheduleType':'timing','scheduleTime':future})
        expired=self.seed_task('expired','canceled',{'scheduleType':'timing','scheduleTime':'2020-01-01 12:00'})
        success=self.seed_task('success','success')
        result=self.service.manage_publication_tasks('task-a','retry',[paused['key'],failed['key'],expired['key'],success['key']])
        self.assertEqual({paused['key'],failed['key']},set(result['changed']))
        self.assertEqual({expired['key'],success['key']},{item['key'] for item in result['skipped']})
        self.assertTrue(any('重新发布' in item['reason'] for item in result['skipped'] if item['key']==expired['key']))
        self.assertEqual(2,sum(name=='vcat_set_publish_priority' for name,args in PublishCat.calls))
    def test_republish_selected_attempt_key_maps_back_to_original_video_and_archives_old_task(self):
        from server.publishing.publisher import Publisher
        self.config();self.service.bind('task-a',fixtures.FakeCat.candidates[0],True);ctx=self.service.load('task-a');item=self.service.expanded(ctx)[0]
        attempt_key=item['key']+':attempt:previous';batch='V3-old-attempt'
        old={'key':attempt_key,'replaces_key':item['key'],'name':item['video']['name'],'status':'failed','remote_state':'failed','local_id':'old-task','batch_name':batch,'uid':'uid-a','payload':self.service.payload(ctx,item)}
        PublishCat.tasks.append({'uid':'uid-a','localId':'old-task','batchSource':batch+'_10-26 20:00:00','statusCode':4})
        self.service.write('publish_execution','task-a',{'items':[old],'previous_items':[],'state':'needs_help'})
        Publisher(self.service).run('task-a',{'mode':'running'},selected_keys=[attempt_key],new_attempt=True)
        state=self.service.publication('task-a')
        self.assertEqual(1,len(state['items']))
        self.assertEqual(old['local_id'],state['items'][0]['replaces_local_id'])
        self.assertEqual([attempt_key],[row['key'] for row in state['previous_items']])
        self.assertEqual(item['video']['name'],state['items'][0]['name'])
        self.assertNotEqual(old['batch_name'],state['items'][0]['batch_name'])
    def test_republish_without_selected_old_tasks_creates_new_batch_from_current_settings(self):
        from server.publishing.publisher import Publisher
        self.service.publish('task-a');self.wait()
        settings=self.service.load('task-a')['settings'];settings['groups'][0]['desc']='new settings';self.service.save('task-a',settings)
        Publisher(self.service).run('task-a',{'mode':'running'},new_attempt=True)
        state=self.service.publication('task-a')
        self.assertEqual(4,len(PublishCat.tasks))
        self.assertEqual(2,len(state['previous_items']))
        self.assertEqual(2,len(state['items']))
        self.assertTrue(all(item['status']=='success' for item in state['items']))
        self.assertEqual('new settings',PublishCat.tasks[2].get('desc'))

    def test_full_reset_cancels_active_task_before_new_batch(self):
        self.config();self.seed_task('waiting','waiting')
        with self.assertRaisesRegex(ValueError,'待发布或正在处理'):
            self.service.save('task-a',self.service.load('task-a')['settings'])
        plan=self.service.prepare_republish('task-a')
        self.assertEqual(['waiting'],[item['key'] for item in plan['cancelled']])
        self.service.confirm_republish('task-a')
        self.service.republish('task-a');self.wait()
        self.assertEqual(3,len(PublishCat.tasks))

    def test_full_reset_allows_successful_batch_after_manual_cleanup_confirmation(self):
        self.service.publish('task-a');self.wait();plan=self.service.prepare_republish('task-a')
        self.assertEqual(2,len(plan['success']));self.assertTrue(plan['ready'])
        self.service.confirm_republish('task-a');self.service.republish('task-a');self.wait()
        state=self.service.publication('task-a')
        self.assertEqual(2,len(state['items']));self.assertEqual(2,len(state['previous_items']))
        self.assertTrue(all(item['status']=='abandoned' for item in state['previous_items']))

    def test_full_reset_blocks_when_old_remote_task_cannot_be_canceled(self):
        self.config();self.seed_task('waiting','waiting');PublishCat.cancel_reject=True
        plan=self.service.prepare_republish('task-a')
        self.assertFalse(plan['ready']);self.assertEqual(1,len(plan['blocked']))
    def test_schedule_retry_auto_selects_failed_items_and_preserves_original_spacing(self):
        from server.publishing.publisher import Publisher
        self.config();first=self.seed_task('failed','failed',{'scheduleType':'timing','scheduleTime':'2026-10-29 07:00'});second=self.seed_task('paused','paused',{'scheduleType':'timing','scheduleTime':'2026-10-29 07:07'});self.seed_task('waiting','waiting',{'scheduleType':'timing','scheduleTime':'2026-10-29 07:14'});self.seed_task('publishing','publishing',{'scheduleType':'timing','scheduleTime':'2026-10-29 07:21'});self.seed_task('localTiming','localTiming',{'scheduleType':'timing','scheduleTime':'2026-10-29 07:28'});self.seed_task('success','success',{'scheduleType':'timing','scheduleTime':'2026-10-29 07:35'})
        from datetime import datetime,timedelta
        from server.publishing.service import SHANGHAI
        start=(datetime.now(SHANGHAI)+timedelta(minutes=20)).replace(second=0,microsecond=0)
        plan=Publisher(self.service).schedule_plan('task-a',start_time=start.strftime('%Y-%m-%d %H:%M'))
        self.assertEqual([first['key'],second['key']],plan['keys'])
        self.assertEqual([start.strftime('%Y-%m-%d %H:%M'),(start+timedelta(minutes=7)).strftime('%Y-%m-%d %H:%M')],[item['new_time'] for item in plan['items'] if item['key'] in plan['keys']])
        self.assertEqual('2026-10-29 07:00',plan['items'][0]['old_time'])
        self.assertEqual({'waiting','publishing','localTiming'}, {item['key'] for item in plan['items'] if item['status'] in ('submitted','publishing','localTiming') and not item['selected']})

    def test_schedule_retry_uses_new_time_when_saved_settings_are_already_expired(self):
        from datetime import datetime,timedelta
        from server.publishing.publisher import Publisher
        from server.publishing.service import SHANGHAI
        settings=self.config()['settings']
        stale=(datetime.now(SHANGHAI)-timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M')
        settings['schedule']={'schedule_type':'timing','start_time':stale,'interval':3}
        self.service.save('task-a',settings)
        ctx=self.service.load('task-a');item=self.service.expanded(ctx)[0]
        failed=self.seed_task('expired-attempt','failed',{'scheduleType':'timing','scheduleTime':stale})
        failed.update({'key':item['key'],'name':item['video']['name'],'group_id':item['group']['id'],'group_name':item['group']['name'],'copy':item['copy'],'payload':{'uid':'uid-a','videoPath':item['video']['path'],'desc':'旧简介','tags':[],'scheduleType':'timing','scheduleTime':stale,'platformOptions':{}}})
        state=self.service.publication('task-a');state['items']=[failed];self.service.write('publish_execution','task-a',state)
        start=(datetime.now(SHANGHAI)+timedelta(minutes=20)).replace(second=0,microsecond=0).strftime('%Y-%m-%d %H:%M')
        plan=Publisher(self.service).schedule_plan('task-a',start_time=start,interval=3)
        Publisher(self.service).run('task-a',{'mode':'running'},selected_keys=plan['keys'],new_attempt=True,reschedule=plan)
        self.assertEqual(1,sum(name=='vcat_create_publish_task' for name,args in PublishCat.calls))
        self.assertEqual(start,PublishCat.tasks[-1]['scheduleTime'])
        self.assertEqual('success',self.service.publication('task-a')['items'][0]['status'])

    def test_schedule_retry_maps_attempt_task_keys_back_to_base_video(self):
        from datetime import datetime,timedelta
        from server.publishing.publisher import Publisher
        from server.publishing.service import SHANGHAI
        self.config();ctx=self.service.load('task-a');item=self.service.expanded(ctx)[0]
        start=(datetime.now(SHANGHAI)+timedelta(minutes=20)).replace(second=0,microsecond=0).strftime('%Y-%m-%d %H:%M')
        old_key=item['key']+':attempt:old';old={'key':old_key,'replaces_key':item['key'],'name':item['video']['name'],'group_id':item['group']['id'],'group_name':item['group']['name'],'copy':item['copy'],'status':'failed','remote_state':'failed','local_id':'old-task','batch_name':'V3-old-attempt','uid':'uid-a','payload':{'uid':'uid-a','videoPath':item['video']['path'],'desc':'旧简介','tags':[],'scheduleType':'timing','scheduleTime':'2026-10-29 07:00','platformOptions':{}}}
        PublishCat.tasks.append({'uid':'uid-a','localId':'old-task','batchSource':'V3-old-attempt_10-26 20:00:00','statusCode':4})
        self.service.write('publish_execution','task-a',{'items':[old],'state':'needs_help'})
        plan=Publisher(self.service).schedule_plan('task-a',keys=[old_key],start_time=start,interval=3)
        Publisher(self.service).run('task-a',{'mode':'running'},selected_keys=[old_key],new_attempt=True,reschedule=plan)
        self.assertEqual(2,len(PublishCat.tasks))
        self.assertEqual(start,PublishCat.tasks[-1]['scheduleTime'])
