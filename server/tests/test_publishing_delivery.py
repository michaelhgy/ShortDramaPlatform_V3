import copy
import unittest
from contextlib import closing
from unittest.mock import patch

from server.publishing.delivery import delivery_confirmation, confirm_saved_deliveries
from server.publishing.progress import progress_index, project
from server.publishing.service import PublishingService
from server.operations_collection import publication_completion
from server.tests import test_publishing_cleanup_gate as cleanup_fixtures


class PublishingDeliveryTests(unittest.TestCase):
    setUp = cleanup_fixtures.PublishingCleanupGateTests.setUp
    tearDown = cleanup_fixtures.PublishingCleanupGateTests.tearDown
    connect = cleanup_fixtures.PublishingCleanupGateTests.connect

    def service(self):
        with closing(self.connect()) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS accounts(id TEXT,channel_id TEXT,status TEXT)")
            conn.commit()
        return PublishingService(self.connect, lambda task: {}, cleanup_fixtures.FakeClient)

    def item(self, key='g:v:0', pid='platform-post', end='2026-11-05T11:14:17+00:00'):
        return {'key': key, 'uid': 'uid', 'local_id': key, 'status': 'success',
                'payload': {'scheduleType': 'timing', 'scheduleTime': '2026-12-01 20:00'},
                'remote': {'uid': 'uid', 'localId': key, 'statusCode': '2', 'platform': 'Channels',
                           '_source': {'postId': pid, 'postEndTime': end}}}

    def task(self):
        with closing(self.connect()) as conn:
            return dict(conn.execute("SELECT * FROM production_tasks WHERE id='task-a'").fetchone())

    def test_whole_batch_delivery_uses_last_upload_end_not_future_schedule(self):
        service = self.service()
        items = [self.item(), self.item('g:v:1', 'second', '2026-11-05T11:15:00Z')]
        service.write('publish_execution', 'task-a', {'items': items})
        gate = publication_completion(self.connect, 'task-a', {'items': items})
        self.assertTrue(gate['complete'])
        self.assertEqual(2, gate['matched'])
        self.assertEqual(1, confirm_saved_deliveries(self.connect))
        row = self.task()
        self.assertEqual('registered', row['release_status'])
        self.assertEqual('', row['actual_release_time'])
        self.assertEqual('2026-11-05 19:15:00', row['delivery_completed_at'])
        self.assertEqual('2026-11-06 19:15:00', row['process_cleanup_at'])
        self.assertEqual('2026-11-12 19:15:00', row['raw_cleanup_at'])
        with closing(self.connect()) as conn:
            self.assertIsNone(conn.execute('SELECT publish_unix FROM v3_publication_history LIMIT 1').fetchone()[0])
        self.assertEqual(0, confirm_saved_deliveries(self.connect))
        self.assertEqual(row, self.task())

    def test_incomplete_or_local_timer_or_bad_identity_never_completes(self):
        service = self.service()
        changes = [
            lambda i: i.update(status='submitted'),
            lambda i: i['remote'].update(statusCode='0'),
            lambda i: i['remote']['_source'].update(postId=''),
            lambda i: i['remote'].update(uid='different'),
            lambda i: i['remote'].update(localId='different'),
            lambda i: i['remote'].update(platform='Douyin'),
            lambda i: i['payload'].update(scheduleType='localTiming'),
            lambda i: i.update(checks={'account': False}),
        ]
        for change in changes:
            with self.subTest(change=change):
                bad = copy.deepcopy(self.item('g:v:1', 'second'))
                change(bad)
                state = {'items': [self.item(), bad]}
                service.write('publish_execution', 'task-a', state)
                self.assertFalse(publication_completion(self.connect, 'task-a', state)['complete'])
                self.assertEqual(0, confirm_saved_deliveries(self.connect))
                self.assertEqual('unregistered', self.task()['release_status'])

    def test_success_log_and_previously_matched_id_complete_without_public_timestamp(self):
        service = self.service()
        item = self.item()
        item['remote']['_source']['postId'] = None
        service.write('publish_execution', 'task-a', {'items': [item]})
        self.assertFalse(delivery_confirmation(item))
        with closing(self.connect()) as conn:
            conn.execute("UPDATE v3_publication_history SET post_id='matched-work',match_state='matched',publication_state='unconfirmed',publish_unix=NULL")
            conn.commit()
        gate = publication_completion(self.connect, 'task-a', {'items': [item]})
        self.assertTrue(gate['complete'])
        self.assertEqual(1, confirm_saved_deliveries(self.connect))
        self.assertEqual('2026-11-05 19:14:17', self.task()['delivery_completed_at'])
        self.assertEqual(1, progress_index(service)['items']['task-a']['delivered'])

    def test_same_official_work_cannot_satisfy_two_copies(self):
        self.service()
        state = {'items': [self.item(), self.item('g:v:1')]}
        self.assertFalse(publication_completion(self.connect, 'task-a', state)['complete'])

    def test_sidebar_converges_unselected_cards_without_external_calls(self):
        service = self.service()
        service.write('publish_execution', 'task-a', {'items': [self.item()]})
        summary = progress_index(service)['items']['task-a']
        self.assertEqual('registered', self.task()['release_status'])
        self.assertEqual(1, summary['delivered'])
        self.assertTrue(project({'items': [self.item()]}, 'publication')['items'][0]['delivery_confirmed'])

    def test_public_list_failure_does_not_block_explicit_successful_delivery(self):
        service = self.service()
        state = {'items': [self.item()]}
        with patch('server.publishing.publisher.Publisher.refresh', return_value=state), \
             patch('server.operations_collection.associate_publications', side_effect=RuntimeError('offline')):
            result = service.refresh_publication('task-a')
        self.assertTrue(result['cleanup_gate']['complete'])
        self.assertTrue(result['items'][0]['delivery_confirmed'])
        self.assertEqual('registered', self.task()['release_status'])

    def test_later_public_release_fills_actual_date_without_changing_cleanup(self):
        from server import operations_collection as ops
        service = self.service()
        items = [self.item(), self.item('g:v:1', 'second')]
        service.write('publish_execution', 'task-a', {'items': items})
        self.assertEqual(1, confirm_saved_deliveries(self.connect))
        before = self.task()
        with closing(self.connect()) as conn:
            conn.execute("UPDATE v3_publication_history SET post_id=CASE WHEN item_key='g:v:0' THEN 'platform-post' ELSE 'second' END,match_state='matched'")
            ops.reconcile(conn, {'uid': [{'uid': 'uid', 'postId': 'platform-post', 'publishStatus': 'published', 'postUnix': 1800000000}]}, {'uid': []})
            conn.commit()
        self.assertEqual('', self.task()['actual_release_time'])
        with closing(self.connect()) as conn:
            ops.reconcile(conn, {'uid': [{'uid': 'uid', 'postId': 'second', 'publishStatus': 'published', 'postUnix': 1800000060}]}, {'uid': []})
            conn.commit()
        after = self.task()
        self.assertEqual('2027-01-15 16:01:00', after['actual_release_time'])
        for field in ['delivery_completed_at', 'process_cleanup_at', 'raw_cleanup_at']:
            self.assertEqual(before[field], after[field])

    def test_old_snapshot_cannot_finish_a_newer_publish_attempt(self):
        import json
        from server.publishing.delivery import apply_completion
        service = self.service()
        state = {'items': [self.item()]}
        service.write('publish_execution', 'task-a', state)
        gate = publication_completion(self.connect, 'task-a', state)
        service.write('publish_execution', 'task-a', {'items': [{**self.item(), 'status': 'submitted'}]})
        with closing(self.connect()) as conn:
            self.assertFalse(apply_completion(conn, 'task-a', gate, expected_content=json.dumps(state, ensure_ascii=False)))
            conn.commit()
        self.assertEqual('unregistered', self.task()['release_status'])

    def test_missing_delivery_end_uses_first_confirmation_and_never_schedule_time(self):
        service = self.service()
        item = self.item(end=None)
        service.write('publish_execution', 'task-a', {'items': [item]})
        self.assertEqual(1, confirm_saved_deliveries(self.connect))
        first = self.task()
        self.assertTrue(first['delivery_completed_at'])
        self.assertNotEqual('2026-12-01 20:00:00', first['delivery_completed_at'])
        self.assertEqual(0, confirm_saved_deliveries(self.connect))
        self.assertEqual(first, self.task())

    def test_cleaned_tasks_are_not_reopened_and_settings_are_snapshotted(self):
        service = self.service()
        service.write('publish_execution', 'task-a', {'items': [self.item()]})
        with closing(self.connect()) as conn:
            conn.execute("UPDATE production_tasks SET cleanup_status='process_cleaned'")
            conn.commit()
        self.assertEqual(0, confirm_saved_deliveries(self.connect))
        self.assertEqual('unregistered', self.task()['release_status'])
        with closing(self.connect()) as conn:
            conn.execute("UPDATE production_tasks SET cleanup_status='active'")
            conn.execute("CREATE TABLE v2_settings(key TEXT,value_json TEXT)")
            conn.execute("INSERT INTO v2_settings VALUES('short_term_cleanup_hours','48')")
            conn.execute("INSERT INTO v2_settings VALUES('raw_material_retention_days','9')")
            conn.commit()
        self.assertEqual(1, confirm_saved_deliveries(self.connect))
        self.assertEqual('2026-11-07 19:14:17', self.task()['process_cleanup_at'])
        self.assertEqual('2026-11-14 19:14:17', self.task()['raw_cleanup_at'])


class ProductionCardLifecycleTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from server import v2_file_service as files
        self.files = files
        self.temporary = tempfile.TemporaryDirectory()
        self.old = files.WORKSPACE, files.DATA_ROOT, files.DATABASE_INITIALIZED_PATH
        files.WORKSPACE = Path(self.temporary.name) / 'workspace'
        files.DATA_ROOT = Path(self.temporary.name) / 'state'
        files.DATABASE_INITIALIZED_PATH = None
        self.task = files.create_task({'source_id': 'isolated-delivery', 'account_name': '隔离账号', 'drama_name': '隔离剧集', 'planned_publish_at': '2026-11-05'})

    def tearDown(self):
        self.files.WORKSPACE, self.files.DATA_ROOT, self.files.DATABASE_INITIALIZED_PATH = self.old
        self.temporary.cleanup()

    def test_completed_card_is_visible_only_until_process_cleanup(self):
        files = self.files
        with closing(files.connection()) as conn:
            conn.execute("UPDATE production_tasks SET release_status='registered'")
            conn.commit()
        self.assertEqual([self.task['id']], [r['id'] for r in files.list_task_summaries()['items']])
        with closing(files.connection()) as conn:
            conn.execute("UPDATE production_tasks SET cleanup_status='process_cleaned'")
            conn.commit()
        self.assertEqual([], files.list_task_summaries()['items'])
        with closing(files.connection()) as conn:
            self.assertEqual(1, conn.execute('SELECT COUNT(*) FROM production_tasks').fetchone()[0])

    def test_additive_upgrade_preserves_public_release_and_saved_deadlines(self):
        files = self.files
        with closing(files.connection()) as conn:
            conn.execute("ALTER TABLE production_tasks DROP COLUMN delivery_completed_at")
            conn.execute("UPDATE production_tasks SET actual_release_time='2026-11-05 23:12:00',process_cleanup_at='2026-11-06 23:12:00'")
            conn.commit()
        files.DATABASE_INITIALIZED_PATH = None
        with closing(files.connection()) as conn:
            row = conn.execute('SELECT * FROM production_tasks').fetchone()
            self.assertEqual('', row['delivery_completed_at'])
            self.assertEqual('2026-11-05 23:12:00', row['actual_release_time'])
            self.assertEqual('2026-11-06 23:12:00', row['process_cleanup_at'])

    def test_due_cleanup_accepts_delivery_time_without_public_release(self):
        from pathlib import Path
        files = self.files
        final = Path(self.task['paths']['finals']) / 'isolated.mp4'
        final.write_bytes(b'isolated output')
        raw = Path(self.task['paths']['materials']) / 'isolated.mp4'
        raw.write_bytes(b'isolated source')
        with closing(files.connection()) as conn:
            conn.execute("UPDATE production_tasks SET release_status='registered',delivery_completed_at='2000-01-01 12:00:00',process_cleanup_at='2000-01-02 12:00:00',raw_cleanup_at='2999-01-01 12:00:00'")
            conn.commit()
        files.run_due_cleanup()
        self.assertFalse(final.exists())
        self.assertTrue(raw.exists())
        with closing(files.connection()) as conn:
            row = conn.execute('SELECT * FROM production_tasks').fetchone()
            self.assertEqual('process_cleaned', row['cleanup_status'])
            self.assertEqual('', row['actual_release_time'])


if __name__ == '__main__':
    unittest.main()
