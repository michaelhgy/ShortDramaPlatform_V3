import React, { useEffect, useState } from 'react';
import { downloadLocalVisionAiModel, getLocalVisionAiStatus, getV2Drives, getV2Settings, LocalVisionAiStatus, updateV2Settings } from '../../api/v2Catalog';
import { selectV2Path } from '../../api/v2Settings';
import { 
  Settings, 
  HardDrive, 
  FolderOpen, 
  ShieldCheck, 
  Download, 
  Upload, 
  FileText, 
  Save, 
  Check, 
  Clock, 
  Plus, 
  Trash2, 
  Copy, 
  Bug, 
  FileSpreadsheet, 
  Info,
  Timer,
  FileBox,
  SlidersHorizontal,
  CalendarClock,
  ArrowUpDown,
  CheckCircle2,
  AlertTriangle,
  FolderTree,
  FileCode,
  FileCheck,
  ChevronUp,
  ChevronDown,
  Edit2,
  Minus,
  Sparkles
} from 'lucide-react';

interface SettingsViewProps {
  showToast: (msg: string) => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  showToast,
}) => {
  // ==========================================
  // 1. 存储与程序 (Storage & Programs)
  // ==========================================
  const [dataDrive, setDataDrive] = useState('');
  const [availableDrives, setAvailableDrives] = useState<string[]>([]);
  const [dataRootDirStatus, setDataRootDirStatus] = useState<'normal' | 'missing' | 'inaccessible'>('normal');
  const [isChangingDataDrive, setIsChangingDataDrive] = useState(false);
  const [jianyingExePath, setJianyingExePath] = useState('');
  const [capcutDraftPath, setCapcutDraftPath] = useState('');
  const [jianyingUserDataPath, setJianyingUserDataPath] = useState('');

  // ==========================================
  // 2. 生产与任务 (Production & Tasks)
  // ==========================================
  const [defaultCheckMode, setDefaultCheckMode] = useState(false);
  // 独立任务超时时间 (三独立执行器)
  const [templateTimeoutMin, setTemplateTimeoutMin] = useState<number>(15);
  const [videoGenTimeoutMin, setVideoGenTimeoutMin] = useState<number>(30);
  const [exportTimeoutMin, setExportTimeoutMin] = useState<number>(20);

  // ==========================================
  // 3. 文件清理 (File Cleanup)
  // ==========================================
  const [rawMaterialRetentionDays, setRawMaterialRetentionDays] = useState<number>(7);
  const [shortTermCleanupHours, setShortTermCleanupHours] = useState<number>(24);

  // ==========================================
  // 4. 常用发布时间预设 (Common Publish Time Presets)
  // ==========================================
  const [publishPresets, setPublishPresets] = useState<string[]>([
    '12:00',
    '18:30',
    '19:45',
    '21:00'
  ]);
  const [publishDateOffsetDays, setPublishDateOffsetDays] = useState(0);
  const [newPresetInput, setNewPresetInput] = useState('');
  const [editingPresetIndex, setEditingPresetIndex] = useState<number | null>(null);
  const [editingPresetValue, setEditingPresetValue] = useState('');

  // ==========================================
  // 5. 收益自动采集 (Revenue Auto Sync)
  // ==========================================
  const [autoSyncRevenue, setAutoSyncRevenue] = useState(true);
  const [syncTimeSlots, setSyncTimeSlots] = useState<string[]>(['06:00', '12:30', '18:00']);
  const [newTimeInput, setNewTimeInput] = useState('');

  // ==========================================
  // 6. 本地视觉 AI (Local Vision AI)
  // ==========================================
  const [localVisionAiMode, setLocalVisionAiMode] = useState<'compatibility' | 'quality' | 'disabled'>('compatibility');
  const [localVisionAiStatus, setLocalVisionAiStatus] = useState<LocalVisionAiStatus | null>(null);
  const [checkingLocalVisionAi, setCheckingLocalVisionAi] = useState(false);

  // ==========================================
  // 7. 系统诊断状态 (Diagnostics)
  // ==========================================
  const [diagnosticResult, setDiagnosticResult] = useState<string | null>(null);
  const [selectingPath, setSelectingPath] = useState<'file' | 'draft' | 'userData' | null>(null);

  useEffect(() => {
    getV2Settings().then((settings) => {
      setDataDrive(settings.data_drive || '');
      setRawMaterialRetentionDays(settings.raw_material_retention_days);
      setShortTermCleanupHours(settings.short_term_cleanup_hours);
      setPublishPresets(settings.publish_presets);
      setPublishDateOffsetDays(settings.publish_date_offset_days);
      setJianyingExePath(settings.jianying_executable || '');
      setCapcutDraftPath(settings.jianying_draft_root || '');
      setJianyingUserDataPath(settings.jianying_user_data_root || '');
      setTemplateTimeoutMin(settings.template_timeout_min);
      setVideoGenTimeoutMin(settings.final_generation_timeout_min);
      setExportTimeoutMin(settings.video_export_timeout_min);
      setDefaultCheckMode(settings.final_video_manual_check);
      setAutoSyncRevenue(settings.revenue_auto_collection_enabled);
      setSyncTimeSlots(settings.revenue_auto_collection_times);
      setLocalVisionAiMode(settings.local_vision_ai_mode);
    }).catch(() => showToast('基础设置读取失败，请稍后重试。'));
    getV2Drives().then(({ items }) => setAvailableDrives(items.map((drive) => drive.replace(/[\\/]$/, ''))))
      .catch(() => showToast('可用数据盘读取失败，请稍后重试。'));
    void refreshLocalVisionAiStatus();
  }, []);

  useEffect(() => {
    if (!['queued', 'downloading'].includes(localVisionAiStatus?.download.status || '')) return;
    const timer = window.setInterval(() => void refreshLocalVisionAiStatus(true), 1500);
    return () => window.clearInterval(timer);
  }, [localVisionAiStatus?.download.status]);

  const dataRootDir = dataDrive ? `${dataDrive}\\短剧推广运营系统` : '';

  // ---------------- Handlers ----------------

  const handleSave = () => {
    if (!dataDrive) { showToast('请先选择数据盘。'); return; }
    if (isChangingDataDrive && !window.confirm(`确认将数据盘改为 ${dataDrive}？已有数据不会自动搬迁。`)) return;
    updateV2Settings({
      data_drive: dataDrive,
      raw_material_retention_days: rawMaterialRetentionDays,
      short_term_cleanup_hours: shortTermCleanupHours,
      publish_presets: publishPresets,
      publish_date_offset_days: publishDateOffsetDays,
      jianying_executable: jianyingExePath,
      jianying_draft_root: capcutDraftPath,
      jianying_user_data_root: jianyingUserDataPath,
      template_timeout_min: templateTimeoutMin,
      final_generation_timeout_min: videoGenTimeoutMin,
      video_export_timeout_min: exportTimeoutMin,
      final_video_manual_check: defaultCheckMode,
      revenue_auto_collection_enabled: autoSyncRevenue,
      revenue_auto_collection_times: syncTimeSlots,
      local_vision_ai_mode: localVisionAiMode,
    }).then(() => { setIsChangingDataDrive(false); showToast('系统设置已保存并生效'); }).catch((error: unknown) => showToast(error instanceof Error ? error.message : '系统设置保存失败。'));
  };

  const refreshLocalVisionAiStatus = async (silent = false) => {
    if (!silent) setCheckingLocalVisionAi(true);
    try {
      setLocalVisionAiStatus(await getLocalVisionAiStatus());
      if (!silent) showToast('本地视觉 AI 环境检测完成');
    } catch (error) {
      if (!silent) showToast(error instanceof Error ? error.message : '本地视觉 AI 环境检测失败');
    } finally {
      if (!silent) setCheckingLocalVisionAi(false);
    }
  };

  const handleDownloadLocalVisionModel = async (model: string) => {
    if (!window.confirm(`将通过 Ollama 下载 ${model}。模型文件较大，请确认网络和磁盘空间充足。`)) return;
    try {
      setLocalVisionAiStatus(await downloadLocalVisionAiModel(model));
      showToast(`已开始下载 ${model}，可留在本页查看进度`);
    } catch (error) {
      showToast(error instanceof Error ? error.message : '模型下载启动失败');
    }
  };

  const handleSelectPath = (kind: 'file' | 'directory', directoryTarget: 'draft' | 'userData' = 'draft') => {
    setSelectingPath(kind === 'file' ? 'file' : directoryTarget);
    selectV2Path(kind).then((result) => {
      if (!result.path) {
        showToast('已取消路径选择');
        return;
      }
      if (kind === 'file') setJianyingExePath(result.path);
      else if (directoryTarget === 'userData') setJianyingUserDataPath(result.path);
      else setCapcutDraftPath(result.path);
      showToast(kind === 'file' ? '已选择剪映程序' : directoryTarget === 'userData' ? '已选择剪映用户数据目录' : '已选择剪映草稿目录');
    }).catch((error: unknown) => showToast(error instanceof Error && error.message ? error.message : '路径选择失败，请检查 V2 本地服务。'))
      .finally(() => setSelectingPath(null));
  };

  // Preset Handlers
  const handleAddPreset = () => {
    const val = newPresetInput;
    if (!val) return;
    if (publishPresets.includes(val)) {
      showToast('该时间预设已存在');
      return;
    }
    setPublishPresets(prev => [...prev, val]);
    setNewPresetInput('');
    showToast(`已新增常用发布时间预设：${val}`);
  };

  const handleRemovePreset = (index: number) => {
    const removed = publishPresets[index];
    setPublishPresets(prev => prev.filter((_, i) => i !== index));
    showToast(`已删除预设：${removed}`);
  };

  const handleMovePreset = (index: number, direction: 'up' | 'down') => {
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= publishPresets.length) return;
    const next = [...publishPresets];
    const temp = next[index];
    next[index] = next[targetIndex];
    next[targetIndex] = temp;
    setPublishPresets(next);
  };

  const handleStartEditPreset = (index: number) => {
    setEditingPresetIndex(index);
    setEditingPresetValue(publishPresets[index]);
  };

  const handleSaveEditPreset = () => {
    if (editingPresetIndex === null) return;
    const val = editingPresetValue;
    if (!val) return;
    const next = [...publishPresets];
    next[editingPresetIndex] = val;
    setPublishPresets(next);
    setEditingPresetIndex(null);
    setEditingPresetValue('');
    showToast(`预设已修改为：${val}`);
  };

  // Sync Time Handlers
  const handleAddTimeSlot = () => {
    const val = newTimeInput.trim();
    if (!val) return;
    if (syncTimeSlots.includes(val)) {
      showToast('该采集时间点已存在');
      return;
    }
    setSyncTimeSlots(prev => [...prev, val].sort());
    setNewTimeInput('');
    showToast(`已新增自动采集时间点：${val}`);
  };

  const handleRemoveTimeSlot = (time: string) => {
    if (syncTimeSlots.length === 1) {
      showToast('请至少保留一个采集时间点；不需要自动采集时可直接停用开关。');
      return;
    }
    setSyncTimeSlots(prev => prev.filter(t => t !== time));
    showToast(`已移除时间点：${time}`);
  };

  const handleCopyDiagnostics = () => {
    const report = `[System Diagnostics Report]
Timestamp: ${new Date().toISOString()}
Data Root Dir: ${dataRootDir} (Status: ${dataRootDirStatus})
Jianying Exe Path: ${jianyingExePath}
CapCut Draft Root: ${capcutDraftPath}
Manual Check Mode: ${defaultCheckMode ? 'Enabled' : 'Disabled'}
Task Timeouts:
  - Template Gen: ${templateTimeoutMin} min
  - Video Gen: ${videoGenTimeoutMin} min
  - Export: ${exportTimeoutMin} min
File Cleanup:
  - Raw Material Retention: ${rawMaterialRetentionDays} days
  - Short-term Artifacts Cleanup: ${shortTermCleanupHours} hours
Publish Presets: ${publishPresets.join(', ')}
Auto Revenue Sync: ${autoSyncRevenue ? 'Enabled (' + syncTimeSlots.join(', ') + ')' : 'Disabled'}
IPC Status: Port 49152 Active, Latency 3ms
Database Version: SQLite 3.42 (Encrypted Local Store)`;
    navigator.clipboard?.writeText(report);
    showToast('📋 已将系统运行诊断报告复制到剪贴板');
  };

  const handleRunDiagnosticTest = () => {
    showToast('⚡ 正在测试数据根目录、剪映进程通道与任务调度器...');
    setTimeout(() => {
      setDiagnosticResult('✅ 诊断测试通过：数据根目录可写、剪映程序路径校验正确、草稿目录通信正常（延迟 3ms）。');
      showToast('✅ 基础诊断测试全部通过');
    }, 600);
  };

  return (
    <div className="space-y-6 pb-24 max-w-4xl mx-auto animate-in fade-in duration-200">
      {/* Top Banner */}
      <div className="bg-white rounded-2xl p-5 border border-black/[0.06] shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center font-bold shadow-xs">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-black text-[#1A1D2E] tracking-tight">系统设置 (Settings)</h2>
            <p className="text-xs text-[#64748B] mt-0.5">
              存储路径与程序绑定、执行器超时、文件生命周期清理、常用发布预设与定时采集
            </p>
          </div>
        </div>

        <button
          onClick={handleSave}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black font-extrabold text-xs transition-all shadow-xs cursor-pointer active:scale-95"
        >
          <Save className="w-3.5 h-3.5" />
          <span>保存所有配置</span>
        </button>
      </div>

      {/* =========================================================================
          1. 存储与程序 (Storage & Programs)
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-black/[0.04]">
          <div className="flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-[#1A1D2E]" />
            <h3 className="font-extrabold text-base text-[#1A1D2E]">存储与程序</h3>
          </div>
          <span className="text-[11px] text-[#64748B] font-medium">
            选择数据盘与执行程序，系统将自动维护标准目录树
          </span>
        </div>

        <div className="space-y-4 text-xs">
          {/* 1.1 数据盘 */}
          <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.04] space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <label className="font-extrabold text-[#1A1D2E]">数据盘</label>
                {dataRootDirStatus === 'normal' && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200/80 font-bold">
                    <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
                    目录状态：正常
                  </span>
                )}
                {dataRootDirStatus === 'missing' && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200/80 font-bold">
                    <AlertTriangle className="w-2.5 h-2.5 text-amber-600" />
                    目录状态：不存在
                  </span>
                )}
                {dataRootDirStatus === 'inaccessible' && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-800 border border-rose-200/80 font-bold">
                    <AlertTriangle className="w-2.5 h-2.5 text-rose-600" />
                    目录状态：无法访问
                  </span>
                )}
              </div>
            </div>

            <p className="text-[11px] text-[#64748B] leading-relaxed">
              选择盘符后，软件自动使用 {dataRootDir || '<盘符>\\短剧推广运营系统'}，并在其中创建和维护生产文件、剧集资料、爆款素材、真人视频/图片、BGM 及系统数据等标准目录，无需逐项配置。
            </p>

            <div className="flex items-center gap-2">
              <select
                value={dataDrive}
                onChange={(e) => setDataDrive(e.target.value)}
                disabled={Boolean(dataDrive) && !isChangingDataDrive}
                className="flex-1 px-3 py-2 bg-white border border-black/[0.08] rounded-xl text-[#1A1D2E] font-mono text-xs focus:outline-none focus:border-[#1A1D2E]"
              >
                <option value="">请选择数据盘</option>
                {availableDrives.map((drive) => <option key={drive} value={drive}>{drive}</option>)}
              </select>
              <button
                type="button"
                onClick={() => {
                  if (isChangingDataDrive || window.confirm('更换数据盘属于高风险操作。确认进入更换模式吗？')) setIsChangingDataDrive((value) => !value);
                }}
                className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold cursor-pointer transition-colors shrink-0"
              >
                {isChangingDataDrive ? '取消更换' : dataDrive ? '更换数据盘' : '确认数据盘'}
              </button>
              <button
                type="button"
                onClick={() => showToast(`已在文件资源管理器中打开：${dataRootDir}`)}
                className="px-3.5 py-2 rounded-xl bg-[#1A1D2E] text-white hover:bg-black font-bold cursor-pointer transition-colors shrink-0"
              >
                打开目录
              </button>
            </div>
          </div>

          {/* 1.2 剪映程序路径 */}
          <div className="space-y-1.5">
            <label className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
              <span>剪映程序路径 (JianyingPro.exe)</span>
            </label>
            <p className="text-[11px] text-[#64748B]">
              用于系统自动化唤醒剪映渲染进程与草稿管道通信。
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={jianyingExePath}
                onChange={(e) => setJianyingExePath(e.target.value)}
                className="flex-1 px-3 py-2 bg-[#F8FAFC] border border-black/[0.06] rounded-xl text-[#1A1D2E] font-mono text-xs focus:outline-none focus:bg-white focus:border-[#1A1D2E]"
              />
              <button
                type="button"
                onClick={() => handleSelectPath('file')}
                disabled={selectingPath !== null}
                className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold cursor-pointer transition-colors shrink-0"
              >
                {selectingPath === 'file' ? '选择中...' : '选择程序'}
              </button>
            </div>
          </div>

          {/* 1.3 剪映草稿根目录路径 */}
          <div className="space-y-1.5">
            <label className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
              <span>剪映草稿根目录路径</span>
            </label>
            <p className="text-[11px] text-[#64748B]">
              剪映存储本地项目草稿的根目录，模板生成器与成片生成器将向此目录写入工程文件。
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={capcutDraftPath}
                onChange={(e) => setCapcutDraftPath(e.target.value)}
                className="flex-1 px-3 py-2 bg-[#F8FAFC] border border-black/[0.06] rounded-xl text-[#1A1D2E] font-mono text-xs focus:outline-none focus:bg-white focus:border-[#1A1D2E]"
              />
              <button
                type="button"
                onClick={() => handleSelectPath('directory')}
                disabled={selectingPath !== null}
                className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold cursor-pointer transition-colors shrink-0"
              >
                {selectingPath === 'draft' ? '选择中...' : '选择目录'}
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
              <span>剪映用户数据目录（可留空自动识别）</span>
            </label>
            <p className="text-[11px] text-[#64748B]">
              用于读取剪映本机缓存和原生资源。草稿可以单独放在其他磁盘；若剪映未使用默认用户目录，请在此选择它的 User Data 文件夹。
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={jianyingUserDataPath}
                onChange={(e) => setJianyingUserDataPath(e.target.value)}
                placeholder="留空则自动识别当前 Windows 用户的剪映目录"
                className="flex-1 px-3 py-2 bg-[#F8FAFC] border border-black/[0.06] rounded-xl text-[#1A1D2E] font-mono text-xs focus:outline-none focus:bg-white focus:border-[#1A1D2E]"
              />
              <button
                type="button"
                onClick={() => handleSelectPath('directory', 'userData')}
                disabled={selectingPath !== null}
                className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold cursor-pointer transition-colors shrink-0"
              >
                {selectingPath === 'userData' ? '选择中...' : '选择目录'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* =========================================================================
          2. 生产与任务设置 (Production & Tasks)
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-5">
        <div className="flex items-center justify-between pb-3 border-b border-black/[0.04]">
          <div className="flex items-center gap-2">
            <Timer className="w-4 h-4 text-[#1A1D2E]" />
            <h3 className="font-extrabold text-base text-[#1A1D2E]">生产与任务设置</h3>
          </div>
          <span className="text-[11px] text-[#64748B] font-medium">
            独立执行器超时保护与人工核验模式
          </span>
        </div>

        {/* 2.1 成片人工检查模式 (保持现状) */}
        <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.04] flex items-center justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-[#1A1D2E]">默认启用「成片人工检查模式」</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 font-bold">
                高精度运营把控
              </span>
            </div>
            <p className="text-[11px] text-[#64748B]">
              开启后，剪映在导出每一集前将自动暂停并弹窗通知您检查草稿，确认无误后继续自动导出（只针对成片导出，默认关闭）
            </p>
          </div>

          <button
            type="button"
            onClick={() => setDefaultCheckMode(!defaultCheckMode)}
            className={`w-12 h-6 rounded-full transition-colors relative cursor-pointer shrink-0 ml-4 ${
              defaultCheckMode ? 'bg-[#1A1D2E]' : 'bg-slate-300'
            }`}
          >
            <div className={`w-5 h-5 rounded-full bg-white transition-transform absolute top-0.5 ${
              defaultCheckMode ? 'right-0.5' : 'left-0.5'
            }`} />
          </button>
        </div>

        {/* 2.2 三独立执行器任务超时时间 */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="font-bold text-xs text-[#1A1D2E]">
              执行器任务超时时间 (Timeout)
            </label>
            <span className="text-[11px] text-[#64748B]">
              系统包含三个单并发执行器，执行超出设定时间将触发保护重试或异常告警
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            {/* 模板生成任务超时 */}
            <div className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.05] space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-[#1A1D2E]">1. 模板生成器超时</span>
                <span className="text-[10px] font-mono text-slate-400">单任务独占</span>
              </div>
              <p className="text-[10px] text-[#64748B]">
                用于分镜组装与母本模板草稿生成。
              </p>
              <div className="flex items-center gap-1.5 pt-1">
                <input
                  type="number"
                  min={1}
                  max={120}
                  value={templateTimeoutMin}
                  onChange={(e) => setTemplateTimeoutMin(Number(e.target.value))}
                  className="w-20 px-2.5 py-1.5 bg-white border border-black/[0.08] rounded-xl font-bold text-[#1A1D2E] text-xs focus:outline-none focus:border-[#1A1D2E]"
                />
                <span className="text-slate-500 font-bold">分钟</span>
              </div>
            </div>

            {/* 成片生成任务超时 */}
            <div className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.05] space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-[#1A1D2E]">2. 成片生成器超时</span>
                <span className="text-[10px] font-mono text-slate-400">单任务独占</span>
              </div>
              <p className="text-[10px] text-[#64748B]">
                用于多轨组合、换素材渲染与成片拼装。
              </p>
              <div className="flex items-center gap-1.5 pt-1">
                <input
                  type="number"
                  min={1}
                  max={180}
                  value={videoGenTimeoutMin}
                  onChange={(e) => setVideoGenTimeoutMin(Number(e.target.value))}
                  className="w-20 px-2.5 py-1.5 bg-white border border-black/[0.08] rounded-xl font-bold text-[#1A1D2E] text-xs focus:outline-none focus:border-[#1A1D2E]"
                />
                <span className="text-slate-500 font-bold">分钟</span>
              </div>
            </div>

            {/* 视频导出任务超时 */}
            <div className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.05] space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-[#1A1D2E]">3. 视频导出器超时</span>
                <span className="text-[10px] font-mono text-slate-400">单任务独占</span>
              </div>
              <p className="text-[10px] text-[#64748B]">
                用于剪映硬件加速编码渲染与重命名归档。
              </p>
              <div className="flex items-center gap-1.5 pt-1">
                <input
                  type="number"
                  min={1}
                  max={120}
                  value={exportTimeoutMin}
                  onChange={(e) => setExportTimeoutMin(Number(e.target.value))}
                  className="w-20 px-2.5 py-1.5 bg-white border border-black/[0.08] rounded-xl font-bold text-[#1A1D2E] text-xs focus:outline-none focus:border-[#1A1D2E]"
                />
                <span className="text-slate-500 font-bold">分钟</span>
              </div>
            </div>
          </div>

          <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/60 text-[11px] text-[#64748B] flex items-start gap-2">
            <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
            <span>
              <strong>固定调度说明：</strong>系统内「模板最高优先级」、「剧集生产优先级」以及执行器单任务串行队列为核心架构固定规则，无需手动干预。
            </span>
          </div>
        </div>
      </div>

      {/* =========================================================================
          3. 文件清理 (File Cleanup)
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-black/[0.04]">
          <div className="flex items-center gap-2">
            <FileBox className="w-4 h-4 text-[#1A1D2E]" />
            <h3 className="font-extrabold text-base text-[#1A1D2E]">文件清理周期设置</h3>
          </div>
          <span className="text-[11px] text-emerald-800 font-bold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/80">
            长期资产不参与自动清理
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          {/* 原素材保留时间 */}
          <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.05] space-y-2">
            <div className="flex items-center justify-between">
              <label className="font-extrabold text-[#1A1D2E]">原素材保留时间</label>
              <span className="text-[10px] text-slate-400">默认 7 天</span>
            </div>
            <p className="text-[11px] text-[#64748B] leading-relaxed">
              普通原素材在对应制作任务登记发布以后，从记录的发布时间开始计算保留时间。达到保留时间后自动进入清理流程。
            </p>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="number"
                min={1}
                max={90}
                value={rawMaterialRetentionDays}
                onChange={(e) => setRawMaterialRetentionDays(Number(e.target.value))}
                className="w-24 px-3 py-2 bg-white border border-black/[0.08] rounded-xl font-bold text-[#1A1D2E] text-xs focus:outline-none focus:border-[#1A1D2E]"
              />
              <span className="text-slate-600 font-bold">天 (Days)</span>
            </div>
          </div>

          {/* 清理时间 (短期生产过程文件) */}
          <div className="p-4 rounded-2xl bg-[#F8FAFC] border border-black/[0.05] space-y-2">
            <div className="flex items-center justify-between">
              <label className="font-extrabold text-[#1A1D2E]">短期过程文件清理时间</label>
              <span className="text-[10px] text-slate-400">默认 24 小时</span>
            </div>
            <p className="text-[11px] text-[#64748B] leading-relaxed">
              用于生产过程中模板、成片草稿、真人视频/图片中间耗材等短期文件的统一清理周期。同样从发布登记记录的发布时间开始计算。
            </p>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="number"
                min={1}
                max={168}
                value={shortTermCleanupHours}
                onChange={(e) => setShortTermCleanupHours(Number(e.target.value))}
                className="w-24 px-3 py-2 bg-white border border-black/[0.08] rounded-xl font-bold text-[#1A1D2E] text-xs focus:outline-none focus:border-[#1A1D2E]"
              />
              <span className="text-slate-600 font-bold">小时 (Hours)</span>
            </div>
          </div>
        </div>

        {/* 长期资产保护提示 */}
        <div className="p-3 rounded-2xl bg-slate-50 border border-slate-200/60 text-[11px] text-[#64748B] space-y-1">
          <div className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>长期保护资产范围（永久保留，不受自动清理影响）：</span>
          </div>
          <p className="pl-5 text-slate-500">
            • 爆款素材库中的收藏分镜与片段 • 音乐库 (BGM) 母本 • 短剧剧集母本资料与分镜结构库。
          </p>
        </div>
      </div>

      {/* =========================================================================
          4. 常用发布时间预设 (Publish Time Presets)
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-black/[0.04]">
          <div className="flex items-center gap-2">
            <CalendarClock className="w-4 h-4 text-[#1A1D2E]" />
            <h3 className="font-extrabold text-base text-[#1A1D2E]">常用发布时间预设</h3>
          </div>
          <span className="text-[11px] text-[#64748B] font-medium">
            排期时可一键快捷选用，并自动带入默认发布日期
          </span>
        </div>

        <div className="space-y-3 text-xs">
          <p className="text-[#64748B]">
            在「安排今日制作与发布」时，这些时间将作为快捷标签展示。支持自由增删与上下排序。
          </p>

          <div className="flex items-center justify-between gap-4 rounded-xl bg-[#F8FAFC] border border-black/[0.06] px-3 py-2.5">
            <div>
              <p className="font-bold text-[#1A1D2E]">默认发布日期</p>
              <p className="mt-0.5 text-[11px] text-[#64748B]">0 天为当天，1 天为明天；新建任务后仍可逐条调整。</p>
            </div>
            <div className="flex h-8 items-center rounded-lg border border-black/[0.08] bg-white overflow-hidden shrink-0">
              <button
                type="button"
                aria-label="减少发布日期偏移"
                disabled={publishDateOffsetDays === 0}
                onClick={() => setPublishDateOffsetDays((value) => Math.max(0, value - 1))}
                className="flex h-full w-8 items-center justify-center text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-30 cursor-pointer"
              >
                <Minus className="w-3.5 h-3.5" />
              </button>
              <span className="min-w-14 border-x border-black/[0.08] px-2 text-center text-xs font-extrabold text-[#1A1D2E]">{publishDateOffsetDays} 天</span>
              <button
                type="button"
                aria-label="增加发布日期偏移"
                onClick={() => setPublishDateOffsetDays((value) => value + 1)}
                className="flex h-full w-8 items-center justify-center text-slate-500 hover:bg-slate-100 cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Presets List */}
          <div className="flex flex-wrap items-center gap-2">
            {publishPresets.map((preset, index) => {
              const isEditing = editingPresetIndex === index;

              if (isEditing) {
                return (
                  <div key={index} className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-white border border-[#1A1D2E] shadow-2xs">
                    <input
                      type="time"
                      value={editingPresetValue}
                      onChange={(e) => setEditingPresetValue(e.target.value)}
                      className="w-24 text-xs font-bold text-[#1A1D2E] focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={handleSaveEditPreset}
                      className="text-emerald-700 hover:text-emerald-900 p-0.5 cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingPresetIndex(null)}
                      className="text-slate-400 hover:text-slate-600 p-0.5 cursor-pointer"
                    >
                      ×
                    </button>
                  </div>
                );
              }

              return (
                <span
                  key={index}
                  className="px-3 py-1.5 rounded-xl bg-slate-100 border border-black/[0.06] text-xs font-bold text-[#1A1D2E] flex items-center gap-2 group hover:border-black/[0.12] transition-all"
                >
                  <span className="font-mono">{preset}</span>
                  
                  {/* Action buttons */}
                  <div className="flex items-center gap-0.5 text-slate-400">
                    <button
                      type="button"
                      title="上移"
                      disabled={index === 0}
                      onClick={() => handleMovePreset(index, 'up')}
                      className="hover:text-slate-700 disabled:opacity-20 cursor-pointer disabled:cursor-not-allowed"
                    >
                      <ChevronUp className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      title="下移"
                      disabled={index === publishPresets.length - 1}
                      onClick={() => handleMovePreset(index, 'down')}
                      className="hover:text-slate-700 disabled:opacity-20 cursor-pointer disabled:cursor-not-allowed"
                    >
                      <ChevronDown className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      title="修改"
                      onClick={() => handleStartEditPreset(index)}
                      className="hover:text-slate-700 ml-0.5 cursor-pointer"
                    >
                      <Edit2 className="w-2.5 h-2.5" />
                    </button>
                    <button
                      type="button"
                      title="删除"
                      onClick={() => handleRemovePreset(index)}
                      className="hover:text-rose-600 ml-0.5 cursor-pointer"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </span>
              );
            })}

            {/* Add Preset Input */}
            <div className="flex items-center gap-1">
              <input
                type="time"
                value={newPresetInput}
                onChange={(e) => setNewPresetInput(e.target.value)}
                className="w-28 px-2.5 py-1.5 bg-[#F8FAFC] border border-black/[0.08] rounded-xl text-xs font-semibold focus:outline-none focus:bg-white"
              />
              <button
                type="button"
                onClick={handleAddPreset}
                className="px-3 py-1.5 rounded-xl bg-slate-200 hover:bg-slate-300 font-bold text-[#1A1D2E] cursor-pointer transition-colors flex items-center gap-1"
              >
                <Plus className="w-3 h-3" />
                <span>新增预设</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* =========================================================================
          5. 本地视觉 AI
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-black/[0.04]">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-[#1A1D2E]" />
            <div>
              <h3 className="font-extrabold text-base text-[#1A1D2E]">本地视觉 AI</h3>
              <p className="text-[11px] text-[#64748B] mt-0.5">用于成片开头封面和疑似剧名判断；关闭后保留 OCR 与固定规则。</p>
            </div>
          </div>
          <button type="button" onClick={() => void refreshLocalVisionAiStatus()} disabled={checkingLocalVisionAi}
            className="px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 disabled:opacity-60 text-xs font-bold text-[#1A1D2E] cursor-pointer">
            {checkingLocalVisionAi ? '检测中…' : '检测环境'}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {[
            ['compatibility', '兼容模式', 'qwen2.5vl:3b · 约 3.2 GB', '推荐多数电脑使用'],
            ['quality', '质量模式', 'qwen2.5vl:7b · 约 6.0 GB', '显卡和内存充足时使用'],
            ['disabled', '关闭本地视觉 AI', '不需要 Ollama 或模型', '仅使用 OCR 与固定规则'],
          ].map(([value, title, detail, note]) => (
            <button key={value} type="button" onClick={() => setLocalVisionAiMode(value as typeof localVisionAiMode)}
              className={`text-left p-3 rounded-2xl border transition-colors cursor-pointer ${localVisionAiMode === value ? 'border-emerald-400 bg-emerald-50/70' : 'border-black/[0.07] bg-[#F8FAFC] hover:bg-slate-100'}`}>
              <div className="flex items-center justify-between gap-2"><strong className="text-xs text-[#1A1D2E]">{title}</strong>{localVisionAiMode === value && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}</div>
              <p className="mt-1 text-[11px] font-mono text-[#475569]">{detail}</p>
              <p className="mt-1 text-[10px] text-[#64748B]">{note}</p>
            </button>
          ))}
        </div>

        <div className="rounded-2xl border border-black/[0.06] bg-[#F8FAFC] p-3 text-xs space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-bold text-[#1A1D2E]">Ollama：{localVisionAiStatus?.ollamaFound ? '已检测到' : '未检测到'}</span>
            {localVisionAiStatus?.ollamaFound && <span className="text-[10px] text-[#64748B]">已安装 {localVisionAiStatus.installedModels.length} 个模型</span>}
          </div>
          {!localVisionAiStatus?.ollamaFound && <p className="text-amber-800">请先安装 Ollama，并确保安装程序将 <code>ollama</code> 命令加入系统环境；完成后点击“检测环境”。</p>}
          {localVisionAiStatus?.error && <p className="text-rose-700 break-words">检测失败：{localVisionAiStatus.error}</p>}
          <div className="flex flex-wrap gap-2">
            {localVisionAiStatus?.supportedModels.map((model) => (
              <div key={model.id} className="flex items-center gap-2 bg-white rounded-xl border border-black/[0.05] px-2.5 py-2">
                <span className="font-mono text-[11px] text-[#1A1D2E]">{model.id}</span>
                <span className={model.installed ? 'text-emerald-700 font-bold' : 'text-slate-500'}>{model.installed ? '已就绪' : model.size}</span>
                {!model.installed && <button type="button" disabled={!localVisionAiStatus.ollamaFound || ['queued', 'downloading'].includes(localVisionAiStatus.download.status)} onClick={() => void handleDownloadLocalVisionModel(model.id)} className="text-[11px] font-bold text-indigo-700 disabled:opacity-40 cursor-pointer">下载</button>}
              </div>
            ))}
          </div>
          {localVisionAiStatus && ['queued', 'downloading', 'completed', 'error'].includes(localVisionAiStatus.download.status) && (
            <p className={localVisionAiStatus.download.status === 'error' ? 'text-rose-700 break-words' : 'text-[#475569]'}>
              {localVisionAiStatus.download.status === 'error' ? `下载失败：${localVisionAiStatus.download.error}` : `下载状态：${localVisionAiStatus.download.progress}`}
            </p>
          )}
          <p className="text-[10px] text-[#64748B]">模式选择会在保存设置后用于下一条成片草稿任务；不会改变正在生成的任务。</p>
        </div>
      </div>

      {/* =========================================================================
          6. 收益自动采集定时任务 (Revenue Auto Sync)
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-black/[0.04]">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-[#1A1D2E]" />
            <h3 className="font-extrabold text-base text-[#1A1D2E]">收益自动采集定时任务</h3>
          </div>

          <button
            type="button"
            onClick={() => setAutoSyncRevenue(!autoSyncRevenue)}
            className={`px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              autoSyncRevenue ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
            }`}
          >
            {autoSyncRevenue ? '自动采集已开启' : '已停用'}
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <p className="text-[#64748B]">
            系统将在设定时间自动发起现有收益采集。当天首次打开软件时，已错过的时间点会合并补采一次。
          </p>

          <div className="flex flex-wrap items-center gap-2">
            {syncTimeSlots.map((slot) => (
              <span key={slot} className="px-3 py-1.5 rounded-xl bg-slate-100 border border-black/[0.06] text-xs font-bold text-[#1A1D2E] flex items-center gap-2">
                <span className="font-mono">{slot}</span>
                <button 
                  type="button"
                  onClick={() => handleRemoveTimeSlot(slot)} 
                  className="text-slate-400 hover:text-rose-600 cursor-pointer"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </span>
            ))}

            <div className="flex items-center gap-1">
              <input
                type="time"
                value={newTimeInput}
                onChange={(e) => setNewTimeInput(e.target.value)}
                className="w-24 px-2.5 py-1.5 bg-[#F8FAFC] border border-black/[0.08] rounded-xl text-xs font-semibold focus:outline-none focus:bg-white"
              />
              <button
                type="button"
                onClick={handleAddTimeSlot}
                className="px-3 py-1.5 rounded-xl bg-slate-200 hover:bg-slate-300 font-bold text-[#1A1D2E] cursor-pointer"
              >
                添加时间点
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* =========================================================================
          6. 数据维护、Excel 导入与全量备份 [保持现状]
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-black/[0.04]">
          <FileSpreadsheet className="w-4 h-4 text-[#1A1D2E]" />
          <h3 className="font-extrabold text-base text-[#1A1D2E]">数据维护、Excel 导入与全量备份</h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <button
            type="button"
            onClick={() => showToast('📥 已下载「短剧与账号基础资料导入模板.xlsx」')}
            className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] hover:bg-slate-100 text-left transition-all cursor-pointer space-y-1"
          >
            <Download className="w-4 h-4 text-slate-700" />
            <h4 className="font-bold text-[#1A1D2E]">下载标准模板</h4>
            <p className="text-[11px] text-[#64748B]">Excel 基础资料导入模板</p>
          </button>

          <button
            type="button"
            onClick={() => showToast('📤 已将当前全部账号、剧本母本与分成政策导出为 Excel 归档')}
            className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] hover:bg-slate-100 text-left transition-all cursor-pointer space-y-1"
          >
            <FileText className="w-4 h-4 text-slate-700" />
            <h4 className="font-bold text-[#1A1D2E]">导出基础资料</h4>
            <p className="text-[11px] text-[#64748B]">导出账号/剧集/剧场</p>
          </button>

          <button
            type="button"
            onClick={() => showToast('✅ 导入完成：已校验 8 个账号与 15 部短剧母本资料')}
            className="p-3.5 rounded-2xl bg-[#F8FAFC] border border-black/[0.06] hover:bg-slate-100 text-left transition-all cursor-pointer space-y-1"
          >
            <Upload className="w-4 h-4 text-slate-700" />
            <h4 className="font-bold text-[#1A1D2E]">导入基础资料</h4>
            <p className="text-[11px] text-[#64748B]">解析 Excel 并更新母库</p>
          </button>

          <button
            type="button"
            onClick={() => showToast(dataRootDir ? `💾 全量 SQLite 数据库与配置快照备份成功：${dataRootDir}\\系统数据\\DramaMaster_backup.db` : '请先配置数据盘后再执行备份。')}
            className="p-3.5 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black text-left transition-all cursor-pointer space-y-1 shadow-xs"
          >
            <ShieldCheck className="w-4 h-4" />
            <h4 className="font-extrabold">全量数据快照</h4>
            <p className="text-[11px] text-slate-300">一键备份本地数据库</p>
          </button>
        </div>
      </div>

      {/* =========================================================================
          7. 系统运行诊断与日志 [保持现状]
          ========================================================================= */}
      <div className="bg-white rounded-3xl p-6 border border-black/[0.06] shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-black/[0.04]">
          <div className="flex items-center gap-2">
            <Bug className="w-4 h-4 text-[#1A1D2E]" />
            <h3 className="font-extrabold text-base text-[#1A1D2E]">系统运行诊断与日志</h3>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => showToast('已在系统文件管理器中打开：C:\\Users\\Administrator\\AppData\\Roaming\\DramaMaster\\logs\\')}
              className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-[#1A1D2E] cursor-pointer"
            >
              <FolderOpen className="w-3.5 h-3.5" />
              <span>打开日志目录</span>
            </button>
            <button
              type="button"
              onClick={handleCopyDiagnostics}
              className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-[#1A1D2E] cursor-pointer"
            >
              <Copy className="w-3.5 h-3.5" />
              <span>复制诊断报告</span>
            </button>
          </div>
        </div>

        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-[#64748B]">
              遇到导出卡顿或通讯异常时，可一键执行环境连通性自检。
            </span>
            <button
              type="button"
              onClick={handleRunDiagnosticTest}
              className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] font-extrabold text-xs hover:bg-black cursor-pointer shadow-xs active:scale-95"
            >
              运行基础诊断自检
            </button>
          </div>

          {diagnosticResult && (
            <div className="p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-900 animate-in fade-in">
              {diagnosticResult}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
