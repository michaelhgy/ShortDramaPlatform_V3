import React, { useState, useMemo, useEffect } from 'react';
import {
  V3ContentAsset,
  ContentAssetFilterState,
  ContentAssetSourceType
} from '../../api/contentLibrary';
import { V3ContentGroup, V3ContentGroupItem } from '../../api/contentGroups';
import { ManualReviewStatus } from '../../api/contentProduction';
import {
  Filter,
  Search,
  Upload,
  FolderOpen,
  Play,
  ShieldCheck,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  Layers,
  Users,
  Sparkles,
  Plus,
  X,
  Sliders
} from 'lucide-react';

interface ContentLibraryPanelProps {
  contentAssetRoot: string;
  assets: V3ContentAsset[];
  groups: V3ContentGroup[];
  groupItems: V3ContentGroupItem[];
  globalAuthLimit: number;
  onUpdateGlobalAuthLimit: (newLimit: number) => void;
  onUpdateAssetManualStatus: (assetId: string, status: ManualReviewStatus) => void;
  onImportExternalAsset: (newAsset: Omit<V3ContentAsset, 'id' | 'createdAt'>) => void;
  onToggleAssetInGroup: (assetId: string, groupId: string) => void;
  showToast: (msg: string) => void;
}

export const ContentLibraryPanel: React.FC<ContentLibraryPanelProps> = ({
  contentAssetRoot,
  assets,
  groups,
  groupItems,
  globalAuthLimit,
  onUpdateGlobalAuthLimit,
  onUpdateAssetManualStatus,
  onImportExternalAsset,
  onToggleAssetInGroup,
  showToast
}) => {
  const [filters, setFilters] = useState<ContentAssetFilterState>({
    dramaTitle: 'ALL',
    sourceType: 'ALL',
    techQualified: 'ALL',
    originalDeclared: 'ALL',
    authUsageRange: 'ALL',
    publishState: 'ALL',
    eliminatedState: 'ALL',
    searchQuery: ''
  });

  // 弹窗：导入外部视频或旧流程成片
  const [showImportModal, setShowImportModal] = useState(false);
  const [importSourceType, setImportSourceType] = useState<ContentAssetSourceType>('外部导入视频');
  const [importVideoName, setImportVideoName] = useState('狂飙天王_外部精剪团队_高燃卡点05.mp4');
  const [importDramaTitle, setImportDramaTitle] = useState('狂飙天王');
  const [importEpisodeRange, setImportEpisodeRange] = useState('第09集 ~ 第15集');
  const [importDuration, setImportDuration] = useState('07分25秒');
  const [importFilePath, setImportFilePath] = useState(
    `${contentAssetRoot}\\外部导入\\狂飙天王_外部精剪团队_高燃卡点05.mp4`
  );

  useEffect(() => {
    setImportFilePath((current) => {
      const fileName = current.split(/[\\/]/).pop() || '外部导入视频.mp4';
      return `${contentAssetRoot.replace(/[\\/]+$/, '')}\\外部导入\\${fileName}`;
    });
  }, [contentAssetRoot]);

  // 弹窗：快速管理某条成片所属编组（多对多）
  const [groupAssignAsset, setGroupAssignAsset] = useState<V3ContentAsset | null>(null);

  const uniqueDramas = useMemo(() => {
    return Array.from(new Set(assets.map((a) => a.dramaTitle)));
  }, [assets]);

  // 7大筛选条件过滤逻辑
  const filteredAssets = useMemo(() => {
    return assets.filter((asset) => {
      // 1. 剧集
      if (filters.dramaTitle !== 'ALL' && asset.dramaTitle !== filters.dramaTitle) {
        return false;
      }
      // 2. 来源类型
      if (filters.sourceType !== 'ALL' && asset.sourceType !== filters.sourceType) {
        return false;
      }
      // 3. 是否合格 (技术状态)
      if (filters.techQualified !== 'ALL' && asset.techStatus !== filters.techQualified) {
        return false;
      }
      // 4. 是否已声明原创
      if (filters.originalDeclared !== 'ALL' && asset.originalStatus !== filters.originalDeclared) {
        return false;
      }
      // 5. 授权次数
      const limit = asset.authMaxLimit || globalAuthLimit;
      if (filters.authUsageRange === 'unused' && asset.authUsedCount !== 0) {
        return false;
      }
      if (
        filters.authUsageRange === 'available' &&
        (asset.authUsedCount === 0 || asset.authUsedCount >= limit)
      ) {
        return false;
      }
      if (filters.authUsageRange === 'exhausted' && asset.authUsedCount < limit) {
        return false;
      }
      // 6. 是否已发布
      const isPublished = asset.usedAccounts.length > 0;
      if (filters.publishState === 'published' && !isPublished) return false;
      if (filters.publishState === 'unpublished' && isPublished) return false;
      // 7. 是否被淘汰
      const isEliminated = asset.manualStatus === '已淘汰';
      if (filters.eliminatedState === 'active' && isEliminated) return false;
      if (filters.eliminatedState === 'eliminated' && !isEliminated) return false;

      // 关键词搜索
      if (filters.searchQuery.trim()) {
        const q = filters.searchQuery.toLowerCase();
        const matchName = asset.videoName.toLowerCase().includes(q);
        const matchDrama = asset.dramaTitle.toLowerCase().includes(q);
        const matchRecord = asset.generationRecord.toLowerCase().includes(q);
        if (!matchName && !matchDrama && !matchRecord) return false;
      }
      return true;
    });
  }, [assets, filters, globalAuthLimit]);

  const getAssetGroups = (assetId: string): V3ContentGroup[] => {
    const gIds = groupItems
      .filter((gi) => gi.assetId === assetId)
      .map((gi) => gi.groupId);
    return groups.filter((g) => gIds.includes(g.id));
  };

  const handleConfirmImport = (e: React.FormEvent) => {
    e.preventDefault();
    if (!importVideoName.trim() || !importFilePath.trim()) {
      showToast('请填写完整的视频名称与本地文件路径');
      return;
    }
    onImportExternalAsset({
      videoName: importVideoName.trim(),
      sourceType: importSourceType,
      dramaId: `drama-custom-${Date.now()}`,
      dramaTitle: importDramaTitle.trim() || '未分类剧集',
      generationRecord:
        importSourceType === '外部导入视频'
          ? `EXT-IMPORT-${new Date().toISOString().slice(0, 10)} · 外部成片校验入库`
          : `LEGACY-SYNC-${new Date().toISOString().slice(0, 10)} · 旧生产中心成片归档引用`,
      templateVersion:
        importSourceType === '外部导入视频' ? '外部原生精剪 (无模板)' : 'Legacy-JianYing-v2.1',
      durationSec: 445,
      durationFormatted: importDuration,
      filePath: importFilePath.trim(),
      episodeRange: importEpisodeRange,
      techStatus: '合格',
      techDetail: '1080×1920 · 导入时已完成声画流与黑屏帧扫描',
      manualStatus: '已通过',
      originalStatus: '未声明原创',
      authUsedCount: 0,
      authMaxLimit: globalAuthLimit,
      usedAccounts: [],
      previewHue: 'from-teal-950 via-slate-900 to-indigo-950'
    });
    setShowImportModal(false);
  };

  return (
    <div className="space-y-5">
      {/* Top Banner & Source Summary */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-5 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <h3 className="text-base font-extrabold text-slate-900">
                内容生产·独立成片库 (v3_content_assets)
              </h3>
              <span className="px-2.5 py-0.5 rounded-md bg-[#1A1D2E] text-[#DDFD00] text-[11px] font-bold">
                共 {assets.length} 条成片
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              独立于旧“生产资源”，统一收纳「原剧二创」、「旧流程成片」、「外部导入视频」三种来源，核算原创声明状态与小V猫授权次数
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* 当前平台授权规则 */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-xs">
              <Sliders className="w-3.5 h-3.5 text-indigo-600" />
              <span className="text-slate-600 font-semibold">单条授权上限(当前规则):</span>
              <input
                type="number"
                value={globalAuthLimit}
                readOnly
                aria-label="当前单条授权上限"
                className="w-12 px-1.5 py-0.5 rounded border border-slate-300 bg-slate-100 font-mono font-bold text-center text-slate-900"
              />
              <span className="text-slate-400">次</span>
            </div>

            <button
              type="button"
              onClick={() => setShowImportModal(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold shadow-xs transition-all cursor-pointer"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>导入外部视频 / 归档旧成片</span>
            </button>
          </div>
        </div>

        {/* 7 Required Filter Criteria Bar */}
        <div className="pt-3 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5 text-xs">
          {/* 1. 剧集 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">1. 所属剧集</label>
            <select
              value={filters.dramaTitle}
              onChange={(e) => setFilters({ ...filters, dramaTitle: e.target.value })}
              className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
            >
              <option value="ALL">全部剧集</option>
              {uniqueDramas.map((d) => (
                <option key={d} value={d}>
                  《{d}》
                </option>
              ))}
            </select>
          </div>

          {/* 2. 来源类型 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">2. 来源类型</label>
            <select
              value={filters.sourceType}
              onChange={(e) =>
                setFilters({ ...filters, sourceType: e.target.value as ContentAssetSourceType | 'ALL' })
              }
              className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
            >
              <option value="ALL">全部三种来源</option>
              <option value="原剧二创">原剧二创</option>
              <option value="旧流程成片">旧流程成片</option>
              <option value="外部导入视频">外部导入视频</option>
            </select>
          </div>

          {/* 3. 是否合格 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">3. 是否合格(技术)</label>
            <select
              value={filters.techQualified}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  techQualified: e.target.value as ContentAssetFilterState['techQualified']
                })
              }
              className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
            >
              <option value="ALL">全部技术状态</option>
              <option value="合格">合格</option>
              <option value="不合格">不合格</option>
              <option value="待检查">待检查</option>
            </select>
          </div>

          {/* 4. 是否已声明原创 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">4. 是否已声明原创</label>
            <select
              value={filters.originalDeclared}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  originalDeclared: e.target.value as ContentAssetFilterState['originalDeclared']
                })
              }
              className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
            >
              <option value="ALL">全部原创状态</option>
              <option value="已声明原创">已声明原创</option>
              <option value="未声明原创">未声明原创</option>
              <option value="声明失败">声明失败</option>
            </select>
          </div>

          {/* 5. 授权次数 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">5. 授权次数额度</label>
            <select
              value={filters.authUsageRange}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  authUsageRange: e.target.value as ContentAssetFilterState['authUsageRange']
                })
              }
              className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
            >
              <option value="ALL">全部授权进度</option>
              <option value="unused">0 次使用 (全新)</option>
              <option value="available">已部分使用 (仍有余量)</option>
              <option value="exhausted">已达上限 ({globalAuthLimit}/{globalAuthLimit})</option>
            </select>
          </div>

          {/* 6. 是否已发布 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">6. 是否已发布</label>
            <select
              value={filters.publishState}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  publishState: e.target.value as ContentAssetFilterState['publishState']
                })
              }
              className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
            >
              <option value="ALL">全部发布状态</option>
              <option value="published">已发布过 (≥1个账号)</option>
              <option value="unpublished">尚未发布</option>
            </select>
          </div>

          {/* 7. 是否被淘汰 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">7. 是否被淘汰</label>
            <select
              value={filters.eliminatedState}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  eliminatedState: e.target.value as ContentAssetFilterState['eliminatedState']
                })
              }
              className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 font-semibold text-slate-800"
            >
              <option value="ALL">包含全部</option>
              <option value="active">仅看未淘汰</option>
              <option value="eliminated">仅看已淘汰</option>
            </select>
          </div>

          {/* 搜索框 */}
          <div>
            <label className="text-[11px] text-slate-400 font-semibold block mb-1">检索名称/批次</label>
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
              <input
                type="text"
                placeholder="搜文件名或记录..."
                value={filters.searchQuery}
                onChange={(e) => setFilters({ ...filters, searchQuery: e.target.value })}
                className="w-full pl-8 pr-2.5 py-1.5 rounded-xl border border-slate-200 bg-slate-50 text-slate-800"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Asset List Display (Showing all 13 required fields clearly) */}
      <div className="space-y-3.5">
        {filteredAssets.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center text-slate-400 text-xs">
            当前筛选条件下暂无匹配的成片记录
          </div>
        ) : (
          filteredAssets.map((asset) => {
            const joinedGroups = getAssetGroups(asset.id);
            const effectiveLimit = globalAuthLimit;
            const remainingAuth = Math.max(0, effectiveLimit - asset.authUsedCount);
            const isExhausted = remainingAuth === 0;

            return (
              <div
                key={asset.id}
                className={`bg-white rounded-2xl border transition-all p-4 sm:p-5 shadow-xs ${
                  asset.manualStatus === '已淘汰'
                    ? 'border-rose-200/70 bg-rose-50/15 opacity-80'
                    : 'border-slate-200/90 hover:border-slate-300'
                }`}
              >
                <div className="flex flex-col xl:flex-row gap-4 justify-between items-start">
                  {/* Left: Preview + Core 13 Fields */}
                  <div className="flex items-start gap-4 flex-1 min-w-0 w-full">
                    {/* Preview Box */}
                    <div
                      className={`w-20 h-28 rounded-xl bg-gradient-to-br ${asset.previewHue} flex-shrink-0 p-2 text-white flex flex-col justify-between border border-slate-800/20`}
                    >
                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-black/40 text-center truncate">
                        {asset.sourceType}
                      </span>
                      <div className="self-center w-7 h-7 rounded-full bg-white/20 flex items-center justify-center">
                        <Play className="w-3.5 h-3.5 fill-current ml-0.5" />
                      </div>
                      <span className="text-[10px] font-mono font-bold bg-black/60 rounded px-1 py-0.5 text-center">
                        {asset.durationFormatted}
                      </span>
                    </div>

                    {/* 13 Required Fields Structured Layout */}
                    <div className="flex-1 min-w-0 space-y-3">
                      {/* Row 1: 视频名称 + 来源类型 + 所属剧集 + 时长 + 状态标签 */}
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-extrabold text-sm text-slate-900">
                          {asset.videoName}
                        </span>

                        {/* 来源类型 */}
                        <span
                          className={`px-2 py-0.5 rounded-md text-[11px] font-bold border ${
                            asset.sourceType === '原剧二创'
                              ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                              : asset.sourceType === '旧流程成片'
                              ? 'bg-amber-50 text-amber-800 border-amber-200'
                              : 'bg-teal-50 text-teal-800 border-teal-200'
                          }`}
                        >
                          来源：{asset.sourceType}
                        </span>

                        {/* 技术状态 */}
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold border ${
                            asset.techStatus === '合格'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : asset.techStatus === '不合格'
                              ? 'bg-rose-50 text-rose-700 border-rose-200'
                              : 'bg-slate-100 text-slate-700 border-slate-200'
                          }`}
                        >
                          <ShieldCheck className="w-3 h-3" />
                          技术状态：{asset.techStatus}
                        </span>

                        {/* 人工状态 */}
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold border ${
                            asset.manualStatus === '已通过'
                              ? 'bg-blue-50 text-blue-700 border-blue-200'
                              : asset.manualStatus === '已淘汰'
                              ? 'bg-rose-100 text-rose-800 border-rose-300'
                              : 'bg-amber-50 text-amber-800 border-amber-200'
                          }`}
                        >
                          人工状态：{asset.manualStatus}
                        </span>

                        {/* 原创状态 */}
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold border ${
                            asset.originalStatus === '已声明原创'
                              ? 'bg-purple-50 text-purple-800 border-purple-200'
                              : asset.originalStatus === '声明失败'
                              ? 'bg-rose-50 text-rose-700 border-rose-200'
                              : 'bg-slate-100 text-slate-600 border-slate-200'
                          }`}
                        >
                          原创状态：{asset.originalStatus}
                          {asset.originalDeclaredAccountName &&
                            ` (${asset.originalDeclaredAccountName})`}
                        </span>
                      </div>

                      {/* Row 2: 所属剧集、生成记录、模板版本、时长、授权已用次数/9 */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 text-xs">
                        <div className="p-2 rounded-xl bg-slate-50 border border-slate-200/70">
                          <span className="text-[10px] text-slate-400 block">所属剧集 & 时长</span>
                          <span className="font-bold text-slate-900">
                            《{asset.dramaTitle}》 {asset.episodeRange} · {asset.durationFormatted}
                          </span>
                        </div>

                        <div className="p-2 rounded-xl bg-slate-50 border border-slate-200/70">
                          <span className="text-[10px] text-slate-400 block">生成记录</span>
                          <span className="font-semibold text-slate-800 truncate block" title={asset.generationRecord}>
                            {asset.generationRecord}
                          </span>
                        </div>

                        <div className="p-2 rounded-xl bg-slate-50 border border-slate-200/70">
                          <span className="text-[10px] text-slate-400 block">模板版本</span>
                          <span className="font-mono font-bold text-slate-800 truncate block">
                            {asset.templateVersion}
                          </span>
                        </div>

                        <div
                          className={`p-2 rounded-xl border ${
                            isExhausted
                              ? 'bg-rose-50/70 border-rose-200 text-rose-900'
                              : 'bg-emerald-50/50 border-emerald-200/80 text-emerald-950'
                          }`}
                        >
                          <span className="text-[10px] opacity-75 block">
                            授权已用次数 / {effectiveLimit}
                          </span>
                          <div className="font-mono font-extrabold text-sm flex items-center justify-between">
                            <span>
                              {asset.authUsedCount} / {effectiveLimit}
                            </span>
                            <span className="text-[11px] font-sans font-bold">
                              剩余 {remainingAuth} 次
                            </span>
                          </div>
                        </div>

                        <div className="p-2 rounded-xl bg-slate-50 border border-slate-200/70">
                          <span className="text-[10px] text-slate-400 block">本地文件路径</span>
                          <span
                            className="font-mono text-[11px] text-slate-700 truncate block"
                            title={asset.filePath}
                          >
                            {asset.filePath}
                          </span>
                        </div>
                      </div>

                      {/* Row 3: 使用过的账号 & 所属编组 (多对多) */}
                      <div className="flex flex-wrap items-center justify-between gap-3 pt-1 text-xs">
                        {/* 使用过的账号 */}
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-slate-500 font-semibold flex items-center gap-1">
                            <Users className="w-3.5 h-3.5 text-slate-400" />
                            使用过的账号：
                          </span>
                          {asset.usedAccounts.length === 0 ? (
                            <span className="text-slate-400">暂无账号发布记录</span>
                          ) : (
                            asset.usedAccounts.map((acc, i) => (
                              <span
                                key={`${acc.accountId}-${i}`}
                                className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border ${
                                  acc.mode === '原创发布'
                                    ? 'bg-purple-50 text-purple-900 border-purple-200'
                                    : 'bg-slate-100 text-slate-800 border-slate-200'
                                }`}
                              >
                                {acc.accountName} ({acc.mode}·实发{acc.publishCount}次)
                              </span>
                            ))
                          )}
                        </div>

                        {/* 所属编组 (同一成片可加入多个编组) */}
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-slate-500 font-semibold flex items-center gap-1">
                            <Layers className="w-3.5 h-3.5 text-indigo-600" />
                            所属编组 ({joinedGroups.length})：
                          </span>
                          {joinedGroups.length === 0 ? (
                            <span className="text-slate-400">未加入编组</span>
                          ) : (
                            joinedGroups.map((g) => (
                              <span
                                key={g.id}
                                className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-800 border border-indigo-200 text-[11px] font-bold"
                              >
                                {g.name}
                              </span>
                            ))
                          )}
                          <button
                            type="button"
                            onClick={() => setGroupAssignAsset(asset)}
                            className="px-2 py-0.5 rounded-md bg-slate-900 text-[#DDFD00] text-[11px] font-bold hover:bg-black cursor-pointer"
                          >
                            + 编组配置
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Right Actions */}
                  <div className="flex xl:flex-col items-center gap-2 self-end xl:self-center flex-shrink-0">
                    <button
                      type="button"
                      onClick={() =>
                        showToast(`📂 已在资源管理器定位：${asset.filePath}`)
                      }
                      className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                    >
                      <FolderOpen className="w-3.5 h-3.5 text-amber-600" />
                      <span>定位文件</span>
                    </button>

                    {asset.manualStatus !== '已淘汰' ? (
                      <button
                        type="button"
                        onClick={() => onUpdateAssetManualStatus(asset.id, '已淘汰')}
                        className="px-3 py-1.5 rounded-xl border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-bold cursor-pointer"
                      >
                        标记淘汰
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onUpdateAssetManualStatus(asset.id, '已通过')}
                        className="px-3 py-1.5 rounded-xl border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-xs font-bold cursor-pointer"
                      >
                        恢复通过
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Modal: 外部导入视频 / 旧流程成片入库 */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <form
            onSubmit={handleConfirmImport}
            className="bg-white rounded-2xl max-w-lg w-full border border-slate-200 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150"
          >
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
              <h4 className="font-extrabold text-sm text-slate-900">
                导入外部视频或归档旧流程成片
              </h4>
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                className="p-1 text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-3.5 text-xs">
              <div>
                <label className="font-bold text-slate-700 block mb-1">成片来源类型</label>
                <select
                  value={importSourceType}
                  onChange={(e) => setImportSourceType(e.target.value as ContentAssetSourceType)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-bold text-slate-900"
                >
                  <option value="外部导入视频">外部导入视频</option>
                  <option value="旧流程成片">旧流程成片 (生产中心归档)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold text-slate-700 block mb-1">所属剧集名称</label>
                  <input
                    type="text"
                    value={importDramaTitle}
                    onChange={(e) => setImportDramaTitle(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-bold"
                  />
                </div>
                <div>
                  <label className="font-bold text-slate-700 block mb-1">对应剧集范围</label>
                  <input
                    type="text"
                    value={importEpisodeRange}
                    onChange={(e) => setImportEpisodeRange(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="font-bold text-slate-700 block mb-1">视频文件名称</label>
                  <input
                    type="text"
                    value={importVideoName}
                    onChange={(e) => setImportVideoName(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-bold"
                  />
                </div>
                <div>
                  <label className="font-bold text-slate-700 block mb-1">时长</label>
                  <input
                    type="text"
                    value={importDuration}
                    onChange={(e) => setImportDuration(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="font-bold text-slate-700 block mb-1">本地磁盘文件路径</label>
                <input
                  type="text"
                  value={importFilePath}
                  onChange={(e) => setImportFilePath(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-mono text-[11px]"
                />
              </div>
            </div>

            <div className="px-5 py-3.5 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                className="px-4 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 cursor-pointer"
              >
                取消
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-extrabold cursor-pointer"
              >
                确认入库
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal: 编组多对多配置 */}
      {groupAssignAsset && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full border border-slate-200 shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
              <div>
                <h4 className="font-extrabold text-sm text-slate-900">
                  分配至发布编组 (支持多对多复用)
                </h4>
                <p className="text-[11px] text-slate-500 truncate mt-0.5">
                  {groupAssignAsset.videoName}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setGroupAssignAsset(null)}
                className="p-1 text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-2.5 text-xs">
              {groups.map((grp) => {
                const isJoined = groupItems.some(
                  (gi) => gi.assetId === groupAssignAsset.id && gi.groupId === grp.id
                );
                return (
                  <div
                    key={grp.id}
                    onClick={() => onToggleAssetInGroup(groupAssignAsset.id, grp.id)}
                    className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                      isJoined
                        ? 'bg-indigo-50/70 border-indigo-300 text-indigo-950'
                        : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    <div>
                      <div className="font-extrabold">{grp.name}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">{grp.description}</div>
                    </div>
                    <span
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-bold ${
                        isJoined ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-700'
                      }`}
                    >
                      {isJoined ? '已加入' : '点击加入'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
