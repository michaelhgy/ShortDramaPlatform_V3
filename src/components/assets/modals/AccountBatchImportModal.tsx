import React, { useState } from 'react';
import { AccountBusinessItem, AccountBusinessStatus } from '../../../assetsTypes';
import { X, FileSpreadsheet, CheckCircle2, AlertCircle, Plus } from 'lucide-react';

interface AccountBatchImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultTheaterName?: string;
  onBatchImport: (accounts: Omit<AccountBusinessItem, 'id'>[]) => void;
}

export const AccountBatchImportModal: React.FC<AccountBatchImportModalProps> = ({
  isOpen,
  onClose,
  defaultTheaterName = '九州剧场',
  onBatchImport,
}) => {
  const [pasteText, setPasteText] = useState('');
  const [parsedRows, setParsedRows] = useState<Omit<AccountBusinessItem, 'id'>[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);

  const normalizeDate = (value: string, allowUnreported: boolean): string | null => {
    const raw = value.trim();
    if (allowUnreported && raw === '未报白') return raw;
    if (/^\d{4}[-\/]\d{1,2}[-\/]\d{1,2}$/.test(raw)) {
      const [year, month, day] = raw.split(/[-\/]/).map(Number);
      const date = new Date(Date.UTC(year, month - 1, day));
      if (date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day) {
        return `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
      }
    }
    if (/^\d+(?:\.\d+)?$/.test(raw)) {
      const serial = Number(raw);
      if (serial >= 1 && serial <= 2958465) {
        return new Date(Date.UTC(1899, 11, 30) + Math.floor(serial) * 86400000).toISOString().slice(0, 10);
      }
    }
    return null;
  };

  if (!isOpen) return null;

  const handleParse = () => {
    if (!pasteText.trim()) {
      setParseError('请先粘贴包含账号信息的文本内容');
      return;
    }

    const lines = pasteText.trim().split('\n').filter(l => l.trim().length > 0);
    const results: Omit<AccountBusinessItem, 'id'>[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      // Skip only an actual header row. A real data row can contain a theater name.
      if (i === 0 && /^(账号昵称|昵称)\s*(账号ID|ID|平台ID)/i.test(line)) {
        continue;
      }

      // Split by tab, comma, semicolon, or 2+ spaces
      const parts = line.split(/\t|,|;|\s{2,}/).map(p => p.trim()).filter(Boolean);
      if (parts.length < 1) continue;

      const nickname = parts[0];
      const accountId = parts[1] || '';
      if (!accountId) {
        setParseError(`第 ${i + 1} 行缺少平台iD，账号iD不能为空`);
        setParsedRows([]);
        return;
      }
      const theaterName = parts[2] || defaultTheaterName;
      const subTheaterName = parts[3] || '';
      
      let rawStatus = parts[4] || '正常';
      const validStatuses: AccountBusinessStatus[] = ['正常', '观察', '限流', '二限', '实名', '封禁', '停用'];
      const status: AccountBusinessStatus = validStatuses.includes(rawStatus as AccountBusinessStatus) 
        ? (rawStatus as AccountBusinessStatus) 
        : '正常';

      const whitelistedDate = normalizeDate(parts[5] || '未报白', true);
      const registeredDate = normalizeDate(parts[6] || '', false);
      if (!whitelistedDate) {
        setParseError(`第 ${i + 1} 行报白时间只能填写“未报白”或有效日期`);
        setParsedRows([]);
        return;
      }
      if (!registeredDate) {
        setParseError(`第 ${i + 1} 行注册时间必须填写有效日期`);
        setParsedRows([]);
        return;
      }
      const notes = parts[7] || '批量导入账号';

      results.push({
        nickname,
        accountId,
        theaterId: 'th-01',
        theaterName,
        subTheaterName,
        status,
        whitelistedDate,
        registeredDate,
        notes,
      });
    }

    if (results.length === 0) {
      setParseError('未能识别到有效的账号数据，请检查格式');
    } else {
      setParseError(null);
      setParsedRows(results);
    }
  };

  const handleConfirmImport = () => {
    if (parsedRows.length === 0) return;
    onBatchImport(parsedRows);
    onClose();
  };

  const handleFillSample = () => {
    const sample = `橘子梨晚\tsphc48GynXCQvm6\t青柠剧场\t雅兮短剧\t正常\t未报白\t2026-08-25\t新号
月亮麦片粥粥\tsphQN3qoneOLgwx\t青柠剧场\t雅兮短剧\t正常\t2026-08-24\t2026-08-24\t正剧`;
    setPasteText(sample);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">批量导入账号</h3>
              <p className="text-xs text-[#64748B]">
                支持从 Excel、表格或多行文本直接复制粘贴，快速批量建立账号档案
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

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-4 text-xs">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="font-semibold text-[#1A1D2E]">
                粘贴多行表格数据 (支持制表符 Tab、逗号、空格分隔)
              </label>
              <button
                type="button"
                onClick={handleFillSample}
                className="text-[11px] text-indigo-600 hover:underline font-medium cursor-pointer"
              >
                填入示例数据
              </button>
            </div>
            <textarea
              rows={5}
              placeholder="账号昵称  账号ID  所属剧场  子剧场  状态  报白时间  注册时间  备注..."
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-mono text-[#1A1D2E] resize-none"
            />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-[#64748B]">
                列顺序建议：账号昵称 | 账号ID | 剧场 | 子剧场 | 状态 | 报白时间 | 注册时间 | 备注
              </span>
              <button
                type="button"
                onClick={handleParse}
                className="px-3.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold text-xs transition-all cursor-pointer"
              >
                解析数据
              </button>
            </div>
          </div>

          {parseError && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{parseError}</span>
            </div>
          )}

          {/* Preview Table */}
          {parsedRows.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  已识别 {parsedRows.length} 个账号
                </span>
                <span className="text-[11px] text-slate-400">核对无误后点击下方确认导入</span>
              </div>
              <div className="border border-black/[0.08] rounded-xl overflow-hidden max-h-48 overflow-y-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-50 border-b border-black/[0.06] text-[#64748B] font-medium sticky top-0">
                    <tr>
                      <th className="py-2 px-3">账号昵称</th>
                      <th className="py-2 px-3">账号ID</th>
                      <th className="py-2 px-3">剧场/子剧场</th>
                      <th className="py-2 px-3">状态</th>
                      <th className="py-2 px-3">报白时间</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/[0.04]">
                    {parsedRows.map((r, i) => (
                      <tr key={i} className="hover:bg-slate-50/60">
                        <td className="py-2 px-3 font-semibold text-[#1A1D2E]">{r.nickname}</td>
                        <td className="py-2 px-3 font-mono text-slate-600">{r.accountId}</td>
                        <td className="py-2 px-3 text-slate-600">{r.theaterName} · {r.subTheaterName}</td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 font-medium text-[10px]">
                            {r.status}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-500 text-[11px]">{r.whitelistedDate}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-black/[0.06] flex items-center justify-end gap-2.5 bg-slate-50/60">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:bg-slate-100 transition-colors cursor-pointer"
          >
            取消
          </button>
          <button
            type="button"
            disabled={parsedRows.length === 0}
            onClick={handleConfirmImport}
            className={`flex items-center gap-1.5 px-5 py-2 rounded-xl text-xs font-bold transition-all shadow-xs ${
              parsedRows.length > 0
                ? 'bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] cursor-pointer'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>确认导入 {parsedRows.length > 0 ? `(${parsedRows.length})` : ''}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
