"""Isolated human verification protocol and durable revenue queue checks. No live API."""
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
import json
import threading
import unittest
from unittest.mock import patch

from server import pingyue_collector as p
from server import revenue_query_settings as settings
from server import v2_file_service as service
from server import v2_revenue_service as revenue
from server import revenue_collection_state as state
from server.collection_jobs import CollectionJobs
from server.tests import test_revenue_collection_rules as fixtures

IMAGE = 'data:image/png;base64,fixture-image'


def data(day='2026-11-03', amount='14.98'):
    return {'summary': {'total_revenue': amount}, 'list': [{'stat_date': day, 'ad_revenue': amount}], 'syncing': False}


class Handler:
    def _json(self, status, result):
        self.status, self.result = status, result


class PingyueProtocolTests(unittest.TestCase):
    def setUp(self):
        p.SESSIONS.clear()
        self.addCleanup(p.SESSIONS.clear)
        self.session = p.get_session(settings.default_config('pingyue'))
        self.calls = []
        self.unlock_ok = True
        self.query_result = {'code': 1, 'data': data()}
        def request(endpoint, params=None, **kw):
            self.calls.append((endpoint, params, kw))
            if endpoint == 'captcha': return IMAGE
            if endpoint == 'resolve': return {'code': 1, 'data': {'need_code': True}}
            if endpoint == 'unlock': return {'code': 1 if self.unlock_ok else 0}
            if endpoint == 'query': return self.query_result
            raise AssertionError(endpoint)
        patcher=patch.object(p.QuerySession, 'request', side_effect=request)
        patcher.start();self.addCleanup(patcher.stop)

    def challenge(self):
        with self.assertRaises(p.VerificationRequired) as caught:
            self.session.query('account-a', '2026-11-03')
        self.assertEqual(self.session.challenge_id, caught.exception.challenge_id)
        return self.session.challenge_id

    def act(self, action='submit', **payload):
        handler=Handler()
        self.assertTrue(p.handle(handler, 'POST', f'/api/v3/revenue-verification/{self.session.challenge_id}/{action}',
            {'generation': self.session.captcha_id, 'answer': 'TEST', **payload}))
        return handler

    def test_no_query_before_human_unlock_then_reuse_for_another_account(self):
        self.challenge()
        self.assertEqual(['resolve', 'captcha'], [call[0] for call in self.calls])
        self.assertTrue(self.act().result['verified'])
        self.assertEqual(Decimal('14.98'), self.session.query('account-a', '2026-11-03')[1])
        self.session.query('account-b', '2026-11-03')
        self.assertEqual(['resolve', 'captcha', 'unlock', 'query', 'query'], [call[0] for call in self.calls])
        unlock = self.calls[2]
        self.assertEqual({'token', 'extract_code', 'captcha_id', 'captcha'}, set(unlock[1]))
        self.assertTrue(unlock[2]['post'])
        self.assertEqual('account-b', self.calls[-1][1]['video_account_id'])
        self.assertEqual('2026-11-03', self.calls[-1][1]['start_date'])
        self.assertNotIn('captcha', self.calls[-1][1])

    def test_multiple_accounts_get_same_challenge_not_new_images(self):
        first=self.challenge();second=self.challenge()
        self.assertEqual(first,second)
        self.assertEqual(['resolve','captcha'],[c[0] for c in self.calls])

    def test_refresh_rejects_stale_image_answer(self):
        self.challenge();old=self.session.captcha_id
        self.act('refresh')
        self.assertNotEqual(old,self.session.captcha_id)
        handler=self.act(generation=old)
        self.assertEqual(HTTPStatus.BAD_REQUEST,handler.status)
        self.assertNotIn('unlock',[c[0] for c in self.calls])

    def test_wrong_answer_refreshes_image_and_does_not_query(self):
        self.challenge();old=self.session.captcha_id;self.unlock_ok=False
        handler=self.act()
        self.assertFalse(handler.result['verified'])
        self.assertNotEqual(old,self.session.captcha_id)
        self.assertFalse(self.session.verified)
        self.assertNotIn('query',[c[0] for c in self.calls])

    def test_expired_unlock_returns_new_challenge(self):
        old=self.challenge();self.act()
        self.query_result={'code':0,'msg':'请先验证提取码'}
        with self.assertRaises(p.VerificationRequired): self.session.query('a','2026-11-03')
        self.assertNotEqual(old,self.session.challenge_id)
        self.assertFalse(self.session.verified)

    def test_defer_and_next_manual_attempt_reopens(self):
        old=self.challenge();self.act('defer')
        self.assertEqual('deferred',p.challenge_state(old))
        self.assertNotEqual(old,self.challenge())

    def test_url_and_code_changes_never_reuse_old_verification(self):
        self.challenge();self.act()
        changed=p.get_session({**settings.default_config('pingyue'),'extract_code':'123456'})
        self.assertIsNot(self.session,changed)
        self.assertFalse(changed.verified)
        self.assertNotIn('987357',repr(self.session))

    def test_pending_inventory_does_not_expose_code(self):
        self.challenge();handler=Handler()
        p.handle(handler,'GET','/api/v3/revenue-verification',None)
        self.assertNotIn('987357',json.dumps(handler.result))
        self.assertEqual(IMAGE,handler.result['items'][0]['image'])

    def test_same_source_limited_link_and_code_validation(self):
        default=settings.default_config('pingyue')
        self.assertEqual('987357',settings.normalize('pingyue',default)['extract_code'])
        for url in ['http://localhost/#/revenue/query/a','http://yt.szmr.com@evil.invalid/#/revenue/query/a',
                    'http://yt.szmr.com/admin','http://yt.szmr.com/#/elsewhere/a','http://yt.szmr.com:9222/#/revenue/query/a',
                    'http://yt.szmr.com/?extract_code=secret#/revenue/query/a']:
            with self.subTest(url=url),self.assertRaises(ValueError):settings.normalize('pingyue',{**default,'source_url':url})
        with self.assertRaises(ValueError):settings.normalize('pingyue',{**default,'extract_code':'123'})
        with self.assertRaises(ValueError):settings.normalize('qingning',{**settings.default_config('qingning'),'source_url':'http://vd.xingvan.com/duangg.html'})

    def test_status_can_recover_completion_after_frontend_event_was_missed(self):
        challenge=self.challenge();self.act();handler=Handler()
        p.handle(handler,'GET','/api/v3/revenue-verification/'+challenge,None)
        self.assertEqual({'state':'ready'},handler.result)

    def test_superseded_configuration_discards_old_pending_challenge(self):
        old=settings.default_config('pingyue');self.challenge()
        p.supersede(old,{**old,'extract_code':'123456'})
        self.assertEqual('superseded',p.challenge_state(self.session.challenge_id))
        self.assertFalse(self.session.verified)

    def test_explicit_normal_empty_is_no_data_and_can_end_backfill(self):
        self.assertEqual('no_data',p.parse_day({'summary':{'total_revenue':'0.00'},'list':[],'syncing':False},'2026-11-03')[0])

    def test_synchronizing_and_missing_are_pending_not_zero(self):
        self.assertEqual('pending',p.parse_day({**data(),'syncing':True},'2026-11-03')[0])
        self.assertEqual('pending',p.parse_day({'summary':{'total_revenue':0},'list':[]},'2026-11-03')[0])

    def test_only_exact_day_amount_and_consistent_total_are_saved(self):
        self.assertEqual(('success',Decimal('14.98'),''),p.parse_day(data(),'2026-11-03'))
        self.assertEqual('success',p.parse_day(data(amount='0.00'),'2026-11-03')[0])
        bad=[data('2026-11-02'),{**data(),'list':data()['list']*2},
             {**data(),'summary':{'total_revenue':'15.98'}}, {'list':[]}, data(amount='NaN'),data(amount='-1'),data(amount='0.001')]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):p.parse_day(value,'2026-11-03')


class PingyueIntegrationTests(unittest.TestCase):
    def setUp(self):
        fixtures.RevenueCollectionRulesTests.setUp(self)
        p.SESSIONS.clear();self.addCleanup(p.SESSIONS.clear)
        revenue.collectors.set_theater(self.conn,'q',['pingyue'])
        revenue.collectors.set_account(self.conn,'q','q','pingyue')
        self.conn.commit()
        self.session=p.get_session(settings.default_config('pingyue'))
        self.session.resolved=True
        self.session.image=IMAGE;self.session.captcha_id='fixture-captcha'
        self.session.state='pending';self.session.challenge_id='fixture-challenge'

    def test_waiting_does_not_create_financial_attempt_or_zero(self):
        result=revenue.collect_supported_theaters(self.conn,'2026-11-03','2026-11-03',account_ids=['q'],initial_backfill=True,
            collected_at=datetime(2026,11,4,12),max_initial_days=10)
        self.assertEqual('verification_required',result['items'][0]['status'])
        self.assertFalse(result['backfills'][0]['complete'])
        for table in ('v2_revenue_collection_attempts','v2_daily_revenues'):
            self.assertEqual(0,self.conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
        self.assertFalse(self.conn.in_transaction)

    def test_preview_waits_then_code_change_needs_matching_successful_test(self):
        config={**settings.default_config('pingyue'),'revision':0,'channel_id':'fixture-channel','query_date':'2026-11-03'}
        preview=settings.preview(self.conn,'pingyue',config)
        self.assertEqual('fixture-challenge',preview['verification_id'])
        self.assertEqual('',preview['test_token'])
        with patch.object(revenue,'_fetch',return_value=('success',Decimal('1.23'),'',[])):
            preview=settings.preview(self.conn,'pingyue',{**config,'extract_code':'123456'})
        with self.assertRaisesRegex(ValueError,'先测试'):
            settings.save(self.conn,'pingyue',{**config,'extract_code':'654321','test_token':preview['test_token']})
        saved=settings.save(self.conn,'pingyue',{**config,'extract_code':'123456','test_token':preview['test_token']})
        self.assertEqual('123456',saved['extract_code'])
        self.assertEqual(0,self.conn.execute('SELECT COUNT(*) FROM v2_daily_revenues').fetchone()[0])

    def job(self):
        jobs=CollectionJobs(service.connection,client_factory=lambda: (_ for _ in ()).throw(AssertionError('no Xiao V')))
        def finish():
            jobs.stop_event.set()
            if jobs.thread:jobs.thread.join(5)
        self.addCleanup(finish)
        return jobs

    def test_other_theater_runs_before_human_then_automatically_continues(self):
        jobs=self.job();other=threading.Event()
        def touch(*args):other.set();return 'success',Decimal('2'),''
        def fetch(channel,day,config):
            if not self.session.verified:raise p.VerificationRequired('fixture-challenge')
            return 'success',Decimal('1') if day=='2026-11-03' else Decimal('0'),''
        with patch.object(state,'clock',return_value=datetime(2026,11,4,12,tzinfo=state.SHANGHAI)),patch.object(p,'fetch_day',side_effect=fetch),patch.object(revenue,'fetch_touch_latest',side_effect=touch):
            jobs.start({'account_ids':['q','t'],'categories':['revenue']})
            self.assertTrue(other.wait(10),'other theater blocked on captcha')
            self.assertTrue(jobs.thread.is_alive())
            self.assertEqual(0,self.conn.execute("SELECT COUNT(*) FROM v2_daily_revenues WHERE account_id='q'").fetchone()[0])
            # This represents a successful HUMAN unlock callback, not solving a live captcha.
            self.session.verified=True;self.session.state='ready'
            jobs.thread.join(10)
        self.assertFalse(jobs.thread.is_alive())
        self.assertEqual('completed',jobs.state()['job']['state'])
        self.assertEqual(8,self.conn.execute("SELECT COUNT(*) FROM v2_daily_revenues WHERE account_id='q'").fetchone()[0])
        self.assertEqual(0,self.conn.execute("SELECT COUNT(*) FROM v2_revenue_collection_attempts WHERE collection_status='failed'").fetchone()[0])

    def test_stop_while_waiting_is_prompt_and_releases_queue(self):
        jobs=self.job();waiting=threading.Event()
        def fetch(*args):waiting.set();raise p.VerificationRequired('fixture-challenge')
        with patch.object(p,'fetch_day',side_effect=fetch):
            started=jobs.start({'account_ids':['q'],'categories':['revenue']})['job']
            self.assertTrue(waiting.wait(10))
            jobs.stop(started['id']);jobs.thread.join(5)
        self.assertFalse(jobs.thread.is_alive())
        self.assertEqual('stopped',jobs.state()['job']['state'])
        self.assertEqual(0,self.conn.execute("SELECT COUNT(*) FROM v2_daily_revenues WHERE account_id='q'").fetchone()[0])

    def test_other_collection_category_runs_while_verification_waits(self):
        other=threading.Event()
        def video_client():
            other.set()
            raise RuntimeError('isolated unavailable client')
        jobs=self.job();jobs.client_factory=video_client
        with patch.object(p,'fetch_day',side_effect=p.VerificationRequired('fixture-challenge')):
            jobs.start({'account_ids':['q'],'categories':['revenue','works']})
            self.assertTrue(other.wait(10),'other category blocked on captcha')
            self.session.state='deferred';jobs.thread.join(5)
        self.assertFalse(jobs.thread.is_alive())
        self.assertEqual('failed',next(c for c in jobs.state()['job']['items'] if c['category']=='works')['status'])

    def legacy(self, *, defer=False):
        waiting=threading.Event();threads=[];real_thread=threading.Thread
        def make_thread(*args,**kwargs):
            value=real_thread(*args,**kwargs);threads.append(value);return value
        def fetch(channel,day,config):
            if not self.session.verified:
                waiting.set();raise p.VerificationRequired('fixture-challenge')
            return 'success',Decimal('1') if day=='2026-11-03' else Decimal('0'),''
        with patch.object(service.threading,'Thread',side_effect=make_thread),patch.object(p,'fetch_day',side_effect=fetch):
            started=service.start_revenue_collection('2026-11-03','2026-11-03',account_ids=['q'],initial_backfill=not defer)
            try:
                self.assertTrue(waiting.wait(10))
                if defer:self.session.state='deferred'
                else:self.session.verified=True;self.session.state='ready'
                threads[0].join(10)
            finally:
                self.session.state='deferred'
                if threads:threads[0].join(5)
        self.assertFalse(threads[0].is_alive())
        return self.conn.execute('SELECT * FROM v2_revenue_collection_runs WHERE id=?',(started['run_id'],)).fetchone()

    def test_legacy_manual_and_automatic_runner_resume_after_human(self):
        run=self.legacy()
        self.assertEqual('completed',run['status'])
        self.assertEqual(8,run['success_units'])
        self.assertEqual(0,run['failed_units'])

    def test_legacy_defer_records_verification_pending_even_without_backfill(self):
        run=self.legacy(defer=True)
        self.assertEqual('completed',run['status'])
        self.assertIn('人工验证待完成',run['error_message'])
        self.assertEqual(0,run['completed_units'])

    def test_defer_finishes_partial_without_hanging(self):
        jobs=self.job();waiting=threading.Event()
        def fetch(*args):waiting.set();raise p.VerificationRequired('fixture-challenge')
        with patch.object(p,'fetch_day',side_effect=fetch):
            jobs.start({'account_ids':['q'],'categories':['revenue']})
            self.assertTrue(waiting.wait(10));self.session.state='deferred'
            jobs.thread.join(5)
        self.assertFalse(jobs.thread.is_alive())
        self.assertEqual('partial',jobs.state()['job']['state'])


if __name__ == '__main__':unittest.main()
