import { AccountFetchModal } from './modals/AccountFetchModal';
import { getV2Accounts, getV2RevenueCollectorDefinitions, type RevenueCollectorDefinition } from '../../api/v2Catalog';
import { toBusinessAccount } from '../../adapters/catalog';
import { AccountAvatar } from '../AccountAvatar';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useAdaptivePageSize } from '../../hooks/useAdaptivePageSize';
import {
  AccountBusinessItem,
  TheaterBusinessItem,
  SubTheaterBusinessItem,
  DramaBusinessItem,
  AccountBusinessStatus,
} from '../../assetsTypes';
import {
  Users,
  Building2,
  GitFork,
  Film,
  Search,
  Plus,
  FileSpreadsheet,
  Download,
  Edit2,
  History,
  CheckCircle,
  AlertTriangle,
  ExternalLink,
  Shield,
  Layers,
  ArrowRight,
  Filter,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  Lock,
  Trash2,
} from 'lucide-react';
import { AccountModal } from './modals/AccountModal';
import { AccountBatchImportModal } from './modals/AccountBatchImportModal';
import { TheaterModal } from './modals/TheaterModal';
import { isAvailableAccountStatus } from '../../services/accountVisibility';
import { TheaterBatchImportModal } from './modals/TheaterBatchImportModal';
import { SubTheaterModal } from './modals/SubTheaterModal';
import { SubTheaterBatchImportModal } from './modals/SubTheaterBatchImportModal';
import { DramaRenameModal } from './modals/DramaRenameModal';
import { DramaBatchImportModal } from './modals/DramaBatchImportModal';
import { createBusinessAccount, createBusinessAccountsBatch, createBusinessDrama, createBusinessDramasBatch, createBusinessSubTheater, createBusinessSubTheatersBatch, createBusinessTheater, createBusinessTheatersBatch, deleteBusinessAccount, deleteBusinessDrama, deleteBusinessSubTheater, deleteBusinessTheater, updateBusinessAccount, updateBusinessAccountCollector, updateBusinessDrama, updateBusinessSubTheater, updateBusinessTheater } from '../../services/assetsCenterService';
import { suggestRevenueCollectors } from '../../utils/revenueCollectors';
import { dataSource } from '../../services/dataSource';

interface BusinessDataTabProps {
  accounts: AccountBusinessItem[];
  theaters: TheaterBusinessItem[];
  subTheaters: SubTheaterBusinessItem[];
  dramas: DramaBusinessItem[];
  onUpdateAccounts: (accounts: AccountBusinessItem[]) => void;
  onUpdateTheaters: (theaters: TheaterBusinessItem[]) => void;
  onUpdateSubTheaters: (subTheaters: SubTheaterBusinessItem[]) => void;
  onUpdateDramas: (dramas: DramaBusinessItem[]) => void;
  onNavigateToDramaProfile?: (dramaId: string) => void;
  onManageQueryLinks?: () => void;
  onShowToast: (message: string) => void;
}

type BusinessSubCategory = 'accounts' | 'theaters' | 'sub_theaters' | 'dramas';

const ALL_ACCOUNT_STATUSES: AccountBusinessStatus[] = ['正常', '观察', '限流', '二限', '实名', '封禁', '停用', '注销'];
const ACCOUNT_STATUS_ORDER: Record<AccountBusinessStatus, number> = {
  '正常': 0, '观察': 1, '限流': 2, '二限': 3, '实名': 4, '封禁': 5, '停用': 6, '注销': 7,
};

const AdaptivePagination: React.FC<{ total: number; page: number; totalPages: number; onChange: (page: number) => void }> = ({ total, page, totalPages, onChange }) => {
  if (totalPages <= 1) return null;
  return <div className="px-4 py-3 border-t border-black/[0.06] flex items-center justify-between bg-slate-50/50">
    <div className="text-xs text-[#64748B]">共 <span className="font-bold text-[#1A1D2E]">{total}</span> 条，当前第 {page} / {totalPages} 页</div>
    <div className="flex items-center gap-1.5">
      <button onClick={() => onChange(Math.max(1, page - 1))} disabled={page === 1} className={`p-1.5 rounded-lg border text-xs transition-all ${page === 1 ? 'border-transparent text-slate-300 cursor-not-allowed' : 'border-black/[0.08] bg-white text-slate-700 hover:bg-slate-100 cursor-pointer'}`}><ChevronLeft className="w-4 h-4" /></button>
      {Array.from({ length: totalPages }, (_, index) => index + 1).map((item) => <button key={item} onClick={() => onChange(item)} className={`w-7 h-7 rounded-lg text-xs font-bold transition-all cursor-pointer ${item === page ? 'bg-[#1A1D2E] text-white shadow-2xs' : 'bg-white text-slate-700 border border-black/[0.08] hover:bg-slate-100'}`}>{item}</button>)}
      <button onClick={() => onChange(Math.min(totalPages, page + 1))} disabled={page === totalPages} className={`p-1.5 rounded-lg border text-xs transition-all ${page === totalPages ? 'border-transparent text-slate-300 cursor-not-allowed' : 'border-black/[0.08] bg-white text-slate-700 hover:bg-slate-100 cursor-pointer'}`}><ChevronRight className="w-4 h-4" /></button>
    </div>
  </div>;
};

export const BusinessDataTab: React.FC<BusinessDataTabProps> = ({
  accounts,
  theaters,
  subTheaters,
  dramas,
  onUpdateAccounts,
  onUpdateTheaters,
  onUpdateSubTheaters,
  onUpdateDramas,
  onNavigateToDramaProfile,
  onManageQueryLinks,
  onShowToast,
}) => {
  const latestAccounts = useRef(accounts);
  latestAccounts.current = accounts;
  const [collectorDefinitions, setCollectorDefinitions] = useState<RevenueCollectorDefinition[]>([]);
  const [collectorError, setCollectorError] = useState('');
  const [pendingCollectorAccounts, setPendingCollectorAccounts] = useState<Set<string>>(new Set());
  useEffect(() => {
    let active = true;
    getV2RevenueCollectorDefinitions().then(result => {
      if (active) { setCollectorDefinitions(result.definitions); setCollectorError(''); }
    }).catch(() => { if (active) setCollectorError('采集器列表读取失败'); });
    return () => { active = false; };
  }, []);

  const [activeCategory, setActiveCategory] = useState<BusinessSubCategory>('accounts');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTheaterFilter, setSelectedTheaterFilter] = useState('ALL');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>('ALL');
  const [selectedForDelete, setSelectedForDelete] = useState<Record<BusinessSubCategory, string[]>>({ accounts: [], theaters: [], sub_theaters: [], dramas: [] });
  const [batchDeleting, setBatchDeleting] = useState(false);

  const [currentPages, setCurrentPages] = useState<Record<BusinessSubCategory, number>>({ accounts: 1, theaters: 1, sub_theaters: 1, dramas: 1 });
  const [tableElement, setTableElement] = useState<HTMLDivElement | null>(null);
  const tableRowHeight = activeCategory === 'accounts' ? 74 : activeCategory === 'dramas' ? 62 : 54;
  const recordsPerPage = useAdaptivePageSize(tableElement, tableRowHeight, { minimum: 3, footerHeight: 76 });

  const setCurrentPage = (category: BusinessSubCategory, page: number) => {
    setCurrentPages((previous) => ({ ...previous, [category]: page }));
  };

  // Modals state
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<AccountBusinessItem | null>(null);
  const [isAccountBatchOpen, setIsAccountBatchOpen] = useState(false);
  const [isAccountFetchOpen, setIsAccountFetchOpen] = useState(false);

  const [isTheaterModalOpen, setIsTheaterModalOpen] = useState(false);
  const [editingTheater, setEditingTheater] = useState<TheaterBusinessItem | null>(null);
  const [isTheaterBatchOpen, setIsTheaterBatchOpen] = useState(false);

  const [isSubTheaterModalOpen, setIsSubTheaterModalOpen] = useState(false);
  const [editingSubTheater, setEditingSubTheater] = useState<SubTheaterBusinessItem | null>(null);
  const [isSubTheaterBatchOpen, setIsSubTheaterBatchOpen] = useState(false);

  const [isDramaModalOpen, setIsDramaModalOpen] = useState(false);
  const [editingDrama, setEditingDrama] = useState<DramaBusinessItem | null>(null);
  const [isDramaBatchOpen, setIsDramaBatchOpen] = useState(false);

  // Status styling map
  const getStatusBadgeStyle = (status: AccountBusinessStatus) => {
    switch (status) {
      case '正常':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case '观察':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case '限流':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case '二限':
        return 'bg-orange-50 text-orange-700 border-orange-200';
      case '实名':
        return 'bg-purple-50 text-purple-700 border-purple-200';
      case '封禁':
        return 'bg-rose-50 text-rose-700 border-rose-200';
      case '停用':
      default:
        return 'bg-slate-100 text-slate-600 border-slate-200';
    }
  };

  // Status counts for accounts
  const accountStatusCounts = useMemo(() => {
    const counts: Record<string, number> = { ALL: accounts.length };
    ALL_ACCOUNT_STATUSES.forEach(s => {
      counts[s] = accounts.filter(a => a.status === s).length;
    });
    return counts;
  }, [accounts]);

  const theaterAccountCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const account of accounts) {
      if (isAvailableAccountStatus(account.status)) {
        counts.set(account.theaterId, (counts.get(account.theaterId) || 0) + 1);
      }
    }
    return counts;
  }, [accounts]);

  // Account Handlers
  const handleSaveAccount = async (accountData: Omit<AccountBusinessItem, 'id'>, id?: string) => {
    if (id) {
      if (dataSource !== 'mock') {
        updateBusinessAccount(id, accountData).then((updated) => { onUpdateAccounts(accounts.map((item) => item.id === id ? updated : item)); onShowToast(`已保存账号「${updated.nickname}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '账号保存失败。'));
        return;
      }
      onUpdateAccounts(accounts.map(a => (a.id === id ? { ...accountData, id } : a)));
      onShowToast(`已保存账号「${accountData.nickname}」的资料`);
    } else {
      if (dataSource !== 'mock') {
        try {
          const created = await createBusinessAccount(accountData);
          onUpdateAccounts([created, ...accounts]);
          onShowToast(`已新增账号「${created.nickname}」`);
        } catch (error) {
          onShowToast(error instanceof Error ? error.message : '账号创建失败。');
        }
        return;
      }
      const newAcc: AccountBusinessItem = {
        ...accountData,
        id: `acc-${Date.now().toString().slice(-4)}`,
      };
      onUpdateAccounts([newAcc, ...accounts]);
      onShowToast(`已新增账号「${newAcc.nickname}」`);
    }
  };

  // Quick inline status change
  const handleQuickChangeAccountStatus = (id: string, newStatus: AccountBusinessStatus) => {
    const acc = accounts.find(a => a.id === id);
    if (!acc) return;
    if (dataSource !== 'mock') {
      const next = { ...acc, status: newStatus };
      updateBusinessAccount(id, next).then((updated) => { onUpdateAccounts(accounts.map((item) => item.id === id ? updated : item)); onShowToast(`已将账号「${acc.nickname}」状态切换为「${newStatus}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '账号状态修改失败。'));
      return;
    }
    onUpdateAccounts(accounts.map(a => (a.id === id ? { ...a, status: newStatus } : a)));
    onShowToast(`已将账号「${acc.nickname}」状态切换为「${newStatus}」`);
  };

  const handleQuickChangeCollector = async (account: AccountBusinessItem, collectorId: string) => {
    if (pendingCollectorAccounts.has(account.id)) return;
    setPendingCollectorAccounts(previous => new Set(previous).add(account.id));
    try {
      const updated = dataSource === 'mock' ? { ...account, revenueCollectorId: collectorId } : await updateBusinessAccountCollector(account.id, collectorId);
      onUpdateAccounts(latestAccounts.current.map(item => item.id === account.id ? updated : item));
      onShowToast('账号收益采集器已保存');
    } catch (error) { onShowToast(error instanceof Error ? error.message : '采集器修改失败。'); }
    finally { setPendingCollectorAccounts(previous => { const next = new Set(previous); next.delete(account.id); return next; }); }
  };

  const handleDeleteAccount = (id: string, name: string) => {
    if (dataSource !== 'mock') {
      deleteBusinessAccount(id).then(() => { onUpdateAccounts(accounts.filter((item) => item.id !== id)); onShowToast(`已删除账号「${name}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '账号删除失败。'));
      return;
    }
    onUpdateAccounts(accounts.filter(a => a.id !== id));
    onShowToast(`已移除账号「${name}」`);
  };

  const handleBatchImportAccounts = (imported: Omit<AccountBusinessItem, 'id'>[]) => {
    if (dataSource !== 'mock') {
      createBusinessAccountsBatch(imported).then((result) => {
        onUpdateAccounts([...result.items, ...accounts]);
        onShowToast(result.skippedNames.length
          ? `已导入 ${result.items.length} 个账号；已跳过 ${result.skippedNames.length} 个已存在账号。`
          : `已成功导入 ${result.items.length} 个账号`);
      }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '账号批量导入失败。'));
      return;
    }
    const newItems: AccountBusinessItem[] = imported.map((item, idx) => ({
      ...item,
      id: `acc-batch-${Date.now().toString().slice(-4)}-${idx}`,
    }));
    onUpdateAccounts([...newItems, ...accounts]);
    onShowToast(`成功批量导入 ${newItems.length} 个账号档案`);
  };

  // Theater Handlers
  const handleSaveTheater = async (theaterData: Omit<TheaterBusinessItem, 'id'>, id?: string) => {
    if (id) {
      if (dataSource !== 'mock') {
        try {
          const updated = await updateBusinessTheater(id, theaterData);
          onUpdateTheaters(theaters.map((item) => item.id === id ? updated : item));
          onUpdateAccounts(accounts.map(account => account.theaterId === id ? { ...account, theaterName: updated.name, revenueCollectorId: updated.revenueCollectorIds?.includes(account.revenueCollectorId || '') ? account.revenueCollectorId : '' } : account));
          onShowToast(`已保存剧场「${updated.name}」`);
        } catch (error) {
          onShowToast(error instanceof Error ? error.message : '剧场保存失败。');
        }
        return;
      }
      onUpdateTheaters(theaters.map(t => (t.id === id ? { ...theaterData, id, revenueCollectorsConfirmed: true } : t)));
      onUpdateAccounts(accounts.map(account => account.theaterId === id && !theaterData.revenueCollectorIds?.includes(account.revenueCollectorId || '') ? { ...account, revenueCollectorId: '' } : account));
      onShowToast(`已保存剧场「${theaterData.name}」参数配置`);
    } else {
      if (dataSource !== 'mock') {
        try {
          const created = await createBusinessTheater(theaterData);
          onUpdateTheaters([created, ...theaters]);
          onShowToast(`已新增剧场「${created.name}」`);
        } catch (error) {
          onShowToast(error instanceof Error ? error.message : '剧场创建失败。');
        }
        return;
      }
      const newTh: TheaterBusinessItem = {
        ...theaterData,
        id: `th-${Date.now().toString().slice(-4)}`,
      };
      onUpdateTheaters([...theaters, newTh]);
      onShowToast(`已新增剧场「${newTh.name}」`);
    }
  };

  const handleDeleteTheater = async (id: string, name: string) => {
    if (dataSource !== 'mock') {
      try {
        await deleteBusinessTheater(id);
        onUpdateTheaters(theaters.filter((item) => item.id !== id));
        onShowToast(`已删除剧场「${name}」`);
      } catch (error) {
        onShowToast(error instanceof Error ? error.message : '剧场删除失败。');
      }
      return;
    }
    onUpdateTheaters(theaters.filter(t => t.id !== id));
    onShowToast(`已删除剧场「${name}」`);
  };

  const handleBatchImportTheaters = async (imported: Omit<TheaterBusinessItem, 'id'>[]) => {
    if (dataSource !== 'mock') {
      try {
        const result = await createBusinessTheatersBatch(imported);
        onUpdateTheaters([...theaters, ...result.items]);
        onShowToast(result.skippedNames.length
          ? `已导入 ${result.items.length} 个剧场；已跳过 ${result.skippedNames.length} 个已存在剧场。`
          : `已成功导入 ${result.items.length} 个剧场`);
      } catch (error) {
        onShowToast(error instanceof Error ? error.message : '剧场批量导入失败。');
      }
      return;
    }
    const newItems: TheaterBusinessItem[] = imported.map((item, idx) => ({
      ...item,
      id: `th-batch-${Date.now().toString().slice(-4)}-${idx}`,
    }));
    onUpdateTheaters([...theaters, ...newItems]);
    onShowToast(`成功批量导入 ${newItems.length} 个剧场档案`);
  };

  // SubTheater Handlers
  const handleSaveSubTheater = async (subData: Omit<SubTheaterBusinessItem, 'id'>, id?: string) => {
    if (id) {
      if (dataSource !== 'mock') {
        updateBusinessSubTheater(id, subData).then((updated) => { onUpdateSubTheaters(subTheaters.map((item) => item.id === id ? updated : item)); onShowToast(`已保存子剧场「${updated.name}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '子剧场保存失败。'));
        return;
      }
      onUpdateSubTheaters(subTheaters.map(st => (st.id === id ? { ...subData, id } : st)));
      onShowToast(`已保存子剧场「${subData.name}」配置`);
    } else {
      if (dataSource !== 'mock') {
        try {
          const created = await createBusinessSubTheater(subData);
          onUpdateSubTheaters([...subTheaters, created]);
          onShowToast(`已新增子剧场「${created.name}」`);
        } catch (error) {
          onShowToast(error instanceof Error ? error.message : '子剧场创建失败。');
        }
        return;
      }
      const newSub: SubTheaterBusinessItem = {
        ...subData,
        id: `sub-${Date.now().toString().slice(-4)}`,
      };
      onUpdateSubTheaters([...subTheaters, newSub]);
      onShowToast(`已新增子剧场「${newSub.name}」`);
    }
  };

  const handleDeleteSubTheater = (id: string, name: string) => {
    if (dataSource !== 'mock') {
      deleteBusinessSubTheater(id).then(() => { onUpdateSubTheaters(subTheaters.filter((item) => item.id !== id)); onShowToast(`已删除子剧场「${name}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '子剧场删除失败。'));
      return;
    }
    onUpdateSubTheaters(subTheaters.filter(st => st.id !== id));
    onShowToast(`已删除子剧场「${name}」`);
  };

  const handleBatchImportSubTheaters = async (imported: Omit<SubTheaterBusinessItem, 'id'>[]) => {
    if (dataSource !== 'mock') {
      try {
        const result = await createBusinessSubTheatersBatch(imported);
        onUpdateSubTheaters([...subTheaters, ...result.items]);
        onShowToast(result.skippedNames.length
          ? `已导入 ${result.items.length} 个子剧场；已跳过 ${result.skippedNames.length} 个同名子剧场。`
          : `已成功导入 ${result.items.length} 个子剧场`);
      } catch (error) {
        onShowToast(error instanceof Error ? error.message : '子剧场批量导入失败。');
      }
      return;
    }
    const newItems: SubTheaterBusinessItem[] = imported.map((item, idx) => ({
      ...item,
      id: `sub-batch-${Date.now().toString().slice(-4)}-${idx}`,
    }));
    onUpdateSubTheaters([...subTheaters, ...newItems]);
    onShowToast(`成功批量导入 ${newItems.length} 个子剧场档案`);
  };

  // Drama Handlers
  const handleSaveDrama = (
    dramaData: { currentName: string; historyNames: string[]; theaterName: string; theaterId: string; isUsedInBusiness?: boolean },
    id?: string
  ) => {
    if (dataSource !== 'mock') {
      if (id) updateBusinessDrama(id, dramaData).then((updated) => { onUpdateDramas(dramas.map((item) => item.id === id ? updated : item)); onShowToast(`已保存剧集「${updated.currentName}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '剧集保存失败。'));
      else createBusinessDrama(dramaData).then((created) => { onUpdateDramas([created, ...dramas]); onShowToast(`已新增剧集「${created.currentName}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '剧集创建失败。'));
      return;
    }
    if (id) {
      onUpdateDramas(
        dramas.map(d =>
          d.id === id
            ? {
                ...d,
                currentName: dramaData.currentName,
                historyNames: dramaData.historyNames,
                theaterName: dramaData.theaterName,
                theaterId: dramaData.theaterId,
              }
            : d
        )
      );
      onShowToast(`已更新剧集「${dramaData.currentName}」名称与历史剧名`);
    } else {
      const newDr: DramaBusinessItem = {
        id: `drama-${Date.now().toString().slice(-4)}`,
        currentName: dramaData.currentName,
        historyNames: dramaData.historyNames,
        theaterId: dramaData.theaterId,
        theaterName: dramaData.theaterName,
        createdAt: new Date().toISOString().slice(0, 10),
        hasContentProfile: false,
        isUsedInBusiness: false,
      };
      onUpdateDramas([newDr, ...dramas]);
      onShowToast(`已创建新剧集档案「${newDr.currentName}」`);
    }
  };

  const handleDeleteDrama = (id: string, name: string) => {
    if (dataSource !== 'mock') { deleteBusinessDrama(id).then(() => { onUpdateDramas(dramas.filter((item) => item.id !== id)); onShowToast(`已删除剧集「${name}」`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '剧集删除失败。')); return; }
    onUpdateDramas(dramas.filter(d => d.id !== id));
    onShowToast(`已删除剧集「${name}」`);
  };

  const toggleDeleteSelection = (id: string, checked: boolean) => {
    setSelectedForDelete((current) => {
      const ids = current[activeCategory];
      return { ...current, [activeCategory]: checked ? [...new Set([...ids, id])] : ids.filter((item) => item !== id) };
    });
  };

  const currentFilteredIds = () => {
    switch (activeCategory) {
      case 'accounts': return filteredAccounts.map((item) => item.id);
      case 'theaters': return filteredTheaters.map((item) => item.id);
      case 'sub_theaters': return filteredSubTheaters.map((item) => item.id);
      case 'dramas': return filteredDramas.map((item) => item.id);
    }
  };

  const toggleFilteredSelection = (checked: boolean) => {
    const visibleIds = currentFilteredIds();
    setSelectedForDelete((current) => ({
      ...current,
      [activeCategory]: checked ? [...new Set([...current[activeCategory], ...visibleIds])] : current[activeCategory].filter((id) => !visibleIds.includes(id)),
    }));
  };

  const handleBatchDelete = async () => {
    const ids = selectedForDelete[activeCategory];
    if (!ids.length || batchDeleting) return;
    const categoryNames: Record<BusinessSubCategory, string> = { accounts: '账号', theaters: '剧场', sub_theaters: '子剧场', dramas: '剧集' };
    if (!window.confirm(`确定批量删除选中的 ${ids.length} 条${categoryNames[activeCategory]}吗？有业务关联的记录会被系统拒绝删除，不会级联删除其他资料。`)) return;
    setBatchDeleting(true);
    const removeIds: string[] = [];
    const failed: string[] = [];
    const items = activeCategory === 'accounts' ? accounts : activeCategory === 'theaters' ? theaters : activeCategory === 'sub_theaters' ? subTheaters : dramas;
    for (const id of ids) {
      const item = items.find((entry) => entry.id === id);
      if (!item) { removeIds.push(id); continue; }
      const name = activeCategory === 'accounts' ? (item as AccountBusinessItem).nickname : activeCategory === 'theaters' ? (item as TheaterBusinessItem).name : activeCategory === 'sub_theaters' ? (item as SubTheaterBusinessItem).name : (item as DramaBusinessItem).currentName;
      try {
        if (dataSource !== 'mock') {
          if (activeCategory === 'accounts') await deleteBusinessAccount(id);
          else if (activeCategory === 'theaters') await deleteBusinessTheater(id);
          else if (activeCategory === 'sub_theaters') await deleteBusinessSubTheater(id);
          else await deleteBusinessDrama(id);
        }
        removeIds.push(id);
      } catch (error) {
        failed.push(`${name}：${error instanceof Error ? error.message : '删除失败'}`);
      }
    }
    if (removeIds.length) {
      if (activeCategory === 'accounts') onUpdateAccounts(accounts.filter((item) => !removeIds.includes(item.id)));
      else if (activeCategory === 'theaters') onUpdateTheaters(theaters.filter((item) => !removeIds.includes(item.id)));
      else if (activeCategory === 'sub_theaters') onUpdateSubTheaters(subTheaters.filter((item) => !removeIds.includes(item.id)));
      else onUpdateDramas(dramas.filter((item) => !removeIds.includes(item.id)));
    }
    setSelectedForDelete((current) => ({ ...current, [activeCategory]: failed.length ? ids.filter((id) => !removeIds.includes(id)) : [] }));
    setBatchDeleting(false);
    onShowToast(failed.length ? `成功删除 ${removeIds.length} 条，${failed.length} 条未删除：${failed.slice(0, 2).join('；')}${failed.length > 2 ? '；…' : ''}` : `已批量删除 ${removeIds.length} 条${categoryNames[activeCategory]}`);
  };

  const handleBatchImportDramas = (
    imported: { currentName: string; theaterName: string; theaterId: string; historyNames: string[] }[]
  ) => {
    if (dataSource !== 'mock') { createBusinessDramasBatch(imported.map((item) => ({ ...item, createdAt: '', hasContentProfile: false }))).then((result) => { onUpdateDramas([...result.items, ...dramas]); onShowToast(result.skippedNames.length ? `已导入 ${result.items.length} 个剧集；已跳过 ${result.skippedNames.length} 个重复剧名。` : `已成功导入 ${result.items.length} 个剧集`); }).catch((error: unknown) => onShowToast(error instanceof Error ? error.message : '剧集批量导入失败。')); return; }
    const newItems: DramaBusinessItem[] = imported.map((item, idx) => ({
      id: `drama-batch-${Date.now().toString().slice(-4)}-${idx}`,
      currentName: item.currentName,
      historyNames: item.historyNames,
      theaterId: item.theaterId,
      theaterName: item.theaterName,
      createdAt: new Date().toISOString().slice(0, 10),
      hasContentProfile: false,
      isUsedInBusiness: false,
    }));
    onUpdateDramas([...newItems, ...dramas]);
    onShowToast(`成功批量导入 ${newItems.length} 部剧集档案`);
  };

  // Filtered lists
  const filteredAccounts = useMemo(() => {
    return accounts.filter(acc => {
      const matchSearch =
        !searchTerm ||
        acc.nickname.toLowerCase().includes(searchTerm.toLowerCase()) ||
        acc.accountId.toLowerCase().includes(searchTerm.toLowerCase()) ||
        acc.subTheaterName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        acc.notes.toLowerCase().includes(searchTerm.toLowerCase());
      const matchTheater = selectedTheaterFilter === 'ALL' || acc.theaterName === selectedTheaterFilter;
      const matchStatus = selectedStatusFilter === 'ALL' || acc.status === selectedStatusFilter;
      return matchSearch && matchTheater && matchStatus;
    }).sort((left, right) => ACCOUNT_STATUS_ORDER[left.status] - ACCOUNT_STATUS_ORDER[right.status]);
  }, [accounts, searchTerm, selectedTheaterFilter, selectedStatusFilter]);

  const filteredTheaters = useMemo(() => {
    return theaters.filter(th => {
      return !searchTerm || th.name.toLowerCase().includes(searchTerm.toLowerCase());
    });
  }, [theaters, searchTerm]);

  const filteredSubTheaters = useMemo(() => {
    return subTheaters.filter(st => {
      const matchSearch =
        !searchTerm ||
        st.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        st.theaterName.toLowerCase().includes(searchTerm.toLowerCase());
      const matchTheater = selectedTheaterFilter === 'ALL' || st.theaterName === selectedTheaterFilter;
      return matchSearch && matchTheater;
    });
  }, [subTheaters, searchTerm, selectedTheaterFilter]);

  // Drama search logic: Matches currentName OR any historyNames, but always displays currentName
  const filteredDramas = useMemo(() => {
    return dramas.map(dr => {
      const matchCurrent = dr.currentName.toLowerCase().includes(searchTerm.toLowerCase());
      const matchedHistory = dr.historyNames.find(h =>
        h.toLowerCase().includes(searchTerm.toLowerCase())
      );
      const isMatched = !searchTerm || matchCurrent || !!matchedHistory;
      const matchTheater = selectedTheaterFilter === 'ALL' || dr.theaterName === selectedTheaterFilter;

      return {
        ...dr,
        isMatched: isMatched && matchTheater,
        matchedHistoryHint: !matchCurrent && matchedHistory ? matchedHistory : null,
      };
    }).filter(dr => dr.isMatched);
  }, [dramas, searchTerm, selectedTheaterFilter]);

  const totalPages = (count: number) => Math.max(1, Math.ceil(count / recordsPerPage));
  const paginatedAccounts: AccountBusinessItem[] = filteredAccounts.slice((currentPages.accounts - 1) * recordsPerPage, currentPages.accounts * recordsPerPage);
  const paginatedTheaters: TheaterBusinessItem[] = filteredTheaters.slice((currentPages.theaters - 1) * recordsPerPage, currentPages.theaters * recordsPerPage);
  const paginatedSubTheaters: SubTheaterBusinessItem[] = filteredSubTheaters.slice((currentPages.sub_theaters - 1) * recordsPerPage, currentPages.sub_theaters * recordsPerPage);
  const paginatedDramas: (DramaBusinessItem & { isMatched: boolean; matchedHistoryHint: string | null })[] = filteredDramas.slice((currentPages.dramas - 1) * recordsPerPage, currentPages.dramas * recordsPerPage);

  useEffect(() => {
    setCurrentPages((previous) => ({
      accounts: Math.min(previous.accounts, totalPages(filteredAccounts.length)),
      theaters: Math.min(previous.theaters, totalPages(filteredTheaters.length)),
      sub_theaters: Math.min(previous.sub_theaters, totalPages(filteredSubTheaters.length)),
      dramas: Math.min(previous.dramas, totalPages(filteredDramas.length)),
    }));
  }, [filteredAccounts.length, filteredDramas.length, filteredSubTheaters.length, filteredTheaters.length, recordsPerPage]);

  return (
    <div className="space-y-6">
      {/* 1. Sub Category Selector Tabs & Counts */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-black/[0.06]">
        <div className="flex items-center gap-1.5 p-1 bg-slate-100/90 rounded-2xl border border-black/[0.04] w-fit">
          <button
            onClick={() => {
              setActiveCategory('accounts');
              setSearchTerm('');
            }}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeCategory === 'accounts'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>账号管理</span>
            <span className="px-1.5 py-0.2 rounded-full bg-slate-100 text-[#1A1D2E] text-[10px] font-mono font-bold">
              {accounts.length}
            </span>
          </button>

          <button
            onClick={() => {
              setActiveCategory('theaters');
              setSearchTerm('');
            }}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeCategory === 'theaters'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            <Building2 className="w-3.5 h-3.5" />
            <span>剧场管理</span>
            <span className="px-1.5 py-0.2 rounded-full bg-slate-100 text-[#1A1D2E] text-[10px] font-mono font-bold">
              {theaters.length}
            </span>
          </button>

          <button
            onClick={() => {
              setActiveCategory('sub_theaters');
              setSearchTerm('');
            }}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeCategory === 'sub_theaters'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            <GitFork className="w-3.5 h-3.5" />
            <span>子剧场管理</span>
            <span className="px-1.5 py-0.2 rounded-full bg-slate-100 text-[#1A1D2E] text-[10px] font-mono font-bold">
              {subTheaters.length}
            </span>
          </button>

          <button
            onClick={() => {
              setActiveCategory('dramas');
              setSearchTerm('');
              setCurrentPage('dramas', 1);
            }}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              activeCategory === 'dramas'
                ? 'bg-white text-[#1A1D2E] shadow-sm'
                : 'text-[#64748B] hover:text-[#1A1D2E]'
            }`}
          >
            <Film className="w-3.5 h-3.5" />
            <span>剧集档案</span>
            <span className="px-1.5 py-0.2 rounded-full bg-slate-100 text-[#1A1D2E] text-[10px] font-mono font-bold">
              {dramas.length}
            </span>
          </button>
        </div>

        {/* Global Operations for Active SubCategory */}
        <div className="flex flex-wrap items-center justify-end gap-2">
          {selectedForDelete[activeCategory].length > 0 && (
            <button onClick={() => void handleBatchDelete()} disabled={batchDeleting} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-rose-200 bg-rose-50 text-rose-700 text-xs font-semibold hover:bg-rose-100 disabled:opacity-50">
              <Trash2 className="w-3.5 h-3.5" />
              {batchDeleting ? '正在删除…' : `批量删除 (${selectedForDelete[activeCategory].length})`}
            </button>
          )}
          {currentFilteredIds().length > 0 && (
            <label className="inline-flex items-center gap-1.5 px-2 text-xs text-slate-600 whitespace-nowrap">
              <input type="checkbox" checked={currentFilteredIds().every((id) => selectedForDelete[activeCategory].includes(id))} onChange={(event) => toggleFilteredSelection(event.target.checked)} className="accent-rose-600" />
              全选筛选结果
            </label>
          )}
          {activeCategory === 'accounts' && (
            <>
              <button
                onClick={() => setIsAccountBatchOpen(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
                <span>批量导入账号</span>
              </button>
              <button type="button" data-testid="fetch-vcat-accounts" disabled={dataSource !== 'v2'} onClick={() => setIsAccountFetchOpen(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs disabled:opacity-40">
                <Download className="w-3.5 h-3.5 text-slate-500" /><span>获取账号</span>
              </button>
              <button
                onClick={() => {
                  setEditingAccount(null);
                  setIsAccountModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] text-xs font-bold shadow-xs transition-all cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>新增账号</span>
              </button>
            </>
          )}

          {activeCategory === 'theaters' && (
            <>
              <button
                onClick={() => setIsTheaterBatchOpen(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
                <span>批量导入剧场</span>
              </button>
              <button
                onClick={() => {
                  setEditingTheater(null);
                  setIsTheaterModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] text-xs font-bold shadow-xs transition-all cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>新增剧场</span>
              </button>
            </>
          )}

          {activeCategory === 'sub_theaters' && (
            <>
              <button
                onClick={() => setIsSubTheaterBatchOpen(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
                <span>批量导入子剧场</span>
              </button>
              <button
                onClick={() => {
                  setEditingSubTheater(null);
                  setIsSubTheaterModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] text-xs font-bold shadow-xs transition-all cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>新增子剧场</span>
              </button>
            </>
          )}

          {activeCategory === 'dramas' && (
            <>
              <button
                onClick={() => setIsDramaBatchOpen(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-black/[0.08] hover:bg-slate-50 text-[#1A1D2E] text-xs font-semibold shadow-2xs transition-all cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
                <span>批量导入剧集</span>
              </button>
              <button
                onClick={() => {
                  setEditingDrama(null);
                  setIsDramaModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] text-xs font-bold shadow-xs transition-all cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>新增剧集</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* 2. Filter & Search Controls */}
      <div className="space-y-3">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Status Tabs for Accounts */}
          {activeCategory === 'accounts' ? (
            <div className="flex items-center gap-1 p-1 bg-slate-100/90 rounded-2xl border border-black/[0.04] w-fit overflow-x-auto">
              <button
                type="button"
                onClick={() => setSelectedStatusFilter('ALL')}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                  selectedStatusFilter === 'ALL'
                    ? 'bg-white text-[#1A1D2E] shadow-sm'
                    : 'text-[#64748B] hover:text-[#1A1D2E]'
                }`}
              >
                全部状态 ({accounts.length})
              </button>
              {ALL_ACCOUNT_STATUSES.map(s => {
                const count = accountStatusCounts[s] || 0;
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSelectedStatusFilter(s)}
                    className={`px-2.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 ${
                      selectedStatusFilter === s
                        ? 'bg-white text-[#1A1D2E] shadow-sm'
                        : 'text-[#64748B] hover:text-[#1A1D2E]'
                    }`}
                  >
                    <span>{s}</span>
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
                        selectedStatusFilter === s
                          ? 'bg-slate-100 text-[#1A1D2E] font-bold'
                          : 'bg-black/[0.04] text-slate-500'
                      }`}
                    >
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div />
          )}

          {/* Search and Theater filter */}
          <div className="flex items-center gap-2">
            {(activeCategory === 'accounts' || activeCategory === 'sub_theaters' || activeCategory === 'dramas') && (
              <div className="flex items-center gap-1.5 text-xs text-[#64748B]">
                <span className="text-[11px] font-semibold text-slate-400">剧场:</span>
                <select
                  value={selectedTheaterFilter}
                  onChange={e => {
                    setSelectedTheaterFilter(e.target.value);
                    setCurrentPage(activeCategory, 1);
                  }}
                  className="px-2.5 py-1.5 rounded-xl border border-black/[0.08] bg-white text-xs font-semibold text-[#1A1D2E] focus:outline-none"
                >
                  <option value="ALL">全部剧场</option>
                  {theaters.map(t => (
                    <option key={t.id} value={t.name}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="relative w-48 sm:w-64">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder={
                  activeCategory === 'accounts'
                    ? '搜索账号昵称、ID、备注...'
                    : activeCategory === 'theaters'
                    ? '搜索剧场名称...'
                    : activeCategory === 'sub_theaters'
                    ? '搜索子剧场或剧场...'
                    : '搜索当前剧名或历史别名...'
                }
                value={searchTerm}
                onChange={e => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(activeCategory, 1);
                }}
                className="w-full pl-8 pr-3 py-1.5 rounded-xl border border-black/[0.08] bg-white text-xs font-medium text-[#1A1D2E] focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20"
              />
            </div>
          </div>
        </div>
      </div>

      {/* 3. Main Data Content Area */}
      
      {/* 3.1 ACCOUNTS TABLE */}
      {activeCategory === 'accounts' && (
        <div ref={setTableElement} className="bg-white rounded-2xl border border-black/[0.06] shadow-xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/90 text-[#64748B] font-bold border-b border-black/[0.06]">
                <tr>
                  <th className="py-3 px-2 w-9" aria-label="选择" />
                  <th className="py-3 px-4">账号昵称 / 平台ID</th>
                  <th className="py-3 px-4">所属剧场 / 子剧场</th>
                  <th className="py-3 px-4">账号状态 (点击切换)</th>
                  <th className="py-3 px-4">收益采集器（点击切换）</th>
                  <th className="py-3 px-4">备注说明</th>
                  <th className="py-3 px-4 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/[0.04] text-slate-700">
                {filteredAccounts.length > 0 ? (
                  paginatedAccounts.map(acc => {
                    const availableCollectors = collectorDefinitions.filter(item => theaters.find(theater => theater.id === acc.theaterId)?.revenueCollectorIds?.includes(item.id));
                    return (
                      <tr key={acc.id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3 px-2"><input type="checkbox" aria-label={`选择账号 ${acc.nickname}`} checked={selectedForDelete.accounts.includes(acc.id)} onChange={(event) => toggleDeleteSelection(acc.id, event.target.checked)} className="accent-rose-600" /></td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <AccountAvatar name={acc.nickname} url={acc.avatarUrl} />
                            <div className="min-w-0">
                              <div className="truncate font-bold text-[#1A1D2E]" title={acc.nickname}>{acc.nickname}</div>
                              <div data-testid="business-account-platform-id" className="truncate whitespace-nowrap text-[11px] leading-4 font-mono text-[#64748B]" title={acc.accountId}>{acc.accountId}</div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="font-semibold text-[#1A1D2E]">{acc.theaterName}</div>
                          <div className="text-[11px] text-[#64748B]">{acc.subTheaterName || '—'}</div>
                        </td>
                        <td className="py-3 px-4">
                          {/* Direct Inline Status Switcher */}
                          <div className="relative inline-block">
                            <select
                              value={acc.status}
                              onChange={e => handleQuickChangeAccountStatus(acc.id, e.target.value as AccountBusinessStatus)}
                              className={`appearance-none px-2.5 py-1 pr-6 rounded-lg text-[11px] font-bold border cursor-pointer focus:outline-none ${getStatusBadgeStyle(acc.status)}`}
                            >
                              {ALL_ACCOUNT_STATUSES.map(s => (
                                <option key={s} value={s}>
                                  {s}
                                </option>
                              ))}
                            </select>
                            <ChevronDown className="w-3 h-3 text-slate-400 absolute right-1.5 top-2 pointer-events-none" />
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <select aria-label={`${acc.nickname}收益采集器`} value={acc.revenueCollectorId || ''} onChange={event => void handleQuickChangeCollector(acc, event.target.value)} disabled={!!collectorError || pendingCollectorAccounts.has(acc.id) || availableCollectors.length === 0} title={collectorError || '选择后立即保存'} className="max-w-44 px-2.5 py-1 rounded-lg text-[11px] font-bold border border-slate-200 bg-slate-50 cursor-pointer disabled:opacity-50">
                            <option value="">{collectorError || (availableCollectors.length ? '待配置' : '剧场未配置采集器')}</option>
                            {acc.revenueCollectorId && !availableCollectors.some(item => item.id === acc.revenueCollectorId) && <option value={acc.revenueCollectorId}>采集器暂不可用</option>}
                            {availableCollectors.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
                          </select>
                        </td>
                        <td className="py-3 px-4 max-w-xs">
                          <span className="text-[11px] text-slate-600 line-clamp-1" title={acc.notes}>
                            {acc.notes || '—'}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => {
                              setEditingAccount(acc);
                              setIsAccountModalOpen(true);
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                          >
                            <Edit2 className="w-3 h-3" />
                            <span>编辑</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-slate-400">
                      未找到符合条件的账号记录
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <AdaptivePagination total={filteredAccounts.length} page={currentPages.accounts} totalPages={totalPages(filteredAccounts.length)} onChange={(page) => setCurrentPage('accounts', page)} />
        </div>
      )}

      {/* 3.2 THEATERS TABLE */}
      {activeCategory === 'theaters' && (
        <div ref={setTableElement} className="bg-white rounded-2xl border border-black/[0.06] shadow-xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/90 text-[#64748B] font-bold border-b border-black/[0.06]">
                <tr>
                  <th className="py-3 px-2 w-9" aria-label="选择" />
                  <th className="py-3 px-4">剧场名称</th>
                  <th className="py-3 px-4">收益采集器</th>
                  <th className="py-3 px-4">默认分成比例</th>
                  <th className="py-3 px-4">默认税率</th>
                  <th className="py-3 px-4">下属子剧场</th>
                  <th className="py-3 px-4">关联剧集数</th>
                  <th className="py-3 px-4 whitespace-nowrap">关联账号</th>
                  <th className="py-3 px-4">启用状态</th>
                  <th className="py-3 px-4 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/[0.04] text-slate-700">
                {filteredTheaters.length > 0 ? (
                  paginatedTheaters.map(th => (
                    <tr key={th.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-2"><input type="checkbox" aria-label={`选择剧场 ${th.name}`} checked={selectedForDelete.theaters.includes(th.id)} onChange={(event) => toggleDeleteSelection(th.id, event.target.checked)} className="accent-rose-600" /></td>
                      <td className="py-3 px-4 font-bold text-[#1A1D2E]">
                        {th.name}
                      </td>
                      <td className="py-3 px-4"><button className="text-left text-[11px] text-slate-600 hover:text-slate-900 cursor-pointer" onClick={() => { setEditingTheater(th); setIsTheaterModalOpen(true); }}>{th.revenueCollectorsConfirmed ? (th.revenueCollectorIds?.map(id => collectorDefinitions.find(item => item.id === id)?.name || id).join('、') || '未配置') : (suggestRevenueCollectors(th.name, collectorDefinitions).length ? '已匹配，待复核' : '待配置')}</button></td>
                      <td className="py-3 px-4 font-mono font-bold text-emerald-700">
                        {th.defaultCommissionRate}%
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-600">
                        {th.defaultTaxRate}%
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-600">
                        {th.subTheatersCount || 0} 个
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-600">
                        {th.dramasCount || 0} 部
                      </td>
                      <td aria-label={`${th.name}关联账号`} className="py-3 px-4 font-mono text-slate-600 whitespace-nowrap">
                        {theaterAccountCounts.get(th.id) || 0} 个
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold border ${
                          th.status === '启用'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-slate-100 text-slate-600 border-slate-200'
                        }`}>
                          {th.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => {
                            setEditingTheater(th);
                            setIsTheaterModalOpen(true);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          <Edit2 className="w-3 h-3" />
                          <span>编辑</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={10} className="py-12 text-center text-slate-400">
                      未找到符合条件的剧场记录
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <AdaptivePagination total={filteredTheaters.length} page={currentPages.theaters} totalPages={totalPages(filteredTheaters.length)} onChange={(page) => setCurrentPage('theaters', page)} />
        </div>
      )}

      {/* 3.3 SUB-THEATERS TABLE */}
      {activeCategory === 'sub_theaters' && (
        <div ref={setTableElement} className="bg-white rounded-2xl border border-black/[0.06] shadow-xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/90 text-[#64748B] font-bold border-b border-black/[0.06]">
                <tr>
                  <th className="py-3 px-2 w-9" aria-label="选择" />
                  <th className="py-3 px-4">子剧场名称</th>
                  <th className="py-3 px-4">所属主剧场</th>
                  <th className="py-3 px-4">实际生效分成</th>
                  <th className="py-3 px-4">继承 / 独立分成</th>
                  <th className="py-3 px-4">已绑定账号数</th>
                  <th className="py-3 px-4">状态</th>
                  <th className="py-3 px-4 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/[0.04] text-slate-700">
                {filteredSubTheaters.length > 0 ? (
                  paginatedSubTheaters.map(st => (
                    <tr key={st.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-2"><input type="checkbox" aria-label={`选择子剧场 ${st.name}`} checked={selectedForDelete.sub_theaters.includes(st.id)} onChange={(event) => toggleDeleteSelection(st.id, event.target.checked)} className="accent-rose-600" /></td>
                      <td className="py-3 px-4 font-bold text-[#1A1D2E]">
                        {st.name}
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-800">
                        {st.theaterName}
                      </td>
                      <td className="py-3 px-4 font-mono font-bold text-emerald-700">
                        {st.commissionRate}%
                      </td>
                      <td className="py-3 px-4">
                        {st.isCommissionOverridden ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                            手动覆盖分成
                          </span>
                        ) : (
                          <span className="text-[11px] text-slate-500">
                            继承剧场默认
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-600">
                        {(st.boundAccountsCount || 0) > 0 ? (
                          <span className="text-slate-800 font-semibold flex items-center gap-1">
                            <Lock className="w-3 h-3 text-slate-400" />
                            {st.boundAccountsCount} 个账号
                          </span>
                        ) : (
                          <span className="text-slate-400">0 个 (可改所属剧场)</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold border ${
                          st.status === '启用'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-slate-100 text-slate-600 border-slate-200'
                        }`}>
                          {st.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => {
                            setEditingSubTheater(st);
                            setIsSubTheaterModalOpen(true);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          <Edit2 className="w-3 h-3" />
                          <span>编辑</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-slate-400">
                      未找到符合条件的子剧场记录
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <AdaptivePagination total={filteredSubTheaters.length} page={currentPages.sub_theaters} totalPages={totalPages(filteredSubTheaters.length)} onChange={(page) => setCurrentPage('sub_theaters', page)} />
        </div>
      )}

      {/* 3.4 DRAMAS TABLE (With Pagination & History Names display) */}
      {activeCategory === 'dramas' && (
        <div ref={setTableElement} className="bg-white rounded-2xl border border-black/[0.06] shadow-xs overflow-hidden flex flex-col">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50/90 text-[#64748B] font-bold border-b border-black/[0.06]">
                <tr>
                  <th className="py-3 px-2 w-9" aria-label="选择" />
                  <th className="py-3 px-4">当前生效剧名</th>
                  <th className="py-3 px-4">所属剧场</th>
                  <th className="py-3 px-4">历史剧名沉淀 (支持搜索/切换)</th>
                  <th className="py-3 px-4">录入时间</th>
                  <th className="py-3 px-4">资料库建档</th>
                  <th className="py-3 px-4 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/[0.04] text-slate-700">
                {paginatedDramas.length > 0 ? (
                  paginatedDramas.map(dr => (
                    <tr key={dr.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3 px-2"><input type="checkbox" aria-label={`选择剧集 ${dr.currentName}`} checked={selectedForDelete.dramas.includes(dr.id)} onChange={(event) => toggleDeleteSelection(dr.id, event.target.checked)} className="accent-rose-600" /></td>
                      <td className="py-3 px-4">
                        <div className="font-bold text-[#1A1D2E] text-xs">
                          {dr.currentName}
                        </div>
                        {dr.matchedHistoryHint && (
                          <div className="text-[10px] text-amber-700 font-medium mt-0.5">
                            已匹配历史剧名: {dr.matchedHistoryHint}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-800">
                        {dr.theaterName}
                      </td>
                      <td className="py-3 px-4 max-w-sm">
                        {dr.historyNames.length > 0 ? (
                          <div className="flex flex-wrap items-center gap-1.5">
                            {dr.historyNames.map((h, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[11px] border border-black/[0.04]"
                                title="历史曾用名"
                              >
                                {h}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-[11px] text-slate-400">无历史别名</span>
                        )}
                      </td>
                      <td className="py-3 px-4 font-mono text-[#64748B] text-[11px]">
                        {dr.createdAt}
                      </td>
                      <td className="py-3 px-4">
                        {dr.hasContentProfile ? (
                          <button
                            onClick={() => onNavigateToDramaProfile && onNavigateToDramaProfile(dr.id)}
                            className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 hover:text-emerald-800 cursor-pointer"
                          >
                            <CheckCircle className="w-3.5 h-3.5" />
                            <span>资料库已就绪</span>
                            <ArrowRight className="w-3 h-3" />
                          </button>
                        ) : (
                          <span className="text-[11px] text-slate-400">待建档</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => {
                            setEditingDrama(dr);
                            setIsDramaModalOpen(true);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                        >
                          <Edit2 className="w-3 h-3" />
                          <span>改名 / 维护</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="py-12 text-center text-slate-400">
                      未找到符合条件的剧集档案
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <AdaptivePagination total={filteredDramas.length} page={currentPages.dramas} totalPages={totalPages(filteredDramas.length)} onChange={(page) => setCurrentPage('dramas', page)} />
        </div>
      )}

      {/* Modals Mounting */}
      {isAccountFetchOpen && <AccountFetchModal theaters={theaters} onClose={() => setIsAccountFetchOpen(false)} onTheaterCreated={theater => onUpdateTheaters([...theaters.filter(t => t.id !== theater.id),theater])} onImported={async () => { const response = await getV2Accounts(); onUpdateAccounts(response.items.map(toBusinessAccount)); }} />}

      <AccountModal
        isOpen={isAccountModalOpen}
        onClose={() => {
          setIsAccountModalOpen(false);
          setEditingAccount(null);
        }}
        account={editingAccount}
        collectorDefinitions={collectorDefinitions}
        collectorError={collectorError}
        theaters={theaters.filter((item) => item.status === '启用' || item.id === editingAccount?.theaterId)}
        subTheaters={subTheaters.filter((item) => item.status === '启用')}
        onSave={handleSaveAccount}
        onDelete={handleDeleteAccount}
      />

      <AccountBatchImportModal
        isOpen={isAccountBatchOpen}
        onClose={() => setIsAccountBatchOpen(false)}
        theaters={theaters.filter((item) => item.status === '启用')}
        onBatchImport={handleBatchImportAccounts}
      />

      <TheaterModal
        isOpen={isTheaterModalOpen}
        onClose={() => {
          setIsTheaterModalOpen(false);
          setEditingTheater(null);
        }}
        theater={editingTheater}
        collectorDefinitions={collectorDefinitions}
        collectorError={collectorError}
        onManageQueryLinks={onManageQueryLinks}
        onSave={handleSaveTheater}
        onDelete={handleDeleteTheater}
      />

      <TheaterBatchImportModal
        isOpen={isTheaterBatchOpen}
        onClose={() => setIsTheaterBatchOpen(false)}
        onBatchImport={handleBatchImportTheaters}
      />

      <SubTheaterModal
        isOpen={isSubTheaterModalOpen}
        onClose={() => {
          setIsSubTheaterModalOpen(false);
          setEditingSubTheater(null);
        }}
        subTheater={editingSubTheater}
        theaters={theaters.filter((item) => item.status === '启用')}
        onSave={handleSaveSubTheater}
        onDelete={handleDeleteSubTheater}
      />

      <SubTheaterBatchImportModal
        isOpen={isSubTheaterBatchOpen}
        onClose={() => setIsSubTheaterBatchOpen(false)}
        theaters={theaters.filter((item) => item.status === '启用')}
        onBatchImport={handleBatchImportSubTheaters}
      />

      <DramaRenameModal
        isOpen={isDramaModalOpen}
        onClose={() => {
          setIsDramaModalOpen(false);
          setEditingDrama(null);
        }}
        drama={editingDrama}
        theaters={theaters.filter((item) => item.status === '启用')}
        onSave={handleSaveDrama}
        onDelete={handleDeleteDrama}
      />

      <DramaBatchImportModal
        isOpen={isDramaBatchOpen}
        onClose={() => setIsDramaBatchOpen(false)}
        theaters={theaters.filter((item) => item.status === '启用')}
        onBatchImport={handleBatchImportDramas}
      />
    </div>
  );
};
