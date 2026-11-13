import test from 'node:test';
import assert from 'node:assert/strict';
import { collectionProfiles, needsCollection, projectedJobRows, mergeRetryRows, planSummary, collectionStatusRows, taskAccountIds, collectionAccountSelectable, scenarioCategories } from './geminiCollectionModel.ts';
import type { AccountInfo } from '../../types/shortDramaOps.ts';
import type { CollectionState, CollectionJob } from '../../api/operationsDashboard.ts';
const accounts = [{id:'a', name:'真实甲', theaterName:'九州剧场', videoTotal:null, followerTotal:null}, {id:'b',name:'真实乙',theaterName:'其他'}] as AccountInfo[];
const state = {yesterday:'2026-11-02',job:null,accounts:[{id:'a',uid:'u',available:true,last_success:{},daily_state:'complete',daily_boundary:'2026-10-01',daily_through:'2026-11-02',daily_missing:0,profile_total:{postCount:0,fans:9},profile_source_time:'2026-11-01 12:00:00'}]} as CollectionState;
test('账号完整性、零作品和来源时间由真实元数据取得，不按剧场或账号位置生成演示数据',()=>{
 const p=collectionProfiles(accounts,state)[0]; assert.equal(p.dailyGapState,'complete');assert.equal(p.videoTotalCount,0);assert.equal(p.followerCount,9);assert.equal(p.profileSourceTime,'2026-11-01 12:00:00');assert.equal(p.revenueMode,'unknown');assert.equal(p.uncollectedOptimizationCount,null);
});
test('缺元数据保持未知，无法采集不进入智能选择；过期完整日不能当昨日完整',()=>{
 const missing=collectionProfiles(accounts,null)[0];assert.equal(missing.dailyGapState,'unknown');assert.equal(missing.videoTotalCount,null);assert.equal(needsCollection(missing),false);
 const old=collectionProfiles(accounts,{...state,accounts:[{...state.accounts[0],daily_through:'2026-11-01'}]})[0];assert.notEqual(old.dailyGapState,'complete');
});
test('预演不能编造日期范围页数或为未知作品数量补300条',()=>{
 const profiles=collectionProfiles(accounts,state);const enabled={daily_stats:false,video_traffic:true,optimization:false,revenue:false};
 assert.equal(planSummary(profiles,new Set(['a']),enabled,'smart_gap','publish_7d').estimatedVideoPages,null);
 profiles[0].videoTotalCount=null;assert.equal(planSummary(profiles,new Set(['a']),enabled,'smart_gap','all_pages').estimatedVideoPages,null);
 profiles[0].videoTotalCount=81;assert.equal(planSummary(profiles,new Set(['a']),enabled,'smart_gap','all_pages').estimatedVideoPages,3);
});
test('真实任务状态映射，失败/停止/部分完成不变成成功，结果原文保留',()=>{
 const items=[{account_id:'a',account_name:'真实甲',category:'works',status:'success',message:'已保存作品'}, {account_id:'b',account_name:'真实乙',category:'works',status:'stopped',message:'已停止，保留原值'}];
 const rows=projectedJobRows({items} as CollectionJob,collectionProfiles(accounts,state));assert.equal(rows[0].overallStatus,'completed');assert.equal(rows[1].overallStatus,'stopped');assert.equal(rows[1].categories.video_traffic?.summaryText,'已停止，保留原值');
});
test('单号重试合并保留其他账号及同账号成功类别，不伪造新入库分类',()=>{
 const profiles=collectionProfiles(accounts,state);
 const before=projectedJobRows({items:[{account_id:'a',account_name:'甲',category:'daily',status:'skipped',message:'已完整'}, {account_id:'a',account_name:'甲',category:'works',status:'failed',message:'失败'},{account_id:'b',account_name:'乙',category:'daily',status:'success',message:'完成'}]} as CollectionJob,profiles);
 const after=projectedJobRows({items:[{account_id:'a',account_name:'甲',category:'works',status:'success',message:'保存'}]} as CollectionJob,profiles);
 const combined=mergeRetryRows(before,after);assert.equal(combined.length,2);assert.equal(combined[0].categories.daily_stats?.status,'skipped');assert.equal(combined[0].categories.video_traffic?.status,'updated');assert.equal(combined[1].overallStatus,'completed');
});

test('重新打开重试任务仍展示未选中的失败项和已完成项，当前结果覆盖原状态',()=>{
 const cell=(id:string,status:string)=>({id:id+':works',account_id:id,account_name:id,category:'works',status,message:status});
 const job={retained_items:[cell('a','failed'),cell('b','failed')],items:[cell('b','success')]} as CollectionJob;
 const rows=projectedJobRows(job,collectionProfiles(accounts,state));
 assert.equal(rows.length,2);assert.equal(rows.find(row=>row.accountId==='a')?.overallStatus,'failed');assert.equal(rows.find(row=>row.accountId==='b')?.overallStatus,'completed');
});

test('已检测过的账号到达下一周期仍需检测，未到期时不把旧记录当新任务',()=>{
  const meta={...state.accounts[0],last_success:{optimization:'2026-11-03T09:00:00+08:00'}};
  assert.equal(collectionProfiles(accounts,{...state,accounts:[{...meta,optimization_due:true}]})[0].optimizationNeedsCheck,true);
  assert.equal(collectionProfiles(accounts,{...state,accounts:[{...meta,optimization_due:false}]})[0].optimizationNeedsCheck,false);
});

test('收益状态来自实际账号绑定，预演区分补历史、更新、跳过与缺配置',()=>{
 const meta={...state.accounts[0],revenue:{available:true,mode:'daily' as const,state:'backfill' as const,collector_name:'青柠绿泡泡',message:'历史待补齐'}};
 const p=collectionProfiles(accounts,{...state,accounts:[meta]});
 assert.equal(p[0].revenueCollectorName,'青柠绿泡泡');assert.equal(p[0].revenueMode,'daily');assert.equal(p[0].revenueUnupdated,true);
 const s=planSummary(p,new Set(['a']),{daily_stats:false,video_traffic:false,optimization:false,revenue:true},'smart_gap','all_pages');
 assert.equal(s.revenueBackfillCount,1);assert.equal(s.revenueCompleteCount,0);
 const done=collectionProfiles(accounts,{...state,accounts:[{...meta,revenue:{...meta.revenue,state:'complete',message:'截至昨日已完成'}}]});
 assert.equal(done[0].revenueUnupdated,false);assert.equal(planSummary(done,new Set(['a']),{daily_stats:false,video_traffic:false,optimization:false,revenue:true},'smart_gap','all_pages').revenueCompleteCount,1);
});

test('收益待更新和查询失败分开显示，二者均保留重试状态',()=>{
 const base={id:'a:revenue',account_id:'a',account_name:'甲',category:'revenue',status:'partial',message:'1天待更新',revenue_result:{pending_days:1,failed_days:0,history_pending:true,empty_days:0,saved_days:0,skipped_days:0}};
 const rows=projectedJobRows({items:[base]} as CollectionJob,collectionProfiles(accounts,state));
 assert.equal(rows[0].categories.revenue?.status,'source_unupdated');assert.equal(rows[0].overallStatus,'partial');
 const failed=projectedJobRows({items:[{...base,status:'failed',revenue_result:{...base.revenue_result,pending_days:0,failed_days:1}}]} as CollectionJob,collectionProfiles(accounts,state));
 assert.equal(failed[0].categories.revenue?.status,'failed');
});

test('四类采集状态顺序固定；作品时间不冒充全量完整，缺失状态不造完成',()=>{
 const s={...state,accounts:[{...state.accounts[0],last_success:{works:'2026-11-03T09:30:00+08:00',optimization:'2026-11-03T08:10:00+08:00'}}]};
 const rows=collectionStatusRows(collectionProfiles(accounts,s)[0],s);
 assert.deepEqual(rows.map(r=>r.label),['昨日数据','视频流量','优化记录','剧场收益']);
 assert.equal(rows[0].text,'完整至 11-02');assert.match(rows[1].text,/上次.*09:30/);assert.match(rows[1].detail,/不表示全部作品已更新/);assert.match(rows[2].text,/检测.*08:10/);assert.equal(rows[3].text,'未配置收益采集器');
 const empty=collectionStatusRows(collectionProfiles(accounts,null)[0],null);assert.equal(empty[1].text,'尚未采集');assert.equal(empty[2].text,'尚未检测');
});
test('四类状态各自显示失败或待更新，不把整账号标失败，也不遮住收益缺配置',()=>{
 const base={...state,job:{items:[{id:'a:works',account_id:'a',category:'works',status:'failed',message:'网络断开'}]} as CollectionJob};
 const rows=collectionStatusRows(collectionProfiles(accounts,base)[0],base);
 assert.equal(rows[0].text,'完整至 11-02');assert.equal(rows[1].text,'查询失败');assert.match(rows[1].detail,/网络断开/);assert.equal(rows[3].text,'未配置收益采集器');
});


test('场景只配置对应类别，日常补齐不带优化，收益未接入不伪装可选',()=>{
 assert.deepEqual(scenarioCategories('daily_routine'),{daily_stats:true,video_traffic:false,optimization:false,revenue:true});
 assert.deepEqual(scenarioCategories('optimization_now'),{daily_stats:false,video_traffic:false,optimization:true,revenue:false});
 assert.equal(scenarioCategories('daily_routine',false).revenue,false);
});
test('推荐跟随当前任务，其他类别失败不误入，强制重置包含完整日',()=>{
 const p=collectionProfiles(accounts,state), daily=scenarioCategories('daily_routine',false);
 assert.deepEqual(taskAccountIds(p,daily,'smart_gap'),[]);
 assert.deepEqual(taskAccountIds(p,daily,'reset_online'),['a']);
 const failed=collectionProfiles(accounts,{...state,job:{items:[{account_id:'a',category:'works',status:'failed'}]} as CollectionJob});
 assert.deepEqual(taskAccountIds(failed,daily,'smart_gap'),[]);
 assert.deepEqual(taskAccountIds(p,scenarioCategories('targeted_video_7d'),'smart_gap'),['a']);
 assert.deepEqual(taskAccountIds(p,scenarioCategories('optimization_now'),'smart_gap'),['a']);
});
test('多类别推荐取并集，收益独立于平台绑定，范围仅由传入列表决定',()=>{
 const meta={...state.accounts[0],revenue:{available:true,mode:'daily' as const,state:'backfill' as const,collector_name:'来源',message:'历史待补齐'}};
 const s={...state,accounts:[meta,{...meta,id:'b',uid:'v',platform_available:false}]}, p=collectionProfiles(accounts,s);
 assert.deepEqual(taskAccountIds(p,scenarioCategories('daily_routine'),'smart_gap'),['a','b']);
 assert.deepEqual(taskAccountIds(p.slice(1),scenarioCategories('revenue_only'),'smart_gap'),['b']);
 assert.deepEqual(taskAccountIds(p,scenarioCategories('optimization_now'),'smart_gap'),['a']);
 assert.deepEqual(taskAccountIds(p.map(x=>({...x,revenueUnupdated:false})),scenarioCategories('revenue_only'),'smart_gap'),[]);
});

test('配置和记录共用登录排序，有效最前、未知中间、失效最后；同组保持顺序',()=>{
 const source=[{id:'bad',name:'失效',loginStatus:'登录失效'},{id:'unknown',name:'未知'},{id:'good',name:'有效',loginStatus:'登录有效'},{id:'unknown2',name:'未知2',loginStatus:'新状态'}] as AccountInfo[];
 assert.deepEqual(collectionProfiles(source,null).map(p=>p.account.id),['good','unknown','unknown2','bad']);
 const newer={...state,accounts:[{...state.accounts[0],id:'bad',login_status:'登录有效'},{...state.accounts[0],id:'good',login_status:'登录失效'}]};
 assert.deepEqual(collectionProfiles(source,newer).map(p=>p.account.id),['bad','unknown','unknown2','good']);
 assert.equal(source[0].loginStatus,'登录失效');
});


test('登录失效只影响默认推荐，手动选择和预演保留；只采收益不看登录',()=>{
 const meta={...state.accounts[0],login_status:'登录失效',revenue:{available:true,mode:'daily' as const,state:'backfill' as const,collector_name:'剧场',message:'历史待补齐'}};
 const profiles=collectionProfiles([accounts[0]],{...state,accounts:[meta]});const p=profiles[0];
 assert.equal(p.videoTotalCount,0);assert.equal(p.followerCount,9);
 for(const scenario of ['targeted_video_7d','optimization_now','daily_routine'] as const){
  const enabled=scenarioCategories(scenario);
  assert.deepEqual(taskAccountIds(profiles,enabled,'smart_gap'),scenario==='daily_routine'?['a']:[]);
  assert.equal(collectionAccountSelectable(p,enabled),true);
  assert.equal(planSummary(profiles,new Set(['a']),enabled,'reset_online','all_pages').selectedCount,1);
 }
 assert.deepEqual(taskAccountIds(profiles,scenarioCategories('daily_routine',false),'reset_online'),[]);
 assert.deepEqual(taskAccountIds(profiles,scenarioCategories('revenue_only'),'smart_gap'),['a']);
 assert.equal(collectionAccountSelectable(p,scenarioCategories('revenue_only')),true);
 assert.equal(planSummary(profiles,new Set(['a']),scenarioCategories('revenue_only'),'smart_gap','all_pages').revenueReadyCount,1);
 assert.ok(collectionStatusRows(p,null).slice(0,3).every(row=>row.text==='登录待核对'));
 assert.equal(collectionStatusRows(p,null)[3].text,'历史待补齐');
 const noRevenue=collectionProfiles([accounts[0]],{...state,accounts:[{...meta,revenue:undefined}]})[0];
 assert.equal(noRevenue.available,true);
 assert.equal(collectionAccountSelectable(noRevenue,scenarioCategories('revenue_only')),false);
 const done={...p,revenueUnupdated:false};
 assert.deepEqual(taskAccountIds([done],scenarioCategories('revenue_only'),'smart_gap'),[]);
});

test('失效账号没有平台绑定时仍可单独采收益，未知状态不当成失效',()=>{
 const meta={...state.accounts[0],login_status:'登录失效',platform_available:false,revenue:{available:true,mode:'daily' as const,state:'missing' as const,collector_name:'剧场',message:'待补齐'}};
 const p=collectionProfiles([accounts[0]],{...state,accounts:[meta]})[0];
 assert.equal(collectionAccountSelectable(p,scenarioCategories('targeted_video_7d')),false);
 assert.equal(collectionAccountSelectable(p,scenarioCategories('revenue_only')),true);
 assert.deepEqual(taskAccountIds([p],scenarioCategories('revenue_only'),'smart_gap'),['a']);
 const unknown={...p,platformAvailable:true,account:{...p.account,loginStatus:undefined}};
 assert.deepEqual(taskAccountIds([unknown],scenarioCategories('targeted_video_7d'),'smart_gap'),['a']);
});


test('近期收益暂无数据仍显示待复查，不能计入已完成跳过',()=>{
 const meta={...state.accounts[0],revenue:{available:true,mode:'daily' as const,state:'missing' as const,collector_name:'青柠端原生',message:'1 天暂无数据，间隔未到，稍后复查'}};
 const profiles=collectionProfiles(accounts,{...state,accounts:[meta]});
 assert.equal(profiles[0].revenueUnupdated,true);
 assert.equal(profiles[0].revenueStatusDesc,meta.revenue.message);
 const summary=planSummary(profiles,new Set(['a']),{daily_stats:false,video_traffic:false,optimization:false,revenue:true},'smart_gap','all_pages');
 assert.equal(summary.revenueCompleteCount,0);
 assert.equal(summary.revenueMissingCount,1);
});


test('停用默认保留收益收尾，平台推荐排除停用，注销即使旧元数据可用也不可采',()=>{
  const states=['正常','观察','限流','二限','实名','封禁','停用','注销'];
  const source=states.map((businessStatus,i)=>({...accounts[0],id:'status'+i,businessStatus,loginStatus:'登录有效'}));
  const metadata=source.map(account=>({...state.accounts[0],id:account.id,uid:'uid'+account.id,platform_available:true,
    daily_state:'unknown',daily_through:undefined,revenue:{available:true,mode:'daily' as const,state:'missing' as const,collector_name:'测试来源',message:'待补齐'}}));
  const profiles=collectionProfiles(source,{...state,accounts:metadata});
  assert.deepEqual(taskAccountIds(profiles,scenarioCategories('targeted_video_7d'),'smart_gap'),source.slice(0,6).map(a=>a.id));
  assert.deepEqual(taskAccountIds(profiles,scenarioCategories('revenue_only'),'smart_gap'),source.slice(0,7).map(a=>a.id));
  assert.deepEqual(taskAccountIds(profiles,scenarioCategories('daily_routine'),'smart_gap'),source.slice(0,7).map(a=>a.id));
  const paused=profiles.find(p=>p.account.businessStatus==='停用')!, cancelled=profiles.find(p=>p.account.businessStatus==='注销')!;
  assert.equal(collectionAccountSelectable(paused,scenarioCategories('targeted_video_7d')),true);
  assert.equal(collectionAccountSelectable(cancelled,scenarioCategories('revenue_only')),false);
  assert.equal(collectionAccountSelectable(cancelled,scenarioCategories('targeted_video_7d')),false);
  const enabled=scenarioCategories('daily_routine'),selected=new Set([paused.account.id]);
  assert.equal(planSummary([paused],selected,enabled,'smart_gap','all_pages',new Set()).dailyNeedFetchCount,0);
  assert.equal(planSummary([paused],selected,enabled,'smart_gap','all_pages',selected).dailyNeedFetchCount,1);
});

test('混合采集中登录失效仍可推荐未完成的收益，平台项不作为推荐依据',()=>{
 const meta={...state.accounts[0],login_status:'登录失效',revenue:{available:true,mode:'daily' as const,state:'missing' as const,collector_name:'来源',message:'待补齐'}};
 const profiles=collectionProfiles([accounts[0]],{...state,accounts:[meta]});
 assert.deepEqual(taskAccountIds(profiles,scenarioCategories('daily_routine'),'smart_gap'),['a']);
 assert.deepEqual(taskAccountIds(profiles,scenarioCategories('targeted_video_7d'),'smart_gap'),[]);
});


test('采集面板使用最新本地状态，档案页旧快照不能重新选入注销账号',()=>{
 const meta={...state.accounts[0],business_status:'注销',available:true,platform_available:true,revenue:{available:true,mode:'daily' as const,state:'missing' as const,collector_name:'来源',message:'待补齐'}};
 const [profile]=collectionProfiles([accounts[0]],{...state,accounts:[meta]});
 assert.equal(profile.account.businessStatus,'注销');assert.equal(profile.available,false);
 assert.deepEqual(taskAccountIds([profile],scenarioCategories('daily_routine'),'smart_gap'),[]);
});
