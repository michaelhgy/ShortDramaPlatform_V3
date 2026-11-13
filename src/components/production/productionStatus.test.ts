import assert from 'node:assert/strict';
import { test } from 'node:test';
import { compositionStatusLabel, matchesProductionStage, productionStageCounts } from './productionStatus.ts';

test('normal and completed groups never overlap; unfinished retains overdue work', () => {
  const fresh = {isCompleted: false, isOverdue: false};
  const overdue = {isCompleted: false, isOverdue: true};
  const completed = {isCompleted: true, isOverdue: true};
  assert.deepEqual(productionStageCounts([fresh, overdue, completed]), {all: 2, in_progress: 2, overdue: 1, completed: 1});
  assert.equal(matchesProductionStage(completed, 'all'), false);
  assert.equal(matchesProductionStage(completed, 'overdue'), false);
  assert.equal(matchesProductionStage(overdue, 'in_progress'), true);
  assert.equal(matchesProductionStage(fresh, 'completed'), false);
});

test('composition labels expose FFmpeg stages without legacy draft terminology', () => {
  const cases = {not_generated:'待合成',pending_export:'等待合成',exporting:'合成中',exported:'已生成',video_error:'合成异常',cancelled:'已取消',draft_queued:'等待合成',draft_generating:'合成中',draft_ready:'待合成',draft_error:'合成异常'} as const;
  for (const [status, expected] of Object.entries(cases)) assert.equal(compositionStatusLabel({status: status as keyof typeof cases}), expected);
  assert.equal(compositionStatusLabel({status: 'exporting', exportProgress: 100}), '合成中 99%');
});
