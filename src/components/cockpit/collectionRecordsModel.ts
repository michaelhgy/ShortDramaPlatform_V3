import type { CollectionCategory, CollectionRecordSummary, CollectionState, CollectionJob } from '../../api/operationsDashboard';
export const recordCategories = [{key:'daily',label:'昨日数据'},{key:'works',label:'视频流量'},{key:'optimization',label:'优化检测'},{key:'revenue',label:'剧场收益'}] as const;
export function recordStatus(record: CollectionRecordSummary): {label:string;tone:'muted'|'ready'|'warning'|'danger'|'active'} {
 const i=record.item;
 if(i.status==='running')return {label:'正在采集',tone:'active'};
 if(i.status==='waiting')return {label:'排队中',tone:'active'};
 if(i.status==='success')return {label:i.category==='revenue'&&i.revenue_result?.empty_days&&!i.revenue_result.saved_days?'无收益记录':'已完成',tone:'ready'};
 if(i.status==='skipped')return {label:'已跳过',tone:'muted'};
 if(i.status==='failed'||(i.status==='partial'&&i.revenue_result?.failed_days&&!i.revenue_result.saved_days&&!i.revenue_result.empty_days&&!i.revenue_result.pending_days))return {label:'查询失败',tone:'danger'};
 if(i.status==='stopped')return {label:'已停止',tone:'warning'};
 if(i.revenue_result?.pending_days && !i.revenue_result.failed_days)return {label:'来源待更新',tone:'warning'};
 return {label:'待继续',tone:'warning'};
}
export function latestAccountRecords(state:CollectionState|null) {
 const map=new Map<string,CollectionRecordSummary>();
 for(const r of state?.record_summaries || [])map.set(r.item.account_id+':'+r.item.category,r);
 // Current attempt only; retained items are earlier attempts and must not get a new timestamp.
 for(const item of state?.job?.items || []){
  if(item.category==='profile')continue;
  map.set(item.account_id+':'+item.category,{job_id:state!.job!.id,source:state!.job!.source||'unknown',started_at:state!.job!.started_at,item});
 }
 return map;
}
export const recordSource=(s:string)=>s==='manual'?'手动采集':s==='automatic'?'自动检测':s==='retry'?'重试／续采':'来源未记录';
export function recordScope(options:CollectionJob['options'],category:CollectionCategory) {
 if(category==='works'){const scope=options.scope?.works;return scope?.mode==='published_range'?`${scope.start_date} 至 ${scope.end_date} 发布作品`:'全部作品';}
 if(category==='daily')return options.scope?.daily?.mode==='reset_online'?'强制在线重置，补齐历史':'补齐历史与缺失日';
 return category==='revenue'?'自动补历史与缺失收益':'检测优化并保存作品分析';
}

export const recordStartedAt=(r:CollectionRecordSummary)=>r.item.started_at||r.started_at;
export function recordRevenueSummary(r:CollectionRecordSummary) {
 const v=r.item.category==='revenue'?r.item.revenue_result:undefined;
 if(!v||v.saved_amount===undefined)return '';
 const parts=[v.collector_name||'剧场收益',`本次入账 ¥${v.saved_amount}`];
 if(v.mode==='cumulative') {
  if(v.source_amount!=null)parts.push(`来源累计 ¥${v.source_amount}${v.source_period&&v.source_period!=='unknown'?'（'+v.source_period+'）':''}`);
  if(v.query_end)parts.push(`入账日期 ${v.query_end}`);
 } else if(v.query_start&&v.query_end)parts.push(`查询日期 ${v.query_start===v.query_end?v.query_end:v.query_start+' 至 '+v.query_end}`);
 return parts.join('；');
}
