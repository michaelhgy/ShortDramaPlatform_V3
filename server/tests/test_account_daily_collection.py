import unittest
from datetime import date, timedelta
from server.account_daily_collection import collect_daily, infer_start, ranges, DAILY_FIELDS


def day(value, **metrics):
    return {'date':value, **{key:0 for key in DAILY_FIELDS}, 'fansTotal':10, **metrics}


def source_days():
    return [day(f'2026-10-{d:02}') for d in range(20,28)] + [day('2026-10-28',view=2),day('2026-10-29'),day('2026-10-30',fansNet=-1),day('2026-10-31'),day('2026-11-01',view=100)]


class Client:
    def __init__(self, local, refreshed=None):
        self.local=local;self.refreshed=refreshed;self.calls=[]
    def call(self,name,args):
        self.calls.append((name,args))
        if name=='vcat_refresh_account_stats':
            if self.refreshed is not None:self.local=self.refreshed
            return {'results':[{'uid':'u','success':True}]}
        return {'total':{'postCount':1,'fans':10},'daily':[r for r in self.local if args['startDate']<=r['date']<=args['endDate']]}


class DailyCollectionTests(unittest.TestCase):
    def collect(self,client,existing=None,end='2026-11-01'):
        return collect_daily(client,'u',existing,end,'2026-11-02T12:00:00+08:00',refresh=True)
    def test_home_visits_are_discarded_from_upstream_and_existing_cache(self):
        import json
        from server.publishing.vcat import VcatClient
        client = VcatClient.__new__(VcatClient)
        payload = {'daily':[{'date':'2026-11-01','view':123,'homeView':8}],
                   'rangeSum':{'homeView':20,'view':456}}
        client.request = lambda *args: {'result':{'content':[{'type':'text','text':json.dumps(payload)}]}}
        cleaned = client.call('vcat_get_account_stats', {})
        self.assertEqual(cleaned, {'daily':[{'date':'2026-11-01','view':123}], 'rangeSum':{'view':456}})
        source = Client([{**r, 'homeView':8} for r in source_days()])
        data, _ = self.collect(source)
        data['rangeSum'] = {'homeViews':55,'view':456}
        data['daily'][0]['homeView'] = 99
        source.calls = []
        data, result = self.collect(source, data)
        self.assertEqual(result['state'],'up_to_date')
        self.assertEqual(source.calls, [])
        self.assertNotIn('homeView', json.dumps(data))
        self.assertEqual(data['rangeSum']['view'],456)

    def test_cache_can_establish_zero_boundary_without_refresh_and_preserve_internal_zeros(self):
        client=Client(source_days());data,result=self.collect(client)
        self.assertEqual(result['state'],'complete');self.assertEqual(result['startDate'],'2026-10-28')
        self.assertEqual(result['platformRefresh'],'not_needed')
        self.assertFalse(any(n=='vcat_refresh_account_stats' for n,_ in client.calls))
        self.assertEqual(next(r for r in data['daily'] if r['date']=='2026-10-29')['view'],0)
    def test_same_day_repeat_does_not_query_xiaovcat_at_all(self):
        client=Client(source_days());data,_=self.collect(client);client.calls=[]
        _,result=self.collect(client,data)
        self.assertEqual(result['state'],'up_to_date');self.assertEqual(client.calls,[])
    def test_only_missing_dates_are_queried_and_existing_values_never_replaced(self):
        client=Client(source_days());data,_=self.collect(client)
        data['daily']=[r for r in data['daily'] if r['date']!='2026-10-30']
        client.local=[{**r,'view':999} if r['date']=='2026-11-01' else r for r in source_days()]
        client.calls=[];updated,result=self.collect(client,data)
        self.assertEqual([(a['startDate'],a['endDate']) for n,a in client.calls],[('2026-10-30','2026-10-30')])
        self.assertEqual(next(r for r in updated['daily'] if r['date']=='2026-11-01')['view'],100)
        self.assertEqual(result['state'],'complete')
    def test_empty_local_cache_actively_refreshes_then_rereads(self):
        client=Client([],source_days());_,result=self.collect(client)
        self.assertEqual(result['state'],'complete')
        self.assertEqual([n for n,_ in client.calls],['vcat_get_account_stats','vcat_refresh_account_stats','vcat_get_account_stats'])
    def test_empty_response_is_missing_not_zero_or_complete(self):
        _,result=self.collect(Client([]))
        self.assertEqual(result['state'],'partial');self.assertFalse(result['boundaryConfirmed'])
        self.assertIn('2026-11-01',result['missingDates'])
    def test_missing_day_in_zero_run_cannot_establish_start(self):
        rows={r['date']:r for r in source_days()};del rows['2026-10-24']
        self.assertIsNone(infer_start(rows))
    def test_missing_metric_is_not_zero_and_partial_day_can_be_filled(self):
        client=Client(source_days());data,_=self.collect(client)
        for row in data['daily']:
            if row['date']=='2026-11-01':row['comment']=None;row['view']=5
        client.calls=[];updated,result=self.collect(client,data)
        row=next(r for r in updated['daily'] if r['date']=='2026-11-01')
        self.assertEqual(row['view'],5);self.assertEqual(row['comment'],0);self.assertEqual(result['state'],'complete')
    def test_existing_yesterday_does_not_hide_an_older_gap(self):
        client=Client(source_days());data,_=self.collect(client)
        data['daily']=[r for r in data['daily'] if r['date']!='2026-10-29']
        client.local=[r for r in source_days() if r['date']!='2026-10-29'];client.calls=[]
        _,result=self.collect(client,data)
        self.assertEqual(result['missingDates'],['2026-10-29']);self.assertEqual(result['state'],'partial')
        queries=[a for n,a in client.calls if n=='vcat_get_account_stats']
        self.assertTrue(all(a['startDate']==a['endDate']=='2026-10-29' for a in queries))
    def test_long_active_history_uses_earliest_day_at_90_day_limit(self):
        days=[day((date(2026,11,1)-timedelta(days=i)).isoformat(),view=1) for i in range(90)]
        client=Client(days);data,result=self.collect(client)
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['startDate'],min(r['date'] for r in days))
        self.assertEqual(data['dailyCollection']['boundary']['rule'],'lookback_limit')
        self.assertFalse(any(n=='vcat_refresh_account_stats' for n,_ in client.calls))
    def test_invalid_negative_counts_are_repaired_but_negative_net_follow_is_valid(self):
        client=Client(source_days());data,_=self.collect(client)
        for row in data['daily']:
            if row['date']=='2026-11-01':row['view']=-1
        updated,result=self.collect(client,data)
        self.assertEqual(next(r for r in updated['daily'] if r['date']=='2026-11-01')['view'],100)
        self.assertEqual(next(r for r in updated['daily'] if r['date']=='2026-10-30')['fansNet'],-1)
        self.assertEqual(result['state'],'complete')
    def test_first_backfill_also_avoids_querying_existing_complete_days(self):
        existing={'daily':[day('2026-11-01',view=100)]}
        client=Client(source_days());_,result=self.collect(client,existing)
        queries=[a for n,a in client.calls if n=='vcat_get_account_stats']
        self.assertEqual(result['state'],'complete')
        self.assertTrue(all(a['endDate']<'2026-11-01' for a in queries))
    def test_backfill_stops_at_90_days_even_if_older_history_is_available(self):
        first=date(2026,4,16);end=first+timedelta(days=199)
        rows=[day((first+timedelta(days=i)).isoformat(),view=0 if i<20 else 1) for i in range(200)]
        client=Client(rows);_,result=self.collect(client,end=end.isoformat())
        cutoff=(end-timedelta(days=89)).isoformat()
        self.assertEqual(result['state'],'complete');self.assertEqual(result['startDate'],cutoff)
        self.assertTrue(all(args['startDate']>=cutoff for name,args in client.calls if name=='vcat_get_account_stats'))
        self.assertFalse(any(n=='vcat_refresh_account_stats' for n,_ in client.calls))
    def test_new_account_starts_on_first_available_day_without_preregistration_zeros(self):
        rows=[day((date(2026,10,15)+timedelta(days=i)).isoformat(),view=1) for i in range(18)]
        client=Client(rows);data,result=self.collect(client)
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['startDate'],'2026-10-15')
        self.assertEqual(result['missingDates'],[])
        self.assertEqual(len(data['daily']),18)
        self.assertEqual(data['dailyCollection']['boundary']['rule'],'lookback_limit')
        self.assertTrue(all(args['startDate']>='2026-08-04' for name,args in client.calls if name=='vcat_get_account_stats'))
        client.calls.clear()
        _,repeat=self.collect(client,data)
        self.assertEqual(repeat['state'],'up_to_date');self.assertEqual(client.calls,[])

    def test_refresh_can_reveal_an_earlier_start_than_the_initial_cache(self):
        rows=[day((date(2026,10,1)+timedelta(days=i)).isoformat(),view=1) for i in range(32)]
        client=Client([row for row in rows if row['date']>='2026-10-15'],rows)
        _,result=self.collect(client)
        self.assertEqual(result['state'],'complete');self.assertEqual(result['startDate'],'2026-10-01')
        self.assertEqual(result['platformRefresh'],'success')

    def test_existing_63_day_snapshot_no_longer_has_27_false_missing_days(self):
        rows=[day((date(2026,9,2)+timedelta(days=i)).isoformat(),view=1) for i in range(63)]
        existing={'daily':rows,'dailyCollection':{'state':'partial','boundary':None}}
        client=Client(rows);data,result=self.collect(client,existing,end='2026-11-03')
        self.assertEqual(result['state'],'complete');self.assertEqual(result['startDate'],'2026-09-02')
        self.assertEqual(result['missingDates'],[]);self.assertEqual(len(data['daily']),63)
        self.assertTrue(all(args['startDate']>='2026-08-06' for name,args in client.calls if name=='vcat_get_account_stats'))
        client.calls.clear()
        _,repeat=self.collect(client,data,end='2026-11-03')
        self.assertEqual(repeat['state'],'up_to_date');self.assertEqual(client.calls,[])

    def test_fallback_preserves_missing_dates_and_incomplete_earliest_record(self):
        rows=[day('2026-10-29',view=1,comment=None),day('2026-10-30',view=1),day('2026-11-01',view=1)]
        data,result=self.collect(Client(rows))
        self.assertEqual(result['startDate'],'2026-10-29');self.assertEqual(result['state'],'partial')
        self.assertEqual(result['missingDates'],['2026-10-29','2026-10-31'])
        self.assertIsNone(data['daily'][0]['comment'])

    def test_new_account_with_only_its_first_day_does_not_hide_later_missing_days(self):
        _,result=self.collect(Client([day('2026-10-15',view=1)]))
        self.assertEqual(result['startDate'],'2026-10-15');self.assertEqual(result['state'],'partial')
        self.assertIn('2026-11-01',result['missingDates'])
        self.assertNotIn('2026-10-14',result['missingDates'])

    def test_all_zero_history_can_use_earliest_available_day(self):
        _,result=self.collect(Client([day('2026-10-31'),day('2026-11-01')]))
        self.assertEqual(result['startDate'],'2026-10-31');self.assertEqual(result['state'],'complete')

    def test_query_failure_cannot_be_used_as_evidence_for_fallback(self):
        class FailedRead(Client):
            def call(self,name,args):
                if name=='vcat_get_account_stats':
                    self.calls.append((name,args));raise RuntimeError('offline')
                return super().call(name,args)
        _,result=self.collect(FailedRead([]),{'daily':[day('2026-11-01',view=1)]})
        self.assertEqual(result['state'],'partial');self.assertFalse(result['boundaryConfirmed'])

    def test_failed_post_refresh_read_keeps_fallback_unconfirmed(self):
        class FailedAfterRefresh(Client):
            def call(self,name,args):
                if name=='vcat_get_account_stats' and any(n=='vcat_refresh_account_stats' for n,_ in self.calls):
                    self.calls.append((name,args));raise RuntimeError('offline')
                return super().call(name,args)
        _,result=self.collect(FailedAfterRefresh([day('2026-11-01',view=1)]))
        self.assertEqual(result['state'],'partial');self.assertFalse(result['boundaryConfirmed'])

    def test_failed_refresh_does_not_finalize_a_sparse_cached_history(self):
        class FailedRefresh(Client):
            def call(self,name,args):
                if name=='vcat_refresh_account_stats':
                    self.calls.append((name,args));return {'results':[{'uid':'u','success':False}]}
                return super().call(name,args)
        _,result=self.collect(FailedRefresh([day('2026-11-01',view=1)]))
        self.assertEqual(result['state'],'partial');self.assertFalse(result['boundaryConfirmed'])

    def test_old_unconfirmed_saved_history_is_retained_but_not_used_to_extend_lookback(self):
        old=day('2026-01-01',view=1)
        client=Client([day('2026-11-01',view=1)])
        data,result=self.collect(client,{'daily':[old]})
        self.assertEqual(result['startDate'],'2026-11-01');self.assertEqual(result['state'],'complete')
        self.assertIn(old,data['daily'])
        self.assertTrue(all(args['startDate']>='2026-08-04' for name,args in client.calls if name=='vcat_get_account_stats'))

    def test_fallback_boundary_is_reused_when_adding_the_next_day(self):
        client=Client([day('2026-10-31',view=1),day('2026-11-01',view=1),day('2026-11-02',view=2)])
        data,_=self.collect(client);client.calls.clear()
        data,result=self.collect(client,data,end='2026-11-02')
        self.assertEqual(result['state'],'complete');self.assertEqual(result['startDate'],'2026-10-31')
        self.assertEqual([(a['startDate'],a['endDate']) for n,a in client.calls],[('2026-11-02','2026-11-02')])

    def test_online_reset_uses_same_90_day_limit_and_new_account_start(self):
        rows=[day((date(2026,10,15)+timedelta(days=i)).isoformat(),view=1) for i in range(18)]
        old=day('2026-01-01',view=2)
        client=Client([],rows)
        data,result=collect_daily(client,'u',{'daily':[old]},'2026-11-01','reset-at',reset_online=True)
        self.assertEqual(result['state'],'complete');self.assertEqual(result['startDate'],'2026-10-15')
        self.assertFalse(data['dailyCollection']['resetPending']);self.assertIn(old,data['daily'])
        self.assertEqual(sum(n=='vcat_refresh_account_stats' for n,_ in client.calls),1)
        self.assertTrue(all(args['startDate']>='2026-08-04' for name,args in client.calls if name=='vcat_get_account_stats'))

    def test_query_ranges_split_at_90_days_and_do_not_include_existing_gaps(self):
        days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(200)]
        days.remove('2026-02-01')
        windows=ranges(days)
        rebuilt=[(date.fromisoformat(a)+timedelta(days=i)).isoformat() for a,b in windows for i in range((date.fromisoformat(b)-date.fromisoformat(a)).days+1)]
        self.assertEqual(rebuilt,days)
        self.assertTrue(all((date.fromisoformat(b)-date.fromisoformat(a)).days<90 for a,b in windows))

    def test_online_reset_refreshes_before_read_and_replaces_complete_saved_day(self):
        client = Client(source_days())
        original, _ = self.collect(client)
        changed = [{**row, 'view': 999} if row['date'] == '2026-11-01' else row for row in source_days()]
        client = Client(source_days(), changed)
        saved = []
        updated, info = collect_daily(client, 'u', original, '2026-11-01', 'reset-at', reset_online=True, save_partial=saved.append)
        self.assertEqual(client.calls[0][0], 'vcat_refresh_account_stats')
        self.assertEqual(sum(name == 'vcat_refresh_account_stats' for name, _ in client.calls), 1)
        self.assertEqual(info['state'], 'complete')
        self.assertEqual(info['startDate'], '2026-10-28')
        self.assertEqual(next(row for row in updated['daily'] if row['date'] == '2026-11-01')['view'], 999)
        self.assertEqual(next(row for row in original['daily'] if row['date'] == '2026-11-01')['view'], 100)
        self.assertFalse(updated['dailyCollection']['resetPending'])
        self.assertTrue(saved[0]['dailyCollection']['resetPending'])
        client.calls.clear()
        self.collect(client, updated)
        self.assertEqual(client.calls, [])

    def test_online_reset_unconfirmed_refresh_preserves_old_data_without_using_stale_cache(self):
        original, _ = self.collect(Client(source_days()))
        class Failed(Client):
            def call(self, name, args):
                self.calls.append((name, args))
                return {'results': [{'uid': 'u', 'success': False}]}
        client = Failed(source_days())
        updated, info = collect_daily(client, 'u', original, '2026-11-01', 'reset-at', reset_online=True)
        self.assertEqual(updated['daily'], original['daily'])
        self.assertEqual([name for name, _ in client.calls], ['vcat_refresh_account_stats'])
        self.assertEqual(info['state'], 'partial')
        self.assertTrue(updated['dailyCollection']['resetPending'])
        self.assertIsNone(updated['dailyCollection']['boundary'])

    def test_online_reset_empty_response_does_not_turn_retained_days_into_new_coverage(self):
        original, _ = self.collect(Client(source_days()))
        client = Client([], [])
        updated, info = collect_daily(client, 'u', original, '2026-11-01', 'reset-at', reset_online=True)
        self.assertEqual(updated['daily'], original['daily'])
        self.assertEqual(info['state'], 'partial')
        self.assertFalse(info['boundaryConfirmed'])
        self.assertIn('2026-11-01', info['missingDates'])
        self.assertEqual(sum(name == 'vcat_refresh_account_stats' for name, _ in client.calls), 1)

    def test_online_reset_incomplete_day_retains_old_values_and_can_resume_on_routine_run(self):
        original, _ = self.collect(Client(source_days()))
        incomplete = [{**row, 'comment': None, 'view': 999} if row['date'] == '2026-11-01' else row for row in source_days()]
        updated, info = collect_daily(Client([], incomplete), 'u', original, '2026-11-01', 'reset-at', reset_online=True)
        self.assertEqual(info['state'], 'partial')
        self.assertIn('2026-11-01', info['missingDates'])
        self.assertEqual(next(row for row in updated['daily'] if row['date'] == '2026-11-01')['view'], 100)
        client = Client([], source_days())
        resumed, result = self.collect(client, updated)
        self.assertEqual(client.calls[0][0], 'vcat_refresh_account_stats')
        self.assertEqual(result['state'], 'complete')
        self.assertFalse(resumed['dailyCollection']['resetPending'])

    def test_stopped_online_reset_keeps_pending_marker_and_original_data(self):
        from server.collection_progress import CollectionStopped
        original, _ = self.collect(Client(source_days()))
        stop = [False]
        class Stopping(Client):
            def call(self, name, args):
                result = super().call(name, args)
                if name == 'vcat_refresh_account_stats': stop[0] = True
                return result
        saved = []
        with self.assertRaises(CollectionStopped):
            collect_daily(Stopping(source_days()), 'u', original, '2026-11-01', 'reset-at', reset_online=True, should_stop=lambda: stop[0], save_partial=saved.append)
        self.assertEqual(saved[-1]['daily'], original['daily'])
        self.assertTrue(saved[-1]['dailyCollection']['resetPending'])

if __name__=='__main__':unittest.main()
