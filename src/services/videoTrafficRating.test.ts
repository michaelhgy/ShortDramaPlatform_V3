import assert from 'node:assert/strict';
import test from 'node:test';
import {rateVideoTraffic} from './videoTrafficRating.ts';

const start=Date.parse('2026-11-01T00:00:00+08:00'),H=3600000;
function video(views=100,extra:Record<string,unknown>={}) {
  return {views,publishTime:'2026-11-01 00:00:00',statsCollectedAt:'2026-11-02 01:00:00',statsState:'record',...extra};
}
test('12 hour observation and 24 hour low reach have exact boundaries and a waiting middle stage',()=>{
  for(const [hours,status] of [[0,'观察中'],[11.999,'观察中'],[12,'待起量'],[23.999,'待起量'],[24,'低播']] as const) {
    const stamp=new Date(start+hours*H).toISOString();
    assert.equal(rateVideoTraffic(video(100,{statsCollectedAt:stamp}),start+hours*H).status,status);
  }
  assert.equal(rateVideoTraffic(video(100,{statsCollectedAt:'2026-11-01 01:00:00'}),start+H).nextEvaluationAt,start+12*H);
  assert.equal(rateVideoTraffic(video(100,{statsCollectedAt:'2026-11-01 12:00:00'}),start+12*H).nextEvaluationAt,start+24*H);
});
test('cumulative thresholds start small viral at 30000, viral at 50000, and major at 100000',()=>{
  for(const [views,status] of [[999,'低播'],[1000,'常规'],[29999,'常规'],[30000,'小爆'],[49999,'小爆'],[50000,'爆款'],[99999,'爆款'],[100000,'大爆']] as const)
    assert.equal(rateVideoTraffic(video(views),start+25*H).status,status);
});
test('high reach qualifies immediately without waiting for the observation period',()=>{
  for(const [views,status] of [[1000,'常规'],[30000,'小爆'],[50000,'爆款'],[100000,'大爆']] as const)
    assert.equal(rateVideoTraffic(video(views,{statsCollectedAt:'2026-11-01 01:00:00'}),start+H).status,status);
});
test('time passing cannot turn an early snapshot into proof of low reach',()=>{
  assert.equal(rateVideoTraffic(video(5,{statsCollectedAt:'2026-11-01 01:00:00'}),start+72*H).status,'待采集');
  assert.equal(rateVideoTraffic(video(5,{statsCollectedAt:''}),start+72*H).status,'待采集');
});
test('missing, invalid and failed counts are not zero; explicit valid zero can be low reach',()=>{
  for(const views of [null,undefined,NaN,-1,Infinity,'0'])assert.equal(rateVideoTraffic(video(1,{views}),start+25*H).status,'待采集');
  assert.equal(rateVideoTraffic(video(100000,{statsState:'failed'}),start+25*H).status,'待采集');
  assert.equal(rateVideoTraffic(video(0),start+25*H).status,'低播');
});
test('Beijing naive timestamps and explicit UTC refer to the same observation boundaries',()=>{
  const now=Date.parse('2026-11-01T04:00:00Z');
  assert.equal(rateVideoTraffic(video(100,{statsCollectedAt:'2026-11-01T04:00:00Z'}),now).status,'待起量');
  assert.equal(rateVideoTraffic(video(100,{statsCollectedAt:'2026-11-01 12:00:00'}),now).status,'待起量');
});
test('date-only collection is a conservative lower bound, never an invented end-of-day observation',()=>{
  assert.equal(rateVideoTraffic(video(10,{publishTime:'2026-11-01 18:00:00',statsCollectedAt:'',statsDate:'2026-11-02'}),start+50*H).status,'待采集');
  assert.equal(rateVideoTraffic(video(10,{publishTime:'2026-11-01 18:00:00',statsCollectedAt:'',statsDate:'2026-11-03'}),start+50*H).status,'低播');
});
test('future or inconsistent times are not used to judge low reach or inflate performance',()=>{
  assert.equal(rateVideoTraffic(video(100000),start+H).status,'待采集');
  assert.equal(rateVideoTraffic(video(10,{statsCollectedAt:'2026-10-31 23:00:00'}),start+25*H).status,'待采集');
  assert.equal(rateVideoTraffic(video(10,{publishTime:'bad'}),start+25*H).status,'待采集');
});
test('old confirmed cumulative success is retained without deriving decline from elapsed time',()=>{
  const v=video(50000,{statsState:'cached_only'});
  assert.equal(rateVideoTraffic(v,start+25*H).status,'爆款');
  assert.equal(rateVideoTraffic(v,start+25*H+30*24*H).status,'爆款');
});
test('completion and platform risk do not override cumulative reach',()=>{
  assert.equal(rateVideoTraffic(video(42000,{completionRate:8.2,hasOptimization:true}),start+25*H).status,'小爆');
  assert.equal(rateVideoTraffic(video(6373,{completionRate:27}),start+25*H).status,'常规');
});
