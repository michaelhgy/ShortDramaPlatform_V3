import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Link2, Loader2, Play, Plus, RefreshCw, ShieldCheck, Square } from 'lucide-react';
import { ApiError, v2Client } from '../../api/client';

type KeywordRole = 'primary' | 'equivalent' | 'related' | 'candidate' | 'rejected';

interface DramaItem { id: string; current_name: string; }
interface KeywordItem {
  id: string; drama_id: string; drama_name: string; keyword: string; role: KeywordRole; enabled: number;
  observation_count: number; first_observed_ymd: string | null; last_observed_ymd: string | null;
}
interface ConnectionState { status: 'connected' | 'not_connected' | 'needs_reconnect'; initialized_at?: string; message?: string; }
interface CaptureState { status: 'running' | 'stopped'; port?: number; message?: string; }

const ROLE_LABEL: Record<KeywordRole, string> = {
  primary: '主关键词', equivalent: '等价词（已确认）', related: '相关词（不合并）', candidate: '待确认候选', rejected: '不采用',
};

function formatYmd(value: string | null): string {
  return value && /^\d{8}$/.test(value) ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}` : '—';
}

export const WechatIndexModule: React.FC<{ showToast: (message: string) => void }> = ({ showToast }) => {
  const [dramas, setDramas] = useState<DramaItem[]>([]);
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);
  const [connection, setConnection] = useState<ConnectionState>({ status: 'not_connected' });
  const [capture, setCapture] = useState<CaptureState>({ status: 'stopped' });
  const [selectedDramaId, setSelectedDramaId] = useState('');
  const [newKeyword, setNewKeyword] = useState('');
  const [newRole, setNewRole] = useState<KeywordRole>('candidate');
  const [requestTemplate, setRequestTemplate] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);
  const [busyKeywordId, setBusyKeywordId] = useState('');
  const [error, setError] = useState('');

  const reload = async () => {
    const [dramaPayload, keywordPayload, connectionPayload, capturePayload] = await Promise.all([
      v2Client.get<{ items: DramaItem[] }>('/api/v2/dramas'),
      v2Client.get<{ items: KeywordItem[] }>('/api/v2/wechat-index/keywords'),
      v2Client.get<ConnectionState>('/api/v2/wechat-index/connection'),
      v2Client.get<CaptureState>('/api/v2/wechat-index/capture'),
    ]);
    setDramas(dramaPayload.items); setKeywords(keywordPayload.items); setConnection(connectionPayload); setCapture(capturePayload);
  };

  useEffect(() => { void reload().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : '微信指数数据读取失败')); }, []);
  useEffect(() => {
    if (capture.status !== 'running') return undefined;
    const timer = window.setInterval(() => { void reload().catch(() => undefined); }, 1500);
    return () => window.clearInterval(timer);
  }, [capture.status]);

  const visibleKeywords = useMemo(
    () => selectedDramaId ? keywords.filter((item) => item.drama_id === selectedDramaId) : keywords,
    [keywords, selectedDramaId],
  );

  const connect = async () => {
    try {
      const parsed = JSON.parse(requestTemplate) as unknown;
      setIsConnecting(true); setError('');
      await v2Client.post('/api/v2/wechat-index/connection/initialize', { request_template: parsed });
      setRequestTemplate(''); await reload(); showToast('本机微信指数已连接。');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '连接初始化失败');
    } finally { setIsConnecting(false); }
  };

  const startCapture = async () => {
    try { setError(''); setIsConnecting(true); await v2Client.post('/api/v2/wechat-index/capture/start'); await reload(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '本机连接初始化启动失败'); }
    finally { setIsConnecting(false); }
  };

  const stopCapture = async () => {
    try { setError(''); setIsConnecting(true); await v2Client.post('/api/v2/wechat-index/capture/stop'); await reload(); showToast('本机连接初始化已停止，代理和采集证书已清理。'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '本机连接初始化停止失败'); }
    finally { setIsConnecting(false); }
  };

  const addKeyword = async () => {
    if (!selectedDramaId || !newKeyword.trim()) { setError('请先选择剧集并填写关键词'); return; }
    try {
      setError('');
      await v2Client.post('/api/v2/wechat-index/keywords', { drama_id: selectedDramaId, keyword: newKeyword.trim(), role: newRole });
      setNewKeyword(''); await reload(); showToast('微信指数关键词已保存。');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '关键词保存失败'); }
  };

  const collect = async (keywordId: string) => {
    try {
      setBusyKeywordId(keywordId); setError('');
      const result = await v2Client.post<{ imported_points: number; first_ymd: string; last_ymd: string }>('/api/v2/wechat-index/history/collect', { keyword_id: keywordId });
      await reload(); showToast(`已采集 ${result.imported_points} 天：${formatYmd(result.first_ymd)} 至 ${formatYmd(result.last_ymd)}`);
    } catch (cause) {
      const message = cause instanceof ApiError ? cause.message : '微信指数采集失败';
      setError(message);
    } finally { setBusyKeywordId(''); }
  };

  const updateRole = async (keyword: KeywordItem, role: KeywordRole) => {
    try {
      setBusyKeywordId(keyword.id); setError('');
      await v2Client.patch(`/api/v2/wechat-index/keywords/${keyword.id}`, { role });
      await reload(); showToast(`已将“${keyword.keyword}”设为${ROLE_LABEL[role]}。`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '关键词角色更新失败'); }
    finally { setBusyKeywordId(''); }
  };

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-black/[0.06] bg-white p-5 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold text-slate-900"><Link2 className="h-4 w-4 text-indigo-600" />微信指数连接</div>
            <p className="mt-1 text-xs leading-5 text-slate-500">连接资料只保存在当前电脑，并由当前 Windows 用户加密保护；它不进入剧集数据库，也不会随软件复制到另一台电脑。</p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${connection.status === 'connected' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
            {connection.status === 'connected' ? '已连接本机微信' : connection.status === 'needs_reconnect' ? '需要重新连接' : '尚未连接'}
          </span>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {capture.status === 'running' ? <>
            <span className="text-xs text-indigo-700">初始化正在运行：请在微信指数手动查询任意一个词，页面识别到“已连接”后即可停止。</span>
            <button disabled={isConnecting} onClick={() => void stopCapture()} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-3 py-2 text-xs font-semibold text-rose-700 disabled:opacity-50"><Square className="h-3.5 w-3.5" />停止并清理</button>
          </> : <button disabled={isConnecting} onClick={() => void startCapture()} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-lime-200 disabled:opacity-50">{isConnecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}开始本机连接初始化</button>}
        </div>
        {connection.status !== 'connected' && capture.status !== 'running' && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-3">
            <p className="text-xs leading-5 text-amber-900">优先使用上面的“开始本机连接初始化”。下面仅作为初始化失败时的备用方式：在 Reqable 选中手动查询后产生的 <code>wxindex</code> 请求，复制为 JSON 请求模板后粘贴到这里。不要把真实请求内容发到聊天里。</p>
            <textarea value={requestTemplate} onChange={(event) => setRequestTemplate(event.target.value)} placeholder={'{"url":"https://search.weixin.qq.com/cgi-bin/wxaweb/wxindex","headers":{...},"body":{...}}'} className="mt-3 min-h-24 w-full rounded-lg border border-amber-200 bg-white p-2 font-mono text-xs outline-none focus:border-indigo-400" />
            <button disabled={isConnecting || !requestTemplate.trim()} onClick={() => void connect()} className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-lime-200 disabled:cursor-not-allowed disabled:opacity-50">
              {isConnecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}初始化本机连接
            </button>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-black/[0.06] bg-white p-5 shadow-xs">
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-52 flex-1 text-xs font-medium text-slate-600">归属剧集
            <select value={selectedDramaId} onChange={(event) => setSelectedDramaId(event.target.value)} className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none">
              <option value="">全部剧集（新增时请先选择）</option>{dramas.map((drama) => <option key={drama.id} value={drama.id}>{drama.current_name}</option>)}
            </select>
          </label>
          <label className="min-w-48 flex-[2] text-xs font-medium text-slate-600">微信指数关键词
            <input value={newKeyword} onChange={(event) => setNewKeyword(event.target.value)} placeholder="例如：剧集正式名称" className="mt-1 block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none" />
          </label>
          <label className="text-xs font-medium text-slate-600">初始角色
            <select value={newRole} onChange={(event) => setNewRole(event.target.value as KeywordRole)} className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none">{Object.entries(ROLE_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          </label>
          <button onClick={() => void addKeyword()} className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white"><Plus className="h-4 w-4" />添加关键词</button>
        </div>
        <p className="mt-3 text-xs text-slate-500">“等价词”代表你人工确认可用于同一剧的对照；当前版本仍保留各词独立原始曲线，不会自动相加。</p>
      </section>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}

      <section className="overflow-hidden rounded-2xl border border-black/[0.06] bg-white shadow-xs">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><div className="font-semibold text-slate-900">关键词原始采集</div><button onClick={() => void reload()} className="inline-flex items-center gap-1 text-xs text-slate-500"><RefreshCw className="h-3.5 w-3.5" />刷新</button></div>
        <div className="overflow-x-auto"><table className="w-full min-w-[780px] text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-5 py-3">剧集 / 关键词</th><th className="px-3 py-3">角色</th><th className="px-3 py-3">原始数据</th><th className="px-5 py-3 text-right">操作</th></tr></thead><tbody>{visibleKeywords.map((keyword) => <tr key={keyword.id} className="border-t border-slate-100"><td className="px-5 py-3"><div className="font-medium text-slate-800">{keyword.keyword}</div><div className="mt-0.5 text-xs text-slate-500">{keyword.drama_name}</div></td><td className="px-3 py-3"><select value={keyword.role} disabled={busyKeywordId === keyword.id} onChange={(event) => void updateRole(keyword, event.target.value as KeywordRole)} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs">{Object.entries(ROLE_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></td><td className="px-3 py-3 text-xs text-slate-600">{keyword.observation_count ? `${keyword.observation_count} 天 · ${formatYmd(keyword.first_observed_ymd)} 至 ${formatYmd(keyword.last_observed_ymd)}` : '尚未采集'}</td><td className="px-5 py-3 text-right"><button disabled={connection.status !== 'connected' || busyKeywordId === keyword.id} onClick={() => void collect(keyword.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 disabled:cursor-not-allowed disabled:opacity-40">{busyKeywordId === keyword.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}验证采集</button></td></tr>)}</tbody></table></div>
        {!visibleKeywords.length && <div className="px-5 py-10 text-center text-sm text-slate-500">还没有维护微信指数关键词。</div>}
      </section>
    </div>
  );
};
