export type V2DataSource = 'mock' | 'v2';

// V2 SQLite is the product default. Mock data is only available through an explicit
// development override and must never be shown as live operational data.
export const dataSource: V2DataSource = import.meta.env.VITE_V2_DATA_SOURCE === 'mock' ? 'mock' : 'v2';

export class DataSourceNotReadyError extends Error {
  constructor(feature: string) {
    super(`${feature} 暂无真实数据，尚未接入 V2 数据服务。`);
    this.name = 'DataSourceNotReadyError';
  }
}
