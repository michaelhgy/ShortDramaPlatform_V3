import assert from 'node:assert/strict';
import test from 'node:test';
import { buildDualTrendLayout, formatTrendViews, trendLabelsOverlap, type DualTrendDatum } from './dualTrendLayout.ts';

function series(count: number, values = (i: number)=>({views:i*117+1,revenue:i*2.53})) {
  return Array.from({length:count},(_,i)=>({date:`2026-10-${String(i+1).padStart(2,'0')}`,
    label:`10-${String(i+1).padStart(2,'0')}`,...values(i)}));
}

test('14 calendar days include values; longer selected windows suppress them even with sparse records',()=>{
  assert.equal(buildDualTrendLayout(series(14)).labels.length,28);
  assert.equal(buildDualTrendLayout(series(15)).labels.length,0);
  assert.equal(buildDualTrendLayout(series(2),{start:'2026-10-01',end:'2026-10-30'}).labels.length,0);
  assert.equal(buildDualTrendLayout(series(2),{start:'2026-10-01',end:'2026-10-14'}).labels.length,4);
});

test('single-day dots and date are horizontally centered; both metrics are retained at their actual coordinates',()=>{
  for(const values of [{views:5188,revenue:8.67},{views:0,revenue:0},{views:500,revenue:0}]) {
    const layout=buildDualTrendLayout([{date:'2026-10-31',label:'10-31',...values}]);
    const point=layout.points[0];
    assert.equal(point.x,layout.svgWidth/2);
    assert.equal(layout.labels.length,2);
    assert.equal(point.overlapping,values.views>0&&values.revenue===0?false:true);
    assert.equal(layout.labels[1].text,`¥${values.revenue.toFixed(2)}`);
    assert.ok(Number.isFinite(point.yViews)&&Number.isFinite(point.yRev));
    assert.ok(!trendLabelsOverlap(layout.labels[0],layout.labels[1]));
  }
});

test('dense zeroes, crossing curves and high peaks keep labels separated and within chart space',()=>{
  const fixtures: DualTrendDatum[][]=[series(14,()=>({views:0,revenue:0})),
    series(14,i=>({views:i%2?30000:50,revenue:i%2?.01:700.45})),
    series(14,i=>({views:i===10?45000:i*31,revenue:i===10?259.22:i*.13}))];
  for(const fixture of fixtures) {
    const layout=buildDualTrendLayout(fixture,undefined,240);
    assert.equal(layout.labels.length,28);
    for(let i=0;i<layout.labels.length;i++) {
      const label=layout.labels[i];
      assert.ok(label.x-label.width/2>=layout.paddingLeft-.01);
      assert.ok(label.x+label.width/2<=layout.svgWidth-layout.paddingRight+.01);
      assert.ok(label.y+label.height/2<layout.dateLabelY-8);
      for(let j=i+1;j<layout.labels.length;j++) assert.ok(!trendLabelsOverlap(label,layout.labels[j]),`${i}/${j}`);
    }
  }
});

test('compact playback values preserve precision through the ten-thousand and hundred-million thresholds',()=>{
  assert.equal(formatTrendViews(9999),'9999');
  assert.equal(formatTrendViews(12345),'1.23万');
  assert.equal(formatTrendViews(10000),'1万');
  assert.equal(formatTrendViews(123450000),'1.23亿');
  assert.deepEqual(buildDualTrendLayout([]).labels,[]);
});


test('missing metric series never produces zero revenue dots or labels', async()=>{
 const {mergeDualTrendData}=await import('./dualTrendLayout.ts');
 const data=mergeDualTrendData([{date:'2026-11-01',views:12}],[{date:'2026-11-02',amount:0}]);
 assert.equal(Number.isNaN(data[0].revenue),true);assert.equal(data[1].revenue,0);
 const result=buildDualTrendLayout(data);
 assert.equal(result.labels.filter(l=>l.metric==='revenue').length,1);
 assert.equal(result.labels.filter(l=>l.metric==='views').length,1);
 assert.ok(Number.isFinite(result.maxViews));assert.ok(Number.isFinite(result.maxRevenue));
});
