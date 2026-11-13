import type { AccountDailyTrafficDetail } from '../types/shortDramaOps.ts';

export const ACCOUNT_DAILY_COLUMNS: { key: keyof AccountDailyTrafficDetail; title: string; numeric?: boolean; signed?: boolean }[] = [
  {key:'accountName',title:'账号'}, {key:'channelId',title:'账号UID'},
  {key:'theater',title:'绑定剧场'}, {key:'date',title:'指定日期'},
  {key:'followerTotal',title:'关注者总量',numeric:true}, {key:'views',title:'总计播放量',numeric:true},
  {key:'followsAdded',title:'新增关注',numeric:true}, {key:'follows',title:'净增关注',numeric:true,signed:true},
  {key:'followsReduced',title:'取消关注',numeric:true}, {key:'hearts',title:'爱心数',numeric:true},
  {key:'thumbsUp',title:'点赞数',numeric:true}, {key:'comments',title:'评论数',numeric:true},
  {key:'shares',title:'分享数',numeric:true},
];

export function accountDailyCell(value: unknown, signed = false): string {
  if (value === null || value === undefined || (typeof value === 'number' && !Number.isFinite(value))) return '—';
  if (typeof value === 'number') return `${signed && value > 0 ? '+' : ''}${value.toLocaleString('zh-CN')}`;
  return String(value);
}

export function accountDailyExport(rows: AccountDailyTrafficDetail[]) {
  return { headers:['记录ID',...ACCOUNT_DAILY_COLUMNS.map(c=>c.title)],
    rows:rows.map(row=>[row.id,...ACCOUNT_DAILY_COLUMNS.map(c=> {
      const value=row[c.key];
      return value === null || value === undefined || (typeof value === 'number' && !Number.isFinite(value)) ? '' : String(value);
    })]) };
}
