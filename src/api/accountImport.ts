import { v2Client } from './client';

export interface RemoteAccount {
  uid: string; nickname: string; avatar?: string; platform: string; platformName: string;
  groupName?: string; localAvatar?: string; tags: string[]; loginStatus: string; fansTotal: number | null;
  match: 'existing' | 'new' | 'nickname_conflict'; local_nickname?: string;
}
export interface AccountPreview { token: string; items: RemoteAccount[]; local_nicknames: string[]; total: number; existing_count: number; new_count: number; conflict_count: number }
export interface AccountSelection { uid: string; nickname: string; theater_id: string }
export interface AccountImportRun {
  kind?: 'avatars';
  id: string; status: 'queued' | 'running' | 'completed' | 'error'; message: string;
  total: number; completed: number; created: number; skipped: number; failed: number; avatars: number; avatar_failed: number;
  results: { uid: string; nickname: string; account_id?: string; status: 'created' | 'updated' | 'skipped' | 'failed'; message: string }[];
}
const root = '/api/v3/drama-catalog/account-import';
export const previewRemoteAccounts = () => v2Client.post<AccountPreview>(`${root}/preview`);
export const startAccountImport = (token: string, items: AccountSelection[]) => v2Client.post<AccountImportRun>(`${root}/start`,{token,items});
export const accountImportStatus = (id: string) => v2Client.get<AccountImportRun>(`${root}/runs/${id}`);

export const syncExistingAccountAvatars = (token: string) => v2Client.post<AccountImportRun>(`${root}/sync-avatars`, {token});
