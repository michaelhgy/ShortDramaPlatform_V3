export type V1OperationStatus = 'queued' | 'running' | 'finished' | 'failed' | 'needs_attention' | 'paused' | 'suspended';

const OPERATION_STATUS_LABELS: Record<V1OperationStatus, string> = {
  queued: '排队中', running: '生产中', finished: '已完成', failed: '失败',
  needs_attention: '需要人工处理', paused: '已暂停', suspended: '已挂起',
};

export function toV2OperationStatus(status: string): string {
  return OPERATION_STATUS_LABELS[status as V1OperationStatus] ?? `未知状态（${status}）`;
}
