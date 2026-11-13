import assert from 'node:assert/strict';
import test from 'node:test';
import type { AnalyticsRevenuePeriod } from '../api/analyticsDataBase';
import type { OperationsDashboardData,RevenueQueryResult } from '../api/operationsDashboard';
import { rateAccountRevenue,revenueTier } from './accountRevenueRating.ts';
import { createCockpitModel } from './cockpitModel.ts';

function day(date:string,amount:string|null,extra:Partial<AnalyticsRevenuePeriod>={}):AnalyticsRevenuePeriod {
  return {id:date,account_id:'a',theater_id:'t',period_label:date,period_start:date,period_end:date,
    period_type:'day',date_precision:'day',amount,currency:'CNY',data_state:'record',freshness_state:'fresh',
    settlement_state:'unsettled',include_in_analysis:1,source_kind:'test',source_attempt_id:'',collection_run_id:'',
    collected_at:'2026-11-01T08:00:00+08:00',raw_result_json:'{"income_updated":true}',...extra};
}
function query(status:string,extra:Partial<RevenueQueryResult>={}):RevenueQueryResult {
  return {id:'q',account_id:'a',theater_id:'t',revenue_date:'2026-10-31',collection_status:status,
    collected_at:'2026-11-01T15:00:00+08:00',error_message:'',adapter_key:'test',data_kind:'account_daily_total',period_type:'day',...extra};
}
function rate(periods:AnalyticsRevenuePeriod[],extra:Record<string,any>={}) {
  return rateAccountRevenue({accountId:'a',theaterId:'t',status:'正常',today:'2026-11-01',
    firstPublishDate:'2026-10-01',periods,...extra});
}

test('cumulative money boundaries include exactly 5000 in S and strictly greater values in SS',()=>{
  for(const [amount,tier] of [[0,'C'],[99.99,'C'],[100,'C'],[199.99,'C'],[200,'B'],[200.01,'B'],[499.99,'B'],[500,'A'],[1999.99,'A'],[2000,'S'],[5000,'S'],[5000.01,'SS']] as const) {
    assert.equal(revenueTier(amount),tier);
    assert.equal(rate([day('2026-10-29','0'),day('2026-10-30','0'),day('2026-10-31',String(amount))]).tier,tier);
  }
});

test('a newly confirmed first day can immediately qualify; stage is not the grade',()=>{
  const r=rate([day('2026-10-31','1200')],{firstPublishDate:'2026-10-31'});
  assert.equal(r.tier,'A');assert.equal(r.phase,'爆发');assert.equal(r.recordedTotal,1200);
  assert.equal(rate([day('2026-10-31','6000')],{firstPublishDate:'2026-10-31'}).tier,'SS');
});

test('first-day income needs 200 to qualify without completing trial observation',()=>{
  for(const amount of ['100','150','199.99']) {
    const r=rate([day('2026-10-31',amount)],{firstPublishDate:'2026-10-31'});
    assert.equal(r.tier,'待评');
  }
  const qualified=rate([day('2026-10-31','200')],{firstPublishDate:'2026-10-31'});
  assert.equal(qualified.tier,'B');
});

test('natural decay changes phase to tail without erasing the accumulated S value',()=>{
  const r=rate([day('2026-10-29','2000'),day('2026-10-30','2'),day('2026-10-31','1')]);
  assert.equal(r.tier,'S');assert.equal(r.phase,'尾量');assert.equal(r.recordedTotal,2003);
  assert.equal(r.reviewReason,null);assert.equal(r.peak?.amount,2000);
});

test('month rollover and waiting for late income preserve grade and last confirmed phase',()=>{
  const rows=[day('2026-10-29','2000'),day('2026-10-30','2'),day('2026-10-31','1')];
  const before=rate(rows),after=rate(rows,{today:'2026-11-02'});
  assert.equal(after.tier,before.tier);assert.equal(after.phase,before.phase);
  assert.equal(after.updateStatus,'待更新');assert.equal(after.confirmedThrough,'2026-10-31');
});

test('today is not assumed queryable and a current-date placeholder cannot inflate grade',()=>{
  const r=rate([day('2026-10-31','500'),day('2026-11-01','9000')]);
  assert.equal(r.tier,'A');assert.equal(r.recordedTotal,500);
});

test('unknown zeroes remain waiting even if queried across midnight or after noon',()=>{
  for(const time of ['08:00','16:00']) {
    const r=rate([day('2026-10-30','600'),day('2026-10-31','0',{raw_result_json:'{}',collected_at:`2026-11-01T${time}:00+08:00`})]);
    assert.equal(r.updateStatus,'待更新');assert.equal(r.tier,'A');assert.equal(r.phase,'爆发');
    assert.equal(r.confirmedThrough,'2026-10-30');
  }
});

test('explicit waiting cannot become a complete result just because there is a number',()=>{
  const r=rate([day('2026-10-30','600'),day('2026-10-31','5',{raw_result_json:'{"income_updated":false}'})]);
  assert.equal(r.recordedTotal,600);assert.equal(r.updateStatus,'待更新');assert.equal(r.phase,'爆发');
});

test('afternoon publication advances revenue date and preserves value with normal falling phase',()=>{
  const old=day('2026-10-30','600');
  const r=rate([old,day('2026-10-31','20',{collected_at:'2026-11-01T15:00:00+08:00'})]);
  assert.equal(r.tier,'A');assert.equal(r.phase,'回落');assert.equal(r.updateStatus,'已更新');
});

test('query failure only changes freshness and keeps saved grade, phase, and money',()=>{
  const rows=[day('2026-10-30','600'),day('2026-10-31','20')];
  const r=rate(rows,{queries:[query('failed',{error_message:'连接超时'})]});
  assert.equal(r.updateStatus,'查询失败');assert.equal(r.tier,'A');assert.equal(r.phase,'回落');
  assert.equal(r.recordedTotal,620);assert.match(r.updateReason,/连接超时/);
});

test('a later failed version cannot erase an available successful daily version',()=>{
  const good=day('2026-10-31','2200',{id:'good'});
  const fail=day('2026-10-31',null,{id:'fail',data_state:'failed',collected_at:'2026-11-01T15:00:00+08:00'});
  const r=rate([good,fail]);assert.equal(r.tier,'S');assert.equal(r.recordedTotal,2200);assert.equal(r.updateStatus,'查询失败');
});

test('no-data successful query is waiting rather than zero or query failure',()=>{
  const r=rate([day('2026-10-30','600')],{queries:[query('no_data')]});
  assert.equal(r.updateStatus,'待更新');assert.equal(r.tier,'A');assert.equal(r.phase,'爆发');
});

test('only known confirmed zero enters phase observations; the label has just three update states',()=>{
  const r=rate([day('2026-10-30','20'),day('2026-10-31','0',{raw_result_json:'{}',data_state:'confirmed_zero'})]);
  assert.equal(r.updateStatus,'已更新');assert.equal(r.lastValid?.amount,0);
  assert.ok(['待更新','已更新','查询失败'].includes(r.updateStatus));
});

test('new trials and filler zeroes cannot immediately classify an unproven account as C',()=>{
  const r=rate([day('2026-10-29','0'),day('2026-10-30','0'),day('2026-10-31','0')],{firstPublishDate:'2026-11-01'});
  assert.equal(r.tier,'待评');assert.equal(r.phase,'试投');assert.equal(r.reviewReason,null);
  assert.equal(rate([day('2026-10-31','5')],{firstPublishDate:'2026-10-31'}).tier,'待评');
});

test('review is limited to adequately observed trials that have never produced meaningful income',()=>{
  const weak=rate([day('2026-10-29','1'),day('2026-10-30','2'),day('2026-10-31','3')]);
  assert.equal(weak.tier,'C');assert.ok(weak.reviewReason);
  assert.match(weak.reviewReason!,/不足¥200/);
  const belowNewBoundary=rate([day('2026-10-29','1'),day('2026-10-30','2'),day('2026-10-31','3'),
    day('2026-10-31','150',{id:'month',period_type:'month_cumulative',date_precision:'month',period_start:'2026-10-01'})]);
  assert.equal(belowNewBoundary.tier,'C');assert.match(belowNewBoundary.reviewReason!,/不足¥200/);
  const tail=rate([day('2026-10-29','50'),day('2026-10-30','2'),day('2026-10-31','3')]);
  assert.equal(tail.phase,'尾量');assert.equal(tail.reviewReason,null);
});

test('tail can rise again or burst again; state is not a one-way lifecycle',()=>{
  const r=rate([day('2026-10-27','600'),day('2026-10-28','2'),day('2026-10-29','1'),day('2026-10-30','20'),day('2026-10-31','550')]);
  assert.equal(r.phase,'爆发');assert.equal(r.tier,'A');
});

test('stable income is covered without calling it a burst or a trial',()=>{
  const r=rate([day('2026-10-29','30'),day('2026-10-30','31'),day('2026-10-31','30')]);
  assert.equal(r.phase,'平稳');assert.equal(r.reviewReason,null);
});

test('missing revenue days do not count as consecutive low days',()=>{
  const r=rate([day('2026-10-28','1000'),day('2026-10-29','1'),day('2026-10-31','1')]);
  assert.notEqual(r.phase,'尾量');assert.equal(r.reviewReason,null);
});

test('monthly amounts can grade cumulative value but never invent a daily phase or peak',()=>{
  const r=rate([day('2026-10-31','3000',{period_type:'month_cumulative',date_precision:'month',period_start:'2026-10-01'})]);
  assert.equal(r.tier,'S');assert.equal(r.phase,'待判');assert.equal(r.peak,null);assert.equal(r.recordedTotal,3000);
  const overlap=rate([day('2026-10-31','10'),day('2026-10-31','1000',{period_type:'month_cumulative',date_precision:'month',period_start:'2026-10-01'})]);
  assert.equal(overlap.recordedTotal,1000);assert.equal(overlap.tier,'A');
});

test('stopped accounts retain cumulative grade and switch only their operating phase',()=>{
  const r=rate([day('2026-10-30','6000'),day('2026-10-31','3')],{status:'停用'});
  assert.equal(r.tier,'SS');assert.equal(r.phase,'停用');assert.equal(r.recordedTotal,6003);assert.equal(r.reviewReason,null);
});

test('settlement does not erase achievement; unverified and missing amounts remain unknown',()=>{
  assert.equal(rate([day('2026-10-31','600',{settlement_state:'settled',include_in_analysis:0})]).tier,'A');
  assert.equal(rate([day('2026-10-31','600',{source_kind:'legacy_v2',freshness_state:'legacy_unverified'})]).tier,'待评');
  assert.equal(rate([]).recordedTotal,null);assert.equal(rate([day('2026-10-31',null)]).recordedTotal,null);
});

test('Beijing dates and timestamps decide publication, not executor timezone or lexicographic timestamps',()=>{
  assert.equal(rate([day('2026-10-31','600',{collected_at:'2026-10-31T16:00:00Z'})]).tier,'A');
  assert.equal(rate([day('2026-10-31','600',{collected_at:'2026-10-31T15:59:00Z'})]).tier,'待评');
  const older=day('2026-10-31','100',{id:'old',collected_at:'2026-11-01T08:00:00+08:00'});
  const newer=day('2026-10-31','600',{id:'new',collected_at:'2026-11-01T00:30:00Z'});
  assert.equal(rate([older,newer]).recordedTotal,600);
});

test('report filters and stored prototype tiers do not alter cumulative labels',()=>{
  const data={today:'2026-11-01',latest_date:'2026-11-01',accounts:[{id:'a',nickname:'账号',theater_id:'t',theater_name:'剧场',status:'正常'}],
    theaters:[],video_accounts:[{account_id:'a',payload_json:'{"tier":"头部爆款"}'}],video_posts:[],video_post_punishments:[],
    video_account_daily:[],revenue_account_periods:[day('2026-10-31','600')],coverage:{}} as unknown as OperationsDashboardData;
  const model=createCockpitModel(data);assert.equal(model.ACCOUNTS[0].tier,'A');
  model.getAccountRankings('ALL','7days');model.getAccountRankings('ALL',{kind:'day',date:'2026-10-01'});
  assert.equal(model.ACCOUNTS[0].tier,'A');
  data.revenue_account_periods.push(day('2026-10-30','1600'));
  assert.equal(createCockpitModel(data).ACCOUNTS[0].tier,'S');
});
