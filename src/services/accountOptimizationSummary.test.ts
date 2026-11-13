import assert from 'node:assert/strict';
import test from 'node:test';
import {summarizeAccountOptimization} from './accountOptimizationSummary.ts';
import type {AccountOptimizationStat} from '../types/shortDramaOps';

function account(total:number,optimized:number,reasons:Record<string,number>={}):AccountOptimizationStat {
  return {totalVideos:total,optimizedVideos:optimized,reasonCounts:reasons} as AccountOptimizationStat;
}
test('homogeneous optimization divides warned works by all published works, not by all warnings',()=>{
  const m=summarizeAccountOptimization([account(399,42,{'原创优化':6,'多次发布':9})]);
  assert.equal(m.totalPublished,399);assert.equal(m.totalOptimized,42);assert.equal(m.avgOptRate,10.5);
  assert.equal(m.homogeneousCount,6);assert.equal(m.homogeneousRate,1.5);
  assert.equal(Math.round(m.reasonTotals['原创优化']/m.totalOptimized*100),14);
  assert.equal(m.topReason,'多次发布');assert.equal(m.topReasonCount,9);
});
test('overall optimization is weighted by work count instead of averaging account percentages',()=>{
  const m=summarizeAccountOptimization([account(1,1,{'原创优化':1}),account(99,1,{'引导优化':1})]);
  assert.equal(m.avgOptRate,2);assert.equal(m.homogeneousRate,1);assert.equal(m.totalPublished,100);
});
test('no published works or warnings produces finite zero rates and no invented top category',()=>{
  for(const stats of [[],[account(0,0)]]){
    const m=summarizeAccountOptimization(stats);assert.equal(m.avgOptRate,0);assert.equal(m.homogeneousRate,0);
    assert.equal(m.topReason,null);assert.equal(m.topReasonCount,0);
  }
});
test('unclassified warnings stay in overall totals without being assigned to homogeneous content',()=>{
  const m=summarizeAccountOptimization([account(20,3)]);
  assert.equal(m.avgOptRate,15);assert.equal(m.homogeneousRate,0);assert.equal(m.topReason,null);
});
