// Transport-only types. Page models belong beside their V2 feature types.
export interface V1ListResponse<T> { items: T[]; }
export interface V1Account { id: number; nickname: string; channel_id: string; status: string; theater_id: number | null; }
export interface V1Plan { id: number; account_id: number; make_date: string; publish_date: string; status: string; }
export interface V1StatusValue { code: string; label: string; color?: string; }
