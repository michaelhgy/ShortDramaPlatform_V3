import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ProductionPublishItem, ProductionPublishProgress } from '../../api/publishing.ts';
import { publicationsByVideo, publicationCounts, publicationLocation, publicationMount, publicationSummary, publicationTime, publicationCard, publicationCardStatus } from './productionPublishingModel.ts';

const item = (patch: Partial<ProductionPublishItem> = {}): ProductionPublishItem => ({key:'g:video:0',video_id:'video',name:'video.mp4',group_name:'正剧视频',copy:1,time:'2026-10-30 20:00',status:'success',error:'',submitted:true,local_id:'queue-id',schedule_type:'timing',submitted_at:'2026-10-26T20:00:00+08:00',mount:{enabled:true,source:'channels_drama',name:'confirmed'},location:{name:'地点A',full_address:'地点A完整地址'},...patch});
test('mount and location remain absent until a submission has an external identifier',()=>{
  const value={kind:'publication' as const,items:[item({submitted:false,status:'pending'})]};
  assert.equal(publicationMount(value),null);assert.equal(publicationLocation({video:value}),null);
});
test('copies aggregate independently from video count and keep paused distinct from failure',()=>{
  const rows=[item(),item({copy:2,status:'publishing'}),item({copy:3,status:'paused'})];
  assert.deepEqual(publicationCounts(rows),{total:3,done:1,processing:1,queued:0,paused:1,issues:0});
  const summary=publicationSummary({kind:'publication',items:rows});assert.equal(summary.tone,'amber');assert.match(summary.text,/1 份已暂停/);
});
test('scheduled success never claims a video has already become public',()=>{
  const value={kind:'publication' as const,items:[item(),item({copy:2,time:'2026-10-30 20:03'})]};
  assert.equal(publicationSummary(value).text,'定时已提交 2/2 份');assert.equal(publicationTime(value),'10月30日 20:00—20:03');
});
test('location groups use saved submitted positions, with a compact common address',()=>{
  const normal={kind:'publication' as const,items:[item()]};
  assert.equal(publicationLocation({v:normal})?.text,'地点A');
  const sheep={kind:'publication' as const,items:[item({video_id:'sheep',group_name:'羊视频',location:{name:'地点B',full_address:'B'}})]};
  assert.equal(publicationLocation({normal,sheep})?.text,'正剧 · 地点A ｜ 羊 · 地点B');
});
test('latest submitted workflow wins by stable video id even after filenames change',()=>{
  const data={publication:{items:[item()]},drafts:{items:[item({name:'new name.mp4',local_id:undefined,draft_id:12,submitted_at:'2026-10-26T21:00:00+08:00'})]}} as ProductionPublishProgress;
  assert.equal(publicationsByVideo(data).video.kind,'draft');
});
test('plugin drafts stay distinct from real publication and expose pending plugin mount in the title',()=>{
  const value={kind:'draft' as const,items:[item({status:'ready',mount:{enabled:false,source:'plugin',name:''}})]};
  assert.equal(publicationSummary(value).text,'小V猫草稿已就绪 1/1 份');assert.equal(publicationMount(value)?.text,'未挂载');assert.match(publicationMount(value)!.title,/待插件处理/);
});
test('cross-date times and mixed mounting parameters stay visible rather than silently taking the first copy',()=>{
  const value={kind:'publication' as const,items:[item({time:'2026-10-30 23:58'}),item({copy:2,time:'2026-10-31 00:01',mount:{enabled:false,source:'',name:''}})]};
  assert.equal(publicationTime(value),'10月30日 23:58—10月31日 00:01');assert.equal(publicationMount(value)?.text,'挂载不一致');
});
test('sidebar switches to publication by copies only after an accepted submission and retains pause status',()=>{
  assert.equal(publicationCard({v:{kind:'publication',items:[item({submitted:false,status:'pending'})]}}),null);
  const card=publicationCard({v:{kind:'publication',items:[item(),item({copy:2,status:'paused'}),item({copy:3,status:'paused'})]}})!;
  assert.equal(card.done,1);assert.equal(card.total,3);assert.equal(publicationCardStatus(card),'发布已暂停');
});

test('verified platform schedules are delivery complete without claiming public release',()=>{
  const value={kind:'publication' as const,items:[item({delivery_confirmed:true}),item({copy:2,delivery_confirmed:true})]};
  assert.equal(publicationSummary(value).text,'官方已定时 2/2 份');
  assert.equal(publicationCardStatus(publicationCard({video:value})!),'官方已定时');
  assert.equal(publicationSummary({kind:'publication',items:[item({delivery_confirmed:true,schedule_type:'now'})]}).text,'发布完成 1/1 份');
  assert.equal(publicationCardStatus(publicationCard({video:{kind:'draft',items:[item({status:'ready'})]}})!),'草稿已就绪');
});
