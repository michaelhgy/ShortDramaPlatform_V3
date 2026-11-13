import React, { useEffect, useState, useMemo } from 'react';
import { V3ContentAsset } from '../../api/contentLibrary';
import {
  V3ContentGroup,
  V3ContentGroupItem,
  V3ContentOriginalRecord,
  V3ContentPublication
} from '../../api/contentGroups';
import { ContentAccountOption } from './contentTypes';
import {
  Plus,
  Edit3,
  Trash2,
  ArrowUp,
  ArrowDown,
  Layers,
  ShieldCheck,
  Send,
  History,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Users,
  Sparkles,
  X
} from 'lucide-react';

interface ContentGroupsPanelProps {
  assets: V3ContentAsset[];
  groups: V3ContentGroup[];
  groupItems: V3ContentGroupItem[];
  originalRecords: V3ContentOriginalRecord[];
  publications: V3ContentPublication[];
  accounts: ContentAccountOption[];
  globalAuthLimit: number;
  onCreateGroup: (name: string, description: string, tags: string[]) => void;
  onRenameGroup: (groupId: string, newName: string, newDesc: string) => void;
  onDeleteGroup: (groupId: string) => void;
  onAddAssetToGroup: (groupId: string, assetId: string) => void;
  onRemoveAssetFromGroup: (groupId: string, assetId: string) => void;
  onMoveGroupItemOrder: (groupId: string, assetId: string, direction: 'up' | 'down') => void;
  onExecuteOriginalPublish: (params: {
    groupId: string;
    assetId: string;
    accountId: string;
    actualPublishCount: number;
    simulateResult: 'success' | 'fail';
  }) => void;
  onExecuteAuthorizedPublish: (params: {
    groupId: string;
    assetId: string;
    accountId: string;
    actualPublishCount: number;
    simulateResult: 'success' | 'fail';
  }) => void;
  showToast: (msg: string) => void;
}

type GroupSubTab = 'detail' | 'original_pub' | 'auth_pub' | 'records';

export const ContentGroupsPanel: React.FC<ContentGroupsPanelProps> = ({
  assets,
  groups,
  groupItems,
  originalRecords,
  publications,
  accounts,
  globalAuthLimit,
  onCreateGroup,
  onRenameGroup,
  onDeleteGroup,
  onAddAssetToGroup,
  onRemoveAssetFromGroup,
  onMoveGroupItemOrder,
  onExecuteOriginalPublish,
  onExecuteAuthorizedPublish,
  showToast
}) => {
  const [selectedGroupId, setSelectedGroupId] = useState<string>(groups[0]?.id || '');
  const [activeSubTab, setActiveSubTab] = useState<GroupSubTab>('detail');

  // 新建/重命名编组状态
  const [showNewGroupModal, setShowNewGroupModal] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupDesc, setNewGroupDesc] = useState('');
  const [editingGroup, setEditingGroup] = useState<V3ContentGroup | null>(null);

  // 添加成片进编组弹窗
  const [showAddAssetModal, setShowAddAssetModal] = useState(false);

  // 原创发布表单状态
  const [origAccountId, setOrigAccountId] = useState<string>(accounts[0]?.id || '');
  const [origAssetId, setOrigAssetId] = useState<string>('');
  const [origPublishCount, setOrigPublishCount] = useState<number>(1);

  // 授权发布表单状态
  const [authAccountId, setAuthAccountId] = useState<string>(accounts[1]?.id || accounts[0]?.id || '');
  const [authAssetId, setAuthAssetId] = useState<string>('');
  const [authPublishCount, setAuthPublishCount] = useState<number>(2);

  // 发布记录筛选
  const [recordModeFilter, setRecordModeFilter] = useState<'ALL' | 'original' | 'publication'>('ALL');

  useEffect(() => {
    if (accounts.length === 0) return;
    if (!accounts.some((account) => account.id === origAccountId)) setOrigAccountId(accounts[0].id);
    if (!accounts.some((account) => account.id === authAccountId)) setAuthAccountId(accounts[1]?.id || accounts[0].id);
  }, [accounts, origAccountId, authAccountId]);

  const currentGroup = groups.find((g) => g.id === selectedGroupId) || groups[0];

  // 当前编组内的成片（按 sortOrder 排序）
  const currentGroupAssetList = useMemo(() => {
    if (!currentGroup) return [];
    const items = groupItems
      .filter((gi) => gi.groupId === currentGroup.id)
      .sort((a, b) => a.sortOrder - b.sortOrder);

    return items
      .map((gi) => {
        const asset = assets.find((a) => a.id === gi.assetId);
        if (!asset) return null;
        return {
          groupItem: gi,
          asset
        };
      })
      .filter((x): x is { groupItem: V3ContentGroupItem; asset: V3ContentAsset } => x !== null);
  }, [currentGroup, groupItems, assets]);

  // 确保默认选中组内第一条视频
  const effectiveOrigAssetId =
    origAssetId && currentGroupAssetList.some((x) => x.asset.id === origAssetId)
      ? origAssetId
      : currentGroupAssetList[0]?.asset.id || '';

  const effectiveAuthAssetId =
    authAssetId && currentGroupAssetList.some((x) => x.asset.id === authAssetId)
      ? authAssetId
      : currentGroupAssetList[0]?.asset.id || '';

  const selectedOrigAsset = assets.find((a) => a.id === effectiveOrigAssetId);
  const selectedAuthAsset = assets.find((a) => a.id === effectiveAuthAssetId);

  const getAssetJoinedGroupNames = (assetId: string): string[] => {
    const gIds = groupItems.filter((gi) => gi.assetId === assetId).map((gi) => gi.groupId);
    return groups.filter((g) => gIds.includes(g.id)).map((g) => g.name);
  };

  const handleCreateGroupSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGroupName.trim()) {
      showToast('请输入编组名称');
      return;
    }
    onCreateGroup(
      newGroupName.trim(),
      newGroupDesc.trim() || '支持跨剧集、跨来源混合发布管理集合',
      ['自定义编组', '混合分发']
    );
    setNewGroupName('');
    setNewGroupDesc('');
    setShowNewGroupModal(false);
  };

  const handleRenameSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingGroup || !editingGroup.name.trim()) return;
    onRenameGroup(editingGroup.id, editingGroup.name.trim(), editingGroup.description.trim());
    setEditingGroup(null);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      {/* 左侧栏 1：编组列表 (Left 3.5 Columns) */}
      <div className="lg:col-span-4 bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/70 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-extrabold text-slate-900">
              编组列表 (v3_content_groups)
            </h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              编组不是制作批次，只是发布管理集合；可跨剧集、跨来源自由混合
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowNewGroupModal(true)}
            className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-[#1A1D2E] hover:bg-black text-[#DDFD00] text-xs font-extrabold cursor-pointer flex-shrink-0"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>新建编组</span>
          </button>
        </div>

        <div className="divide-y divide-slate-100">
          {groups.map((grp) => {
            const count = groupItems.filter((gi) => gi.groupId === grp.id).length;
            const isSelected = currentGroup?.id === grp.id;

            return (
              <div
                key={grp.id}
                onClick={() => setSelectedGroupId(grp.id)}
                className={`p-4 cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-[#1A1D2E] text-white'
                    : 'hover:bg-slate-50 text-slate-800'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-extrabold text-sm flex items-center gap-2">
                    <Layers
                      className={`w-4 h-4 flex-shrink-0 ${
                        isSelected ? 'text-[#DDFD00]' : 'text-indigo-600'
                      }`}
                    />
                    <span>{grp.name}</span>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded-md font-mono text-[11px] font-bold flex-shrink-0 ${
                      isSelected
                        ? 'bg-[#DDFD00] text-slate-950'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {count} 条成片
                  </span>
                </div>

                <p
                  className={`text-xs mt-1.5 line-clamp-2 ${
                    isSelected ? 'text-slate-300' : 'text-slate-500'
                  }`}
                >
                  {grp.description}
                </p>

                <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
                  <div className="flex flex-wrap gap-1">
                    {grp.tags.map((t, i) => (
                      <span
                        key={i}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          isSelected
                            ? 'bg-white/10 text-slate-200'
                            : 'bg-indigo-50 text-indigo-700'
                        }`}
                      >
                        {t}
                      </span>
                    ))}
                  </div>

                  <div
                    className="flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      onClick={() => setEditingGroup({ ...grp })}
                      className={`p-1 rounded-lg text-xs ${
                        isSelected
                          ? 'text-slate-300 hover:text-white hover:bg-white/10'
                          : 'text-slate-400 hover:text-slate-700 hover:bg-slate-200/60'
                      } cursor-pointer`}
                      title="重命名编组"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                    {groups.length > 1 && (
                      <button
                        type="button"
                        onClick={() => onDeleteGroup(grp.id)}
                        className={`p-1 rounded-lg text-xs ${
                          isSelected
                            ? 'text-rose-300 hover:text-rose-200 hover:bg-white/10'
                            : 'text-slate-400 hover:text-rose-600 hover:bg-rose-50'
                        } cursor-pointer`}
                        title="删除编组"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 右侧主区：编组详情 / 原创发布 / 授权发布 / 发布记录 (Right 8 Columns) */}
      <div className="lg:col-span-8 space-y-5">
        {/* 二级功能切换栏 */}
        <div className="bg-white rounded-2xl border border-slate-200/90 p-3 shadow-xs flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setActiveSubTab('detail')}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-extrabold transition-all cursor-pointer ${
                activeSubTab === 'detail'
                  ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>编组详情 ({currentGroupAssetList.length})</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveSubTab('original_pub')}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-extrabold transition-all cursor-pointer ${
                activeSubTab === 'original_pub'
                  ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>原创发布</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveSubTab('auth_pub')}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-extrabold transition-all cursor-pointer ${
                activeSubTab === 'auth_pub'
                  ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <Send className="w-3.5 h-3.5" />
              <span>授权发布 (小V猫)</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveSubTab('records')}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-extrabold transition-all cursor-pointer ${
                activeSubTab === 'records'
                  ? 'bg-[#1A1D2E] text-[#DDFD00] shadow-xs'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>发布记录 ({originalRecords.length + publications.length})</span>
            </button>
          </div>

          {currentGroup && (
            <div className="text-xs font-bold text-slate-600 px-2">
              当前编组：<span className="text-slate-900">「{currentGroup.name}」</span>
            </div>
          )}
        </div>

        {/* 子模块 1：编组详情 */}
        {activeSubTab === 'detail' && currentGroup && (
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/70 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="font-extrabold text-sm text-slate-900">
                    {currentGroup.name} · 组内成片与顺序管理
                  </h4>
                  <button
                    type="button"
                    onClick={() => setEditingGroup({ ...currentGroup })}
                    className="text-xs text-indigo-600 hover:underline font-semibold cursor-pointer"
                  >
                    重命名
                  </button>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  支持跨剧集、跨来源混合编排；同一条成片可同时加入多个编组，互不锁定
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowAddAssetModal(true)}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-extrabold shadow-xs cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>添加成片到本编组</span>
              </button>
            </div>

            {currentGroupAssetList.length === 0 ? (
              <div className="p-12 text-center text-slate-400 text-xs">
                当前编组暂无成片，请点击右上角「添加成片到本编组」
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {currentGroupAssetList.map(({ groupItem, asset }, idx) => {
                  const allGroupNames = getAssetJoinedGroupNames(asset.id);
                  const remainingAuth = Math.max(0, globalAuthLimit - asset.authUsedCount);

                  return (
                    <div
                      key={groupItem.id}
                      className="p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 hover:bg-slate-50/60"
                    >
                      <div className="flex items-start gap-3.5 flex-1 min-w-0">
                        {/* Sort Order Number & Up/Down Controls */}
                        <div className="flex flex-col items-center gap-1 pt-0.5">
                          <button
                            type="button"
                            disabled={idx === 0}
                            onClick={() =>
                              onMoveGroupItemOrder(currentGroup.id, asset.id, 'up')
                            }
                            className={`p-1 rounded border ${
                              idx === 0
                                ? 'text-slate-300 border-slate-100 cursor-not-allowed'
                                : 'text-slate-600 border-slate-200 hover:bg-slate-100 cursor-pointer'
                            }`}
                            title="上移顺序"
                          >
                            <ArrowUp className="w-3 h-3" />
                          </button>
                          <span className="font-mono text-xs font-extrabold text-slate-700">
                            #{idx + 1}
                          </span>
                          <button
                            type="button"
                            disabled={idx === currentGroupAssetList.length - 1}
                            onClick={() =>
                              onMoveGroupItemOrder(currentGroup.id, asset.id, 'down')
                            }
                            className={`p-1 rounded border ${
                              idx === currentGroupAssetList.length - 1
                                ? 'text-slate-300 border-slate-100 cursor-not-allowed'
                                : 'text-slate-600 border-slate-200 hover:bg-slate-100 cursor-pointer'
                            }`}
                            title="下移顺序"
                          >
                            <ArrowDown className="w-3 h-3" />
                          </button>
                        </div>

                        <div className="space-y-1.5 flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-extrabold text-sm text-slate-900">
                              {asset.videoName}
                            </span>
                            <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 text-[11px] font-bold">
                              {asset.sourceType}
                            </span>
                            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px] font-bold">
                              《{asset.dramaTitle}》 {asset.episodeRange}
                            </span>
                          </div>

                          {/* 发布状态汇总 */}
                          <div className="flex flex-wrap items-center gap-3 text-xs">
                            <span
                              className={`font-bold ${
                                asset.originalStatus === '已声明原创'
                                  ? 'text-purple-700'
                                  : asset.originalStatus === '声明失败'
                                  ? 'text-rose-600'
                                  : 'text-slate-500'
                              }`}
                            >
                              原创状态：{asset.originalStatus}
                              {asset.originalDeclaredAccountName &&
                                ` (${asset.originalDeclaredAccountName})`}
                            </span>

                            <span className="text-slate-300">|</span>

                            <span className="font-mono font-bold text-emerald-700">
                              授权额度：已用 {asset.authUsedCount} / {globalAuthLimit} (余 {remainingAuth})
                            </span>

                            <span className="text-slate-300">|</span>

                            <span className="text-slate-600">
                              已发账号数：{asset.usedAccounts.length} 个
                            </span>
                          </div>

                          {/* 多编组复用标识 */}
                          <div className="text-[11px] text-slate-400">
                            同时存在于编组：{allGroupNames.join(' 、 ')}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 self-end sm:self-center">
                        <button
                          type="button"
                          onClick={() => {
                            setOrigAssetId(asset.id);
                            setActiveSubTab('original_pub');
                          }}
                          className="px-3 py-1.5 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-800 border border-purple-200 text-xs font-bold cursor-pointer"
                        >
                          去原创发布
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setAuthAssetId(asset.id);
                            setActiveSubTab('auth_pub');
                          }}
                          className="px-3 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 text-xs font-bold cursor-pointer"
                        >
                          去授权发布
                        </button>
                        <button
                          type="button"
                          onClick={() => onRemoveAssetFromGroup(currentGroup.id, asset.id)}
                          className="px-2.5 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-semibold cursor-pointer"
                        >
                          移出编组
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* 子模块 2：原创发布 */}
        {activeSubTab === 'original_pub' && (
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-5 space-y-5">
            <div className="border-b border-slate-100 pb-4">
              <h4 className="font-extrabold text-sm text-slate-900 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-purple-600" />
                <span>原创声明与首发控制 (v3_content_original_records)</span>
              </h4>
              <p className="text-xs text-slate-500 mt-1">
                业务规则：选择原创首发账号与编组内视频，设置该账号实际发布次数（1次/2次/3次均如实记录）。当前按钮是界面演示，不调用真实发布接口。
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              {/* 选择编组内视频 */}
              <div className="space-y-1.5">
                <label className="font-bold text-slate-700 block">
                  1. 选择当前编组「{currentGroup?.name}」内视频
                </label>
                <select
                  value={effectiveOrigAssetId}
                  onChange={(e) => setOrigAssetId(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-slate-50 font-bold text-slate-900"
                >
                  {currentGroupAssetList.map(({ asset }) => (
                    <option key={asset.id} value={asset.id}>
                      {asset.videoName} [{asset.originalStatus}]
                    </option>
                  ))}
                </select>
              </div>

              {/* 选择原创账号 */}
              <div className="space-y-1.5">
                <label className="font-bold text-slate-700 block">
                  2. 选择原创发布账号
                </label>
                <select
                  value={origAccountId}
                  onChange={(e) => setOrigAccountId(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-slate-50 font-bold text-slate-900"
                >
                  {accounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.name} ({acc.theaterName} · {acc.tier || '未定级'})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* 显示选中视频的原创状态 */}
            {selectedOrigAsset && (
              <div
                className={`p-4 rounded-xl border flex flex-wrap items-center justify-between gap-3 text-xs ${
                  selectedOrigAsset.originalStatus === '已声明原创'
                    ? 'bg-purple-50/70 border-purple-200 text-purple-950'
                    : selectedOrigAsset.originalStatus === '声明失败'
                    ? 'bg-rose-50/70 border-rose-200 text-rose-950'
                    : 'bg-slate-50 border-slate-200 text-slate-800'
                }`}
              >
                <div className="space-y-1">
                  <div className="font-extrabold text-sm">
                    当前视频原创状态：{selectedOrigAsset.originalStatus}
                  </div>
                  <div className="text-[11px] opacity-85">
                    {selectedOrigAsset.originalStatus === '已声明原创'
                      ? `已由账号「${selectedOrigAsset.originalDeclaredAccountName}」于 ${selectedOrigAsset.originalDeclaredAt} 成功声明原创`
                      : selectedOrigAsset.originalStatus === '声明失败'
                      ? `上次由「${selectedOrigAsset.originalDeclaredAccountName}」尝试声明原创失败（失败不算原创成功，可换号或重新发起）`
                      : '该成片尚未声明原创，可执行首发原创声明'}
                  </div>
                </div>
              </div>
            )}

            {/* 设置账号实际发布次数 */}
            <div className="space-y-2 text-xs">
              <label className="font-bold text-slate-700 block">
                3. 设置本账号实际发布次数（不把“每账号每天2条”写死成固定约束，1次、2次、3次均如实记录）
              </label>
              <div className="flex flex-wrap items-center gap-2.5">
                {[1, 2, 3, 4].map((cnt) => (
                  <button
                    key={cnt}
                    type="button"
                    onClick={() => setOrigPublishCount(cnt)}
                    className={`px-4 py-2 rounded-xl font-bold border transition-all cursor-pointer ${
                      origPublishCount === cnt
                        ? 'bg-[#1A1D2E] text-[#DDFD00] border-[#1A1D2E]'
                        : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    实际发布 {cnt} 次
                  </button>
                ))}
              </div>
            </div>

            {/* 触发按钮：成功 vs 模拟失败 */}
            <div className="pt-2 flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={!selectedOrigAsset}
                onClick={() => {
                  if (!currentGroup || !selectedOrigAsset) return;
                  onExecuteOriginalPublish({
                    groupId: currentGroup.id,
                    assetId: selectedOrigAsset.id,
                    accountId: origAccountId,
                    actualPublishCount: origPublishCount,
                    simulateResult: 'success'
                  });
                }}
                className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-extrabold text-xs flex items-center gap-2 shadow-xs cursor-pointer"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>演示记录原创成功 (消耗 {origPublishCount} 次)</span>
              </button>

              <button
                type="button"
                disabled={!selectedOrigAsset}
                onClick={() => {
                  if (!currentGroup || !selectedOrigAsset) return;
                  onExecuteOriginalPublish({
                    groupId: currentGroup.id,
                    assetId: selectedOrigAsset.id,
                    accountId: origAccountId,
                    actualPublishCount: origPublishCount,
                    simulateResult: 'fail'
                  });
                }}
                className="px-4 py-2.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-bold text-xs flex items-center gap-1.5 cursor-pointer"
              >
                <XCircle className="w-4 h-4" />
                <span>演示记录原创失败 (不计消耗)</span>
              </button>
            </div>
          </div>
        )}

        {/* 子模块 3：授权发布 */}
        {activeSubTab === 'auth_pub' && (
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-5 space-y-5">
            <div className="border-b border-slate-100 pb-4">
              <h4 className="font-extrabold text-sm text-slate-900 flex items-center gap-2">
                <Send className="w-4 h-4 text-emerald-600" />
                <span>小V猫授权发布管理 (v3_content_publications)</span>
              </h4>
              <p className="text-xs text-slate-500 mt-1">
                业务规则：授权调用走小V猫，V3只记录结果。当前页面只演示记录，不调用小V猫；授权上限按当前规则 {globalAuthLimit} 次显示。
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="space-y-1.5">
                <label className="font-bold text-slate-700 block">
                  1. 选择编组内待授权视频
                </label>
                <select
                  value={effectiveAuthAssetId}
                  onChange={(e) => setAuthAssetId(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-slate-50 font-bold text-slate-900"
                >
                  {currentGroupAssetList.map(({ asset }) => (
                    <option key={asset.id} value={asset.id}>
                      {asset.videoName} (已用 {asset.authUsedCount}/{globalAuthLimit})
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="font-bold text-slate-700 block">
                  2. 选择被授权矩阵账号
                </label>
                <select
                  value={authAccountId}
                  onChange={(e) => setAuthAccountId(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-slate-50 font-bold text-slate-900"
                >
                  {accounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.name} ({acc.theaterName} · {acc.tier || '未定级'})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* 授权额度仪表盘 + 已经使用过的账号 */}
            {selectedAuthAsset && (
              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-3 text-xs">
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-3 rounded-xl bg-white border border-slate-200">
                    <span className="text-slate-400 text-[11px] block">授权次数上限 (可配置)</span>
                    <span className="font-mono font-extrabold text-lg text-slate-900">
                      {globalAuthLimit} 次
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-white border border-slate-200">
                    <span className="text-slate-400 text-[11px] block">已用授权次数</span>
                    <span className="font-mono font-extrabold text-lg text-indigo-600">
                      {selectedAuthAsset.authUsedCount} 次
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-white border border-slate-200">
                    <span className="text-slate-400 text-[11px] block">剩余可用授权次数</span>
                    <span
                      className={`font-mono font-extrabold text-lg ${
                        Math.max(0, globalAuthLimit - selectedAuthAsset.authUsedCount) === 0
                          ? 'text-rose-600'
                          : 'text-emerald-600'
                      }`}
                    >
                      {Math.max(0, globalAuthLimit - selectedAuthAsset.authUsedCount)} 次
                    </span>
                  </div>
                </div>

                <div>
                  <div className="font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
                    <Users className="w-3.5 h-3.5 text-indigo-600" />
                    <span>已经使用过该成片的账号明细：</span>
                  </div>
                  {selectedAuthAsset.usedAccounts.length === 0 ? (
                    <div className="text-slate-400">尚无账号使用记录</div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {selectedAuthAsset.usedAccounts.map((u, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-slate-800 font-semibold"
                        >
                          {u.accountName} · {u.mode} · 实发 {u.publishCount} 次 ({u.lastPublishedAt})
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 实际发布次数设置 */}
            <div className="space-y-2 text-xs">
              <label className="font-bold text-slate-700 block">
                3. 本次账号实际发布次数（成功发布后按实际次数扣减额度，失败扣 0 次）
              </label>
              <div className="flex flex-wrap items-center gap-2.5">
                {[1, 2, 3].map((cnt) => (
                  <button
                    key={cnt}
                    type="button"
                    onClick={() => setAuthPublishCount(cnt)}
                    className={`px-4 py-2 rounded-xl font-bold border transition-all cursor-pointer ${
                      authPublishCount === cnt
                        ? 'bg-[#1A1D2E] text-[#DDFD00] border-[#1A1D2E]'
                        : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    实际发布 {cnt} 次
                  </button>
                ))}
              </div>
            </div>

            <div className="pt-2 flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={
                  !selectedAuthAsset ||
                  selectedAuthAsset.authUsedCount + authPublishCount > globalAuthLimit
                }
                onClick={() => {
                  if (!currentGroup || !selectedAuthAsset) return;
                  onExecuteAuthorizedPublish({
                    groupId: currentGroup.id,
                    assetId: selectedAuthAsset.id,
                    accountId: authAccountId,
                    actualPublishCount: authPublishCount,
                    simulateResult: 'success'
                  });
                }}
                className={`px-5 py-2.5 rounded-xl font-extrabold text-xs flex items-center gap-2 shadow-xs cursor-pointer ${
                  !selectedAuthAsset ||
                  selectedAuthAsset.authUsedCount + authPublishCount > globalAuthLimit
                    ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                    : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                }`}
              >
                <Send className="w-4 h-4" />
                <span>演示记录授权成功 (扣减 {authPublishCount} 次)</span>
              </button>

              <button
                type="button"
                disabled={!selectedAuthAsset}
                onClick={() => {
                  if (!currentGroup || !selectedAuthAsset) return;
                  onExecuteAuthorizedPublish({
                    groupId: currentGroup.id,
                    assetId: selectedAuthAsset.id,
                    accountId: authAccountId,
                    actualPublishCount: authPublishCount,
                    simulateResult: 'fail'
                  });
                }}
                className="px-4 py-2.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-bold text-xs flex items-center gap-1.5 cursor-pointer"
              >
                <AlertTriangle className="w-4 h-4" />
                <span>演示记录授权失败 (不扣授权次数)</span>
              </button>
            </div>
          </div>
        )}

        {/* 子模块 4：发布记录 (独立区分原创记录与授权发布记录) */}
        {activeSubTab === 'records' && (
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-5 space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div>
                <h4 className="font-extrabold text-sm text-slate-900">
                  原创声明记录与小V猫发布流水
                </h4>
                <p className="text-xs text-slate-500 mt-0.5">
                  区分存储 v3_content_original_records (原创声明) 与 v3_content_publications (账号实际发布 1次/2次/3次 记录)
                </p>
              </div>

              <div className="flex items-center gap-1.5 text-xs">
                <button
                  type="button"
                  onClick={() => setRecordModeFilter('ALL')}
                  className={`px-3 py-1.5 rounded-xl font-bold cursor-pointer ${
                    recordModeFilter === 'ALL'
                      ? 'bg-slate-900 text-white'
                      : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  全部显示
                </button>
                <button
                  type="button"
                  onClick={() => setRecordModeFilter('original')}
                  className={`px-3 py-1.5 rounded-xl font-bold cursor-pointer ${
                    recordModeFilter === 'original'
                      ? 'bg-purple-700 text-white'
                      : 'bg-purple-50 text-purple-800'
                  }`}
                >
                  原创声明记录 ({originalRecords.length})
                </button>
                <button
                  type="button"
                  onClick={() => setRecordModeFilter('publication')}
                  className={`px-3 py-1.5 rounded-xl font-bold cursor-pointer ${
                    recordModeFilter === 'publication'
                      ? 'bg-emerald-700 text-white'
                      : 'bg-emerald-50 text-emerald-800'
                  }`}
                >
                  账号发布流水 ({publications.length})
                </button>
              </div>
            </div>

            {/* 1. 原创声明记录表 */}
            {(recordModeFilter === 'ALL' || recordModeFilter === 'original') && (
              <div className="space-y-2.5">
                <h5 className="text-xs font-extrabold text-purple-900 flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-purple-600" />
                  <span>原创声明记录表 (v3_content_original_records)</span>
                </h5>
                <div className="space-y-2">
                  {originalRecords.map((rec) => (
                    <div
                      key={rec.id}
                      className={`p-3.5 rounded-xl border text-xs flex flex-wrap items-center justify-between gap-3 ${
                        rec.status === '原创声明成功'
                          ? 'bg-purple-50/40 border-purple-200/80'
                          : 'bg-rose-50/60 border-rose-200'
                      }`}
                    >
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded font-bold text-[11px] ${
                              rec.status === '原创声明成功'
                                ? 'bg-purple-600 text-white'
                                : 'bg-rose-600 text-white'
                            }`}
                          >
                            {rec.status}
                          </span>
                          <span className="font-extrabold text-slate-900">{rec.videoName}</span>
                          <span className="text-slate-500">· 账号：{rec.accountName}</span>
                        </div>
                        {rec.failureReason && (
                          <div className="text-rose-700 font-semibold text-[11px]">
                            原因：{rec.failureReason}
                          </div>
                        )}
                      </div>

                      <div className="text-right font-mono text-[11px] space-y-0.5">
                        <div className="font-bold text-slate-800">
                          实发设置：{rec.actualPublishCount}次 · 有效消耗：{rec.consumedOriginalCount}次
                        </div>
                        <div className="text-slate-400">{rec.recordedAt}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 2. 账号发布记录表 */}
            {(recordModeFilter === 'ALL' || recordModeFilter === 'publication') && (
              <div className="space-y-2.5 pt-2">
                <h5 className="text-xs font-extrabold text-emerald-900 flex items-center gap-1.5">
                  <Send className="w-3.5 h-3.5 text-emerald-600" />
                  <span>小V猫发布流水表 (v3_content_publications)</span>
                </h5>
                <div className="space-y-2">
                  {publications.map((pub) => (
                    <div
                      key={pub.id}
                      className={`p-3.5 rounded-xl border text-xs flex flex-wrap items-center justify-between gap-3 ${
                        pub.status === '发布成功'
                          ? 'bg-slate-50/80 border-slate-200'
                          : 'bg-rose-50/60 border-rose-200'
                      }`}
                    >
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded font-bold text-[11px] ${
                              pub.status === '发布成功'
                                ? 'bg-emerald-600 text-white'
                                : 'bg-rose-600 text-white'
                            }`}
                          >
                            {pub.status}
                          </span>
                          <span className="px-2 py-0.5 rounded bg-slate-200 text-slate-800 font-bold text-[11px]">
                            {pub.publishMode}
                          </span>
                          <span className="font-extrabold text-slate-900">{pub.videoName}</span>
                          <span className="font-bold text-indigo-700">→ {pub.accountName}</span>
                        </div>
                        <div className="text-[11px] text-slate-500">
                          流水号: <span className="font-mono">{pub.xiaovmaoFlowCode}</span> · 所属编组: {pub.groupName || '直发'}
                        </div>
                        {pub.failureReason && (
                          <div className="text-rose-700 font-semibold text-[11px]">
                            {pub.failureReason}
                          </div>
                        )}
                      </div>

                      <div className="text-right font-mono text-[11px] space-y-0.5">
                        <div className="font-bold text-slate-900">
                          账号实际发布：{pub.actualPublishCount} 次 · 扣减授权：{pub.authQuotaDeducted} 次
                        </div>
                        <div className="text-slate-400">{pub.publishedAt}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal: 新建编组 */}
      {showNewGroupModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <form
            onSubmit={handleCreateGroupSubmit}
            className="bg-white rounded-2xl max-w-md w-full border border-slate-200 shadow-2xl overflow-hidden"
          >
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
              <h4 className="font-extrabold text-sm text-slate-900">新建发布编组</h4>
              <button
                type="button"
                onClick={() => setShowNewGroupModal(false)}
                className="p-1 text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-3.5 text-xs">
              <div>
                <label className="font-bold text-slate-700 block mb-1">编组名称</label>
                <input
                  type="text"
                  placeholder="例如：周末午间档·多剧混合冲量组"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-bold"
                />
              </div>
              <div>
                <label className="font-bold text-slate-700 block mb-1">编组说明</label>
                <textarea
                  rows={3}
                  placeholder="描述该编组的发布策略（可跨剧集、跨来源自由添加成片）"
                  value={newGroupDesc}
                  onChange={(e) => setNewGroupDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50"
                />
              </div>
            </div>
            <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowNewGroupModal(false)}
                className="px-4 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 cursor-pointer"
              >
                取消
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-extrabold cursor-pointer"
              >
                创建编组
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal: 重命名编组 */}
      {editingGroup && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <form
            onSubmit={handleRenameSubmit}
            className="bg-white rounded-2xl max-w-md w-full border border-slate-200 shadow-2xl overflow-hidden"
          >
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
              <h4 className="font-extrabold text-sm text-slate-900">重命名与编辑编组</h4>
              <button
                type="button"
                onClick={() => setEditingGroup(null)}
                className="p-1 text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-3.5 text-xs">
              <div>
                <label className="font-bold text-slate-700 block mb-1">编组名称</label>
                <input
                  type="text"
                  value={editingGroup.name}
                  onChange={(e) => setEditingGroup({ ...editingGroup, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 font-bold"
                />
              </div>
              <div>
                <label className="font-bold text-slate-700 block mb-1">编组说明</label>
                <textarea
                  rows={3}
                  value={editingGroup.description}
                  onChange={(e) =>
                    setEditingGroup({ ...editingGroup, description: e.target.value })
                  }
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50"
                />
              </div>
            </div>
            <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingGroup(null)}
                className="px-4 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 cursor-pointer"
              >
                取消
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-extrabold cursor-pointer"
              >
                保存修改
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal: 添加成片进当前编组 */}
      {showAddAssetModal && currentGroup && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full border border-slate-200 shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
              <div>
                <h4 className="font-extrabold text-sm text-slate-900">
                  向「{currentGroup.name}」添加成片
                </h4>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  支持混合不同剧集与不同来源；已在其他编组的成片也可加入本编组
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowAddAssetModal(false)}
                className="p-1 text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 max-h-[420px] overflow-y-auto divide-y divide-slate-100 text-xs">
              {assets
                .filter((a) => a.manualStatus !== '已淘汰')
                .map((asset) => {
                  const alreadyInGroup = groupItems.some(
                    (gi) => gi.groupId === currentGroup.id && gi.assetId === asset.id
                  );
                  return (
                    <div
                      key={asset.id}
                      className="py-3 flex items-center justify-between gap-3"
                    >
                      <div>
                        <div className="font-extrabold text-slate-900">{asset.videoName}</div>
                        <div className="text-[11px] text-slate-500 mt-0.5">
                          来源: {asset.sourceType} · 《{asset.dramaTitle}》 · 原创: {asset.originalStatus} · 授权: {asset.authUsedCount}/{globalAuthLimit}
                        </div>
                      </div>

                      {alreadyInGroup ? (
                        <span className="px-3 py-1.5 rounded-xl bg-slate-100 text-slate-400 font-bold">
                          已在组内
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onAddAssetToGroup(currentGroup.id, asset.id)}
                          className="px-3.5 py-1.5 rounded-xl bg-[#1A1D2E] text-[#DDFD00] font-extrabold cursor-pointer"
                        >
                          + 加入本编组
                        </button>
                      )}
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
