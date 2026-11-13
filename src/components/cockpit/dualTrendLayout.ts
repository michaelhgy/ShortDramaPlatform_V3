export interface DualTrendDatum {
  date: string;
  label: string;
  views: number;
  revenue: number;
}

export interface ChartDateBounds { start: string; end: string }

export interface TrendValueLabel {
  index: number;
  metric: 'views' | 'revenue';
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  pointX: number;
  pointY: number;
}

export function formatTrendViews(value: number): string {
  if (value >= 100000000) return `${Number((value / 100000000).toFixed(2))}亿`;
  if (value >= 10000) return `${Number((value / 10000).toFixed(2))}万`;
  return Math.round(value).toLocaleString('zh-CN', { useGrouping: false });
}

export function trendLabelsOverlap(a: TrendValueLabel, b: TrendValueLabel, gap = 3): boolean {
  return Math.abs(a.x-b.x) < (a.width+b.width)/2+gap && Math.abs(a.y-b.y) < (a.height+b.height)/2+gap;
}

/** SVG geometry only: labels may move; points always retain their true dual-axis coordinates. */
export function buildDualTrendLayout(data: DualTrendDatum[], bounds?: ChartDateBounds, height = 260) {
  const ordered = [...data].sort((a,b) => a.date.localeCompare(b.date));
  const start = bounds?.start || ordered[0]?.date;
  const end = bounds?.end || ordered.at(-1)?.date;
  const days = start && end ? Math.max(1, Math.round((Date.parse(end+'T00:00:00Z')-Date.parse(start+'T00:00:00Z'))/86400000)+1) : 0;
  const showValues = days > 0 && days <= 14;
  const svgWidth = 720, paddingLeft = 55, paddingRight = 55, paddingTop = 30;
  const paddingBottom = showValues ? 60 : 40;
  const chartWidth = svgWidth-paddingLeft-paddingRight;
  const chartHeight = height-paddingTop-paddingBottom;
  const bottom = paddingTop+chartHeight;
  const maxViews = Math.max(0,...ordered.map(d=>d.views).filter(Number.isFinite))*1.15 || 10000;
  const maxRevenue = Math.max(0,...ordered.map(d=>d.revenue).filter(Number.isFinite))*1.15 || 1000;
  const points = ordered.map((d,i) => {
    const x = ordered.length === 1 ? svgWidth/2 : paddingLeft+i/(ordered.length-1)*chartWidth;
    const yViews = bottom-d.views/maxViews*chartHeight;
    const yRev = bottom-d.revenue/maxRevenue*chartHeight;
    return { x,yViews,yRev,data:d,index:i,overlapping:Math.abs(yViews-yRev)<8 };
  });
  const labels: TrendValueLabel[] = [];
  if (showValues) {
    const markers = points.flatMap(p=>[{x:p.x,y:p.yViews},{x:p.x,y:p.yRev}]).filter(p=>Number.isFinite(p.y));
    for (const p of points) {
      for (const metric of ['views','revenue'] as const) {
        if(!Number.isFinite(p.data[metric]))continue;
        const text = metric === 'views' ? formatTrendViews(p.data.views) : `¥${p.data.revenue.toFixed(2)}`;
        const width = [...text].reduce((sum,c)=>sum+(/[万亿]/.test(c)?9:5.3),0)+4;
        const pointY = metric === 'views' ? p.yViews : p.yRev;
        const preferredY = pointY+(metric === 'views' ? -15 : 15);
        const clampX = (x: number) => Math.min(svgWidth-paddingRight-width/2, Math.max(paddingLeft+width/2,x));
        const candidates: Array<TrendValueLabel & {score:number}> = [];
        const ys = [preferredY,pointY+(metric === 'views'?15:-15)];
        for (let y=10;y<=bottom+23;y+=15) ys.push(y);
        for (const xOffset of [0,-12,12,-24,24]) {
          const x = clampX(p.x+xOffset);
          for (const y of ys) {
            if (y<10 || y>bottom+23) continue;
            const candidate = {index:p.index,metric,text,x,y,width,height:12,pointX:p.x,pointY};
            if (labels.some(label=>trendLabelsOverlap(label,candidate))) continue;
            if (markers.some(m=>Math.abs(m.x-x)<width/2+5 && Math.abs(m.y-y)<12)) continue;
            // Prefer nearby text, with a small extra cost for placing it across a curve.
            let crossings = 0;
            for (let i=1;i<points.length;i++) {
              const a=points[i-1], b=points[i];
              if (x<a.x || x>b.x) continue;
              const ratio=(x-a.x)/(b.x-a.x);
              for (const key of ['yViews','yRev'] as const) {
                if (Math.abs(a[key]+(b[key]-a[key])*ratio-y)<9) crossings++;
              }
            }
            candidates.push({...candidate,score:Math.abs(x-p.x)*1.2+Math.abs(y-preferredY)+crossings*12});
          }
        }
        candidates.sort((a,b)=>a.score-b.score);
        const chosen = candidates[0];
        // Compact financial labels fit normal chart columns; retain a label even for unusually long input.
        labels.push(chosen || {index:p.index,metric,text,x:clampX(p.x),y:Math.max(10,Math.min(bottom+23,preferredY)),
          width,height:12,pointX:p.x,pointY});
      }
    }
  }
  return {points,labels,days,showValues,svgWidth,svgHeight:height,paddingLeft,paddingRight,paddingTop,
    chartWidth,chartHeight,maxViews,maxRevenue,dateLabelY:bottom+(showValues?45:20),
    dateLabelStep:showValues?1:Math.max(1,Math.ceil(points.length/14))};
}

/** A day without a source record stays missing; an observed zero stays zero. */
export function mergeDualTrendData(traffic:Array<{date:string;views:number}>,revenue:Array<{date:string;amount:number}>):DualTrendDatum[] {
  const days=new Map<string,{views:number;revenue:number}>();
  for(const row of traffic){if(!Number.isFinite(row.views))continue;const d=days.get(row.date)||{views:Number.NaN,revenue:Number.NaN};d.views=(Number.isFinite(d.views)?d.views:0)+row.views;days.set(row.date,d);}
  for(const row of revenue){if(!Number.isFinite(row.amount))continue;const d=days.get(row.date)||{views:Number.NaN,revenue:Number.NaN};d.revenue=(Number.isFinite(d.revenue)?d.revenue:0)+row.amount;days.set(row.date,d);}
  return [...days].sort(([a],[b])=>a.localeCompare(b)).map(([date,d])=>({date,label:date.slice(5),...d}));
}
