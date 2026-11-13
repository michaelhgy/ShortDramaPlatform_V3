import type { VideoTrafficItem } from '../types/shortDramaOps';

export type VideoTrafficStatus='待采集'|'观察中'|'待起量'|'低播'|'常规'|'小爆'|'爆款'|'大爆';
export const VIDEO_TRAFFIC_RULES:ReadonlyArray<{status:VideoTrafficStatus;rule:string}>=[
  {status:'待采集',rule:'缺少有效播放数据，或还未采到覆盖满24小时的数据'},
  {status:'观察中',rule:'发布不足12小时，累计播放不足1000'},
  {status:'待起量',rule:'发布满12小时、不足24小时，累计播放不足1000'},
  {status:'低播',rule:'发布满24小时后已有有效采集，累计播放仍不足1000'},
  {status:'常规',rule:'累计播放1000—不足3万'},
  {status:'小爆',rule:'累计播放3万—不足5万'},
  {status:'爆款',rule:'累计播放5万—不足10万'},
  {status:'大爆',rule:'累计播放达到10万'},
];
const HOUR=60*60*1000;
type VideoFacts=Pick<VideoTrafficItem,'views'|'publishTime'|'statsCollectedAt'|'statsDate'|'statsState'>;
export interface VideoTrafficRating {
  status:VideoTrafficStatus;
  reason:string;
  rule:string;
  asOf:string|null;
  nextEvaluationAt?:number;
}
function instant(value:string|undefined):number|null {
  if(!value||!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value))return null;
  const parsed=Date.parse(/([zZ]|[+-]\d{2}:?\d{2})$/.test(value)?value:value.replace(' ','T')+'+08:00');
  return Number.isFinite(parsed)?parsed:null;
}

/** Cumulative reach is independent of completion rate and platform penalties. */
export function rateVideoTraffic(video:VideoFacts,now=Date.now()):VideoTrafficRating {
  const exact=!!video.statsCollectedAt;
  const asOf=video.statsCollectedAt||(video.statsDate?video.statsDate+'T00:00:00+08:00':null);
  const captured=instant(asOf||undefined),published=instant(video.publishTime);
  const result=(status:VideoTrafficStatus,reason:string,nextEvaluationAt?:number):VideoTrafficRating=>({
    status,reason,rule:VIDEO_TRAFFIC_RULES.find(r=>r.status===status)!.rule,asOf,nextEvaluationAt,
  });
  if(!Number.isFinite(now)||typeof video.views!=='number'||!Number.isFinite(video.views)||video.views<0
    ||(video.statsState&&!['record','confirmed_zero','zero','cached_only'].includes(video.statsState))) {
    return result('待采集','没有可用的播放记录；不把缺失或失败当作零播放。');
  }
  if((asOf&&captured===null)||(captured!==null&&captured>now)
    ||(published!==null&&published>now)||(exact&&captured!==null&&published!==null&&captured<published)) {
    return result('待采集','发布时间或采集时间尚无法确认，暂不判断表现。');
  }
  for(const [threshold,status] of [[100000,'大爆'],[50000,'爆款'],[30000,'小爆'],[1000,'常规']] as const) {
    if(video.views>=threshold)return result(status,`已记录累计播放 ${video.views.toLocaleString('zh-CN')} 次；达到门槛即升级。`);
  }
  if(published===null)return result('待采集','发布时间不明确，不据此判断观察期或低播。');
  const age=now-published;
  if(age<12*HOUR)return result('观察中','发布不足12小时，先观察，不提前判低播。',published+12*HOUR);
  if(age<24*HOUR)return result('待起量','已过12小时观察期，尚未满24小时，继续等待表现。',published+24*HOUR);
  if(captured===null||captured-published<24*HOUR) {
    return result('待采集','发布已满24小时，但尚无覆盖满24小时的有效采集，不能据旧值判低播。');
  }
  return result('低播','满24小时后的有效采集仍不足1000播放；低播不代表平台限流。');
}
