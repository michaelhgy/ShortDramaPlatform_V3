import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Clock3, Database, Info, Loader2, RefreshCw, Square, X, ChevronDown, AlertTriangle, ArrowLeft } from 'lucide-react';
import { CockpitModal } from './CockpitModal';
import { loadCollectionState, startCollection, retryCollection, stopCollection, type CollectionJob, type CollectionState } from '../../api/operationsDashboard';
import { accountProgress, buildCollectionRequest, categoryLabels, entryCategories, recentPublicationRange, supports, type CollectionDraft, type CollectionEntry, type VisibleCategory } from './collectionPanelModel';

const categories: Array<{id: VisibleCategory; note: string}> = [
  {id: 'daily', note: '补齐截至昨天的历史与缺日；已有完整日不重复获取'},
  {id: 'works', note: '主动更新作品当前累计流量、封面和播放地址'},
  {id: 'optimization', note: '读取已有诊断，补齐V3作品分析；已存分析复用'},
  {id: 'revenue', note: '有效结果不重复查询；首次补采与累计差额由后端处理'},
];
const stateLabels: Record<CollectionJob['state'], string> = {running: '正在采集', stopping: '正在停止后续请求', completed: '本次采集完成', partial: '部分数据待补齐', paused: '访问受限，已暂停', stopped: '本次采集已停止', failed: '本次采集未完成'};
const itemLabels = {waiting: '等待中', running: '进行中', success: '已完成', skipped: '已跳过', partial: '待补齐', failed: '失败', stopped: '未完成'};
const shortTime = (value?: string) => value ? value.replace('T', ' ').replace(/\+08:00$/, '') : '尚未取得';
const active = (job?: CollectionJob | null) => !!job && ['running', 'stopping'].includes(job.state);
const fieldClass = 'rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs text-slate-700 outline-none focus:border-indigo-300 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400';
const buttonClass = 'rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40';

function DateFields({label, start, end, latest, disabled, onStart, onEnd}: {
  label: string; start: string; end: string; latest?: string; disabled?: boolean; onStart: (value: string) => void; onEnd: (value: string) => void;
}) {
  return <div className="mt-2 flex flex-wrap items-center gap-2">
    <input type="date" aria-label={`${label}开始日期`} value={start} max={latest} disabled={disabled} onChange={e => onStart(e.target.value)} className={fieldClass} />
    <span className="text-xs text-slate-400">至</span>
    <input type="date" aria-label={`${label}结束日期`} value={end} max={latest} disabled={disabled} onChange={e => onEnd(e.target.value)} className={fieldClass} />
  </div>;
}

export function CollectionPanel({open, onClose, initialAccountIds, initialEntry = 'routine', onDataSaved, onActivity}: {
  open: boolean; onClose: () => void; initialAccountIds: string[]; initialEntry?: CollectionEntry; onDataSaved: () => void; onActivity: (running: boolean) => void;
}) {
  const [state, setState] = useState<CollectionState | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [selectedCategories, setCategories] = useState<VisibleCategory[]>(entryCategories(initialEntry));
  const [interval, setIntervalValue] = useState('2');
  const [cooldown, setCooldown] = useState('1');
  const [forceWorks, setForceWorks] = useState(false);
  const [dailyMode, setDailyMode] = useState<CollectionDraft['dailyMode']>('fill_missing');
  const [dailyStart, setDailyStart] = useState(''), [dailyEnd, setDailyEnd] = useState('');
  const [worksMode, setWorksMode] = useState<CollectionDraft['worksMode']>('all');
  const [worksStart, setWorksStart] = useState(''), [worksEnd, setWorksEnd] = useState('');
  const [revenueMode, setRevenueMode] = useState<CollectionDraft['revenueMode']>('routine');
  const [revenueStart, setRevenueStart] = useState(''), [revenueEnd, setRevenueEnd] = useState('');
  const [search, setSearch] = useState('');
  const [error, setError] = useState(''), [pollError, setPollError] = useState(''), [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false), [showLog, setShowLog] = useState(false), [advanced, setAdvanced] = useState(false);
  const [phase, setPhase] = useState<'setup' | 'result'>('setup');
  const [tick, setTick] = useState(Date.now());
  const initialized = useRef(false), wasOpen = useRef(false), completion = useRef(''), observedJob = useRef('');
  const refresh = useRef(onDataSaved); refresh.current = onDataSaved;
  const activity = useRef(onActivity); activity.current = onActivity;
  const capabilities = state?.capabilities;
  useEffect(() => {
    if (open && !wasOpen.current) {
      setSelected(initialAccountIds); setCategories(entryCategories(initialEntry, capabilities));
      setPhase(active(state?.job) ? 'result' : 'setup'); setNotice(''); setError(''); setSearch('');
      setDailyMode('fill_missing'); setForceWorks(false); setRevenueMode('routine');
    }
    wasOpen.current = open;
  }, [open, initialAccountIds.join('|'), initialEntry]);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await loadCollectionState();
        if (disposed) return;
        setState(result); setPollError('');
        if (!initialized.current) {
          setIntervalValue(String(result.page_interval_seconds));
          setDailyStart(result.yesterday); setDailyEnd(result.yesterday);
          setRevenueStart(result.yesterday); setRevenueEnd(result.yesterday);
          const range = recentPublicationRange(result.yesterday, 7);
          setWorksStart(range.start); setWorksEnd(range.end);
          setWorksMode(supports(result.capabilities, 'works_publication_range') ? 'recent7' : 'all');
          setCategories(entryCategories(initialEntry, result.capabilities)); initialized.current = true;
        }
        activity.current(active(result.job));
        if (result.job && !active(result.job) && completion.current !== result.job.id) { completion.current = result.job.id; refresh.current(); }
        timer = setTimeout(poll, active(result.job) || open ? 1200 : 6000);
      } catch (e) {
        if (!disposed) {setPollError(e instanceof Error ? e.message : '读取任务进度失败'); timer = setTimeout(poll, 3000);}
      }
    };
    void poll();
    return () => {disposed = true; clearTimeout(timer);};
  }, [open]);
  useEffect(() => {
    if (state?.job && active(state.job) && observedJob.current !== state.job.id) {
      observedJob.current = state.job.id; setPhase('result');
      // The running job and retry subset never overwrite the next collection's account/range draft.
    }
  }, [state?.job?.id, state?.job?.state]);
  useEffect(() => {if (!open) return; const timer = setInterval(() => setTick(Date.now()), 1000); return () => clearInterval(timer);}, [open]);
  if (!open) return null;
  const job = state?.job, running = active(job), showTask = !!job && (running || phase === 'result');
  const accounts = state?.accounts || [], validIds = new Set(accounts.filter(a => a.available).map(a => a.id));
  const chosen = selected.filter(id => validIds.has(id));
  const visible = accounts.filter(a => `${a.name} ${a.uid}`.toLowerCase().includes(search.toLowerCase()));
  const groups = job ? accountProgress(job) : [], finishedAccounts = groups.filter(group => group.done).length;
  const progress = groups.length ? finishedAccounts / groups.length * 100 : 0;
  const current = job?.items.find(i => i.id === job.current_item);
  const stepWait = current ? Math.max(0, Math.floor((tick - Date.parse(current.updated_at)) / 1000)) : 0;
  const retryCount = job?.items.filter(i => ['partial', 'failed', 'stopped'].includes(i.status)).length || 0;
  const works = selectedCategories.includes('works'), daily = selectedCategories.includes('daily'), revenue = selectedCategories.includes('revenue');
  const request = buildCollectionRequest({accountIds: chosen, categories: selectedCategories, interval, cooldown, forceWorks, dailyMode, dailyStart, dailyEnd, worksMode, worksStart, worksEnd, revenueMode, revenueStart, revenueEnd}, state?.yesterday || '', capabilities);
  const elapsed = job ? Math.max(0, Math.floor(((job.finished_at ? Date.parse(job.finished_at) : tick) - Date.parse(job.started_at)) / 1000)) : 0;
  const lastWorks = chosen.map(id => accounts.find(a => a.id === id)?.last_success.works).filter(Boolean).sort();
  const toggleCategory = (id: VisibleCategory) => setCategories(old => old.includes(id) ? old.filter(value => value !== id) : [...old, id]);
  const act = async (kind: 'start' | 'retry' | 'stop') => {
    if (busy || (kind === 'start' && (!state || !request.options))) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = kind === 'stop' ? await stopCollection(job!.id) : kind === 'retry' ? await retryCollection() : await startCollection(request.options!);
      setState(old => old ? {...old, job: result.job} : old); setPhase('result');
      activity.current(active(result.job));
      if ('reused' in result && result.reused) setNotice('已有任务正在执行，已打开它的进度；没有重复发起采集。');
    } catch (e) {setError(e instanceof Error ? e.message : '操作未完成，请重试');}
    finally {setBusy(false);}
  };
  return <CockpitModal label="更新数据" onClose={onClose} width="max-w-5xl" testId="collection-panel">
    <div className="flex shrink-0 items-center justify-between border-b border-slate-100 bg-slate-50/80 px-5 py-4 sm:px-6">
      <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#1E1644] text-[#DDFD00] shadow-sm"><Database className="h-5 w-5" /></div><div><h3 className="text-base font-extrabold text-[#1E1644]">更新数据</h3><p className="mt-0.5 text-xs text-slate-400">{showTask ? '采集进度与结果 · 关闭窗口后任务仍可继续' : '缺失数据按需补齐，视频流量由你选择更新'}</p></div></div>
      <button aria-label="关闭采集面板" onClick={onClose} className="rounded-xl p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X className="h-5 w-5" /></button>
    </div>
    <div className="space-y-4 overflow-y-auto p-5 sm:p-6">
      {error && <div role="alert" className="rounded-xl border border-rose-100 bg-rose-50 p-3 text-xs text-rose-700">{error}</div>}
      {pollError && <div role="alert" className="rounded-xl border border-amber-100 bg-amber-50 p-3 text-xs text-amber-800">{pollError}。读取进度失败不会自动重新发起采集。</div>}
      {notice && <div role="status" className="rounded-xl bg-indigo-50 p-3 text-xs text-indigo-700">{notice}</div>}
      {!showTask ? <>
        <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex flex-wrap gap-2">
          {([['routine', '日常补齐'], ['works', '更新视频流量'], ['optimization', '补齐优化记录']] as const).map(([entry, label]) => <button key={entry} type="button" onClick={() => {setCategories(entryCategories(entry, capabilities)); setDailyMode('fill_missing'); setForceWorks(false);}} className={`${buttonClass} ${entryCategories(entry, capabilities).join() === selectedCategories.join() ? 'border-indigo-200 bg-indigo-50 text-indigo-700' : ''}`}>{label}</button>)}
        </div>{job && <button onClick={() => setPhase('result')} className="text-xs font-semibold text-indigo-600">查看最近结果</button>}</div>
        <fieldset disabled={busy || !state} className="space-y-4 disabled:opacity-60">
          <div><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-bold text-slate-800">更新哪些数据</h4><span className="text-[11px] text-slate-400">可自由组合，打开本面板不会发起采集</span></div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">{categories.map(category => {
              const unavailable = category.id === 'revenue' && !supports(capabilities, 'revenue');
              return <label key={category.id} className={`flex items-start gap-3 rounded-xl border p-3 transition-colors ${unavailable ? 'cursor-not-allowed border-slate-100 bg-slate-50' : selectedCategories.includes(category.id) ? 'cursor-pointer border-indigo-200 bg-indigo-50/60' : 'cursor-pointer border-slate-200 hover:bg-slate-50'}`}>
                <input type="checkbox" aria-label={categoryLabels[category.id]} checked={selectedCategories.includes(category.id)} disabled={unavailable} onChange={() => toggleCategory(category.id)} className="mt-0.5 accent-indigo-600" />
                <span className="min-w-0"><span className="flex items-center gap-2 text-xs font-bold text-slate-800">{categoryLabels[category.id]}{unavailable && <span className="rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">待接入</span>}</span><span className="mt-1 block text-[11px] leading-relaxed text-slate-500">{category.note}</span></span>
              </label>;
            })}</div>
            <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-slate-500"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />视频数、关注者数随账号日数据附带读取小V猫已有资料，按来源更新时间显示。</p>
          </div>
          {daily && <section className="rounded-xl border border-slate-200 p-3"><h4 className="text-xs font-bold text-slate-800">账号日数据</h4><div className="mt-2 flex flex-wrap gap-2">
            <label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="radio" name="daily-mode" checked={dailyMode === 'fill_missing'} onChange={() => setDailyMode('fill_missing')} className="accent-indigo-600" />自动补缺</label>
            <label className="flex items-center gap-1.5 text-xs text-slate-500"><input type="radio" name="daily-mode" checked={dailyMode === 'force_range'} disabled={!supports(capabilities, 'daily_force_range')} onChange={() => setDailyMode('force_range')} className="accent-indigo-600" />强制重取指定日期{!supports(capabilities, 'daily_force_range') && '（待接入）'}</label>
          </div><p className="mt-2 text-[11px] leading-relaxed text-slate-500">首次向前补齐历史，后续补截至{state?.yesterday || '昨天'}的缺日；已有完整日跳过，缺字段不算完整。</p>
            {dailyMode === 'force_range' && <><DateFields label="日数据" start={dailyStart} end={dailyEnd} latest={state?.yesterday} onStart={setDailyStart} onEnd={setDailyEnd} /><p className="mt-2 text-[11px] text-amber-700">仅重取所选账号和日期；获取失败保留原值。</p></>}
          </section>}
          {works && <section className="rounded-xl border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-xs font-bold text-slate-800">作品发布时间范围</h4><span className="text-[11px] text-slate-400">更新所选作品当前累计值</span></div>
            <div className="mt-2 flex flex-wrap gap-2">{([['all', '全部作品'], ['recent7', '近7天'], ['recent30', '近30天'], ['custom', '自定义']] as const).map(([mode, label]) => <button type="button" key={mode} disabled={mode !== 'all' && !supports(capabilities, 'works_publication_range')} aria-pressed={worksMode === mode} onClick={() => setWorksMode(mode)} className={`${buttonClass} ${worksMode === mode ? 'border-indigo-200 bg-indigo-50 text-indigo-700' : ''}`}>{label}</button>)}</div>
            {worksMode === 'custom' && <DateFields label="作品发布时间" start={worksStart} end={worksEnd} latest={state ? recentPublicationRange(state.yesterday, 1).end : undefined} onStart={setWorksStart} onEnd={setWorksEnd} />}
            {worksMode.startsWith('recent') && state && <p className="mt-2 text-[11px] text-slate-500">{recentPublicationRange(state.yesterday, worksMode === 'recent7' ? 7 : 30).start} 至 {recentPublicationRange(state.yesterday, 1).end}（含今天）</p>}
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{supports(capabilities, 'works_publication_range') ? '按发布时间从新到旧分页，到范围下界后停止；范围外作品保留上次数据。' : '当前支持全部作品更新；按发布时间提前停止翻页尚待采集器接入，暂不可选。'}{lastWorks.length ? ` 所选账号最近一次作品采集：${shortTime(lastWorks.at(-1))}。` : ''}</p>
          </section>}
          <details className="rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2.5"><summary className="cursor-pointer text-xs font-semibold text-slate-600">剧场收益如何更新{!supports(capabilities, 'revenue') && ' · 等待后端接入'}</summary><div className="mt-2 space-y-1.5 text-[11px] leading-relaxed text-slate-500"><p>按日来源日常查昨天；已取得有效结果的账号日期跳过，未更新和失败不计为零收益。</p><p>首次向前补采，连续7天明确零收益后停止；中断后接着补。累计来源按查询能力读取本月、上月、上上月，首次金额归采集日，以后只记新增差额，漏采不拆回历史日期。</p><p>青柠默认只存账号日收益。无法查询的月份保留缺失。各剧场能力、去重与金额归属由收益后端统一判断。</p></div></details>
          {revenue && <section className="rounded-xl border border-slate-200 p-3"><h4 className="text-xs font-bold text-slate-800">收益查询范围</h4><div className="mt-2 flex flex-wrap gap-3"><label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="radio" name="revenue-mode" checked={revenueMode === 'routine'} onChange={() => setRevenueMode('routine')} className="accent-indigo-600" />日常更新 / 首次自动补采</label><label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="radio" name="revenue-mode" checked={revenueMode === 'date_range'} onChange={() => setRevenueMode('date_range')} className="accent-indigo-600" />指定日期（支持的来源）</label></div>{revenueMode === 'date_range' && <DateFields label="收益" start={revenueStart} end={revenueEnd} latest={state?.yesterday} onStart={setRevenueStart} onEnd={setRevenueEnd} />}<p className="mt-2 text-[11px] text-slate-500">日期范围不表示每个剧场都能查询历史；不支持的来源应返回未执行原因，不改成其他日期查询。</p></section>}
          <section><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-bold text-slate-800">账号范围 <span className="ml-1 text-xs font-normal text-slate-400">已选 {chosen.length} 个</span></h4><div className="flex gap-3 text-xs"><button type="button" onClick={() => setSelected(accounts.filter(a => a.available).map(a => a.id))} className="font-semibold text-indigo-600">全选可采集账号</button><button type="button" onClick={() => setSelected([])} className="text-slate-500">清空</button></div></div>
            <input aria-label="搜索采集账号" value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索账号名称 / 平台账号" className="mb-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs outline-none focus:border-indigo-300" />
            <div className="max-h-40 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200">{visible.map(account => <label key={account.id} className={`flex items-start gap-3 px-3 py-2.5 ${account.available ? 'cursor-pointer hover:bg-slate-50' : 'opacity-50'}`}><input type="checkbox" aria-label={`采集账号 ${account.name}`} disabled={!account.available} checked={chosen.includes(account.id)} onChange={() => setSelected(old => old.includes(account.id) ? old.filter(value => value !== account.id) : [...old, account.id])} className="mt-1 accent-indigo-600" /><span className="min-w-0 flex-1"><span className="block text-xs font-semibold text-slate-800">{account.name}</span><span className="mt-0.5 block text-[11px] leading-relaxed text-slate-400">{!account.available ? account.unavailable_reason : daily ? account.daily_through ? `日数据已完整至 ${account.daily_through}；本次只补缺失日期` : account.daily_missing ? `已记录 ${account.daily_missing} 个缺失日期，历史仍待补齐` : '尚未确认完整历史，首次将补齐可获取的数据' : works ? `上次作品采集：${shortTime(account.last_success.works)}` : `上次优化读取：${shortTime(account.last_success.optimization)}`}</span></span></label>)}{!visible.length && <p className="p-5 text-center text-xs text-slate-400">{state ? '没有匹配账号' : '正在读取账号与本地采集状态…'}</p>}</div>
          </section>
          {works && <section className="rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2.5"><button type="button" aria-expanded={advanced} onClick={() => setAdvanced(value => !value)} className="flex w-full items-center justify-between text-xs font-semibold text-slate-600">高级设置 · 翻页速度与重复更新<ChevronDown className={`h-3.5 w-3.5 transition-transform ${advanced ? 'rotate-180' : ''}`} /></button>{advanced && <div className="mt-3 space-y-3"><div className="flex flex-wrap gap-4"><label className="text-[11px] text-slate-500">每页等待上限（秒）<input aria-label="每页等待上限" type="number" min="0.1" max="60" step="0.1" value={interval} onChange={e => setIntervalValue(e.target.value)} className={`${fieldClass} ml-2 w-20`} /></label><label className="text-[11px] text-slate-500">重复更新间隔（小时）<input aria-label="作品重复更新间隔" type="number" min="0" max="168" value={cooldown} onChange={e => setCooldown(e.target.value)} className={`${fieldClass} ml-2 w-20`} /></label></div><label className="flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={forceWorks} onChange={e => setForceWorks(e.target.checked)} className="accent-indigo-600" />本次仍要更新作品，忽略重复更新间隔</label><p className="text-[11px] leading-relaxed text-slate-400">翻页在等待上限内随机等待。重复更新间隔只作用于视频流量，不改变日数据与收益的完整性判断；不是平台安全频率承诺。</p></div>}</section>}
        </fieldset>
        <div className="rounded-xl bg-indigo-50/60 px-3 py-2.5 text-[11px] leading-relaxed text-indigo-700" aria-live="polite">本次：{chosen.length} 个账号 · {selectedCategories.map(category => categoryLabels[category]).join('、') || '尚未选择数据'}{daily && '；日数据已有完整日跳过'}{works && `；作品${worksMode === 'all' ? '全部更新' : '按发布时间范围更新'}`}{revenue && '；收益有效结果跳过'}。{request.error && <span className="mt-1 block text-amber-700">{request.error}</span>}</div>
      </> : job && <>
        <section className="rounded-2xl border border-slate-200 p-4" aria-live="polite"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="flex items-center gap-2 text-sm font-bold text-slate-800">{running ? <Loader2 className="h-4 w-4 animate-spin text-indigo-600" /> : job.state === 'completed' ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertTriangle className="h-4 w-4 text-amber-500" />}{stateLabels[job.state]}</h4><span className="text-[11px] text-slate-400">耗时 {Math.floor(elapsed / 60)}分{elapsed % 60}秒</span></div>
          <p className="mt-2 text-xs text-slate-500">{groups.length} 个账号 · {[...new Set(job.items.filter(item => item.category !== 'profile').map(item => categoryLabels[item.category]))].join('、')}{job.items.some(item => item.category === 'profile') && ' · 附带账号总量'}</p>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label="账号完成进度" aria-valuenow={finishedAccounts} aria-valuemin={0} aria-valuemax={groups.length}><div className={`h-full rounded-full transition-all ${job.state === 'completed' ? 'bg-emerald-500' : 'bg-indigo-500'}`} style={{width: `${progress}%`}} /></div>
          <div className="mt-2 flex flex-wrap justify-between gap-2 text-[11px] text-slate-500"><span>已完成 {finishedAccounts} / {groups.length} 个账号（含无需更新）{groups.some(group => group.needsAttention) && ` · ${groups.filter(group => group.needsAttention).length} 个账号待处理`}</span><span>停止、失败不计为完成</span></div>
          {running && current && <div className="mt-3 rounded-xl bg-indigo-50/60 p-3"><p className="text-xs font-bold text-indigo-800">{current.account_name} · {categoryLabels[current.category]}</p><p className="mt-1 text-xs leading-relaxed text-indigo-700">{current.message}</p>{stepWait >= 8 && <p className="mt-1 text-[11px] text-indigo-500">此步骤已等待 {stepWait} 秒，正在等待当前请求返回；暂无新的进度回报。</p>}</div>}
          {job.state === 'stopping' && <p className="mt-2 text-[11px] text-amber-700">当前请求返回后停止，已保存结果保留。</p>}
        </section>
        <div className="space-y-2">{groups.map(group => <section key={group.id} className="rounded-xl border border-slate-200 p-3"><div className="mb-2 flex items-center justify-between"><h5 className="text-xs font-bold text-slate-800">{group.name}</h5><span className={`text-[11px] ${group.done ? 'text-emerald-600' : group.needsAttention ? 'text-amber-600' : 'text-slate-400'}`}>{group.done ? '已完成' : group.needsAttention ? '待处理' : group.items.some(item => item.status === 'running') ? '进行中' : '等待中'}</span></div><div className="space-y-2">{group.items.map(item => <div key={item.id} className="flex items-start gap-2 text-[11px]"><span className={`shrink-0 rounded px-1.5 py-0.5 ${item.status === 'success' || item.status === 'skipped' ? 'bg-emerald-50 text-emerald-700' : ['failed', 'partial', 'stopped'].includes(item.status) ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>{itemLabels[item.status]}</span><p className="min-w-0 break-words leading-relaxed text-slate-500"><span className="font-semibold text-slate-700">{categoryLabels[item.category]}：</span>{item.message || '等待前面的步骤完成'}</p></div>)}</div></section>)}</div>
        <div><button type="button" onClick={() => setShowLog(value => !value)} className="flex items-center gap-1 text-xs font-semibold text-slate-500"><ChevronDown className={`h-3.5 w-3.5 ${showLog ? 'rotate-180' : ''}`} />{showLog ? '收起详细进度' : '查看详细进度'}</button>{showLog && <div className="mt-2 max-h-44 space-y-1 overflow-y-auto rounded-xl bg-slate-50 p-3 text-[11px] text-slate-500">{job.events.map((event, i) => <p key={i} className="break-words leading-relaxed">{shortTime(event.time)} · {event.account_name} · {categoryLabels[event.category]} · {event.message}</p>)}</div>}</div>
      </>}
    </div>
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/70 px-5 py-3 sm:px-6"><p className="flex items-center gap-1.5 text-[11px] text-slate-400"><Clock3 className="h-3.5 w-3.5 shrink-0" />{running ? '单批串行采集；关闭面板不停止任务' : showTask ? '重试只处理未完成项，不改变下一次选择' : '先选范围，再主动开始；页面刷新仅读本地数据'}</p><div className="flex flex-wrap gap-2">
      {running ? <button onClick={() => void act('stop')} disabled={busy || job?.state === 'stopping'} className={buttonClass}><span className="flex items-center gap-1.5"><Square className="h-3 w-3" />{job?.state === 'stopping' ? '正在停止' : '停止后续采集'}</span></button> : showTask ? <><button onClick={() => setPhase('setup')} className={buttonClass}><span className="flex items-center gap-1"><ArrowLeft className="h-3.5 w-3.5" />调整下次范围</span></button>{retryCount > 0 && <button onClick={() => void act('retry')} disabled={busy} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 disabled:opacity-40">{busy ? '正在提交…' : `重试未完成项（${retryCount}）`}</button>}<button onClick={onClose} className={buttonClass}>完成</button></> : <button onClick={() => void act('start')} disabled={busy || !state || !!request.error} className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40">{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}{busy ? '正在提交…' : '开始采集'}</button>}
    </div></div>
  </CockpitModal>;
}
