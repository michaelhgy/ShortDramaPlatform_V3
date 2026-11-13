import unittest
from server.tests import test_publishing_publish as fixtures
from server.publishing.progress import project
from server.publishing.progress import card_summary,progress_index
PublishCat=fixtures.PublishCat


class PublishingProgressTests(unittest.TestCase):
    setUp=fixtures.PublishingPublishTests.setUp
    tearDown=fixtures.PublishingPublishTests.tearDown
    connect=fixtures.PublishingPublishTests.connect
    wait=fixtures.PublishingPublishTests.wait

    def test_no_execution_does_not_contact_small_cat_or_show_configured_location(self):
        PublishCat.calls=[]
        result=self.service.progress('task-a')
        self.assertFalse(result['publication']['items']);self.assertFalse(result['drafts']['items']);self.assertFalse(result['needs_poll'])
        self.assertFalse(PublishCat.calls)

    def test_refresh_paused_tasks_is_read_only_and_preserves_submitted_snapshot(self):
        self.service.publish('task-a');self.wait()
        before=len(PublishCat.tasks)
        for row in PublishCat.tasks:row['statusCode']='3'
        PublishCat.calls=[]
        result=self.service.progress('task-a')
        self.assertTrue(all(r['status']=='paused' and r['submitted'] for r in result['publication']['items']))
        self.assertFalse(result['needs_poll']);self.assertEqual(before,len(PublishCat.tasks))
        self.assertFalse(any(n in ('vcat_create_publish_task','vcat_create_draft') for n,p in PublishCat.calls))

    def test_projection_uses_original_video_identity_and_accepted_payload_not_current_settings(self):
        state={'items':[{'key':'group:stable-video:0','name':'renamed.mp4','copy':1,'status':'ready','draft_id':12,
            'payload':{'videoPath':'private path','platformOptions':{'CAT_location':{'name':'old'}}},
            'accepted_payload':{'scheduleType':'timing','platformOptions':{'CAT_location':{'name':'manually confirmed','fullAddress':'full'},
                'CAT_extReading':{'type':8,'drama':{'id':'exact','name':'confirmed drama'}}}}}]}
        item=project(state,'draft')['items'][0]
        self.assertEqual('stable-video',item['video_id']);self.assertTrue(item['submitted'])
        self.assertEqual('manually confirmed',item['location']['name']);self.assertEqual('channels_drama',item['mount']['source'])
        self.assertNotIn('payload',item);self.assertNotIn('videoPath',item);self.assertEqual('confirmed drama',item['mount']['name'])

    def test_preflight_record_is_not_a_confirmed_submission(self):
        item=project({'items':[{'key':'g:v:0','status':'pending','payload':{'platformOptions':{'CAT_location':{'name':'configured'}}}}]},'publication')['items'][0]
        self.assertFalse(item['submitted'])

    def test_read_failure_keeps_cached_progress_without_attempting_publication(self):
        self.service.write('publish_execution','task-a',{'items':[{'key':'g:v:0','status':'submitted','local_id':'existing'}]})
        def fail(task):raise RuntimeError('offline')
        self.service.refresh_publication=fail
        result=self.service.progress('task-a')
        self.assertEqual('offline',result['refresh_error']);self.assertTrue(result['needs_poll'])
        self.assertEqual('existing',result['publication']['items'][0]['local_id'])

    def test_sidebar_index_uses_local_records_without_external_calls(self):
        self.service.write('publish_execution','task-a',{'items':[{'key':'g:v:0','status':'paused','local_id':'existing','payload':{'scheduleType':'timing'}}]})
        PublishCat.calls=[];summary=progress_index(self.service)['items']['task-a']
        self.assertEqual(1,summary['total']);self.assertEqual(1,summary['paused']);self.assertTrue(summary['scheduled'])
        self.assertFalse(PublishCat.calls)

    def test_sidebar_stays_in_generation_before_first_confirmed_submission(self):
        self.assertIsNone(card_summary({'items':[{'key':'g:v:0','status':'pending'}]},{}))
