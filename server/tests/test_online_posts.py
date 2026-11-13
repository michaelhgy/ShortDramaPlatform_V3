import unittest
from unittest.mock import Mock
from server.publishing.online_posts import PagePacer, read_online_posts, validate_page_interval
from server.publishing.vcat import VcatClient


class Clock:
    def __init__(self): self.now=100.; self.waits=[]
    def clock(self): return self.now
    def sleep(self, value): self.waits.append(value); self.now+=value


class Client:
    account_data=True
    def __init__(self, pages): self.pages=iter(pages); self.requests=[]
    def _online_posts_page(self, uid, params):
        self.requests.append((uid,dict(params)))
        page=next(self.pages)
        if isinstance(page,Exception):raise page
        return page


def page(ids, *, total=None, more=False, cursor=None, uid='u'):
    return {'list':[{'uid':uid,'postId':i} for i in ids], 'total':len(ids) if total is None else total,
            'hasMore':more,'nextState':cursor}


class OnlinePostsTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock()
        self.gate=PagePacer(sleeper=self.clock.sleep,clock=self.clock.clock,uniform=lambda a,b:(a+b)/2)
    def read(self, client, uid='u'):
        return read_online_posts(client,uid,page_interval_seconds=2,pacer=self.gate)
    def test_real_cursor_is_followed_and_wait_is_per_page_not_per_video(self):
        c=Client([page(['a','b'],total=3,more=True,cursor={'page':2}),page(['c'],total=3)])
        self.assertEqual([x['postId'] for x in self.read(c)],['a','b','c'])
        self.assertEqual(c.requests,[('u',{}),('u',{'page':2})])
        self.assertEqual(self.clock.waits,[1.5])
    def test_gate_also_paces_first_page_of_next_account(self):
        self.read(Client([page(['a'])]))
        self.read(Client([page(['b'],uid='v')]),'v')
        self.assertEqual(self.clock.waits,[1.5])
    def test_interval_draw_is_randomized_with_configured_bounds(self):
        choices=iter([1.1,1.9]);calls=[]
        def draw(a,b):calls.append((a,b));return next(choices)
        gate=PagePacer(sleeper=self.clock.sleep,clock=self.clock.clock,uniform=draw)
        for _ in range(3):gate.run(lambda:None,2)
        self.assertEqual(calls,[(1.,2.),(1.,2.)]);self.assertEqual(self.clock.waits,[1.1,1.9])
    def test_long_idle_does_not_add_an_unnecessary_wait(self):
        self.gate.run(lambda:None,2);self.clock.now+=30;self.gate.run(lambda:None,2)
        self.assertEqual(self.clock.waits,[])
    def test_failure_keeps_pacing_and_does_not_retry(self):
        c=Client([RuntimeError('offline')])
        with self.assertRaises(RuntimeError):self.read(c)
        self.assertEqual(len(c.requests),1)
        self.read(Client([page(['b'])]));self.assertEqual(self.clock.waits,[1.5])
    def test_duplicate_ids_are_not_a_successful_snapshot(self):
        with self.assertRaisesRegex(RuntimeError,'重复'):
            self.read(Client([page(['a'],total=2,more=True,cursor={'page':2}),page(['a'],total=2)]))
    def test_changing_total_is_not_a_successful_snapshot(self):
        with self.assertRaisesRegex(RuntimeError,'总数变化'):
            self.read(Client([page(['a'],total=2,more=True,cursor={'page':2}),page(['b'],total=3)]))
    def test_missing_last_page_is_not_a_successful_snapshot(self):
        with self.assertRaisesRegex(RuntimeError,'不完整'):self.read(Client([page(['a'],total=2)]))
    def test_wrong_account_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'账号'):self.read(Client([page(['a'],uid='v')]))
    def test_empty_account_is_valid_only_when_total_is_zero(self):
        self.assertEqual(self.read(Client([page([])])),[])
    def test_repeated_cursor_stops_without_a_third_request(self):
        c=Client([page(['a'],total=3,more=True,cursor={'page':2}),page(['b'],total=3,more=True,cursor={'page':2})])
        with self.assertRaisesRegex(RuntimeError,'未推进'):self.read(c)
        self.assertEqual(len(c.requests),2)
    def test_missing_metric_is_preserved_not_coerced_to_zero(self):
        self.assertNotIn('view',self.read(Client([page(['a'])]))[0])
    def test_invalid_interval_is_rejected_before_request(self):
        for value in (True,False,0,-1,61,float('nan'),float('inf'),'2',None):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_page_interval(value)
    def test_online_transport_requires_explicit_data_collection_gate(self):
        c=VcatClient.__new__(VcatClient);c.account_data=False;c.evaluate=Mock()
        with self.assertRaises(ValueError):c.online_account_posts('u',pacer=self.gate)
        c.evaluate.assert_not_called()


def dated(post_id, day, *, uid='u', **extra):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return {'uid':uid, 'postId':post_id, 'postUnix':datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp(), 'publishStatus':'published', **extra}


def dated_page(rows, *, total=None, more=False, cursor=None):
    return {'list':rows, 'total':len(rows) if total is None else total, 'hasMore':more, 'nextState':cursor}


class PublicationRangeTests(unittest.TestCase):
    setUp = OnlinePostsTests.setUp
    def read_range(self, client, start='2026-10-28', end='2026-11-03', **kwargs):
        return read_online_posts(client,'u',pacer=self.gate,published_start=start,published_end=end,**kwargs)

    def test_stop_at_lower_boundary_without_requesting_remaining_history(self):
        source=Client([
            dated_page([dated('a','2026-11-03'),dated('b','2026-10-28T23:59:59')],total=5,more=True,cursor={'page':2}),
            dated_page([dated('c','2026-10-28'),dated('d','2026-10-27T23:59:59')],total=5,more=True,cursor={'page':3}),
        ])
        messages=[];rows=self.read_range(source,progress=messages.append)
        self.assertEqual([row['postId'] for row in rows],['a','b','c'])
        self.assertEqual(len(source.requests),2)
        self.assertTrue(any('停止后续翻页' in message for message in messages))

    def test_shanghai_dates_include_start_midnight_and_last_second_of_end_day(self):
        source=Client([dated_page([dated('future','2026-11-04'),dated('end','2026-11-03T23:59:59'),dated('start','2026-10-28'),dated('before','2026-10-27T23:59:59')])])
        self.assertEqual([row['postId'] for row in self.read_range(source)],['end','start'])

    def test_old_pinned_work_is_not_a_history_boundary(self):
        source=Client([
            dated_page([dated('pin','2020-01-01',isSticky=True),dated('a','2026-11-03')],total=4,more=True,cursor={'page':2}),
            dated_page([dated('b','2026-10-30'),dated('old','2026-10-20')]),
        ])
        # Keep the official total stable across both pages.
        pages=list(source.pages);pages[-1]['total']=4;source.pages=iter(pages)
        self.assertEqual([row['postId'] for row in self.read_range(source)],['a','b'])
        self.assertEqual(len(source.requests),2)

    def test_nonchronological_or_unknown_time_cannot_be_saved_as_completed_range(self):
        from server.publishing.online_posts import PublicationRangeError
        samples=[
            [dated('old','2026-10-01'),dated('new','2026-11-01')],
            [dict(dated('unknown','2026-11-01'),postUnix=None)],
            [dict(dated('invalid','2026-11-01'),postUnix=float('nan'))],
        ]
        for rows in samples:
            with self.subTest(rows=rows),self.assertRaises(PublicationRangeError):
                self.read_range(Client([dated_page(rows)]))

    def test_timestamp_order_is_checked_across_pages(self):
        from server.publishing.online_posts import PublicationRangeError
        source=Client([dated_page([dated('a','2026-10-30')],total=2,more=True,cursor={'page':2}),dated_page([dated('b','2026-11-01')],total=2)])
        with self.assertRaises(PublicationRangeError):self.read_range(source)

    def test_range_may_complete_with_zero_matches_but_not_with_missing_last_page(self):
        self.assertEqual(self.read_range(Client([dated_page([dated('old','2026-10-01')],total=5,more=True,cursor={'page':2})])),[])
        with self.assertRaisesRegex(RuntimeError,'不完整'):
            self.read_range(Client([dated_page([dated('old','2026-10-01')],total=5)]))

    def test_scheduled_work_cannot_establish_a_publication_boundary(self):
        source=Client([dated_page([{'uid':'u','postId':'s','publishStatus':'scheduled','postUnix':None}],total=2,more=True,cursor={'page':2}),dated_page([dated('p','2026-11-01')],total=2)])
        self.assertEqual([row['postId'] for row in self.read_range(source)],['p'])
        self.assertEqual(len(source.requests),2)

    def test_invalid_range_is_rejected_without_any_external_requests(self):
        for start,end in [('2026-02-30','2026-03-01'),('2026-11-02','2026-11-01'),('20261101','2026-11-02'),('2026-11-01','2999-01-01'),('',None)]:
            source=Client([])
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):self.read_range(source,start,end)
            self.assertEqual(source.requests,[])


if __name__=='__main__':unittest.main()
