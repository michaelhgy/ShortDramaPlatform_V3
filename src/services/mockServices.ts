import { INITIAL_ACCOUNTS, DRAMA_LIBRARY, INITIAL_SCHEDULE_TASKS, INITIAL_TASK_CENTER_QUEUE, RECENT_DRAMA_PREDICTIONS } from '../mockData';
import { MOCK_ACCOUNTS_ANALYTICS, MOCK_COLLECTION_LOGS, MOCK_DRAMAS_ANALYTICS, MOCK_PLATFORM_VIDEOS } from '../analyticsMockData';
import { EXPLORE_ACCOUNTS, EXPLORE_DRAMAS, EXPLORE_INSIGHTS } from '../exploreMockData';
import { INITIAL_PRODUCTION_UNITS } from '../productionMockData';
import { DataSourceNotReadyError, dataSource } from './dataSource';

function mockOnly<T>(feature: string, value: T): Promise<T> {
  if (dataSource === 'v2') return Promise.reject(new DataSourceNotReadyError(feature));
  return Promise.resolve(value);
}

export function loadWorkbenchSeed() {
  return mockOnly('工作台', { accounts: INITIAL_ACCOUNTS, dramas: DRAMA_LIBRARY, predictions: RECENT_DRAMA_PREDICTIONS, tasks: INITIAL_SCHEDULE_TASKS, taskQueue: INITIAL_TASK_CENTER_QUEUE });
}
export function loadProductionUnits() { return mockOnly('生产中心', INITIAL_PRODUCTION_UNITS); }
export function loadAnalyticsSeed() { return mockOnly('数据分析', { accounts: MOCK_ACCOUNTS_ANALYTICS, dramas: MOCK_DRAMAS_ANALYTICS, videos: MOCK_PLATFORM_VIDEOS, collectionLogs: MOCK_COLLECTION_LOGS }); }
export function loadExploreSeed() { return mockOnly('探索工作台', { insights: EXPLORE_INSIGHTS, dramas: EXPLORE_DRAMAS, accounts: EXPLORE_ACCOUNTS }); }
