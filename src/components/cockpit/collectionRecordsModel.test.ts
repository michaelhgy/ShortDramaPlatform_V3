import test from 'node:test';
import assert from 'node:assert/strict';
import { latestAccountRecords, recordStatus, recordScope, recordSource, recordRevenueSummary, recordStartedAt } from './collectionRecordsModel.ts';
import type { CollectionState, CollectionRecordSummary } from '../../api/operationsDashboard.ts';
const r=(category='works',status='failed',job_id='old')=>({job_id,source:'manual',started_at:'2026-11-03T08:00:00+08:00',item:{id:'a:'+category,account_id:'a',account_name:'甲',category,status,message:'真实结果',updated_at:'2026-11-03T08:01:00+08:00'}} as CollectionRecordSummary);
test('账号四类记录独立取最新，重试保留项不变成新执行记录',()=>{
 const daily=r('daily','success'),works=r();
 const state={record_summaries:[daily,works],job:{id:'new',source:'retry',started_at:'2026-11-04T08:00:00+08:00',items:[{...works.item,status:'running'}],retained_items:[daily.item]}} as CollectionState;
 const records=latestAccountRecords(state);assert.equal(records.get('a:daily')?.job_id,'old');assert.equal(records.get('a:works')?.job_id,'new');assert.equal(records.size,2);
});
test('来源待更新、查询失败、跳过与成功不混淆，没有优化记录不用于判断检测成功',()=>{
 assert.equal(recordStatus({...r('revenue','partial'),item:{...r().item,status:'partial',revenue_result:{pending_days:1,failed_days:0,history_pending:false,empty_days:0,saved_days:0,skipped_days:0}}}).label,'来源待更新');
 assert.equal(recordStatus(r()).label,'查询失败');assert.equal(recordStatus(r('optimization','success')).label,'已完成');assert.equal(recordStatus(r('revenue','skipped')).label,'已跳过');assert.equal(recordSource('unknown'),'来源未记录');
});
test('详细记录使用当次范围，不随配置页后续修改而变化',()=>{
 assert.equal(recordScope({scope:{works:{mode:'published_range',start_date:'2026-10-28',end_date:'2026-11-03'}}} as never,'works'),'2026-10-28 至 2026-11-03 发布作品');
 assert.match(recordScope({scope:{daily:{mode:'reset_online'}}} as never,'daily'),/强制/);
});

test('累计收益记录区分来源累计与本次新增入账，并使用本项实际开始时间',()=>{
 const record={...r('revenue','success'),started_at:'2026-11-05T08:00:00+08:00',item:{...r('revenue','success').item,started_at:'2026-11-05T09:00:00+08:00',revenue_result:{mode:'cumulative' as const,saved_amount:'30.00',source_amount:'130.00',source_period:'2026-11',collector_name:'古言端原生',query_end:'2026-11-05',pending_days:0,failed_days:0,history_pending:false,empty_days:0,saved_days:1,skipped_days:0}}};
 assert.equal(recordRevenueSummary(record),'古言端原生；本次入账 ¥30.00；来源累计 ¥130.00（2026-11）；入账日期 2026-11-05');
 assert.equal(recordStartedAt(record),'2026-11-05T09:00:00+08:00');
 assert.equal(recordRevenueSummary(r('revenue','failed')),'');
});
test('整轮失败的旧记录与正常无收益记录有明确状态',()=>{
 const result={pending_days:0,failed_days:92,history_pending:true,empty_days:0,saved_days:0,skipped_days:0};
 assert.equal(recordStatus({...r('revenue','partial'),item:{...r('revenue','partial').item,revenue_result:result}}).label,'查询失败');
 assert.equal(recordStatus({...r('revenue','success'),item:{...r('revenue','success').item,revenue_result:{...result,failed_days:0,empty_days:7,history_pending:false}}}).label,'无收益记录');
});
