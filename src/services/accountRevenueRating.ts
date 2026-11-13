import type { AnalyticsRevenuePeriod } from '../api/analyticsDataBase';
import type { RevenueQueryResult } from '../api/operationsDashboard';
import type { AccountRevenueRating, RevenueAccountTier } from '../types/shortDramaOps.ts';
import { shiftDate } from './cockpitDateRange.ts';
import { beijingDateString } from '../utils/beijingTime.ts';

export const REVENUE_TIER_LIMITS = { SS:5000, S:2000, A:500, B:200 } as const;
export function revenueTier(amount:number):RevenueAccountTier {
  return amount>REVENUE_TIER_LIMITS.SS?'SS':amount>=REVENUE_TIER_LIMITS.S?'S':amount>=REVENUE_TIER_LIMITS.A?'A':amount>=REVENUE_TIER_LIMITS.B?'B':'C';
}
function capturedTime(value:string):number {
  if(!value)return 0;
  const zoned=/([zZ]|[+-]\d{2}:?\d{2})$/.test(value)?value:
    `${value.length===10?value+'T00:00:00':value.replace(' ','T')}+08:00`;
  const time=Date.parse(zoned);return Number.isFinite(time)?time:0;
}
function capturedDay(value:string):string|null {
  const time=capturedTime(value);return time?beijingDateString(new Date(time)):null;
}
export function formatRevenueQueryTime(value:string|null):string {
  const time=value?capturedTime(value):0;
  if(!time)return '—';
  return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(time));
}
function meta(row:AnalyticsRevenuePeriod):Record<string,unknown> {
  try{return JSON.parse(row.raw_result_json||'{}')||{};}catch{return {};}
}
function usable(row:AnalyticsRevenuePeriod) {
  return ['record','confirmed_zero','zero','cached_only'].includes(row.data_state)
    && row.amount!==null && row.amount!==undefined && String(row.amount).trim()!==''
    && Number.isFinite(Number(row.amount)) && Number(row.amount)>=0
    && (!row.currency||row.currency==='CNY') && row.source_kind!=='legacy_v2'
    && !['legacy_unverified','legacy_unknown','expired'].includes(row.freshness_state)
    && (row.include_in_analysis===1||row.settlement_state==='settled');
}
function daily(row:AnalyticsRevenuePeriod) {
  return row.period_type==='day'&&(!row.date_precision||row.date_precision==='day')&&row.period_start===row.period_end;
}
function confirmed(row:AnalyticsRevenuePeriod,today:string) {
  if(!usable(row)||row.period_end>=today)return false;
  const day=capturedDay(row.collected_at),m=meta(row);
  if(!day||day>today||day<=row.period_end)return false;
  if(m.income_updated===false||m.finalized===false||m.update_status==='待更新'||m.update_status==='pending')return false;
  // Published nonempty amounts differ from empty or ambiguous zero responses.
  return Number(row.amount)>0||row.data_state==='confirmed_zero'||m.income_updated===true||m.finalized===true
    ||(row.source_kind==='development_seed'&&m.generated===true);
}
function newer(a:{id:string;collected_at:string},b:{id:string;collected_at:string}) {
  return capturedTime(a.collected_at)>capturedTime(b.collected_at)
    ||(capturedTime(a.collected_at)===capturedTime(b.collected_at)&&a.id>b.id);
}

/** Value, operating phase and query freshness are encoded in one account label. */
export function rateAccountRevenue(input:{
  accountId:string;theaterId:string;status:string;today:string;periods:AnalyticsRevenuePeriod[];
  queries?:RevenueQueryResult[];firstPublishDate?:string;
}):AccountRevenueRating {
  const {accountId,theaterId,status,today,firstPublishDate}=input,yesterday=shiftDate(today,-1);
  const rows=input.periods.filter(r=>r.account_id===accountId&&(!r.theater_id||r.theater_id===theaterId)
    &&r.period_end<=yesterday&&/^\d{4}-\d{2}-\d{2}$/.test(r.period_end));
  const byDay=new Map<string,AnalyticsRevenuePeriod>();
  const goodDays=new Map<string,AnalyticsRevenuePeriod>();
  const months=new Map<string,AnalyticsRevenuePeriod>();
  for(const row of rows) {
    if(daily(row)) {
      const old=byDay.get(row.period_end);if(!old||newer(row,old))byDay.set(row.period_end,row);
      if(confirmed(row,today)) {
        const good=goodDays.get(row.period_end);if(!good||newer(row,good))goodDays.set(row.period_end,row);
      }
    } else if(row.period_type==='month_cumulative'&&row.period_start<=row.period_end&&confirmed(row,today)) {
      const key=`${row.period_start}:${row.period_end}`,old=months.get(key);
      if(!old||newer(row,old))months.set(key,row);
    }
  }
  const days=[...goodDays.values()].sort((a,b)=>a.period_end.localeCompare(b.period_end));
  const relevantDays=days.filter(r=>!firstPublishDate||r.period_end>=firstPublishDate||Number(r.amount)>0);
  const latest=relevantDays.at(-1);
  const acceptedMonths:AnalyticsRevenuePeriod[]=[];
  for(const row of [...months.values()].sort((a,b)=>b.period_end.localeCompare(a.period_end))) {
    if(acceptedMonths.some(m=>row.period_start<=m.period_end&&row.period_end>=m.period_start))continue;
    acceptedMonths.push(row);
  }
  const uncovered=days.filter(d=>!acceptedMonths.some(m=>d.period_end>=m.period_start&&d.period_end<=m.period_end));
  const financialFacts=[...uncovered,...acceptedMonths];
  const recordedTotal=financialFacts.length?financialFacts.reduce((sum,r)=>sum+Math.round(Number(r.amount)*100),0)/100:null;
  const confirmedThrough=financialFacts.map(r=>r.period_end).sort().at(-1)||null;
  const fullObservation=relevantDays.filter(r=>firstPublishDate&&r.period_end>firstPublishDate);
  const trialFinished=fullObservation.some(r=>goodDays.has(shiftDate(r.period_end,-1))&&shiftDate(r.period_end,-1)>firstPublishDate!);
  const tier:RevenueAccountTier=recordedTotal!==null&&(recordedTotal>=REVENUE_TIER_LIMITS.B||trialFinished)?revenueTier(recordedTotal):'待评';
  const peak=relevantDays.length?relevantDays.map(r=>({date:r.period_end,amount:Number(r.amount)})).reduce((a,b)=>b.amount>a.amount?b:a):null;

  // Advance by confirmed revenue dates, not by midnight or by the latest query timestamp.
  let phase:AccountRevenueRating['phase']=firstPublishDate&&firstPublishDate>=yesterday?'试投':'待判';
  let phaseReason=phase==='试投'?'尚无足够的已确认日收益，等待试投数据。':'日收益依据不足，运营阶段暂不判断；已确认累计仍可用于收益分级。';
  let hadOutput=false;
  for(let i=0;i<relevantDays.length;i++) {
    const row=relevantDays[i],amount=Number(row.amount),date=row.period_end;
    const prev=goodDays.get(shiftDate(date,-1)),prevAmount=prev?Number(prev.amount):null;
    const priorOutput=hadOutput;
    if(amount>=500){phase='爆发';phaseReason=`${date} 已确认单日收益达到¥500。`;}
    else if(priorOutput&&prevAmount!==null&&amount<10&&prevAmount<10){phase='尾量';phaseReason=`截至${date}，连续两个确认收益日不足¥10，保留历史收益等级。`;}
    else if(amount>=10&&(prevAmount===null?!priorOutput:prevAmount===0||amount>=prevAmount*1.3)){phase='起量';phaseReason=`${date} 收益出现明确增长或首次有效产出。`;}
    else if(priorOutput&&prevAmount!==null&&amount<=Math.max(prevAmount,...relevantDays.slice(Math.max(0,i-2),i).filter(r=>r.period_end>=shiftDate(date,-2)).map(r=>Number(r.amount)))*.7){phase='回落';phaseReason=`${date} 收益较近期高点下降至少30%。`;}
    else if(prevAmount!==null&&(!firstPublishDate||shiftDate(date,-1)>firstPublishDate)){phase='平稳';phaseReason=`截至${date}，连续日收益没有达到起量或回落条件。`;}
    else if(amount>=10){phase='平稳';phaseReason=`${date} 有已确认产出；相邻日数据不足，不推断涨跌。`;}
    hadOutput ||= amount>=10;
  }
  const previous=latest?goodDays.get(shiftDate(latest.period_end,-1)):undefined;
  const review=!!latest&&!!previous&&trialFinished&&recordedTotal!==null&&recordedTotal<REVENUE_TIER_LIMITS.B
    &&Number(latest.amount)<10&&Number(previous.amount)<10&&!hadOutput;
  const lastValid=latest?{date:latest.period_end,amount:Number(latest.amount)}:null;
  const anchor=latest?.period_end||yesterday;
  const recentDays:AccountRevenueRating['recentDays']=[-2,-1,0].map(offset=>{
    const date=shiftDate(anchor,offset),good=goodDays.get(date),raw=byDay.get(date);
    const relevant=good&&(!firstPublishDate||date>=firstPublishDate||Number(good.amount)>0);
    return {date,amount:relevant?Number(good!.amount):null,state:relevant?'record':!raw?'missing':!usable(raw)?'failed':'partial'};
  });
  const queries=(input.queries||[]).filter(q=>q.account_id===accountId&&(!q.theater_id||q.theater_id===theaterId)
    &&(!['day','date_range'].includes(q.period_type)||q.revenue_date<=yesterday));
  const latestQuery=queries.reduce<RevenueQueryResult|null>((old,q)=>!old||capturedTime(q.collected_at)>capturedTime(old.collected_at)
    ||(capturedTime(q.collected_at)===capturedTime(old.collected_at)&&(q.revenue_date>old.revenue_date||(q.revenue_date===old.revenue_date&&q.id>old.id)))?q:old,null);
  const latestRow=rows.reduce<AnalyticsRevenuePeriod|null>((old,r)=>!old||newer(r,old)?r:old,null);
  const queryIsLatest=!!latestQuery&&(!latestRow||capturedTime(latestQuery.collected_at)>=capturedTime(latestRow.collected_at));
  const lastQueryAt=queryIsLatest?latestQuery!.collected_at:latestRow?.collected_at||null;
  const failed=queryIsLatest?['failed','error'].includes(latestQuery!.collection_status):!!latestRow&&['failed','error'].includes(latestRow.data_state);
  const hasUnconfirmedTarget=queryIsLatest?latestQuery!.revenue_date>=yesterday&&['no_data','pending','indeterminate','unavailable'].includes(latestQuery!.collection_status)
    :!!byDay.get(yesterday)&&!confirmed(byDay.get(yesterday)!,today);
  const updateStatus:AccountRevenueRating['updateStatus']=failed?'查询失败':!hasUnconfirmedTarget&&confirmedThrough===yesterday?'已更新':'待更新';
  const updateReason=failed?(latestQuery?.error_message||'最近收益查询失败，已有等级、阶段与收益记录保留。')
    :updateStatus==='已更新'?`已取得截至${yesterday}的有效收益。`
    :`${yesterday}收益尚未确认更新${confirmedThrough?`；已有收益截至${confirmedThrough}`:''}。不将等待更新计为零收益。`;
  if(status==='停用'){phase='停用';phaseReason='账号已人工停用，累计收益等级及历史成绩保留。';}
  const reason=recordedTotal===null?'尚无可确认的累计收益。':tier==='待评'?`已确认累计¥${recordedTotal.toFixed(2)}，试投观察数据尚不足。`
    :`按已确认累计收益¥${recordedTotal.toFixed(2)}评为${tier}级；正常回落不降级，跨月不清零。`;
  return {tier,phase,updateStatus,confirmedThrough,lastQueryAt,updateReason,reason,phaseReason,lastValid,peak,recordedTotal,
    recentDays,recentTotal:Math.round(recentDays.reduce((sum,r)=>sum+(r.amount||0),0)*100)/100,
    recentComplete:recentDays.every(r=>r.amount!==null),
    reviewReason:review&&status!=='停用'?`试投后累计仍不足¥${REVENUE_TIER_LIMITS.B}，最近两个确认日均不足¥10且一直未明显起量，建议人工复核；不会自动停用。`:null};
}
