import React, { useEffect, useState } from 'react';
import { getDraftExecution } from '../../api/publishing';

export function PublishingPreparationStatus({ taskId, refreshKey }: { taskId: string; refreshKey: string }) {
  const [state, setState] = useState('idle');
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try { const result = await getDraftExecution(taskId); if (active) { setState(result.running ? 'running' : result.state); if (result.running) timer = setTimeout(load, 2000); } }
      catch { /* Opening the workbench displays a detailed connection error. */ }
    };
    void load();
    return () => { active = false; clearTimeout(timer); };
  }, [taskId, refreshKey]);
  const label = ({ ready: '草稿已就绪', needs_help: '待人工处理', running: '草稿处理中', stopped: '已停止，可继续', interrupted: '已中断，待核对' } as Record<string, string>)[state] || '待配置';
  return <span className={`rounded-lg px-2 py-0.5 text-[11px] font-bold ${state === 'ready' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'}`}>{label}</span>;
}
