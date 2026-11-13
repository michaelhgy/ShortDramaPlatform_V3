import base64
import copy
import io
import unittest
from PIL import Image
from server.tests import test_publishing as fixtures
from server.publishing.service import PublishingService
from server.publishing.profiles import PublishProfiles,base_config

class PublishingCoverTests(unittest.TestCase):
    setUp=fixtures.PublishingTests.setUp
    tearDown=fixtures.PublishingTests.tearDown
    connect=fixtures.PublishingTests.connect

    def image(self,color='red'):
        output=io.BytesIO();Image.new('RGB',(320,480),color).save(output,'PNG')
        return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()

    def upload(self,color='red'):
        return self.service.import_cover('task-a',{'data_url':self.image(color)})

    def test_disable_survives_save_reopen_and_actual_payload(self):
        ctx=self.service.load('task-a')
        for group in ctx['settings']['groups']:group.update(cover_mode='none',mount_required=False)
        self.service.save('task-a',ctx['settings'])
        fresh=PublishingService(self.connect,lambda task:{'videos':self.rows},fixtures.FakeCat)
        result=fresh.load('task-a')
        self.assertEqual(['none','none'],[g['cover_mode'] for g in result['settings']['groups']])
        result['cover']={'exists':True,'path':'must-not-use.jpg'}
        result['sheep_cover']=result['cover']
        for item in fresh.expanded(result):self.assertNotIn('cover',fresh.payload(result,item))

    def test_custom_image_is_durable_shared_and_both_payloads_use_owned_copy(self):
        image=self.upload();self.assertEqual(image,self.upload())
        ctx=self.service.load('task-a')
        for g in ctx['settings']['groups']:g.update(cover_mode='custom',cover_source='custom',custom_cover_id=image['id'],mount_required=False)
        self.service.save('task-a',ctx['settings'])
        fresh=PublishingService(self.connect,lambda task:{'videos':self.rows},fixtures.FakeCat)
        expected=fresh.covers().path(image['id'])
        with Image.open(expected) as saved:self.assertEqual('JPEG',saved.format)
        self.assertNotIn(expected,self.root.glob('*.png'))
        for item in fresh.expanded(fresh.load('task-a')):self.assertEqual(str(expected),fresh.payload(fresh.load('task-a'),item)['cover'])
        other=self.upload('blue');self.assertNotEqual(image['id'],other['id']);self.assertTrue(expected.is_file())

    def test_missing_custom_fails_without_falling_back_but_disabled_can_save(self):
        image=self.upload();ctx=self.service.load('task-a');g=ctx['settings']['groups'][0]
        g.update(cover_mode='custom',cover_source='custom',custom_cover_id=image['id'],mount_required=False)
        self.service.save('task-a',ctx['settings']);self.service.covers().path(image['id']).unlink()
        loaded=self.service.load('task-a');item=self.service.expanded(loaded)[0]
        with self.assertRaisesRegex(ValueError,'缺失'):self.service.payload(loaded,item)
        g['cover_mode']='none';saved=self.service.save('task-a',ctx['settings'])
        self.assertEqual(image['id'],saved['settings']['groups'][0]['custom_cover_id'])

    def test_profile_cover_scope_default_capture_and_independent_sheep(self):
        image=self.upload();config=base_config();config['schedule']['schedule_type']='now'
        config['groups']['normal'].update(cover_mode='none',mount_required=False)
        config['groups']['sheep'].update(cover_mode='custom',cover_source='custom',custom_cover_id=image['id'])
        profile=self.service.profile_save('task-a',{'name':'封面配置','config':config,'software_default':True})['profile']
        ctx=self.service.load('task-b');normal,sheep=ctx['settings']['groups']
        self.assertEqual('none',normal['cover_mode']);self.assertEqual('custom',sheep['cover_mode'])
        self.assertEqual(image['id'],sheep['custom_cover_id'])
        capture=self.service.profile_capture('task-b',{'settings':ctx['settings']})['config']
        self.assertEqual(config['groups']['sheep']['custom_cover_id'],capture['groups']['sheep']['custom_cover_id'])
        self.service.save('task-b',ctx['settings'])
        self.assertFalse(self.service.load('task-b')['profile_state']['modified'])
        settings=copy.deepcopy(ctx['settings']);settings['groups'][0]['cover_mode']='auto'
        excluded=PublishProfiles(self.service).apply(settings,profile,ctx,['copies'])['settings']
        self.assertEqual('auto',excluded['groups'][0]['cover_mode'])
        applied=PublishProfiles(self.service).apply(settings,profile,ctx,['cover'])['settings']
        self.assertEqual('none',applied['groups'][0]['cover_mode'])
        self.assertEqual(image['id'],applied['groups'][1]['custom_cover_id'])

    def test_legacy_profile_defaults_without_rewriting_document(self):
        config=base_config()
        for g in config['groups'].values():
            for key in ('cover_mode','cover_source','custom_cover_id'):g.pop(key)
        book={'items':[{'id':'old','name':'旧配置','revision':1,'config':config}],'software_default_id':None,'account_defaults':{}}
        self.service.write('publish_profiles','library',book)
        loaded=self.service.profile_library('task-a')
        self.assertEqual('auto',loaded['items'][0]['config']['groups']['normal']['cover_mode'])
        self.assertEqual(book,self.service.read('publish_profiles','library'))

    def test_invalid_import_and_path_traversal_are_rejected(self):
        for data in ('bad','data:image/png;base64,!!!!','data:image/png;base64,YWJj','data:image/svg+xml;base64,YWJj'):
            with self.subTest(data=data),self.assertRaises(ValueError):self.service.import_cover('task-a',{'data_url':data})
        for value in ('../x','a'*63,3):
            with self.assertRaises(ValueError):self.service.covers().path(value)

    def test_profile_image_replacement_and_deletion_preserve_saved_task(self):
        first=self.upload();second=self.upload('blue');config=base_config();config['schedule']['schedule_type']='now'
        config['groups']['normal'].update(cover_mode='custom',cover_source='custom',custom_cover_id=first['id'],mount_required=False)
        profile=self.service.profile_save('task-a',{'name':'共享图片','config':config,'software_default':True})['profile']
        ctx=self.service.load('task-a');self.service.save('task-a',ctx['settings'])
        config['groups']['normal']['custom_cover_id']=second['id']
        updated=self.service.profile_save('task-a',{**profile,'config':config})['profile']
        old=self.service.load('task-a');self.assertEqual(first['id'],old['settings']['groups'][0]['custom_cover_id'])
        self.assertEqual(second['id'],self.service.load('task-b')['settings']['groups'][0]['custom_cover_id'])
        self.service.profile_delete('task-a',{'id':updated['id'],'revision':updated['revision']})
        old=self.service.load('task-a');self.assertTrue(old['profile_state']['deleted'])
        item=self.service.expanded(old)[0];self.assertEqual(str(self.service.covers().path(first['id'])),self.service.payload(old,item)['cover'])
        self.assertTrue(self.service.covers().path(second['id']).is_file())

    def test_later_sheep_group_restores_own_profile_cover(self):
        image=self.upload();config=base_config();config['groups']['normal']['cover_mode']='none'
        config['groups']['sheep'].update(cover_mode='custom',cover_source='custom',custom_cover_id=image['id'])
        self.service.profile_save('task-a',{'name':'后出羊视频','config':config,'software_default':True})
        self.rows.pop();ctx=self.service.load('task-a');self.service.save('task-a',ctx['settings'])
        self.rows.append({'id':'video-b','output_path':str(self.sheep),'sequence_no':2})
        ctx=self.service.load('task-a');sheep=next(g for g in ctx['settings']['groups'] if g['kind']=='sheep')
        self.assertEqual('custom',sheep['cover_mode']);self.assertEqual(image['id'],sheep['custom_cover_id'])
