import base64
import copy
import json
import sqlite3
import tempfile
import time
from datetime import datetime,timezone,timedelta
import unittest
from contextlib import closing
from pathlib import Path
from server import v2_file_service as files
from server.publishing.matching import normalized_name,search_terms,rank_candidates
from server.publishing.service import PublishingService,initialize,RUNS,verify_draft
from server.publishing.vcat import VcatClient,DraftOutcomeUnknown


class FakeCat:
    candidates=[];calls=[];drafts={};next_id=1;outcome_unknown=False;gate=None
    def __init__(self,*args,**kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def accounts(self):return [{'uid':'uid-a','platform':'Channels','loginStatus':'登录有效'}]
    def worker(self,uid,method,params):
        self.calls.append((method,params))
        if method=='getDramaComponent':return {'list':copy.deepcopy(self.candidates),'totalCount':len(self.candidates),'baseResp':{'errcode':0}}
        return {'list':[{'name':'春熙路','poiCheckSum':'poi-a','fullAddress':'四川省成都市锦江区'}],'_searchQuery':params}
    def find_draft(self,title):
        return next(({'draftId':key} for key,value in self.drafts.items() if value.get('title')==title),None)
    def call(self,name,args):
        self.calls.append((name,copy.deepcopy(args)))
        if name=='vcat_create_draft':
            if self.gate:self.gate.wait(3)
            key=type(self).next_id;type(self).next_id+=1
            opts={**args['platformOptions'],'CAT_desc':args.get('desc',''),'topics':args.get('tags',[]),'CAT_timing':{'type':{'now':1,'timing':2,'localTiming':3}[args['scheduleType']]}}
            if args.get('cover'):opts['CAT_cover']=args['cover']
            if args.get('comment'):opts['CAT_comment']=args['comment']
            if args.get('scheduleTime'):
                when=datetime.strptime(args['scheduleTime'],'%Y-%m-%d %H:%M').replace(tzinfo=timezone(timedelta(hours=8)))
                opts['CAT_timing'].update(time=when.astimezone(timezone.utc).isoformat(),autoReset=False)
            self.drafts[key]={'title':args['draftTitle'],'accounts':[{'uid':args['uid']}],'content':{'videoPath':args['videoPath'],'title':args.get('title','')},'platformOptionsByUid':{args['uid']:opts}}
            if self.outcome_unknown:raise DraftOutcomeUnknown('uncertain')
            return {'draftId':key}
        if name=='vcat_list_drafts':return copy.deepcopy(self.drafts[args['draftId']])
        raise AssertionError('Forbidden fake call '+name)


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.db=self.root/'test.db'
        with closing(self.connect()) as c:
            c.executescript('''CREATE TABLE production_tasks(id TEXT,account_name TEXT,drama_name TEXT,planned_publish_at TEXT,release_status TEXT);
                CREATE TABLE accounts(id TEXT,nickname TEXT,channel_id TEXT,theater_id TEXT);
                CREATE TABLE theaters(id TEXT,name TEXT);
                CREATE TABLE dramas(id TEXT,current_name TEXT,theater_id TEXT);
                CREATE TABLE drama_aliases(drama_id TEXT,alias_name TEXT);
                CREATE TABLE drama_profiles(drama_id TEXT,cover_path TEXT,updated_at TEXT);
                INSERT INTO theaters VALUES('theater-a','剧场A');
                INSERT INTO accounts VALUES('account-a','账号A','uid-a','theater-a'),('account-b','账号B','uid-b','theater-a');
                INSERT INTO dramas VALUES('drama-a','《生恩如纸，养恩如山》','theater-a');
                INSERT INTO drama_aliases VALUES('drama-a','旧剧名');
                INSERT INTO production_tasks VALUES('task-a','账号A','旧剧名','','unregistered'),('task-b','账号B','旧剧名','','unregistered');''')
            initialize(c);c.commit()
        self.video=self.root/'剧名-1.mp4';self.video.write_bytes(b'fixture')
        self.sheep=self.root/'羊-剧名-2.mp4';self.sheep.write_bytes(b'fixture')
        self.rows=[{'id':'video-a','output_path':str(self.video),'sequence_no':1,'output_duration_seconds':2},
            {'id':'video-b','output_path':str(self.sheep),'sequence_no':2,'output_duration_seconds':3}]
        FakeCat.candidates=[{'id':'mount-a','name':'生恩如纸养恩如山','usable':True,'mediaCount':100}]
        FakeCat.calls=[];FakeCat.drafts={};FakeCat.next_id=1;FakeCat.outcome_unknown=False;FakeCat.gate=None
        self.service=PublishingService(self.connect,lambda task:{'videos':self.rows},FakeCat)
        RUNS.clear()
    def connect(self):
        c=sqlite3.connect(self.db,timeout=5);c.row_factory=sqlite3.Row;return c
    def tearDown(self):
        for run in list(RUNS.values()):run['mode']='stopped';run['thread'].join(5)
        self.temp.cleanup()
    def config(self):
        ctx=self.service.load('task-a');self.service.save('task-a',ctx['settings']);return ctx
    def wait(self):
        for _ in range(300):
            result=self.service.execution('task-a')
            if not result['running']:return result
            time.sleep(.01)
        self.fail('draft runner did not finish')
    def test_symbol_search_is_normalized_before_query(self):
        self.config();result=self.service.dramas('task-a')
        self.assertEqual('生恩如纸养恩如山',FakeCat.calls[0][1]['queryString'])
        self.assertEqual('auto',result['status'])
    def test_letters_digits_and_parenthetical_words_are_preserved(self):
        self.assertNotEqual(normalized_name('归来'),normalized_name('归来2'))
        self.assertNotEqual(normalized_name('归来（上）'),normalized_name('归来'))
        self.assertEqual(normalized_name('《归来，母亲》'),normalized_name('归来 母亲'))
    def test_different_words_require_manual_confirmation(self):
        FakeCat.candidates=[{'id':'x','name':'生恩如纸养恩如海','usable':True}]
        result=self.service.dramas('task-a');self.assertEqual('choose',result['status']);self.assertIsNone(result['binding'])
        with self.assertRaises(ValueError):self.service.bind('task-a',FakeCat.candidates[0],False)
    def test_duplicate_exact_candidates_do_not_auto_bind(self):
        rows,auto=rank_candidates([{'id':'a','name':'归来','usable':True},{'id':'b','name':'《归来》','usable':False}],['归来'])
        self.assertIsNone(auto);self.assertEqual(2,len(rows))
    def test_ranked_suggestions_never_treat_similarity_as_confirmation(self):
        rows,auto=rank_candidates([{'id':'far','name':'打工人','usable':True},{'id':'near','name':'归来的妈妈','usable':True}],['归来的母亲'])
        self.assertEqual('near',rows[0]['id']);self.assertIsNone(auto)
    def test_binding_is_shared_but_account_override_does_not_leak(self):
        original=self.service.bind('task-a',FakeCat.candidates[0],True)
        self.assertEqual(original,self.service.load('task-b')['binding'])
        override=self.service.bind('task-b',{'id':'other','name':'另一个挂载','usable':True},True,True)
        self.assertEqual(override,self.service.load('task-b')['binding'])
        self.assertEqual(original,self.service.load('task-a')['binding'])
    def test_confirmed_id_not_silently_replaced_by_same_name(self):
        self.service.bind('task-a',FakeCat.candidates[0],True)
        FakeCat.candidates=[{**FakeCat.candidates[0],'id':'different'}]
        result=self.service.dramas('task-a');self.assertEqual('unavailable',result['status'])
        self.assertEqual('mount-a',self.service.load('task-a')['binding']['drama']['id'])
    def test_manual_search_does_not_replace_an_existing_binding(self):
        self.service.bind('task-a',{'id':'old','name':'原来已经确认的剧集','usable':True},True)
        result=self.service.dramas('task-a','生恩如纸')
        self.assertEqual('choose',result['status'])
        self.assertEqual('old',self.service.load('task-a')['binding']['drama']['id'])
    def test_switching_from_account_override_to_shared_replaces_current_choice(self):
        self.service.bind('task-a',{'id':'special','name':'账号专用','usable':True},True,True)
        self.service.bind('task-a',FakeCat.candidates[0],True,False)
        self.assertEqual('mount-a',self.service.load('task-a')['binding']['drama']['id'])
    def test_names_can_change_after_identity_is_saved(self):
        self.config()
        with closing(self.connect()) as c:c.execute("UPDATE dramas SET current_name='新剧名'");c.execute('DELETE FROM drama_aliases');c.execute("UPDATE accounts SET nickname='新账号名'");c.commit()
        ctx=self.service.load('task-a');self.assertEqual('drama-a',ctx['drama']['id']);self.assertEqual('account-a',ctx['account']['id'])
    def test_addresses_are_complete_and_per_account(self):
        address=self.service.addresses('task-a','成都春熙路')['items'][0]
        self.service.save_address('task-a',address,True)
        self.assertEqual(address,self.service.load('task-a')['settings']['groups'][0]['location'])
        self.assertEqual([],self.service.load('task-b')['addresses'])
        self.assertIsNone(self.service.load('task-b')['settings']['groups'][0]['location'])
    def test_public_address_reuse_keeps_account_defaults_separate(self):
        address=self.service.addresses('task-a','成都')['items'][0]
        other={**address,'poiCheckSum':'poi-b','name':'第二个地点'}
        self.service.save_address('task-a',address,True);self.service.save_address('task-b',other,True)
        self.assertEqual(address,self.service.load('task-a')['default_address'])
        self.assertEqual(other,self.service.load('task-b')['default_address'])
        self.assertEqual({address['poiCheckSum'],other['poiCheckSum']},{a['poiCheckSum'] for a in self.service.load('task-b')['public_addresses']})
        calls=len(FakeCat.calls)
        self.service.save_address('task-b',address)
        self.assertEqual(calls,len(FakeCat.calls));self.assertEqual(other,self.service.load('task-b')['default_address'])
        self.assertEqual(address,self.service.load('task-b')['addresses'][0])
        self.service.save_address('task-b',address)
        self.assertEqual(2,len(self.service.load('task-b')['public_addresses']))
    def test_public_delete_never_changes_defaults_or_saved_groups(self):
        address=self.service.addresses('task-a','成都')['items'][0]
        self.service.save_address('task-a',address,True);self.service.save_address('task-b',address,True);self.config()
        self.service.delete_address('task-b',address['poiCheckSum'],'public')
        for task in ('task-a','task-b'):
            ctx=self.service.load(task);self.assertEqual([],ctx['public_addresses']);self.assertEqual(address,ctx['default_address']);self.assertEqual(address,ctx['settings']['groups'][0]['location'])
        self.assertEqual([address],self.service.load('task-a')['addresses'])
        self.assertEqual([],self.service.load('task-a')['public_addresses'])
    def test_existing_confirmed_addresses_seed_public_book_without_get_writes(self):
        address={'poiCheckSum':'legacy','name':'已有地址','_searchQuery':{'query':'已有地址'}}
        self.service.write('addresses','uid-a',[address]);self.service.write('address_default','uid-b',address)
        self.assertEqual([address],self.service.load('task-b')['public_addresses'])
        self.assertIsNone(self.service.read('public_addresses','shared'))
        self.service.delete_address('task-a','legacy','public')
        self.assertEqual([],self.service.load('task-b')['public_addresses'])
    def test_private_history_delete_does_not_remove_shared_entry(self):
        address=self.service.addresses('task-a','成都')['items'][0];self.service.save_address('task-a',address,True)
        self.service.delete_address('task-a',address['poiCheckSum'])
        self.assertEqual([address],self.service.load('task-b')['public_addresses'])
        with self.assertRaises(ValueError):self.service.delete_address('task-a','x','invalid')
        with self.assertRaises(ValueError):self.service.save_address('task-a',None)
    def test_address_city_prefix_has_a_place_name_fallback(self):
        from unittest.mock import patch
        queries=[]
        def lookup(client,uid,method,params):
            queries.append(params['query'])
            return {'address':{'city':'成都市'},'list':[{'name':'春熙路' if params['query']=='春熙路' else '周边商家','poiCheckSum':params['query']}],'_searchQuery':params}
        with patch.object(FakeCat,'worker',lookup):result=self.service.addresses('task-a','成都春熙路')
        self.assertEqual(['成都春熙路','春熙路'],queries);self.assertEqual('春熙路',result['items'][0]['name'])
    def test_verifier_rejects_unrequested_location_or_mount(self):
        self.config();self.service.start('task-a');result=self.wait()
        record=result['items'][0];payload=copy.deepcopy(record['payload'])
        payload['platformOptions'].pop('CAT_extReading')
        self.assertFalse(verify_draft(FakeCat.drafts[record['draft_id']],payload)['CAT_extReading'])
    def test_address_delete_does_not_mutate_saved_group(self):
        a=self.service.addresses('task-a','成都')['items'][0];self.service.save_address('task-a',a,True);self.config()
        self.service.delete_address('task-a',a['poiCheckSum']);self.assertEqual(a,self.service.load('task-a')['settings']['groups'][0]['location'])
    def test_no_cover_is_valid_and_sheep_defaults_to_corresponding(self):
        ctx=self.config();self.assertEqual('auto',ctx['settings']['groups'][1]['cover_mode'])
        self.service.dramas('task-a');ctx=self.service.load('task-a')
        payload=self.service.payload(ctx,self.service.expanded(ctx)[0]);self.assertNotIn('cover',payload)
    def test_copy_order_and_time_offsets(self):
        ctx=self.config();g=ctx['settings']['groups'][0];g.update(video_ids=['video-a','video-b'],copies=2,schedule_type='timing',start_time='2030-01-01 12:00',interval=7)
        ctx['settings']['groups']=[g];rows=self.service.expanded(ctx)
        ctx['settings']['schedule']={'schedule_type':'timing','start_time':'2030-01-01 12:00','interval':7};rows=self.service.expanded(ctx)
        self.assertEqual(['video-a','video-b','video-a','video-b'],[r['video']['id'] for r in rows])
        self.assertEqual('2030-01-01 12:21',rows[-1]['time'])
        g['order']='consecutive';self.assertEqual(['video-a','video-a','video-b','video-b'],[r['video']['id'] for r in self.service.expanded(ctx)])
    def test_invalid_files_pause_only_affected_group(self):
        self.config();self.video.unlink();self.service.start('task-a');result=self.wait()
        self.assertEqual(['needs_help','ready'],[r['status'] for r in result['items']])
        with closing(self.connect()) as c:self.assertEqual('unregistered',c.execute("SELECT release_status FROM production_tasks WHERE id='task-a'").fetchone()[0])
    def test_retries_verify_existing_drafts_without_duplicates(self):
        self.config();self.service.start('task-a');result=self.wait();self.assertTrue(all(i['status']=='ready' for i in result['items']))
        self.service.start('task-a');self.wait();self.assertEqual(2,len(FakeCat.drafts))
    def test_start_without_prior_save_still_has_stable_retry_identity(self):
        self.service.start('task-a');self.wait()
        self.service.start('task-a');self.wait()
        self.assertEqual(2,len(FakeCat.drafts))
    def test_unknown_creation_is_reconciled_without_recreation(self):
        self.config();FakeCat.outcome_unknown=True;self.service.start('task-a');result=self.wait()
        self.assertTrue(all(i['status']=='uncertain' for i in result['items']))
        FakeCat.outcome_unknown=False;self.service.start('task-a');result=self.wait();self.assertEqual(2,len(FakeCat.drafts));self.assertTrue(all(i['status']=='ready' for i in result['items']))
    def test_edited_config_keeps_old_draft_for_manual_handling(self):
        self.config();self.service.start('task-a');self.wait();ctx=self.service.load('task-a');ctx['settings']['groups'][0]['desc']='changed'
        self.service.save('task-a',ctx['settings']);self.service.start('task-a');result=self.wait()
        self.assertEqual('needs_help',result['items'][0]['status']);self.assertEqual(2,len(FakeCat.drafts))
    def test_current_draft_edits_can_be_read_back(self):
        self.config();self.service.start('task-a');result=self.wait();key=result['items'][0]['draft_id']
        FakeCat.drafts[key]['platformOptionsByUid']['uid-a']['CAT_desc']='manual change'
        self.service.start('task-a');result=self.wait();self.assertEqual('needs_help',result['items'][0]['status'])
    def test_manual_changes_are_adopted_per_item_after_confirmation(self):
        self.config();self.service.start('task-a');result=self.wait();item=result['items'][0];key=item['draft_id']
        FakeCat.drafts[key]['platformOptionsByUid']['uid-a']['CAT_desc']='人工辅助后的简介'
        preview=self.service.draft_assist('task-a',item['key'],'adopt-draft',False)
        self.assertFalse(preview['accepted']);self.assertNotIn('accepted_payload',self.service.execution('task-a')['items'][0])
        self.service.draft_assist('task-a',item['key'],'adopt-draft',True)
        self.service.start('task-a');result=self.wait()
        self.assertTrue(all(i['status']=='ready' for i in result['items']));self.assertEqual(2,len(FakeCat.drafts))
        self.assertEqual('',self.service.load('task-a')['settings']['groups'][0]['desc'])
    def test_manual_assistance_cannot_accept_wrong_account_or_video(self):
        self.config();self.service.start('task-a');result=self.wait();item=result['items'][0]
        FakeCat.drafts[item['draft_id']]['accounts']=[{'uid':'wrong'}]
        with self.assertRaisesRegex(ValueError,'账号发生变化'):self.service.draft_assist('task-a',item['key'],'adopt-draft',True)
    def test_actual_publication_is_rejected_by_client(self):
        client=object.__new__(VcatClient);client.writable=True
        for name in ('vcat_publish_draft','vcat_create_publish_task','vcat_post_publish'):
            with self.assertRaisesRegex(ValueError,'禁止发布'):client.call(name,{})
    def test_same_video_cannot_be_in_multiple_groups(self):
        ctx=self.config();ctx['settings']['assignment_mode']='manual';ctx['settings']['groups'][1]['video_ids']=['video-a']
        with self.assertRaisesRegex(ValueError,'一个分组'):self.service.save('task-a',ctx['settings'])
    def test_auto_assignment_corrects_stale_selection_and_finds_new_videos(self):
        ctx=self.config();ctx['settings']['groups'][0]['video_ids']=[]
        ctx['settings']['groups'][1]['video_ids']=['video-a','video-b']
        result=self.service.save('task-a',ctx['settings'])
        self.assertEqual([['video-a'],['video-b']],[g['video_ids'] for g in result['settings']['groups']])
        extra=self.root/'剧名-3.mp4';extra.write_bytes(b'new video')
        self.rows.append({'id':'video-new','output_path':str(extra),'sequence_no':3})
        result=self.service.load('task-a');self.assertEqual(['video-a','video-new'],result['settings']['groups'][0]['video_ids'])
    def test_manual_assignment_is_preserved_until_auto_is_restored(self):
        ctx=self.config();ctx['settings']['assignment_mode']='manual'
        ctx['settings']['groups'][0]['video_ids']=['video-b'];ctx['settings']['groups'][1]['video_ids']=['video-a']
        result=self.service.save('task-a',ctx['settings'])
        self.assertEqual(['video-b'],result['settings']['groups'][0]['video_ids'])
        result['settings']['assignment_mode']='auto';result=self.service.save('task-a',result['settings'])
        self.assertEqual(['video-a'],result['settings']['groups'][0]['video_ids'])
    def test_whole_batch_schedule_automatically_connects_groups(self):
        start=(datetime.now(timezone(timedelta(hours=8)))+timedelta(days=1)).replace(hour=12,minute=0,second=0,microsecond=0)
        ctx=self.config();ctx['settings']['schedule']={'schedule_type':'timing','start_time':start.strftime('%Y-%m-%d %H:%M'),'interval':7}
        ctx['settings']['groups'][0]['copies']=2
        result=self.service.save('task-a',ctx['settings']);rows=self.service.expanded(result)
        self.assertEqual([(start+timedelta(minutes=n)).strftime('%Y-%m-%d %H:%M') for n in (0,7,14)],[r['time'] for r in rows])
        self.assertEqual((start+timedelta(minutes=14)).strftime('%Y-%m-%d %H:%M'),result['settings']['groups'][1]['start_time'])
        self.service.start('task-a');execution=self.wait()
        self.assertTrue(all(i['status']=='ready' for i in execution['items']),execution)

    def test_later_item_uses_its_own_future_time_when_group_start_has_passed(self):
        from datetime import datetime,timedelta
        from server.publishing.service import SHANGHAI
        settings=self.config()['settings'];settings['groups'][0]['copies']=3
        start=(datetime.now(SHANGHAI)-timedelta(minutes=10)).replace(second=0,microsecond=0).strftime('%Y-%m-%d %H:%M')
        settings['schedule']={'schedule_type':'timing','start_time':start,'interval':10}
        result=self.service.save('task-a',settings);self.service.dramas('task-a');ctx=self.service.load('task-a')
        later=next(row for row in self.service.expanded(ctx) if row['time']>(datetime.now(SHANGHAI)+timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M'))
        payload=self.service.payload(ctx,later)
        self.assertEqual(later['time'],payload['scheduleTime'])
    def test_reversing_groups_and_crossing_midnight_keeps_one_timeline(self):
        ctx=self.config();ctx['settings'].update(group_order='sheep_first',schedule={'schedule_type':'localTiming','start_time':'2030-01-01 23:58','interval':7})
        result=self.service.save('task-a',ctx['settings']);rows=self.service.expanded(result)
        self.assertTrue(rows[0]['video']['sheep']);self.assertEqual('2030-01-02 00:05',rows[1]['time'])
    def test_cover_is_always_auto_selected_and_absence_is_valid(self):
        self.config();self.service.dramas('task-a');ctx=self.service.load('task-a')
        ctx['cover']={'exists':True,'path':'normal.png'};ctx['sheep_cover']={'exists':True,'path':'sheep.png'}
        rows=self.service.expanded(ctx)
        self.assertEqual(['normal.png','sheep.png'],[self.service.payload(ctx,r)['cover'] for r in rows])
        ctx['sheep_cover']={'exists':False,'path':''}
        self.assertNotIn('cover',self.service.payload(ctx,rows[1]))
    def test_no_cover_setting_is_preserved_after_save(self):
        ctx=self.config();ctx['settings']['groups'][0]['cover_mode']='none'
        result=self.service.save('task-a',ctx['settings'])
        self.assertEqual('none',result['settings']['groups'][0]['cover_mode'])
    def test_legacy_default_group_recovers_auto_ownership_and_preserves_parameters(self):
        ctx=self.config();g=ctx['settings']['groups'][0]
        g.update(name='分组 1',kind='custom',copies=3,desc='保留文案')
        ctx['settings'].update(groups=[g],assignment_mode='manual')
        result=self.service.save('task-a',ctx['settings'])
        self.assertEqual('auto',result['settings']['assignment_mode'])
        self.assertEqual(['normal','sheep'],[g['kind'] for g in result['settings']['groups']])
        self.assertEqual([['video-a'],['video-b']],[g['video_ids'] for g in result['settings']['groups']])
        self.assertEqual([3,3],[g['copies'] for g in result['settings']['groups']])
        self.assertTrue(all(g['desc']=='保留文案' for g in result['settings']['groups']))
    def test_explicit_manual_default_group_is_not_reclassified(self):
        ctx=self.config();g=ctx['settings']['groups'][0];g.update(name='分组 1',kind='custom')
        ctx['settings'].update(groups=[g],assignment_mode='manual',assignment_confirmed=True)
        result=self.service.save('task-a',ctx['settings'])
        self.assertEqual('manual',result['settings']['assignment_mode']);self.assertEqual(1,len(result['settings']['groups']))
    def test_source_sheep_marker_survives_unmarked_output_name(self):
        self.rows[1].update(output_path=str(self.video),name='羊-剧名-2.mp4')
        self.assertTrue(self.service.load('task-a')['videos'][1]['sheep'])
        self.rows[1].update(name='羊')
        self.assertTrue(self.service.load('task-a')['videos'][1]['sheep'])
    def test_shooting_declaration_has_real_region_codes_and_timestamp(self):
        from server.publishing.declarations import REGIONS
        ctx=self.config();self.service.dramas('task-a');ctx=self.service.load('task-a')
        group=ctx['settings']['groups'][0];country=next(r for r in REGIONS if r['name']=='中国');province=next(r for r in country['sub'] if r['name']=='四川');city=next(r for r in province['sub'] if r['name']=='成都')
        codes=[country['code'],province['code'],city['code']]
        group.update(tag_type=5,shoot_date='2026-01-01',shoot_region_codes=codes)
        tag=self.service.payload(ctx,self.service.expanded(ctx)[0])['platformOptions']['tagInfo']
        self.assertEqual(5,tag['tagType']);self.assertEqual(codes,list(tag['shootInfo'][k] for k in ['countryCode','provinceCode','cityCode']))
        self.assertEqual(str(int(datetime(2026,1,1,tzinfo=timezone(timedelta(hours=8))).timestamp())),tag['shootInfo']['postTimestamp'])
    def test_declaration_incomplete_can_save_but_cannot_create(self):
        ctx=self.config();group=ctx['settings']['groups'][0]
        for kind in (5,7):
            group.update(tag_type=kind);self.service.validate_group(group,strict=False)
            with self.assertRaises(ValueError):self.service.validate_group(group)
        group.update(tag_type=7,repost_source='来源'*251)
        with self.assertRaisesRegex(ValueError,'500'):self.service.validate_group(group,strict=False)
        group.update(tag_type=5,shoot_date='2099-01-01',shoot_region_codes=[999999])
        with self.assertRaises(ValueError):self.service.validate_group(group,strict=False)
    def test_repost_declaration_is_preserved_in_draft_and_readback(self):
        ctx=self.config();ctx['settings']['groups'][0].update(tag_type=7,repost_source=' 测试来源 ')
        self.service.save('task-a',ctx['settings']);self.service.start('task-a');result=self.wait()
        first=result['items'][0];self.assertEqual('ready',first['status'])
        self.assertEqual({'tagType':7,'repostSource':'测试来源'},first['payload']['platformOptions']['tagInfo'])
        self.assertTrue(first['checks']['tagInfo'])
    def test_short_title_symbols_match_native_rules(self):
        ctx=self.config();g=ctx['settings']['groups'][0]
        g['short_title']='测试短标题，逗号'
        with self.assertRaisesRegex(ValueError,'特殊字符'):self.service.validate_group(g,strict=False)
        g['short_title']='测试短标题：精彩';self.service.validate_group(g,strict=False)
    def test_last_scheduled_copy_cannot_exceed_platform_range(self):
        ctx=self.config();self.service.dramas('task-a');ctx=self.service.load('task-a')
        start=(datetime.now(timezone(timedelta(hours=8)))+timedelta(days=29)).replace(hour=15,minute=0)
        ctx['settings']['schedule']={'schedule_type':'timing','start_time':start.strftime('%Y-%m-%d %H:%M'),'interval':1440}
        ctx['settings']['groups'][0]['copies']=3
        rows=self.service.expanded(ctx)
        self.service.payload(ctx,rows[0])
        with self.assertRaisesRegex(ValueError,'30天'):self.service.payload(ctx,rows[2])
    def test_video_title_and_short_title_have_independent_payloads_and_history(self):
        ctx=self.config();g=ctx['settings']['groups'][0]
        g.update(video_title='这是一个超过十六字的视频标题，保留逗号和其他符号！',short_title='这是独立短标题',desc='这是独立简介')
        self.service.save('task-a',ctx['settings']);self.service.start('task-a');result=self.wait()
        item=result['items'][0];self.assertEqual('ready',item['status'])
        self.assertEqual(g['video_title'],item['payload']['title']);self.assertEqual(g['short_title'],item['payload']['platformOptions']['CAT_shortTitle'])
        self.assertEqual('这是独立简介',item['payload']['desc']);self.assertTrue(item['checks']['video_title'])
        history=self.service.load('task-a')['history'];self.assertIn(g['video_title'],history['video_title']);self.assertIn(g['short_title'],history['short_title'])
        self.assertNotIn(g['video_title'],history['short_title'])
    def test_legacy_title_content_stays_in_short_title(self):
        ctx=self.config();g=ctx['settings']['groups'][0];g.pop('short_title',None);g.pop('video_title',None);g['title']='原来填写的短标题'
        self.service.write('settings','task-a',ctx['settings']);self.service.write('history','title',['旧短标题记录'])
        result=self.service.load('task-a')
        self.assertEqual('原来填写的短标题',result['settings']['groups'][0]['short_title']);self.assertEqual('',result['settings']['groups'][0]['video_title'])
        self.assertEqual(['旧短标题记录'],result['history']['short_title']);self.assertEqual([],result['history']['video_title'])
    def test_title_only_falls_back_to_channels_description_never_short_title(self):
        self.config();self.service.dramas('task-a');ctx=self.service.load('task-a');g=ctx['settings']['groups'][0]
        g.update(video_title='独立视频标题',short_title='',desc='')
        payload=self.service.payload(ctx,self.service.expanded(ctx)[0])
        self.assertEqual('独立视频标题',payload['desc']);self.assertEqual('',payload['platformOptions']['CAT_shortTitle'])
    def test_planned_calendar_day_never_overrides_actual_publish_clock(self):
        self.config();self.service.dramas('task-a')
        with closing(self.connect()) as conn:conn.execute("UPDATE production_tasks SET planned_publish_at='2026-10-26' WHERE id='task-a'");conn.commit()
        ctx=self.service.load('task-a')
        self.assertEqual('now',ctx['settings']['schedule']['schedule_type'])
        when=(datetime.now(timezone(timedelta(hours=8)))+timedelta(days=1)).replace(hour=19,minute=37).strftime('%Y-%m-%d %H:%M')
        ctx['settings']['schedule']={'schedule_type':'timing','start_time':when,'interval':7}
        ctx=self.service.save('task-a',ctx['settings']);payload=self.service.payload(ctx,self.service.expanded(ctx)[0])
        self.assertEqual(when,payload['scheduleTime']);self.assertTrue(payload['scheduleTime'].endswith('19:37'))
    def test_confirmation_is_not_a_rename(self):
        self.service.bind('task-a',{'id':'x','name':'完全不同的挂载名','usable':True},True)
        self.assertEqual('《生恩如纸，养恩如山》',self.service.context('task-a')['drama']['name'])
    def test_history_persists_and_deletes_independently(self):
        ctx=self.config();ctx['settings']['groups'][0]['desc']='测试文案';self.service.save('task-a',ctx['settings'])
        self.assertEqual(['测试文案'],self.service.load('task-b')['history']['desc'])
        self.service.write('history','desc',[]);self.assertEqual('测试文案',self.service.load('task-a')['settings']['groups'][0]['desc'])


class CoverPersistenceTests(unittest.TestCase):
    def test_first_cover_creates_profile_and_replacement_preserves_metadata(self):
        original=(files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH)
        with tempfile.TemporaryDirectory() as temp:
            files.WORKSPACE=Path(temp)/'workspace';files.DATA_ROOT=Path(temp)/'data';files.DATABASE_INITIALIZED_PATH=None
            try:
                theater=files.create_theater({'name':'封面测试剧场'})
                drama=files.create_drama({'current_name':'封面测试剧集','theater_id':theater['id']})
                saved=files.upload_drama_cover(drama['id'],{'filename':'cover.png','content_base64':'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=='})
                self.assertTrue(Path(saved['file_path']).is_file())
                with closing(files.connection()) as c:
                    before=dict(c.execute('SELECT * FROM drama_profiles WHERE drama_id=?',(drama['id'],)).fetchone())
                files.upload_drama_cover(drama['id'],{'filename':'new.png','content_base64':'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGNkYPjPwMDAxMDAwMDAAAALHwEDmIWXfgAAAABJRU5ErkJggg=='})
                with closing(files.connection()) as c:after=dict(c.execute('SELECT * FROM drama_profiles WHERE drama_id=?',(drama['id'],)).fetchone())
                self.assertEqual(before['id'],after['id']);self.assertEqual(before['master_path'],after['master_path'])
            finally:files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH=original

if __name__=='__main__':unittest.main()
