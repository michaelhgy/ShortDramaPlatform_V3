import React, { useState, useEffect } from 'react';
import { AccountBusinessItem, AccountBusinessStatus } from '../../../assetsTypes';
import { X, UserPlus, Save, Trash2, AlertCircle } from 'lucide-react';

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  account: AccountBusinessItem | null;
  theaters: { id: string; name: string }[];
  subTheaters: { id: string; name: string; theaterName: string }[];
  onSave: (accountData: Omit<AccountBusinessItem, 'id'>, id?: string) => void;
  onDelete?: (id: string, name: string) => void;
}

const ALL_STATUSES: AccountBusinessStatus[] = ['正常', '观察', '限流', '二限', '实名', '封禁', '停用'];

export const AccountModal: React.FC<AccountModalProps> = ({
  isOpen,
  onClose,
  account,
  theaters,
  subTheaters,
  onSave,
  onDelete,
}) => {
  const [nickname, setNickname] = useState('');
  const [accountId, setAccountId] = useState('');
  const [theaterName, setTheaterName] = useState(theaters[0]?.name || '九州剧场');
  const [subTheaterName, setSubTheaterName] = useState('');
  const [status, setStatus] = useState<AccountBusinessStatus>('正常');
  const [whitelistedDate, setWhitelistedDate] = useState('');
  const [registeredDate, setRegisteredDate] = useState(new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');

  useEffect(() => {
    if (account) {
      setNickname(account.nickname);
      setAccountId(account.accountId);
      setTheaterName(account.theaterName);
      setSubTheaterName(account.subTheaterName);
      setStatus(account.status);
      setWhitelistedDate(account.whitelistedDate === '未报白' ? '' : account.whitelistedDate);
      setRegisteredDate(account.registeredDate);
      setNotes(account.notes || '');
    } else {
      setNickname('');
      setAccountId('');
      setTheaterName(theaters[0]?.name || '九州剧场');
      setSubTheaterName('');
      setStatus('正常');
      setWhitelistedDate('');
      setRegisteredDate(new Date().toISOString().slice(0, 10));
      setNotes('');
    }
  // A background catalog refresh replaces `theaters` with a new array. It is
  // reference data, not a request to reset a form the user is currently typing.
  }, [account?.id, isOpen]);

  // Filter subtheaters belonging to chosen theater
  const filteredSubTheaters = subTheaters.filter(s => s.theaterName === theaterName);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!nickname.trim() || !accountId.trim()) return;

    const matchedTheater = theaters.find(t => t.name === theaterName);
    
    onSave({
      nickname: nickname.trim(),
      accountId: accountId.trim(),
      theaterId: matchedTheater?.id || 'th-01',
      theaterName,
      subTheaterName: subTheaterName.trim() || '主分发专区',
      status,
      whitelistedDate: whitelistedDate || '未报白',
      registeredDate: registeredDate || new Date().toISOString().slice(0, 10),
      notes: notes.trim(),
      isUsedInBusiness: account ? account.isUsedInBusiness : false,
    }, account ? account.id : undefined);

    onClose();
  };

  const isDeletable = account && !account.isUsedInBusiness;

  const handleDelete = () => {
    if (!account || !onDelete) return;
    if (!isDeletable) return;
    onDelete(account.id, account.nickname);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-xl rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center">
              <UserPlus className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">
                {account ? '编辑账号资料' : '快速新增账号'}
              </h3>
              <p className="text-xs text-[#64748B]">
                {account ? '修改账号基础档案与状态，支持在未产生业务关联时删除' : '录入新账号基础信息，支持后续排期与收益结算'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto space-y-4 text-xs">
          {/* Row 1: Nickname & Account ID */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5">
                账号昵称 <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="平台昵称"
                value={nickname}
                onChange={e => setNickname(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-medium text-[#1A1D2E]"
              />
            </div>
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5">
                账号 ID / 原始 ID <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="平台iD"
                value={accountId}
                onChange={e => setAccountId(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-mono font-medium text-[#1A1D2E]"
              />
            </div>
          </div>

          {/* Row 2: Theater & SubTheater */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5">
                所属剧场 <span className="text-rose-500">*</span>
              </label>
              <select
                value={theaterName}
                onChange={e => {
                  setTheaterName(e.target.value);
                  setSubTheaterName('');
                }}
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-medium text-[#1A1D2E]"
              >
                {theaters.map(t => (
                  <option key={t.id} value={t.name}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5 flex items-center justify-between">
                <span>所属子剧场</span>
                <span className="text-[10px] text-slate-400 font-normal">方便结算联系</span>
              </label>
              <input
                type="text"
                list="subtheater-suggestions"
                placeholder="输入匹配或选择"
                value={subTheaterName}
                onChange={e => setSubTheaterName(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-medium text-[#1A1D2E]"
              />
              <datalist id="subtheater-suggestions">
                {filteredSubTheaters.map(st => (
                  <option key={st.id} value={st.name} />
                ))}
              </datalist>
            </div>
          </div>

          {/* Row 3: Status Selector */}
          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5">
              账号当前状态 <span className="text-rose-500">*</span>
            </label>
            <div className="grid grid-cols-4 sm:grid-cols-7 gap-1.5">
              {ALL_STATUSES.map(s => {
                const isSelected = status === s;
                let activeStyle = 'bg-slate-100 text-slate-600 border-black/[0.06] hover:bg-slate-200/60';
                if (isSelected) {
                  if (s === '正常') activeStyle = 'bg-emerald-600 text-white font-bold shadow-xs border-emerald-600';
                  else if (s === '观察') activeStyle = 'bg-blue-600 text-white font-bold shadow-xs border-blue-600';
                  else if (s === '限流') activeStyle = 'bg-amber-500 text-white font-bold shadow-xs border-amber-500';
                  else if (s === '二限') activeStyle = 'bg-orange-600 text-white font-bold shadow-xs border-orange-600';
                  else if (s === '实名') activeStyle = 'bg-purple-600 text-white font-bold shadow-xs border-purple-600';
                  else if (s === '封禁') activeStyle = 'bg-rose-600 text-white font-bold shadow-xs border-rose-600';
                  else if (s === '停用') activeStyle = 'bg-slate-600 text-white font-bold shadow-xs border-slate-600';
                }

                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setStatus(s)}
                    className={`py-1.5 px-2 rounded-xl text-center text-xs border transition-all cursor-pointer ${activeStyle}`}
                  >
                    {s}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Row 4: Whitelisted Date & Registered Date */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5 flex items-center justify-between">
                <span>报白时间</span>
                <span className="text-[10px] text-slate-400 font-normal">未报白可留空</span>
              </label>
              <input
                type="date"
                value={whitelistedDate}
                onChange={e => setWhitelistedDate(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-medium text-[#1A1D2E]"
              />
            </div>
            <div>
              <label className="block font-semibold text-[#1A1D2E] mb-1.5">
                注册时间
              </label>
              <input
                type="date"
                value={registeredDate}
                onChange={e => setRegisteredDate(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-medium text-[#1A1D2E]"
              />
            </div>
          </div>

          {/* Row 5: Notes */}
          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5">
              备注说明
            </label>
            <textarea
              rows={2}
              placeholder="记录账号权重特点、主要推送题材、封控注意事项等..."
              value={notes}
              onChange={e => setNotes(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs text-[#1A1D2E] leading-relaxed resize-none"
            />
          </div>

          {/* Deletion constraint hint when editing */}
          {account && (
            <div className="pt-2">
              {!isDeletable ? (
                <div className="p-2.5 rounded-xl bg-slate-50 border border-black/[0.06] flex items-center gap-2 text-[11px] text-[#64748B]">
                  <AlertCircle className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>该账号已产生实际业务关联或发布记录，系统保护锁定，禁止删除。</span>
                </div>
              ) : (
                <div className="p-2.5 rounded-xl bg-rose-50/60 border border-rose-100 flex items-center gap-2 text-[11px] text-rose-700">
                  <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
                  <span>当前账号无实际业务绑定，支持永久删除此档案。</span>
                </div>
              )}
            </div>
          )}

          {/* Footer Actions */}
          <div className="pt-3 border-t border-black/[0.06] flex items-center justify-between gap-2.5">
            <div>
              {account && onDelete && (
                <button
                  type="button"
                  disabled={!isDeletable}
                  onClick={handleDelete}
                  className={`flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                    isDeletable
                      ? 'text-rose-600 hover:bg-rose-50 active:scale-95'
                      : 'text-slate-300 cursor-not-allowed opacity-60'
                  }`}
                  title={!isDeletable ? '已关联业务，不可删除' : '删除该账号'}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>删除账号</span>
                </button>
              )}
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:bg-slate-100 transition-colors cursor-pointer"
              >
                取消
              </button>
              <button
                type="submit"
                className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold hover:bg-black/90 active:scale-[0.98] transition-all shadow-xs cursor-pointer"
              >
                <Save className="w-3.5 h-3.5" />
                <span>{account ? '保存修改' : '确认新增'}</span>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
