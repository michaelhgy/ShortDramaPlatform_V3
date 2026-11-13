import {OFFICIAL_OPTIMIZATION_DEFINITIONS,type AccountOptimizationStat,type SimplifiedOptimizationReason} from '../types/shortDramaOps.ts';

/** Both rates use all works in the selected account scope, never only warned works. */
export function summarizeAccountOptimization(stats:AccountOptimizationStat[]) {
  const reasons=[...new Set([...Object.keys(OFFICIAL_OPTIMIZATION_DEFINITIONS),...stats.flatMap(stat=>Object.keys(stat.reasonCounts))])] as SimplifiedOptimizationReason[];
  const reasonTotals=Object.fromEntries(reasons.map(reason=>[reason,0])) as Record<SimplifiedOptimizationReason,number>;
  let totalPublished=0,totalOptimized=0;
  for(const stat of stats) {
    totalPublished+=stat.totalVideos;
    totalOptimized+=stat.optimizedVideos;
    for(const reason of reasons)reasonTotals[reason]+=stat.reasonCounts[reason]||0;
  }
  const complete=stats.every(stat=>stat.optimizationKnown!==false);
  const rate=(count:number)=>!complete?null:totalPublished>0?Number((count/totalPublished*100).toFixed(1)):0;
  let topReason:SimplifiedOptimizationReason|null=null,topReasonCount=0;
  for(const reason of reasons)if(reason!=='待归类'&&reasonTotals[reason]>topReasonCount){topReason=reason;topReasonCount=reasonTotals[reason];}
  const homogeneousCount=reasons.filter(reason=>Object.hasOwn(OFFICIAL_OPTIMIZATION_DEFINITIONS,reason)&&OFFICIAL_OPTIMIZATION_DEFINITIONS[reason].homogeneous).reduce((sum,reason)=>sum+reasonTotals[reason],0);
  return {totalPublished,totalOptimized,avgOptRate:rate(totalOptimized),reasonTotals,topReason,topReasonCount,
    homogeneousCount,homogeneousRate:rate(homogeneousCount)};
}
