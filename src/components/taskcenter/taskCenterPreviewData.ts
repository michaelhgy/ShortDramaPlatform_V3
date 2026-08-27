import { INITIAL_TASKS } from './taskCenterMockData';
import { TaskItem } from './taskCenterTypes';

// The ZIP preview contains fictional names. Keep its state combinations, but
// show the accounts and dramas that already exist in the V2 workspace.
const accountNames: Record<string, string> = {
  '微雨问海棠火': '斤斤计较1681',
};

const dramaNames: Record<string, string> = {
  '风雪草原苍狼少女': '一台好戏守人心',
  '辣厨回乡鲜椒越香店越旺': '八零：从下岗女工到制衣女王',
  '坠海逢生我率万鲨踏浪归来': '一双大手闯赛场，矮个子也能当女王',
  '我用十元盒饭惊艳全城': '八零：从下岗女工到制衣女王',
};

export const INITIAL_PREVIEW_TASKS: TaskItem[] = INITIAL_TASKS.map((task) => {
  const accountName = accountNames[task.accountName] || task.accountName;
  const dramaName = dramaNames[task.dramaName] || task.dramaName;
  const title = task.taskCategory === 'template'
    ? `${accountName} × 《${dramaName}》 · 模板`
    : `${accountName} × 《${dramaName}》 · ${task.materialName || '成片'}`;

  return { ...task, accountName, dramaName, title };
});
