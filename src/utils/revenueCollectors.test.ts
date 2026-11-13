import assert from 'node:assert/strict';
import { test } from 'node:test';
import { suggestRevenueCollectors } from './revenueCollectors.ts';
const definitions = [
  {id:'q',name:'青柠收益采集器',aliases:['青柠','青柠剧场','青柠端'],date_precision:'day',notes:'',runtime_verified:false},
  {id:'q2',name:'青柠其他采集器',aliases:['青柠','青柠剧场'],date_precision:'day',notes:'',runtime_verified:false},
];
test('名称与登记别名推荐所有适用采集器，支持输入空格', () => {
  assert.deepEqual(suggestRevenueCollectors(' 青柠 ',definitions),['q','q2']);
  assert.deepEqual(suggestRevenueCollectors('青柠端',definitions),['q']);
});
test('未知剧场与局部包含的名称不盲目匹配，不生成未实现的采集器', () => {
  for (const name of ['', '子诗', '其他青柠剧场']) assert.deepEqual(suggestRevenueCollectors(name,definitions),[]);
});
