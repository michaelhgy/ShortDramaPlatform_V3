import { v2Client } from './client';

export function selectV2Path(kind: 'file' | 'directory'): Promise<{ path: string; cancelled: string }> {
  return v2Client.post('/api/v2/select-path', { kind });
}
