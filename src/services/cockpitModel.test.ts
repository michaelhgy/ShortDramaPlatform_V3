import { OPTIMIZATION_NOTICE_RULES } from '../types/optimizationNotices.ts';
import assert from 'node:assert/strict';
import test from 'node:test';
import { createCockpitModel } from './cockpitModel.ts';
import { summarizeAccountOptimization } from './accountOptimizationSummary.ts';
import type { OperationsDashboardData } from '../api/operationsDashboard';

function fixture(): OperationsDashboardData {
  return {
    today: '2026-11-01', latest_date: '2026-10-31',
    accounts: [{ id: 'a', nickname: '甲账号', theater_id: 't', theater_name: '甲剧场', status: '正常' }],
    theaters: [{ id: 't', name: '甲剧场', status: '启用' }],
    video_accounts: [], video_posts: [], video_post_punishments: [],
    video_account_daily: [
      { id: 'ok', account_id: 'a', stat_date: '2026-10-31', view: 100, fans_net: -3, like_count: 8, comment_count: 2, data_state: 'record' },
      { id: 'failed', account_id: 'a', stat_date: '2026-10-30', view: 9999, fans_net: 9999, data_state: 'failed' },
      { id: 'zero', account_id: 'a', stat_date: '2026-10-29', view: 0, fans_net: 0, like_count: 0, comment_count: 0, data_state: 'confirmed_zero' },
    ],
    revenue_account_periods: [
      { id: 'day', account_id: 'a', period_type: 'day', period_start: '2026-10-31', period_end: '2026-10-31', amount: '12.30', data_state: 'record', include_in_analysis: 1, settlement_state: 'unsettled' },
      { id: 'month', account_id: 'a', period_type: 'month_cumulative', period_start: '2026-10-01', period_end: '2026-10-31', amount: '80.50', data_state: 'record', include_in_analysis: 1, settlement_state: 'unsettled' },
    ],
    coverage: { account_days: 3, failed_account_days: 1, failed_revenue_periods: 0, unclassified_risks: 0 },
  } as OperationsDashboardData;
}

test('available account counts exclude unavailable states without dropping stopped or banned history', () => {
  const data = fixture();
  const statuses = ['正常','观察','限流','二限','实名','封禁','封号','停用','注销'];
  data.accounts = statuses.map((status,index) => ({...data.accounts[0],id:index ? `a${index}` : 'a',status}));
  const model = createCockpitModel(data);
  assert.deepEqual(model.AVAILABLE_ACCOUNTS.map(account => account.businessStatus), statuses.slice(0,5));
  assert.equal(model.ACCOUNTS.length, 9);
  assert.equal(model.getKPISummary().totalRevenue, 12.3);
  data.accounts[0].status = '停用';
  const changed = createCockpitModel(data);
  assert.equal(changed.AVAILABLE_ACCOUNTS.length, 4);
  assert.equal(changed.getKPISummary().totalRevenue, 12.3);
  data.accounts[0].status = '正常';
  assert.equal(createCockpitModel(data).AVAILABLE_ACCOUNTS.length, 5);
});

test('only enabled theaters are offered by the homepage while disabled theater history is retained', () => {
  const data = fixture();
  data.theaters.push({id:'disabled',name:'停用剧场',status:'停用'});
  data.accounts[0].theater_id = 'disabled';
  data.accounts[0].theater_name = '停用剧场';
  const model = createCockpitModel(data);
  assert.deepEqual(model.ENABLED_THEATERS.map(theater => theater.id), ['t']);
  assert.equal(model.THEATERS.length, 2);
  assert.equal(model.ACCOUNTS.length, 1);
  assert.equal(model.getKPISummary().totalRevenue, 12.3);
  data.theaters[0].status = '停用';
  assert.equal(createCockpitModel(data).ENABLED_THEATERS.length, 0);
  data.theaters[1].status = '启用';
  assert.deepEqual(createCockpitModel(data).ENABLED_THEATERS.map(theater => theater.id), ['disabled']);
});

test('注销 retains account metrics, posts and income; page scopes control visibility', () => {
  const data = fixture();
  data.accounts[0].status = '注销';
  data.accounts[0].channel_id = 'uid-a';
  data.video_account_daily.push({ ...data.video_account_daily[0], id:'uid-only', account_id:'', uid:'uid-a' });
  data.video_posts = [{ id:'v', post_id:'v', account_id:'a', data_state:'record',post_time:'2026-10-31 12:00:00',view:10,full_view:.2,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}' }] as OperationsDashboardData['video_posts'];
  const retired = createCockpitModel(data);
  assert.equal(retired.ACCOUNTS.length, 1);
  assert.equal(retired.HISTORICAL_TRAFFIC.length, 3);
  assert.equal(retired.HISTORICAL_REVENUE.length, 2);
  assert.equal(retired.VIDEO_TRAFFIC_DATA.length, 1);
  assert.equal(retired.getKPISummary().totalRevenue, 12.3);
  assert.equal(createCockpitModel(data,'all','current').ACCOUNTS.length,0);
  assert.equal(createCockpitModel(data,'all','cancelled').getKPISummary().totalRevenue,12.3);
  data.accounts[0].status = '停用';
  data.accounts[0].notes = '账号备注';
  const restored = createCockpitModel(data);
  assert.equal(restored.ACCOUNTS[0].businessStatus, '停用');
  assert.equal(restored.ACCOUNTS[0].description, '账号备注');
  assert.equal(restored.VIDEO_TRAFFIC_DATA.length, 1);
  assert.equal(restored.getKPISummary().totalRevenue, 12.3);
});

test('month rollover keeps recent 30 days populated; yesterday is computed by backend date', () => {
  const model = createCockpitModel(fixture());
  assert.equal(model.getDateFilterBoundary('30days'), '2026-10-02');
  assert.equal(model.getDateFilterBoundary('7days'), '2026-10-25');
  assert.equal(model.yesterday, '2026-10-31');
  assert.equal(model.getKPISummary('ALL', 'ALL', '30days').totalViews, 100);
});

test('profile followers use the latest usable account total; selected-period videos are not lifetime totals', () => {
  const data = fixture();
  data.accounts[0].channel_id = 'uid-a';
  data.video_accounts = [
    { account_id:'a',uid:'uid-a',fans_total:80,snapshot_date:'2026-10-30',data_state:'record' },
    { account_id:'',uid:'uid-a',fans_total:3039,snapshot_date:'2026-10-31',data_state:'record' },
    { account_id:'a',uid:'uid-a',fans_total:9999,snapshot_date:'2026-11-01',data_state:'failed' },
  ] as OperationsDashboardData['video_accounts'];
  const model = createCockpitModel(data);
  assert.equal(model.ACCOUNTS[0].followerTotal, 3039);
  assert.equal(model.ACCOUNTS[0].videoTotal, null);
  model.getAccountRankings('ALL', 'yesterday');
  assert.equal(model.ACCOUNTS[0].followerTotal, 3039);
});

test('missing or invalid profile totals stay unknown; confirmed zero followers remains zero', () => {
  const data = fixture();
  assert.equal(createCockpitModel(data).ACCOUNTS[0].followerTotal, null);
  for (const [followers, expected] of [[0,0],[-1,null],[NaN,null]] as const) {
    data.video_accounts = [{account_id:'a',fans_total:followers,data_state:'record'}] as OperationsDashboardData['video_accounts'];
    assert.equal(createCockpitModel(data).ACCOUNTS[0].followerTotal,expected);
  }
});

test('failed metrics are excluded; confirmed zero and negative followers survive', () => {
  const model = createCockpitModel(fixture());
  assert.equal(model.HISTORICAL_TRAFFIC.length, 2);
  assert.equal(model.getKPISummary().totalFollows, -3);
  assert.equal(model.HISTORICAL_TRAFFIC.find(r => r.id === 'zero')?.views, 0);
});

test('overview originality counts exclude repeated publishing and unknown notices, using all published works as denominator', () => {
  const data=fixture();
  data.video_posts=Array.from({length:4},(_,i)=>({id:'row'+i,post_id:'p'+i,account_id:'a',post_time:'2026-10-31 18:00:00',data_state:'record',view:100,full_view:.2,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}'})) as OperationsDashboardData['video_posts'];
  data.video_post_punishments=[OPTIMIZATION_NOTICE_RULES[4].analysis,OPTIMIZATION_NOTICE_RULES[0].analysis,'尚未归类的作品分析'].map((notice,i)=>({id:'risk'+i,account_id:'a',post_id_or_export_id:'p'+i,snapshot_date:'2026-11-01',payload_json:JSON.stringify({notice})})) as OperationsDashboardData['video_post_punishments'];
  const model=createCockpitModel(data),kpi=model.getKPISummary('ALL','ALL','7days');
  assert.equal(kpi.totalVideos,4);assert.equal(kpi.publishedAccountCount,1);
  assert.equal(kpi.optimizedVideos,3);assert.equal(kpi.overallOptRate,75);
  assert.equal(kpi.originalOptimizedVideos,1);assert.equal(kpi.originalOptRate,25);
  const optimization=summarizeAccountOptimization(model.getAccountOptimizationStats('ALL','7days'));
  assert.equal(kpi.originalOptimizedVideos,optimization.homogeneousCount);
  assert.equal(kpi.originalOptRate,optimization.homogeneousRate);
});

test('overview publishing and originality metrics honor date, theater, account and cancelled-account scope', () => {
  const data=fixture();
  data.accounts.push({...data.accounts[0],id:'b',nickname:'乙账号',theater_id:'t2',theater_name:'乙剧场'});
  data.theaters.push({id:'t2',name:'乙剧场',status:'启用'});
  const specs=[['a','2026-10-31'],['a','2026-10-24'],['b','2026-10-31'],['b','2026-10-30']];
  data.video_posts=specs.map(([account_id,day],i)=>({id:'row'+i,post_id:'p'+i,account_id,post_time:day+' 18:00:00',data_state:'record',view:100,full_view:.2,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}'})) as OperationsDashboardData['video_posts'];
  data.video_post_punishments=[4,4,0].map((type,i)=>({id:'risk'+i,account_id:specs[i][0],post_id_or_export_id:'p'+i,snapshot_date:'2026-11-01',payload_json:JSON.stringify({notice:OPTIMIZATION_NOTICE_RULES[type].analysis})})) as OperationsDashboardData['video_post_punishments'];
  const model=createCockpitModel(data);
  const all=model.getKPISummary('ALL','ALL','7days');
  assert.equal(all.totalVideos,3);assert.equal(all.publishedAccountCount,2);assert.equal(all.originalOptRate,33.3);
  const theater=model.getKPISummary('甲剧场','ALL','7days');
  assert.equal(theater.totalVideos,1);assert.equal(theater.originalOptRate,100);
  const account=model.getKPISummary('ALL','b','7days');
  assert.equal(account.totalVideos,2);assert.equal(account.originalOptRate,0);assert.equal(account.publishedAccountCount,1);
  assert.equal(model.getKPISummary('ALL','ALL','yesterday').originalOptRate,50);
  const empty=model.getKPISummary('不存在','ALL','7days');
  assert.equal(empty.totalVideos,0);assert.equal(empty.publishedAccountCount,0);assert.equal(empty.originalOptRate,0);
  data.accounts[1].status='注销';
  const cancelled=createCockpitModel(data).getKPISummary('ALL','ALL','7days');
  assert.equal(cancelled.totalVideos,3);assert.equal(cancelled.originalOptRate,33.3);assert.equal(cancelled.publishedAccountCount,2);
});

test('matrix daily summary is fixed to yesterday while top metrics follow the selected period', () => {
  const data=fixture();
  data.video_account_daily.push({...data.video_account_daily[0],id:'earlier',stat_date:'2026-10-28',view:999});
  const model=createCockpitModel(data);
  const day=model.getAccountRankings('ALL','yesterday')[0],all=model.getAccountRankings('ALL','all')[0];
  assert.notEqual(day.views,all.views);
  assert.deepEqual(day.dailySummary,all.dailySummary);
  assert.equal(day.dailySummary.views,100);assert.equal(day.dailySummary.hearts,8);
});

test('matrix historical revenue includes settled facts and removes day/month overlap across date filters', () => {
  const data=fixture();
  data.revenue_account_periods.forEach(row=>Object.assign(row,{currency:'CNY',collected_at:'2026-11-01T12:00:00+08:00',raw_result_json:JSON.stringify({income_updated:true})}));
  data.revenue_account_periods[1].settlement_state='settled';
  data.revenue_account_periods.push({...data.revenue_account_periods[0],id:'older-paid',period_start:'2026-09-30',period_end:'2026-09-30',amount:'200.00',settlement_state:'settled'});
  const model=createCockpitModel(data);
  for(const range of ['yesterday','7days','all'] as const) {
    assert.equal(model.getAccountRankings('ALL',range)[0].account.rating?.recordedTotal,280.5);
  }
});

test('account optimization applies the shared 20 and 50 percent health boundaries',()=>{
  for(const [optimized,level] of [[1,'healthy'],[2,'healthy'],[3,'warning'],[5,'critical']] as const){
    const data=fixture();
    data.video_posts=Array.from({length:10},(_,i)=>({id:'row'+i,post_id:'p'+i,account_id:'a',post_time:'2026-10-31 18:00:00',data_state:'record',view:100,full_view:.2,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}'})) as OperationsDashboardData['video_posts'];
    data.video_post_punishments=Array.from({length:optimized},(_,i)=>({id:'r'+i,post_id_or_export_id:'p'+i,snapshot_date:'2026-11-01',payload_json:JSON.stringify({notice:OPTIMIZATION_NOTICE_RULES[4].analysis})})) as OperationsDashboardData['video_post_punishments'];
    const stat=createCockpitModel(data).getAccountOptimizationStats('ALL','7days')[0];
    assert.equal(stat.healthLevel,level);assert.equal(stat.optimizationRate,optimized*10);assert.equal(stat.totalVideos,10);
  }
});

test('a monthly total is not attributed to its end date or split into days', () => {
  const model = createCockpitModel(fixture());
  assert.equal(model.filterRevenue('ALL', 'ALL', 'yesterday').length, 1);
  assert.equal(model.getKPISummary('ALL', 'ALL', 'yesterday').totalRevenue, 12.3);
  assert.equal(model.filterRevenue('ALL', 'ALL', '7days').length, 1);
  assert.equal(model.getKPISummary('ALL', 'ALL', 'all').totalRevenue, 80.5);
});

test('refresh derives aggregates from the new dataset, not a retained mock array', () => {
  const original = fixture();
  const first = createCockpitModel(original);
  original.video_account_daily[0].view = 200;
  const next = createCockpitModel(original);
  assert.equal(first.getKPISummary().totalViews, 100);
  assert.equal(next.getKPISummary().totalViews, 200);
  assert.equal(next.filterTraffic('不存在的剧场').length, 0);
});

test('empty database data produces empty lists and zero totals', () => {
  const data = fixture();
  data.accounts = []; data.video_account_daily = []; data.revenue_account_periods = [];
  const model = createCockpitModel(data);
  assert.equal(model.getKPISummary().totalVideos, 0);
  assert.equal(model.getKPISummary().totalRevenue, 0);
  assert.deepEqual(model.getAccountRankings(), []);
});

test('account identity and artwork come from the catalog without changing work metrics', () => {
  const data = fixture();
  data.accounts[0].channel_id = 'actual-channel-id';
  data.accounts[0].avatar_url = '/api/v3/drama-catalog/accounts/a/avatar';
  data.dramas = [{ id: 'd1', name: '资料库新剧名', cover_url: '/api/v2/dramas/d1/cover' }];
  data.video_posts = [{ id: 'p', post_id: 'official-post-id', account_id: 'a', post_time: '2026-10-31 18:30:00',
    fetched_at:'2026-11-01T09:00:00+08:00',snapshot_date:'2026-11-01',
    data_state: 'record', full_view: .32, view: 12345, love_count: 1, comment_count: 2, forward_count: 3, like_count: 4,
    payload_json: JSON.stringify({ drama_id: 'd1', drama_name: '过期名称', file_name: '过期名称-7.mp4', episode: 7 }),
  }] as OperationsDashboardData['video_posts'];
  const model = createCockpitModel(data);
  assert.equal(model.ACCOUNTS[0].channelId, 'actual-channel-id');
  assert.equal(model.ACCOUNTS[0].avatarUrl, data.accounts[0].avatar_url);
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].dramaTitle, '资料库新剧名');
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].fileName, '作品 official-post-id');
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].coverUrl, '/api/v2/dramas/d1/cover');
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].views, 12345);
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].id, 'official-post-id');
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].statsCollectedAt,'2026-11-01T09:00:00+08:00');
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].statsDate,'2026-11-01');
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].statsState,'record');
});

test('custom dates constrain revenue, traffic, works, rankings and risk summaries to the same publication interval', () => {
  const data = fixture();
  const dates = ['2026-10-28', '2026-10-29', '2026-10-31', '2026-11-01'];
  data.video_posts = dates.map((date, i) => ({ id: `row${i}`, post_id: `p${i}`, account_id: 'a',
    post_time: date + ' 18:00:00', data_state: 'record', full_view: .4, view: 10, love_count: 1,
    comment_count: 1, forward_count: 1, like_count: 1, payload_json: '{}',
  })) as OperationsDashboardData['video_posts'];
  data.video_post_punishments = dates.map((_, i) => ({ id: `risk${i}`, post_id_or_export_id: `p${i}`,
    snapshot_date: '2026-11-01', payload_json: JSON.stringify({ notice: OPTIMIZATION_NOTICE_RULES[4].analysis, detectedDate: '2026-11-01' }),
  })) as OperationsDashboardData['video_post_punishments'];
  const model = createCockpitModel(data);
  const range = { kind: 'range' as const, start: '2026-10-29', end: '2026-10-31' };
  const day = { kind: 'day' as const, date: '2026-10-31' };
  assert.deepEqual(model.filterVideos('ALL', 'ALL', range).map(v => v.id).sort(), ['p1', 'p2']);
  assert.deepEqual(model.filterVideos('ALL', 'ALL', day).map(v => v.id), ['p2']);
  assert.deepEqual(model.filterTraffic('ALL', 'ALL', range).map(t => t.date), ['2026-10-29', '2026-10-31']);
  assert.equal(model.getKPISummary('ALL', 'ALL', range).totalVideos, 2);
  assert.equal(model.getKPISummary('ALL', 'ALL', range).totalRevenue, 12.3);
  assert.equal(model.getAccountRankings('ALL', range)[0].videoCount, 2);
  assert.equal(model.getAccountOptimizationStats('ALL', range)[0].optimizedVideos, 2);
  assert.equal(model.getOptimizationReasonDistribution('ALL', 'ALL', range)[0].count, 2);
  assert.deepEqual(model.getDailyOptimizationTrends('ALL', 'ALL', range).map(t => t.date), ['2026-10-29', '2026-10-31']);
  assert.equal(model.filterVideos('ALL', 'ALL', 'month').length, 1);
  assert.equal(model.filterVideos('ALL', 'ALL', '7days').length, 3);
});

test('custom periods include monthly revenue only when its whole period is contained', () => {
  const model = createCockpitModel(fixture());
  assert.equal(model.filterRevenue('ALL', 'ALL', { kind: 'day', date: '2026-10-31' }).length, 1);
  assert.equal(model.getKPISummary('ALL', 'ALL', { kind: 'range', start: '2026-10-01', end: '2026-10-31' }).totalRevenue, 80.5);
  assert.equal(model.getKPISummary('ALL', 'ALL', { kind: 'range', start: '2026-10-01', end: '2026-10-30' }).totalRevenue, 0);
});


test('optimization tag is derived from original analysis rather than a conflicting saved label', () => {
  const data = fixture();
  data.video_posts = [{id:'raw',post_id:'raw',account_id:'a',post_time:'2026-10-31 18:00:00',data_state:'record',view:100,full_view:.2,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}'}] as OperationsDashboardData['video_posts'];
  const original = '作品分析：\n' + OPTIMIZATION_NOTICE_RULES[4].analysis;
  data.video_post_punishments = [{id:'r',post_id_or_export_id:'raw',snapshot_date:'2026-11-01',punish_state:'已记录的状态',payload_json:JSON.stringify({notice:original,simplifiedReason:'多次发布'})}] as OperationsDashboardData['video_post_punishments'];
  const model = createCockpitModel(data), risk = model.OPTIMIZATION_RECORDS[0];
  assert.equal(risk.simplifiedReason, '原创优化');
  assert.equal(risk.officialNotice, original);
  assert.equal(risk.impactNotice, '已记录的状态');
  assert.equal(model.getAccountOptimizationStats('ALL','7days')[0].reasonCounts['多次发布'], 0);
});

test('missing analysis stays unclassified while the warning is still counted', () => {
  const data = fixture();
  data.video_posts = [{id:'raw',post_id:'raw',account_id:'a',post_time:'2026-10-31 18:00:00',data_state:'record',view:100,full_view:.2,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}'}] as OperationsDashboardData['video_posts'];
  data.video_post_punishments = [{id:'r',post_id_or_export_id:'raw',snapshot_date:'2026-11-01',punish_state:'推荐曝光减少',payload_json:JSON.stringify({simplifiedReason:'同质化内容'})}] as OperationsDashboardData['video_post_punishments'];
  const model = createCockpitModel(data), risk = model.OPTIMIZATION_RECORDS[0];
  assert.equal(risk.simplifiedReason, '待归类');
  assert.equal(risk.officialNotice, '');
  assert.equal(risk.severity, '未判定');
  assert.equal(model.VIDEO_TRAFFIC_DATA[0].hasOptimization, true);
  const stat = model.getAccountOptimizationStats('ALL','7days')[0];
  assert.equal(stat.optimizedVideos, 1);
  assert.equal(stat.reasonCounts['待归类'], 1);
});

test('legacy demo severity is not promoted into a platform finding', () => {
  const data = fixture();
  data.video_posts = [{id:'raw',post_id:'raw',account_id:'a',post_time:'2026-10-31 18:00:00',data_state:'record',view:100,full_view:.2,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}'}] as OperationsDashboardData['video_posts'];
  data.video_post_punishments = [{id:'r',post_id_or_export_id:'raw',snapshot_date:'2026-11-01',punish_state:'',payload_json:JSON.stringify({notice:OPTIMIZATION_NOTICE_RULES[0].analysis,generated:true,severity:'严重'})}] as OperationsDashboardData['video_post_punishments'];
  const risk = createCockpitModel(data).OPTIMIZATION_RECORDS[0];
  assert.equal(risk.simplifiedReason, '多次发布');
  assert.equal(risk.severity, '未判定');
  assert.equal(risk.impactNotice, '');
});

function liveHistory(id:string, state:'optimized'|'not_detected'|'unknown'='not_detected') {
  return {id,uid:'u',account_id:'a',post_id:id,publish_time:'2026-10-31 19:30:00',
    publication_state:'published',match_state:'matched',payload_json:'{}',optimization_state:state,
    optimization:state==='optimized'?{analysis:OPTIMIZATION_NOTICE_RULES.find(r=>r.homogeneous)!.analysis,platform_state:'异常',first_seen_at:'2026-11-01'}:null};
}
test('live V3 denominator remains separate from all-account work traffic and survives deletion',()=>{
  const data=fixture();
  data.video_posts=[{id:'outside',post_id:'outside',account_id:'a',post_time:'2026-10-31 20:00:00',view:900,full_view:.1,love_count:2,like_count:3,comment_count:1,forward_count:1,data_state:'record',payload_json:'{}'}] as any;
  data.publication_history=[liveHistory('deleted','optimized'),liveHistory('normal')];
  const model=createCockpitModel(data),s=model.getKPISummary('ALL','ALL','all');
  assert.equal(model.VIDEO_TRAFFIC_DATA.length,1);assert.equal(model.VIDEO_TRAFFIC_DATA[0].views,900);
  assert.equal(s.totalVideos,2);assert.equal(s.overallOptRate,50);assert.equal(s.originalOptRate,50);
  assert.equal(s.totalViews,100);assert.equal(model.HISTORY_VIDEOS[0].accountId,'a');
  assert.equal(model.OPTIMIZATION_RECORDS.length,1);
});
test('missing V3 history or unobserved diagnosis displays unknown instead of zero',()=>{
  const data=fixture();data.publication_history=[];
  assert.equal(createCockpitModel(data).getKPISummary().overallOptRate,null);
  data.publication_history=[liveHistory('p','unknown')];
  const model=createCockpitModel(data);assert.equal(model.getKPISummary().overallOptRate,null);
  assert.equal(model.getAccountOptimizationStats()[0].optimizationRate,null);
  assert.equal(model.getDailyOptimizationTrends('ALL','ALL','all')[0].rate,null);
});
test('pending and ambiguous V3 works do not enter the denominator',()=>{
  const data=fixture();data.publication_history=[{...liveHistory('s'),publication_state:'scheduled'}, {...liveHistory('a'),match_state:'ambiguous'},liveHistory('p')];
  const s=createCockpitModel(data).getKPISummary();assert.equal(s.totalVideos,1);assert.equal(s.overallOptRate,0);
});
test('live full official analysis aliases classify by exact text',()=>{
  for(const rule of OPTIMIZATION_NOTICE_RULES)for(const analysis of rule.aliases||[]){
    const data=fixture();data.publication_history=[{...liveHistory('p','optimized'),optimization:{analysis,platform_state:'异常',first_seen_at:'2026-11-01'}}];
    assert.equal(createCockpitModel(data).OPTIMIZATION_RECORDS[0].simplifiedReason,rule.tag);
  }
});


test('daily export retains all fields and partial days instead of dropping known metrics',()=>{
  const data=fixture();
  data.video_account_daily.push({id:'partial',uid:'u',account_id:'a',stat_date:'2026-10-28',view:123,
    fans_total:100,fans_add:5,fans_net:null,fans_reduce:2,like_count:4,favorite_count:8,comment_count:1,forward_count:3,data_state:'incomplete'} as any);
  const detail=createCockpitModel(data).filterTrafficDetails('ALL','a','all').find(r=>r.id==='partial')!;
  assert.equal(detail.views,123);assert.equal(detail.follows,null);assert.equal(detail.followsAdded,5);
  assert.equal(detail.thumbsUp,8);assert.equal(detail.shares,3);
});


test('work artwork prefers collected cover and names only use the matched publication file', () => {
  const data=fixture();
  data.dramas=[{id:'d',name:'后来改过的剧名',cover_url:'/api/v2/dramas/d/cover'}];
  data.video_posts=[{id:'p',post_id:'p',account_id:'a',post_time:'2026-10-31 18:00:00',data_state:'record',
    view:10,full_view:20,love_count:0,comment_count:0,forward_count:0,like_count:0,
    title:'不能用这个标题代替ID',cover_url:'/api/v3/work-covers/abc',video_url:'https://finder.video.qq.com/video?sign=one',
    video_duration:8,payload_json:JSON.stringify({drama_id:'d',file_name:'不能采用的旧文件名.mp4',episode:1})}
  ] as OperationsDashboardData['video_posts'];
  data.publication_history=[{id:'h',uid:'u',account_id:'a',post_id:'p',publish_time:'2026-10-31 18:00:00',
    publication_state:'published',match_state:'matched',optimization_state:'unknown',optimization:null,
    payload_json:JSON.stringify({name:'当时真正发布的文件名-05.mp4',drama_id:'d'})}];
  const model=createCockpitModel(data),work=model.VIDEO_TRAFFIC_DATA[0];
  assert.equal(work.fileName,'当时真正发布的文件名-05.mp4');
  assert.equal(work.coverUrl,'/api/v3/work-covers/abc');
  assert.equal(work.fallbackCoverUrl,'/api/v2/dramas/d/cover');
  assert.equal(work.videoUrl,data.video_posts[0].video_url);
  assert.equal(work.videoDuration,8);
  data.publication_history[0].account_id='other-account';
  assert.equal(createCockpitModel(data).VIDEO_TRAFFIC_DATA[0].fileName,'作品 p');
  data.publication_history=[];
  data.video_posts[0].cover_url='';
  assert.equal(createCockpitModel(data).VIDEO_TRAFFIC_DATA[0].coverUrl,'/api/v2/dramas/d/cover');
});

test('deleted published works retain their last collected cover and playback address',()=>{
 const data=fixture();
 data.publication_history=[{id:'h',uid:'u',account_id:'a',post_id:'p',publish_time:'2026-10-31 18:00:00',
  publication_state:'published',match_state:'matched',optimization_state:'unknown',optimization:null,
  payload_json:JSON.stringify({name:'原发布文件.mp4',cover_url:'/api/v3/work-covers/abc',video_url:'https://finder.video.qq.com/video?sign=one'})}];
 const work=createCockpitModel(data).HISTORY_VIDEOS[0];
 assert.equal(work.fileName,'原发布文件.mp4');
 assert.equal(work.coverUrl,'/api/v3/work-covers/abc');
 assert.equal(work.videoUrl,'https://finder.video.qq.com/video?sign=one');
});


test('matrix account receives the saved login observation independently of revenue/profile freshness', () => {
  const data = fixture();
  data.accounts[0].login_status = '登录失效'; data.accounts[0].login_checked_at = '2026-11-03T10:00:00+08:00';
  const account = createCockpitModel(data).ACCOUNTS[0];
  assert.equal(account.loginStatus, '登录失效'); assert.equal(account.loginCheckedAt, '2026-11-03T10:00:00+08:00');
  delete data.accounts[0].login_status; delete data.accounts[0].login_checked_at;
  assert.equal(createCockpitModel(data).ACCOUNTS[0].loginStatus, undefined);
});

test('default all-work scope includes official external and deleted works; software switch preserves account daily metrics',()=>{
  const data=fixture();
  const software=liveHistory('software','optimized');
  const external={...liveHistory('external','optimized'),software:false,payload_json:JSON.stringify({title:'官方作品'})};
  const deleted={...liveHistory('deleted'),software:false};
  data.publication_history=[software];
  data.work_history=[{...software,software:true},external,deleted];
  data.video_posts=[{id:'external',post_id:'external',account_id:'a',post_time:external.publish_time,view:999,full_view:.2,love_count:2,like_count:3,comment_count:1,forward_count:1,data_state:'record',payload_json:'{}'}] as any;
  const all=createCockpitModel(data),only=createCockpitModel(data,'software');
  assert.equal(all.workScope,'all');
  assert.equal(all.getKPISummary('ALL','ALL','all').totalVideos,3);
  assert.equal(all.getKPISummary('ALL','ALL','all').optimizedVideos,2);
  assert.equal(only.getKPISummary('ALL','ALL','all').totalVideos,1);
  assert.equal(only.getKPISummary('ALL','ALL','all').optimizedVideos,1);
  assert.equal(only.VIDEO_TRAFFIC_DATA.length,0);
  assert.equal(all.VIDEO_TRAFFIC_DATA.length,1);
  assert.equal(all.getKPISummary().totalViews,only.getKPISummary().totalViews);
  assert.equal(all.getKPISummary().totalRevenue,only.getKPISummary().totalRevenue);
  assert.equal(data.publication_history.length,1);
});

test('pending official notifications remain visible and prevent false complete optimization rates',()=>{
  const data=fixture();data.publication_history=[];data.work_history=[{...liveHistory('external'),software:false}];
  data.pending_optimizations=[{id:'pending',uid:'u',account_id:'a',publish_time:'2026-10-31 19:00:00',export_id:'unlinked',match_state:'pending',analysis:'待核对'}];
  const model=createCockpitModel(data);
  assert.equal(model.pendingOptimizations.length,1);
  assert.equal(model.getKPISummary().overallOptRate,null);
  assert.equal(model.getKPISummary().optimizedVideos,0);
  assert.equal(createCockpitModel(data,'software').pendingOptimizations.length,0);
});

test('pending notification on a day with no retained work still makes interval rate incomplete',()=>{
 const data=fixture();data.publication_history=[];data.work_history=[{...liveHistory('external'),software:false}];
 data.pending_optimizations=[{id:'pending',uid:'u',account_id:'a',publish_time:'2026-10-30 19:00:00',export_id:'deleted-before-collection',match_state:'pending',analysis:''}];
 const model=createCockpitModel(data);
 assert.equal(model.getKPISummary('ALL','ALL','7days').overallOptRate,null);
 assert.equal(model.getAccountOptimizationStats('ALL','7days')[0].optimizationKnown,false);
 assert.equal(model.getKPISummary('ALL','ALL','yesterday').overallOptRate,0);
 assert.equal(model.getAccountRankings('ALL','7days')[0].videoCount,1);
});


test('saved analysis labels reclassify historical badges, counts and analysis descriptions together',()=>{
  const data=fixture();
  const work=liveHistory('labeled','optimized');
  const original=OPTIMIZATION_NOTICE_RULES[0].analysis;
  work.optimization!.analysis=original;
  data.work_history=[{...work,software:false}];
  data.publication_history=[];
  for(const tag of ['同质化','ALL','__proto__','原创优化','待归类']) {
    data.optimization_analysis_configuration={version:1,mappings:[{analysis:original,tag}]};
    const model=createCockpitModel(data);
    assert.equal(model.HISTORY_VIDEOS[0].optimization?.simplifiedReason,tag);
    const stats=model.getAccountOptimizationStats('ALL','all');
    assert.equal(stats[0].reasonCounts[tag],1);
    const summary=summarizeAccountOptimization(stats);
    assert.equal(summary.totalOptimized,1);
    assert.equal(summary.homogeneousCount,tag==='原创优化'?1:0);
    assert.equal(model.getOptimizationReasonDistribution('ALL','ALL','all').find(row=>row.reason===tag)?.count,1);
    assert.ok(model.getOptimizationAnalysisTexts(tag).includes(original));
    assert.ok(!model.getOptimizationAnalysisTexts('多次发布').includes(original));
  }
  delete data.optimization_analysis_configuration;
  assert.equal(createCockpitModel(data).HISTORY_VIDEOS[0].optimization?.simplifiedReason,'多次发布');
  assert.equal(work.optimization!.analysis,original);
});


test('collected missing-link analysis does not display a leftover default suggestion alongside it',()=>{
  const data=fixture();
  const rule=OPTIMIZATION_NOTICE_RULES.find(r=>r.tag==='未挂链接')!;
  const actual=rule.aliases![0];
  const work=liveHistory('missing-link','optimized');
  work.optimization!.analysis=actual;
  data.work_history=[{...work,software:false}];
  data.publication_history=[];
  const model=createCockpitModel(data);
  assert.deepEqual(model.getOptimizationAnalysisTexts('未挂链接'),[actual]);
  const row=model.getOptimizationReasonDistribution('ALL','ALL','all').find(r=>r.reason==='未挂链接')!;
  assert.equal(row.officialNotice,actual);
  assert.equal(row.count,1);
  assert.equal(model.HISTORY_VIDEOS[0].optimization?.officialNotice,actual);
  assert.equal(model.getKPISummary('ALL','ALL','all').optimizedVideos,1);
});


test('each page scope keeps all six current statuses and applies consistently to KPIs, ranking, videos and exports', () => {
  const data=fixture(), base=data.accounts[0], daily=data.video_account_daily[0], income=data.revenue_account_periods[0];
  const states=['正常','观察','限流','二限','实名','封禁','停用','注销'];
  data.accounts=states.map((status,i)=>({...base,id:'scope'+i,channel_id:'uid'+i,status}));
  data.video_account_daily=states.map((_,i)=>({...daily,id:'day'+i,account_id:'scope'+i,uid:'uid'+i,view:100}));
  data.revenue_account_periods=states.map((_,i)=>({...income,id:'income'+i,account_id:'scope'+i,amount:'10'}));
  data.video_posts=states.map((_,i)=>({id:'video'+i,post_id:'post'+i,account_id:'scope'+i,post_time:'2026-10-31 12:00:00',view:100,full_view:0,love_count:0,comment_count:0,forward_count:0,like_count:0,payload_json:'{}',data_state:'record'})) as OperationsDashboardData['video_posts'];
  data.coverage.account_days=8;
  for(const [scope,count] of [['all',8],['current',6],['paused',1],['cancelled',1]] as const) {
    const model=createCockpitModel(data,'all',scope), kpi=model.getKPISummary('ALL','ALL','7days');
    assert.equal(model.ACCOUNTS.length,count,scope);assert.equal(kpi.totalRevenue,count*10,scope);
    assert.equal(kpi.totalViews,count*100,scope);assert.equal(model.getAccountRankings('ALL','7days').length,count,scope);
    assert.equal(model.filterVideos('ALL','ALL','7days').length,count,scope);
    assert.equal(model.filterTrafficDetails('ALL','ALL','7days').length,count,scope);
    assert.equal(model.coverage.account_days,count,scope);
  }
  const statuses=createCockpitModel(data,'all','current').ACCOUNTS.map(a=>a.businessStatus);
  assert.deepEqual(statuses,states.slice(0,6));
  assert.equal(data.accounts.length,8);assert.equal(data.revenue_account_periods.length,8);
});


test('结算后注销仍保留期间收益，结算月累计与覆盖的日收益只计一次',()=>{
  const data=fixture();data.accounts[0].status='注销';
  data.revenue_account_periods.forEach(row=>{row.settlement_state='settled';row.include_in_analysis=0;});
  const model=createCockpitModel(data);
  assert.equal(model.getKPISummary('ALL','ALL','yesterday').totalRevenue,12.3);
  assert.equal(model.getKPISummary('ALL','ALL','all').totalRevenue,80.5);
  assert.equal(model.getAccountRankings('ALL','all')[0].revenue,80.5);
  assert.equal(model.filterRevenue('ALL','ALL','all').length,1);
  assert.equal(createCockpitModel(data,'all','cancelled').getKPISummary('ALL','ALL','all').totalRevenue,80.5);
  assert.equal(createCockpitModel(data,'all','current').getKPISummary('ALL','ALL','all').totalRevenue,0);
});
