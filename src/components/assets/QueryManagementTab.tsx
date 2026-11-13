import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronRight, History, Link2, Loader2, Search, Settings2, ShieldCheck, X } from 'lucide-react';
import { deferRevenueVerification, loadRevenueVerification, loadQuerySettings, saveQuerySetting, testQuerySetting, type QueryCandidate, type QueryPreview, type QuerySetting } from '../../api/revenueQuerySettings';
import { beijingDateString } from '../../utils/beijingTime';
const beijingYesterdayDateString = () => beijingDateString(new Date(Date.now() - 86_400_000));

const inputStyle = 'w-full rounded-xl border border-black/[0.08] bg-slate-50 px-3 py-2.5 text-xs outline-none focus:border-[#1A1D2E]/40 focus:bg-white disabled:opacity-50';
const errorMessage = (error: unknown) => error instanceof Error ? error.message : '操作失败，请稍后重试';
const formatTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '尚未测试';

interface Props { onShowToast: (message: string) => void }
export function QueryManagementTab({ onShowToast }: Props) {
  const [items, setItems] = useState<QuerySetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<QuerySetting | null>(null);
  const load = async () => {
    setLoading(true);
    setError('');
    try { setItems((await loadQuerySettings()).items); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const filtered = items.filter(item => `${item.name} ${item.aliases.join(' ')}`.toLowerCase().includes(search.trim().toLowerCase()));
  return <div className="space-y-5">
    <section className="rounded-2xl border border-black/[0.06] bg-white p-5 shadow-xs">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#1A1D2E] text-[#DDFD00]"><Link2 className="h-5 w-5" /></div>
          <div><h2 className="text-sm font-black text-[#1A1D2E]">查单管理</h2><p className="mt-1 text-xs leading-5 text-slate-500">维护软件内置采集器的查单链接，换链接不用重新绑定剧场和账号。</p></div>
        </div>
        <div className="flex gap-2 text-[11px] font-semibold"><span className="rounded-lg bg-slate-100 px-3 py-2">内置 {items.length} 个</span><span className="rounded-lg bg-emerald-50 px-3 py-2 text-emerald-700">启用 {items.filter(item => item.enabled).length} 个</span></div>
      </div>
      <div className="mt-4 flex gap-2 rounded-xl border border-black/[0.04] bg-slate-50 p-3 text-[11px] leading-5 text-slate-500"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-slate-600" /><p>先测试，再确认生效。测试只查询并预览，不写入收益；失败时旧配置继续保留。这里只能修改已适配来源，换网站或返回字段变化仍需适配采集器。</p></div>
    </section>
    <section className="overflow-hidden rounded-2xl border border-black/[0.06] bg-white shadow-xs">
      <div className="flex items-center justify-between gap-3 border-b border-black/[0.06] p-4 flex-wrap">
        <div className="relative w-full sm:w-72"><Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><input aria-label="搜索采集器" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索剧场或采集器名称" className={`${inputStyle} pl-9`} /></div>
        <button type="button" onClick={() => void load()} disabled={loading} className="rounded-xl border border-black/[0.08] px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50">{loading ? '正在读取…' : '刷新配置'}</button>
      </div>
      {error && <div role="alert" className="m-4 rounded-xl bg-rose-50 p-3 text-xs text-rose-700">{error}，可点击刷新重试；已有配置未被修改。</div>}
      <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs">
        <thead className="bg-slate-50/70 text-[11px] text-slate-500"><tr>{['采集器 / 收益类型', '当前生效链接', '状态', '最近试查', '操作'].map(label => <th key={label} className="px-4 py-3 font-semibold">{label}</th>)}</tr></thead>
        <tbody className="divide-y divide-black/[0.04]">{filtered.map(item => <tr key={item.id} className="hover:bg-slate-50/50">
          <td className="px-4 py-4"><p className="whitespace-nowrap font-bold text-[#1A1D2E]">{item.name}</p><p className="mt-1.5 text-[10px] text-slate-400">{item.date_precision === 'day' ? '按日查询 · 最多到昨天' : `累计收益 · ${item.source_period === 'auto' ? (item.daily_url ? '按结果识别月份 · 日/月核对' : '按结果识别月份 · 月累计') : item.source_period === 'unknown' ? '期间待确认' : item.source_period}`}</p></td>
          <td className="max-w-[300px] px-4 py-4"><p className="break-all text-[11px] leading-5 text-slate-500" title={item.source_url}>{item.source_url}</p><p className="mt-1 text-[10px] text-slate-400">{item.revision ? `配置版本 ${item.revision}` : '软件内置默认链接'}</p></td>
          <td className="px-4 py-4"><span className={`whitespace-nowrap rounded-md px-2 py-1 text-[10px] font-bold ${item.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>{item.enabled ? '已启用' : '已停用'}</span></td>
          <td className="px-4 py-4"><p className={`whitespace-nowrap text-[11px] ${item.last_test?.passed ? 'text-emerald-700' : item.last_test ? 'text-amber-700' : 'text-slate-400'}`}>{item.last_test ? item.last_test.passed ? '候选测试通过' : '候选未通过' : '尚未试查'}</p><p className="mt-1 whitespace-nowrap text-[10px] text-slate-400">{item.last_test ? formatTime(item.last_test.tested_at) : '不代表来源在线状态'}</p></td>
          <td className="px-4 py-4"><button type="button" onClick={() => setEditing(item)} aria-label={`管理${item.name}`} className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-black/[0.08] px-2.5 py-2 font-semibold text-slate-600 hover:bg-slate-100"><Settings2 className="h-3.5 w-3.5" />管理<ChevronRight className="h-3 w-3" /></button></td>
        </tr>)}</tbody>
      </table></div>
      {!filtered.length && <div className="p-10 text-center text-xs text-slate-400">{loading ? '正在读取内置采集器…' : error ? '暂时无法读取采集器' : '没有匹配的采集器'}</div>}
    </section>
    {editing && <QueryEditor key={`${editing.id}-${editing.revision}`} item={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); onShowToast('查单配置已生效，剧场和账号绑定保持不变'); void load(); }} />}
  </div>;
}

const QueryEditor: React.FC<{ item: QuerySetting; onClose: () => void; onSaved: () => void }> = ({ item, onClose, onSaved }) => {
  const daily = item.date_precision === 'day';
  const zishi = item.id.startsWith('zishi_');
  const [candidate, setCandidate] = useState<QueryCandidate>({ source_url: item.source_url, daily_url: item.daily_url, previous_month_url: item.previous_month_url, extract_code: item.extract_code, source_period: item.source_period, enabled: item.enabled, revision: item.revision, channel_id: '', query_date: beijingYesterdayDateString(), period_relation: 'same' });
  const [preview, setPreview] = useState<QueryPreview | null>(null);
  const [busy, setBusy] = useState<'test' | 'save' | ''>('');
  const [error, setError] = useState('');
  const [restored, setRestored] = useState('');
  const [confirmClose, setConfirmClose] = useState(false);
  const [waitingVerification, setWaitingVerification] = useState('');
  const [showCode, setShowCode] = useState(false);
  const update = (patch: Partial<QueryCandidate>) => { if (waitingVerification) void deferRevenueVerification(waitingVerification).catch(() => {}); setCandidate(old => ({ ...old, ...patch, test_token: '' })); setPreview(null); setError(''); setWaitingVerification(''); };
  const changed = candidate.source_url.trim() !== item.source_url || candidate.daily_url !== item.daily_url || candidate.previous_month_url !== item.previous_month_url || candidate.source_period !== item.source_period || candidate.extract_code !== item.extract_code;
  const needsTest = changed || (candidate.enabled && !item.enabled);
  const runTest = async () => {
    setBusy('test'); setError(''); setPreview(null);
    try { const result = await testQuerySetting(item.id, candidate); setPreview(result); setWaitingVerification(result.verification_id || ''); setCandidate(old => ({ ...old, test_token: result.test_token || '' })); }
    catch (cause) { setError(errorMessage(cause)); setCandidate(old => ({ ...old, test_token: '' })); }
    finally { setBusy(''); }
  };
  useEffect(() => {
    if (!waitingVerification) return;
    let disposed = false, resumed = false;
    let timer: ReturnType<typeof setTimeout>;
    const continueTest = () => {
      if (!disposed && !resumed) { resumed = true; setWaitingVerification(''); void runTest(); }
    };
    const resume = (event: Event) => {
      if ((event as CustomEvent<{id: string}>).detail?.id === waitingVerification) continueTest();
    };
    const poll = async () => {
      try {
        const result = await loadRevenueVerification(waitingVerification);
        if (disposed || resumed) return;
        if (result.state === 'ready') { continueTest(); return; }
        if (result.state !== 'pending') { setWaitingVerification(''); setError('人工验证暂未完成，可重新试查；当前配置未改变'); return; }
      } catch { /* Preserve the waiting state during a temporary local connection failure. */ }
      if (!disposed && !resumed) timer = setTimeout(poll, 2000);
    };
    window.addEventListener('revenue-verification-completed', resume);
    void poll();
    return () => { disposed = true; clearTimeout(timer); window.removeEventListener('revenue-verification-completed', resume); };
  }, [waitingVerification, candidate]);
  const save = async () => {
    setBusy('save'); setError('');
    try { await saveQuerySetting(item.id, candidate); onSaved(); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(''); }
  };
  const leave = () => {
    if (waitingVerification) void deferRevenueVerification(waitingVerification).catch(() => {});
    onClose();
  };
  const close = () => {
    if (busy) return;
    if (changed || candidate.enabled !== item.enabled) { setConfirmClose(true); return; }
    leave();
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1A1D2E]/40 p-4 backdrop-blur-sm" role="presentation">
    <section role="dialog" aria-modal="true" aria-labelledby="query-editor-title" onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key === 'Tab') {
        const controls = Array.from<HTMLElement>(event.currentTarget.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled)')).filter(control => !control.matches(':disabled'));
        const first = controls[0], last = controls[controls.length - 1];
        if (first && event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (last && !event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }} className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/30 bg-white shadow-2xl">
      <header className="flex shrink-0 items-center justify-between border-b border-black/[0.06] px-5 py-4"><div><h3 id="query-editor-title" className="text-sm font-black text-[#1A1D2E]">{item.name} · 查单设置</h3><p className="mt-1 text-[10px] text-slate-400">内置编号 {item.id} · 修改链接不会改变绑定</p></div><button type="button" aria-label="关闭查单设置" onClick={close} disabled={Boolean(busy)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 disabled:opacity-40"><X className="h-4 w-4" /></button></header>
      <div className="space-y-5 overflow-y-auto p-5 text-xs">
        <div className="rounded-xl bg-slate-50 p-3 text-[11px] leading-5 text-slate-500">{item.notes}<br />{daily ? '可测试昨天或更早的某一天；正式采集仍按既有补采和去重规则执行。' : zishi ? '月累计增量归采集日；只查询此业务已配置的月份入口，没有链接的历史月份保留未知。' : '累计增量仍归入实际采集日期。这里只标注来源期间，不会把累计金额拆成每日收益，也不新增历史月份查询能力。'}</div>
        {item.last_test && <details className="rounded-xl border border-black/[0.06] p-3 text-[11px] text-slate-500"><summary className="cursor-pointer font-semibold">上次试查：{item.last_test.passed ? '候选测试通过' : '候选未通过'} · {formatTime(item.last_test.tested_at)}</summary><p className="mt-2 break-all leading-5">{item.last_test.message}</p><p className="mt-1 break-all text-[10px] text-slate-400">试查链接：{item.last_test.source_url}</p></details>}
        <fieldset disabled={Boolean(busy)} className="space-y-4">
          <label className="block font-semibold text-[#1A1D2E]">{zishi ? '本月查单链接' : '查单链接'}<input aria-label="查单链接" autoFocus value={candidate.source_url} onChange={event => update({ source_url: event.target.value })} className={`${inputStyle} mt-2 font-normal`} /></label>
          <p className="-mt-2 text-[10px] leading-5 text-slate-400">只支持当前已适配网站的查单链接；更换链接后请先试查。</p>
          {item.id === 'pingyue' && <div><label className="block font-semibold text-[#1A1D2E]">提取码<div className="mt-2 flex gap-2"><input aria-label="提取码" autoComplete="off" type={showCode ? 'text' : 'password'} inputMode="numeric" maxLength={6} value={candidate.extract_code || ''} onChange={event => update({extract_code: event.target.value})} className={`${inputStyle} font-normal`} /><button type="button" aria-label={showCode ? '隐藏提取码' : '显示提取码'} onClick={() => setShowCode(value => !value)} className="shrink-0 rounded-xl border border-black/[0.08] px-3 text-slate-500">{showCode ? '隐藏' : '显示'}</button></div></label><p className="mt-1.5 text-[10px] leading-5 text-slate-400">链接或提取码更新后需重新验证并试查；账号和剧场的关联保持不变。</p></div>}
          {zishi && <div className="space-y-3 rounded-xl border border-black/[0.06] p-3">
            {item.daily_url && <label className="block font-semibold text-[#1A1D2E]">昨日查单链接<input aria-label="昨日查单链接" value={candidate.daily_url || ''} onChange={event => update({ daily_url: event.target.value })} className={`${inputStyle} mt-2 font-normal`} /></label>}
            {item.id === 'zishi_agency' && <label className="block font-semibold text-[#1A1D2E]">上月查单链接（可留空）<input aria-label="上月查单链接" value={candidate.previous_month_url || ''} onChange={event => update({ previous_month_url: event.target.value })} className={`${inputStyle} mt-2 font-normal`} /></label>}
            <p className="text-[10px] leading-5 text-slate-500">上面的查单链接用于本月累计。月份按结果字段识别；配置昨日入口时保留实际日期，用于核对，不再重复相加。所有链接一起试查通过后生效。</p>
          </div>}
          {!daily && !zishi && <div className="space-y-3 rounded-xl border border-black/[0.06] p-3">
            <label className="block font-semibold">来源收益期间<input aria-label="来源收益期间" value={candidate.source_period === 'unknown' ? '' : candidate.source_period} onChange={event => update({ source_period: event.target.value || 'unknown' })} placeholder="未确认，可填 2026-11" className={`${inputStyle} mt-2 font-normal`} /></label>
            <label className="block text-slate-500">与当前链接的关系<select aria-label="期间关系" value={candidate.period_relation} onChange={event => update({ period_relation: event.target.value as 'same' | 'new' })} className={`${inputStyle} mt-2`}><option value="same">同一收益期间，仅换链接或补充月份标注</option><option value="new">新的收益月份，不沿用旧月份累计金额</option></select></label>
            <p className="text-[10px] leading-5 text-amber-700">请按查单页面核对月份。换成上月／新月的链接必须选择“新的收益月份”；新期间首次采集的总额会归入采集日。同一期补充月份标注会保留原累计基线，避免重复入账。</p>
          </div>}
          <label className="flex items-start gap-2 rounded-xl border border-black/[0.06] p-3"><input type="checkbox" checked={candidate.enabled} onChange={event => update({ enabled: event.target.checked })} className="mt-0.5 accent-[#1A1D2E]" /><span><span className="font-semibold">启用此采集器</span><span className="mt-1 block text-[10px] leading-5 text-slate-400">停用后不会向该来源发起收益查询；已有收益和账号绑定不删除。</span></span></label>
          <div className="space-y-3 border-t border-black/[0.06] pt-4">
            <div className="flex items-center justify-between"><h4 className="font-bold">只读试查</h4><span className="text-[10px] text-slate-400">不入账 · 不改变补采进度</span></div>
            <div className={daily ? 'grid grid-cols-1 gap-3 sm:grid-cols-2' : ''}><label className="block text-slate-600">账号 ID<input aria-label="试查账号 ID" autoComplete="off" value={candidate.channel_id} onChange={event => update({ channel_id: event.target.value })} placeholder="仅填写此来源对应的账号" className={`${inputStyle} mt-1.5`} /></label>{daily && <label className="block text-slate-600">查询日期<input aria-label="试查日期" type="date" max={beijingYesterdayDateString()} value={candidate.query_date} onChange={event => update({ query_date: event.target.value })} className={`${inputStyle} mt-1.5`} /></label>}</div>
            <button type="button" disabled={!candidate.channel_id.trim()} onClick={() => void runTest()} className="flex items-center gap-2 rounded-xl border border-black/[0.1] bg-white px-4 py-2.5 font-bold hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">{busy === 'test' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}{busy === 'test' ? '正在只读查询，请稍候…' : '测试并预览结果'}</button>
          </div>
        </fieldset>
        {preview && <div role="status" className={`rounded-xl border p-3 text-[11px] leading-5 ${preview.passed ? 'border-emerald-100 bg-emerald-50 text-emerald-800' : 'border-amber-100 bg-amber-50 text-amber-800'}`}><p className="flex items-center gap-1.5 font-bold">{preview.passed ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}{preview.passed ? '测试通过，等待确认生效' : preview.verification_id ? '等待人工验证，提交后自动继续试查' : '本次试查未通过，旧配置未变'}</p>{preview.amount !== null && <p className="mt-2">{daily ? `${preview.query_date} 日收益` : '来源累计金额'}：<strong className="font-mono">¥ {preview.amount}</strong></p>}<p className="mt-1">{preview.message}</p>{!daily && preview.passed && <p className="mt-1">这是来源原始累计值，不是本次应入账增量。</p>}</div>}
        {error && <div role="alert" className="rounded-xl bg-rose-50 p-3 text-[11px] leading-5 text-rose-700">{error}</div>}
        <div className="border-t border-black/[0.06] pt-4"><label className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500"><History className="h-3.5 w-3.5" />恢复旧链接</label><select aria-label="恢复旧链接" disabled={Boolean(busy)} value={restored} onChange={event => {
          const value = event.target.value; setRestored(value); const old = item.history.find(history => String(history.revision) === value); if (old) update({ source_url: old.source_url, daily_url: old.daily_url, previous_month_url: old.previous_month_url, extract_code: old.extract_code, enabled: old.enabled });
        }} className={`${inputStyle} mt-2`}><option value="">选择历史版本，载入后重新测试确认</option>{item.history.filter(history => history.revision !== item.revision).map(history => <option key={history.revision} value={history.revision}>{history.revision ? `版本 ${history.revision} · ${formatTime(history.saved_at)}` : '软件内置默认链接'}</option>)}</select><p className="mt-1.5 text-[10px] leading-5 text-slate-400">只载入旧链接、提取码和启停状态，收益期间沿用当前设置，请按来源重新核对。不会删除历史收益或立刻替换配置。</p></div>
      </div>
      {confirmClose && <div role="alert" className="flex shrink-0 items-center justify-between gap-3 bg-amber-50 px-5 py-3 text-[11px] leading-5 text-amber-800"><p>尚未确认生效的修改将丢弃，当前链接保持不变。</p><div className="flex shrink-0 gap-3"><button type="button" onClick={leave} className="font-bold underline underline-offset-2">放弃修改并关闭</button><button type="button" onClick={() => setConfirmClose(false)} className="text-slate-600">继续编辑</button></div></div>}
      <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-black/[0.06] bg-slate-50/50 px-5 py-4"><p className="text-[10px] leading-4 text-slate-400">{needsTest && !candidate.test_token ? '变更链接、提取码、期间或重新启用前，请先测试通过' : '确认后仅影响后续采集，历史收益保持不变'}</p><div className="flex shrink-0 gap-2"><button type="button" onClick={close} disabled={Boolean(busy)} className="rounded-xl border border-black/[0.08] bg-white px-4 py-2.5 text-xs font-semibold text-slate-600 disabled:opacity-40">取消</button><button type="button" disabled={Boolean(busy) || (needsTest && !candidate.test_token)} onClick={() => void save()} className="flex items-center gap-1.5 rounded-xl bg-[#1A1D2E] px-4 py-2.5 text-xs font-bold text-[#DDFD00] hover:bg-black/90 disabled:cursor-not-allowed disabled:opacity-40">{busy === 'save' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}确认生效</button></div></footer>
    </section>
  </div>;
}
