import type { AccountInfo } from '../../types/shortDramaOps';

export function AccountProfileTotals({ account }: { account: Pick<AccountInfo, 'videoTotal' | 'followerTotal'> }) {
  return <div data-account-profile-totals className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] leading-4 text-slate-500">
    <span className="whitespace-nowrap">视频 <span className="ml-1 font-medium tabular-nums text-slate-700">{account.videoTotal == null ? '—' : account.videoTotal.toLocaleString('zh-CN')}</span></span>
    <span className="whitespace-nowrap">关注者 <span className="ml-1 font-medium tabular-nums text-slate-700">{account.followerTotal == null ? '—' : account.followerTotal.toLocaleString('zh-CN')}</span></span>
  </div>;
}
