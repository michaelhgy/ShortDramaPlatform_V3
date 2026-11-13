import { ApiClient } from './client';
import type { RevenueCollectorDefinition } from './v2Catalog';

export interface QueryConfig {
  source_url: string;
  extract_code?: string;
  daily_url?: string;
  previous_month_url?: string;
  source_period: string;
  enabled: boolean;
  revision: number;
  saved_at: string;
}
export interface QueryPreview {
  status: string;
  verification_id?: string;
  passed: boolean;
  amount: string | null;
  query_date: string;
  source_period: string;
  source_url: string;
  message: string;
  test_token?: string;
  tested_at?: string;
}
export interface QuerySetting extends RevenueCollectorDefinition, QueryConfig {
  default_url: string;
  history: QueryConfig[];
  last_test: QueryPreview | null;
}
export interface QueryCandidate extends Omit<QueryConfig, 'saved_at'> {
  period_relation: 'same' | 'new';
  channel_id: string;
  query_date: string;
  test_token?: string;
}
// A source can require several read-only requests; ordinary 15-second timeout is too short.
const client = new ApiClient({ timeoutMs: 180_000 });
const base = '/api/v3/revenue-query-settings';
export const loadQuerySettings = () => client.get<{ items: QuerySetting[] }>(base);
export const testQuerySetting = (id: string, candidate: QueryCandidate) => client.post<QueryPreview>(`${base}/${id}/test`, candidate);
export const saveQuerySetting = (id: string, candidate: QueryCandidate) => client.patch<QueryConfig>(`${base}/${id}`, candidate);

export interface RevenueVerification {
  id: string;
  collector_id: string;
  collector_name: string;
  source_url: string;
  state: string;
  image: string;
  generation: string;
  message: string;
}
export interface VerificationResult extends Partial<RevenueVerification> { verified: boolean; deferred?: boolean }
const verificationBase = '/api/v3/revenue-verification';
export const loadRevenueVerifications = () => client.get<{items: RevenueVerification[]}>(verificationBase);
export const submitRevenueVerification = (id: string, generation: string, answer: string) => client.post<VerificationResult>(`${verificationBase}/${id}/submit`, {generation, answer});
export const refreshRevenueVerification = (id: string) => client.post<RevenueVerification>(`${verificationBase}/${id}/refresh`, {});
export const deferRevenueVerification = (id: string) => client.post<VerificationResult>(`${verificationBase}/${id}/defer`, {});

export const loadRevenueVerification = (id: string) => client.get<{state: string}>(`${verificationBase}/${id}`);
