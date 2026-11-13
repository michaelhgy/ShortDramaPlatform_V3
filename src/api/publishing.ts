import { ApiClient } from './client';
import type { MountSource } from './dramaCatalog';

const client = new ApiClient({ timeoutMs: 150_000 });
export interface LocationValue { poiCheckSum: string; name?: string; city?: string; fullAddress?: string; _searchQuery: Record<string, unknown>; [key: string]: unknown }
export interface MountDrama { id: string; name: string; coverUrl?: string; mediaCount?: number; miniAppName?: string; usable: boolean; unusableReason?: string; score?: number; exact?: boolean }
export interface MountBinding { drama: MountDrama; account_only: boolean; confirmed_at: string; source?: MountSource; from_task?: boolean }
export interface PublishGroup {
  id: string; name: string; kind?: 'normal' | 'sheep' | 'custom'; video_ids: string[]; cover_mode: 'auto' | 'drama' | 'none' | 'custom'; cover_source?: 'auto' | 'custom'; custom_cover_id?: string;
  title: string; video_title?: string; short_title?: string; desc: string; tags: string[]; schedule_type: 'now' | 'timing' | 'localTiming';
  start_time: string; interval: number; copies: number; order: 'round' | 'consecutive';
  location: LocationValue | null; mount_required: boolean; tag_type: number; original: boolean; comment: string; comment_top: boolean;
  shoot_date?: string; shoot_region_codes?: number[]; repost_source?: string;
}
export interface PublishSchedule { schedule_type: 'now' | 'timing' | 'localTiming'; start_time: string; interval: number }
export interface PublishSettings { account_id: string; drama_id: string; port: number; groups: PublishGroup[]; schedule?: PublishSchedule; assignment_mode?: 'auto' | 'manual'; assignment_confirmed?: boolean; group_order?: 'normal_first' | 'sheep_first'; sync_location?: boolean; mount_source?: MountSource; profile_ref?: ProfileReference | null }
export type ProfileScope = 'schedule' | 'copies' | 'text' | 'declaration' | 'location_mount' | 'cover';
export type ProfileGroup = Partial<Pick<PublishGroup, 'cover_mode' | 'cover_source' | 'custom_cover_id'>> & Pick<PublishGroup, 'copies' | 'order' | 'mount_required' | 'video_title' | 'desc' | 'tags' | 'short_title' | 'comment' | 'comment_top' | 'tag_type' | 'original' | 'repost_source' | 'shoot_region_codes'>;
export interface PublishProfileConfig { schedule: Pick<PublishSchedule, 'schedule_type' | 'interval'>; group_order: 'normal_first' | 'sheep_first'; sheep_inherit: boolean; groups: Record<'normal' | 'sheep', ProfileGroup>; location: { mode: 'account' | 'none' | 'public'; checksum: string; sync: boolean } }
export interface PublishProfile { id: string; name: string; revision: number; config: PublishProfileConfig; updated_at?: string }
export interface ProfileLibrary { items: PublishProfile[]; software_default_id: string | null; account_default_id: string | null }
export interface ProfileReference { id: string; name: string; revision: number; scopes: ProfileScope[]; baseline: { root: Record<string, unknown>; groups: Record<string, Record<string, unknown>> }; problem?: string }
export interface ProfileState { id: string; name: string; modified: boolean; deleted: boolean; update_available: boolean }
export interface ProfilePreview { settings: PublishSettings; changes: { label: string; before: string; after: string }[]; has_special_groups: boolean }
export interface ShootRegion { name: string; code: number; sub?: ShootRegion[] }
export interface DraftItem { key: string; group_id: string; group_name: string; name: string; copy: number; time: string; status: string; draft_id?: number; local_id?: string; replaces_local_id?: string | null; archived_at?: string; remote_state?: string; batch_name?: string; error?: string; checks?: Record<string, boolean>; accepted_payload?: unknown }
export interface DraftExecution { state: string; running: boolean; mode?: string; items: DraftItem[]; previous_items?: DraftItem[]; error?: string; reset_status?: 'blocked' | 'awaiting_manual_cleanup' | 'ready'; reset_plan?: unknown }
export interface PublishContext {
  task_id: string; account: { id: string; nickname: string; uid: string };
  drama: { id: string; name: string; history_names: string[]; theater_id: string; theater_name: string };
  cover: { path: string; exists: boolean; url: string }; sheep_cover?: { path: string; exists: boolean; url: string }; sheep_cover_visible?: boolean; planned_time: string;
  videos: { id: string; name: string; path: string; exists: boolean; duration: number; sheep: boolean; sequence: number }[];
  settings: PublishSettings;
  mount_source?: MountSource; task_mount_source?: MountSource | '';
}
export interface PublishingData extends PublishContext {
  shoot_regions?: ShootRegion[];
  binding: MountBinding | null; addresses: LocationValue[]; history: Record<string, string[]>; execution: DraftExecution;
  public_addresses?: LocationValue[]; default_address?: LocationValue | null;
  profile_library?: ProfileLibrary; profile_state?: ProfileState | null;
  publication?: DraftExecution;
}
export interface PublishingAddressBook { addresses: LocationValue[]; public_addresses: LocationValue[]; default_address: LocationValue | null }
export interface DramaSearchResult { items: MountDrama[]; binding: MountBinding | null; status: 'auto' | 'bound' | 'choose' | 'not_found' | 'unavailable' | 'plugin'; queries: string[]; message?: string; mount_source?: MountSource }
const url = (task: string, action = '') => `/api/v2/publishing/tasks/${task}${action ? `/${action}` : ''}`;
export const getPublishing = (task: string) => client.get<PublishingData>(url(task), { t: Date.now() });
export const getPublishingAddressBook = (task: string) => client.get<PublishingAddressBook>(url(task, 'address-book'), { t: Date.now() });
export const getPublishingProfiles = (task: string) => client.get<ProfileLibrary>(url(task, 'profiles'), { t: Date.now() });
export const getPublishingHistory = (task: string) => client.get<Record<string, string[]>>(url(task, 'history'), { t: Date.now() });
export const getPublishingContext = (task: string) => client.get<PublishContext>(url(task, 'context'), { t: Date.now() });
export const savePublishing = (task: string, settings: PublishSettings) => client.post<PublishingData>(url(task, 'settings'), settings);
export const publishingAction = <T = Record<string, unknown>>(task: string, action: string, body: unknown = {}) => client.post<T>(url(task, action), body);
export const getDraftExecution = (task: string) => client.get<DraftExecution>(url(task, 'execution'), { t: Date.now() });
export const getPublication = (task: string) => client.get<DraftExecution>(url(task, 'publication'), { t: Date.now() });

export interface ProductionPublishItem {
  key: string; video_id: string; name: string; group_name: string; copy: number; time: string; status: string; error: string;
  submitted: boolean; delivery_confirmed?: boolean; local_id?: string; draft_id?: number; schedule_type: string; submitted_at: string;
  mount: { enabled: boolean; source: string; name: string }; location: { name: string; full_address: string };
}
export interface ProductionPublishExecution { state: string; running: boolean; mode?: string; error: string; items: ProductionPublishItem[] }
export interface ProductionPublishProgress {
  task_id: string; publication: ProductionPublishExecution; drafts: ProductionPublishExecution; needs_poll: boolean; refresh_error: string;
}
export const getProductionPublishProgress = (task: string) => client.get<ProductionPublishProgress>(url(task, 'progress'), { t: Date.now() });
export interface ProductionPublishCard { total: number; done: number; processing: number; queued: number; paused: number; issues: number; draft_only: boolean; scheduled: boolean; delivered?: number }
export const getProductionPublishIndex = () => client.get<{items: Record<string, ProductionPublishCard>}>('/api/v2/publishing/progress-index', {t: Date.now()});
