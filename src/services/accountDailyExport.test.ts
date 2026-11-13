import assert from 'node:assert/strict';
import test from 'node:test';
import { accountDailyExport, accountDailyCell } from './accountDailyExport.ts';
import type { AccountDailyTrafficDetail } from '../types/shortDramaOps.ts';

test('all account daily metrics export in their own columns; missing differs from zero',()=>{
  const row:AccountDailyTrafficDetail={id:'r',accountId:'a',accountName:'甲',channelId:'uid',theater:'剧场',date:'2026-11-01',
    views:0,followerTotal:100,followsAdded:2,follows:-1,followsReduced:3,hearts:4,thumbsUp:5,comments:6,shares:7};
  const result=accountDailyExport([row]);
  const byHeader=Object.fromEntries(result.headers.map((h,i)=>[h,result.rows[0][i]]));
  assert.equal(byHeader['总计播放量'],'0');assert.equal(byHeader['新增关注'],'2');assert.equal(byHeader['净增关注'],'-1');
  assert.equal(byHeader['取消关注'],'3');assert.equal(byHeader['爱心数'],'4');assert.equal(byHeader['点赞数'],'5');
  assert.equal(byHeader['评论数'],'6');assert.equal(byHeader['分享数'],'7');assert.equal('主页访问' in byHeader,false);
  assert.equal(accountDailyCell(null),'—');assert.equal(accountDailyCell(0),'0');assert.equal(accountDailyCell(-1,true),'-1');
});
