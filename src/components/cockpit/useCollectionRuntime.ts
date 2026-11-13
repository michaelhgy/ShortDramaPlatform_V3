import { useEffect, useMemo, useRef, useState } from 'react';
import { loadCollectionState, refreshCollectionLogins, startCollection, retryCollection, stopCollection, saveOptimizationDetection, type OptimizationDetectionSettings, type CollectionOptions, type CollectionState, type CollectionCategory } from '../../api/operationsDashboard';
import type { AccountInfo } from '../../types/shortDramaOps';
import type { ActiveJobSummary, AccountExecutionRow } from './DataCollectionModal';
import { collectionProfiles, projectedJobRows, mergeRetryRows } from './geminiCollectionModel';

export function useCollectionRuntime({isOpen, accounts, onDataSaved, onJobStateChange}: {
  isOpen: boolean; accounts: AccountInfo[]; onDataSaved?: () => void; onJobStateChange?: (summary: ActiveJobSummary) => void;
}) {
  const [state, setState] = useState<CollectionState | null>(null);
  const [error, setError] = useState(''), [pollError, setPollError] = useState(''), [notice, setNotice] = useState('');
  const detectionSaving = useRef(false);
  const [detectionBusy, setDetectionBusy] = useState(false);
  const [loginBusy,setLoginBusy]=useState(false);const loginRefreshing=useRef(false);
  const [busy, setBusy] = useState(false), [viewStage, setViewStage] = useState<'plan' | 'monitor'>('plan');
  const [carry, setCarry] = useState<AccountExecutionRow[]>([]), [isRetryRun, setIsRetryRun] = useState(false);
  const lastCompleted = useRef(''), seenJob = useRef('');
  const onSaved = useRef(onDataSaved); onSaved.current = onDataSaved;
  const onSummary = useRef(onJobStateChange); onSummary.current = onJobStateChange;
  const retryBase = useRef<AccountExecutionRow[] | null>(null);
  const apply = (result: CollectionState) => {
    const id = result.job?.id || '';
    if (id && id !== seenJob.current) {
      seenJob.current = id;
      setCarry(retryBase.current || []); setIsRetryRun(!!retryBase.current); retryBase.current = null;
      if (result.job && ['running','stopping'].includes(result.job.state)) setViewStage('monitor');
    }
    setState(result);
  };
  useEffect(() => {
    let disposed = false, timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await loadCollectionState(); if (disposed) return;
        apply(result); setPollError('');
        if (result.job && !['running','stopping'].includes(result.job.state) && lastCompleted.current !== result.job.id) {
          lastCompleted.current = result.job.id; onSaved.current?.();
        }
        timer = setTimeout(poll, isOpen || result.job && ['running','stopping'].includes(result.job.state) ? 1200 : 6000);
      } catch (e) {if (!disposed) {setPollError(e instanceof Error ? e.message : '读取本地进度失败'); timer = setTimeout(poll, 3000);}}
    };
    void poll(); return () => {disposed = true; clearTimeout(timer);};
  }, [isOpen]);
  const accountProfiles = useMemo(() => collectionProfiles(accounts, state), [accounts, state]);
  const executionRows = useMemo(() => mergeRetryRows(carry, projectedJobRows(state?.job || null, accountProfiles)), [carry, state, accountProfiles]);
  const rawState = state?.job?.state;
  const jobState: 'idle' | 'running' | 'stopping' | 'completed' | 'partial_failed' | 'stopped' = !rawState ? 'idle' : rawState === 'running' || rawState === 'stopping' || rawState === 'completed' || rawState === 'stopped' ? rawState : 'partial_failed';
  const current = state?.job?.items.find(item => item.id === state.job?.current_item);
  const wait = current ? Math.max(0, Math.floor((Date.now() - Date.parse(current.updated_at)) / 1000)) : 0;
  const currentWaitExplanation = jobState === 'stopping' ? '已请求停止；当前请求返回后停止后续请求，已保存结果保留。' : current ? `${current.account_name}：${current.message}${jobState === 'running' && wait >= 8 ? `（本步骤已等待${wait}秒，暂无新回报）` : ''}` : '尚未发起采集，查看此页面不会自动访问外部来源。';
  const summary: ActiveJobSummary = {
    isRunning: jobState === 'running' || jobState === 'stopping', isStopping: jobState === 'stopping', status: jobState === 'stopping' ? 'running' : jobState,
    completedAccounts: executionRows.filter(row => ['completed','skipped'].includes(row.overallStatus)).length,
    totalAccounts: executionRows.length, currentAccountName: current?.account_name, currentActionText: currentWaitExplanation,
    failedCount: executionRows.filter(row => ['partial','failed','stopped'].includes(row.overallStatus)).length,
  };
  useEffect(() => {onSummary.current?.(summary);}, [JSON.stringify(summary)]);
  const submit = async (kind: 'start' | 'retry' | 'stop', options?: CollectionOptions, accountIds?: string[]) => {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    if (kind === 'retry') retryBase.current = executionRows;
    try {
      const result = kind === 'start' ? await startCollection(options!) : kind === 'retry' ? await retryCollection(accountIds) : await stopCollection(state!.job!.id);
      setState(previous => previous ? {...previous, job: result.job} : previous); setViewStage('monitor');
      if ('reused' in result && result.reused) {retryBase.current = null; setNotice('已有采集任务，正在显示其实际进度，未重复排队。');}
    } catch (e) {retryBase.current = null; setError(e instanceof Error ? e.message : '采集操作未完成');}
    finally {setBusy(false);}
  };
  const refreshLogins=async()=>{
    if(loginRefreshing.current)return;loginRefreshing.current=true;setLoginBusy(true);setError('');setNotice('');
    try{const result=await refreshCollectionLogins();apply(result.state);setNotice(result.message);onSaved.current?.();}
    catch(e){setError(e instanceof Error?e.message:'登录状态刷新失败，保留原状态');}
    finally{loginRefreshing.current=false;setLoginBusy(false);}
  };
  const retryRecord=async(accountId:string,category:CollectionCategory,jobId:string)=>{
    if(busy)return;setBusy(true);setError('');setNotice('');
    try{
      const result=await retryCollection([accountId],jobId,[category]);
      apply(await loadCollectionState());
      if(result.reused)setNotice('已有采集正在执行，未重复启动；请等待当前任务完成。');
    }catch(e){setError(e instanceof Error?e.message:'本项重试未完成');}
    finally{setBusy(false);}
  };
  const saveDetection = async (settings: OptimizationDetectionSettings) => {
    if (detectionSaving.current) return;
    detectionSaving.current = true; setDetectionBusy(true); setError(''); setNotice('');
    try {
      const saved = await saveOptimizationDetection(settings);
      setState(previous => previous ? {...previous, ...saved} : previous);
      setNotice(saved.optimization_detection.enabled
        ? `全局自动检测已开启，随机间隔${saved.optimization_detection.min_minutes}～${saved.optimization_detection.max_minutes}分钟。`
        : '全局自动检测已关闭。');
    } catch (e) {setError(e instanceof Error ? e.message : '自动检测设置保存失败，原设置保留');}
    finally {detectionSaving.current = false; setDetectionBusy(false);}
  };
  return {state, accountProfiles, executionRows, jobState, viewStage, setViewStage, currentWaitExplanation, activeRunningAccountId: current?.account_id || null,
    isRetryRun, summary, busy, error, pollError, notice, setError, submit, detectionBusy, saveDetection, retryRecord, refreshLogins, loginBusy};
}
