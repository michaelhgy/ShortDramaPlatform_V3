const colors: Record<string, string> = {
  正常: 'bg-emerald-50 text-emerald-700', 观察: 'bg-blue-50 text-blue-700',
  限流: 'bg-amber-50 text-amber-700', 二限: 'bg-orange-50 text-orange-700',
  实名: 'bg-purple-50 text-purple-700', 封禁: 'bg-rose-50 text-rose-700',
  停用: 'bg-slate-100 text-slate-500', 注销: 'bg-slate-100 text-slate-500',
};

export function BusinessAccountStatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  return <span data-business-account-status={status} aria-label={`账号状态：${status}`}
    className={`inline-flex flex-none items-center whitespace-nowrap rounded-md px-1.5 py-0.5 text-[10px] font-medium leading-4 ${colors[status] || 'bg-slate-100 text-slate-500'}`}>{status}</span>;
}
