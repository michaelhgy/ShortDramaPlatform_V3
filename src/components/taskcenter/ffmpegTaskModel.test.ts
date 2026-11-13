import assert from 'node:assert/strict';
import { test } from 'node:test';
import { currentCounts, jobStatusText, productionProgress, queueState, liveVideo } from './ffmpegTaskModel.ts';
import type { ProductionUnit, ProductionVideoItem } from '../../productionTypes.ts';
import type { FinalJob, FinalSnapshot } from '../../api/finalComposition.ts';

const job = (id: string, status: FinalJob['status'], progress = 0): FinalJob => ({ id, status, progress, task_id: 'task', material_id: id, name: id, template_id: 'template', account_name: '账号', drama_name: '剧集', stage: '成片合成', elapsed_seconds: 12, error: '', output_path: null });
const video = (id: string, status: ProductionVideoItem['status']) => ({ id, status }) as ProductionVideoItem;
const unit = (videos: ProductionVideoItem[] = []) => ({ id: 'task', materialsCount: 5, scannedMaterials: [], videos }) as ProductionUnit;

test('排队不算完成，当前22%与批次已完成条数分开', () => {
  const summary = productionProgress(unit(), [job('1', 'done', 100), job('2', 'running', 22), ...['3', '4', '5'].map(id => job(id, 'waiting'))]);
  assert.deepEqual([summary.done, summary.total, summary.percent, summary.running, summary.waiting, summary.pending], [1, 5, 20, 1, 3, 0]);
  assert.equal(jobStatusText('running', summary.current!.progress, 'final'), '合成中 22%');
});
test('校验与保存结束前最多99%，全完成才是100%', () => {
  assert.equal(jobStatusText('running', 100, 'final'), '合成中 99%');
  assert.equal(jobStatusText('running', Number.NaN, 'final'), '合成中 0%');
  assert.equal(productionProgress(unit(), ['1','2','3','4','5'].map(id => job(id, 'done', 100))).percent, 100);
});
test('最新任务覆盖旧详情，失败和取消不显示成合成中', () => {
  const videos = [video('1','exporting'), video('2','pending_export'), video('pending-3','not_generated'), video('4','exported'), video('5','not_generated')];
  const jobs = [job('1','error',67),job('2','cancelled'),job('3','running',22),job('4','done',100)];
  const p = productionProgress(unit(videos),jobs);
  assert.deepEqual([p.errors,p.cancelled,p.running,p.done,p.pending], [1,1,1,1,1]);
  assert.equal(liveVideo(videos[2],jobs).exportProgress,22);
  assert.equal(liveVideo(videos[0],jobs).status,'video_error');
});
test('摘要陈旧的运行数量不会覆盖已完成队列；其他剧集不混入', () => {
  const u = { ...unit(), exportingCount: 1, exportQueuedCount: 4 };
  const jobs = ['1','2','3','4','5'].map(id => job(id,'done',100));
  jobs.push({ ...job('other','running',50),task_id:'other-task' });
  const p = productionProgress(u,jobs);
  assert.deepEqual([p.done,p.running,p.waiting,p.percent], [5,0,0,100]);
});
test('暂停后的当前条继续显示真实进度，排队条等待恢复', () => {
  assert.equal(queueState({ paused:true,counts:{ running:1,waiting:3,error:0 } }),'本条完成后暂停');
  assert.equal(queueState({ paused:true,counts:{ running:0,waiting:3,error:0 } }),'已暂停');
  assert.equal(jobStatusText('waiting',0,'final',true),'等待恢复');
  assert.equal(jobStatusText('running',22,'final',true),'合成中 22%');
});
test('任务监控统计只加两条新队列，已取消单列', () => {
  const snapshot = { counts:{ running:1,waiting:2,done:3,error:1,cancelled:4 } } as FinalSnapshot;
  assert.deepEqual(currentCounts(snapshot),{ running:1,waiting:2,done:3,error:1,cancelled:4 });
  assert.deepEqual(currentCounts(),{ running:0,waiting:0,done:0,error:0,cancelled:0 });
});


test('成片显示提交时插片配方和包含插片的总时长', () => {
  const source = { ...video('pending-1', 'not_generated'), durationSec: 600 };
  const queued = { ...job('1', 'waiting'), insertions: { total_frames: 18600, midroll: { status: 'inserted', insert_at_seconds: 222 }, endroll: { status: 'inserted' } } };
  const actual = liveVideo(source, [queued]);
  assert.equal(actual.durationSec, 620);
  assert.equal(actual.insertionResultText, '中插 · 尾插');
});

test('只显示配方中实际插入的类型，关闭或跳过均隐藏，旧配方保留已有时长', () => {
  const source = { ...video('1', 'exported'), durationSec: 90 };
  const done = { ...job('1', 'done'), insertions: { total_frames: 2700, midroll: { status: 'skipped_short_source' }, endroll: { status: 'disabled' } } };
  for (const midStatus of ['disabled', 'skipped_short_source', 'skipped_invalid_window']) {
    for (const endStatus of ['disabled', 'inserted']) {
      const current = { ...done, insertions: { ...done.insertions, midroll: { status: midStatus }, endroll: { status: endStatus } } };
      assert.equal(liveVideo(source, [current]).insertionResultText, endStatus === 'inserted' ? '尾插' : undefined);
    }
  }
  const middleOnly = { ...done, insertions: { ...done.insertions, midroll: { status: 'inserted', insert_at_seconds: 30 } } };
  assert.equal(liveVideo(source, [middleOnly]).insertionResultText, '中插');
  assert.equal(liveVideo(source, [job('1', 'done')]).durationSec, 90);
  assert.equal(liveVideo(source, []).insertionResultText, undefined);
});
