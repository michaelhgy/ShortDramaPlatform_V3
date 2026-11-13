import React, { useState } from 'react';
import { TheaterBusinessItem } from '../../../assetsTypes';
import { X, FileSpreadsheet, CheckCircle2, AlertCircle, Plus } from 'lucide-react';

interface TheaterBatchImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onBatchImport: (theaters: Omit<TheaterBusinessItem, 'id'>[]) => void;
}

export const TheaterBatchImportModal: React.FC<TheaterBatchImportModalProps> = ({
  isOpen,
  onClose,
  onBatchImport,
}) => {
  const [pasteText, setPasteText] = useState('');
  const [parsedRows, setParsedRows] = useState<Omit<TheaterBusinessItem, 'id'>[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleParse = () => {
    if (!pasteText.trim()) {
      setParseError('请先粘贴剧场数据');
      return;
    }

    const lines = pasteText.trim().split('\n').filter(l => l.trim().length > 0);
    const results: Omit<TheaterBusinessItem, 'id'>[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (i === 0 && (line.includes('剧场') || line.includes('分成') || line.includes('税率'))) {
        continue;
      }

      const parts = line.split(/\t|,|;|\s{2,}/).map(p => p.trim()).filter(Boolean);
      if (parts.length < 1) continue;

      const name = parts[0];
      const commissionRate = parts[1] ? Number(parts[1].replace('%', '')) : 40;
      const taxRate = parts[2] ? Number(parts[2].replace('%', '')) : 6;
      const status: '启用' | '停用' = parts[3] === '停用' ? '停用' : '启用';

      results.push({
        name,
        defaultCommissionRate: isNaN(commissionRate) ? 40 : commissionRate,
        defaultTaxRate: isNaN(taxRate) ? 6 : taxRate,
        status,
        subTheatersCount: 0,
        dramasCount: 0,
      });
    }

    if (results.length === 0) {
      setParseError('未能识别到有效的剧场数据');
    } else {
      setParseError(null);
      setParsedRows(results);
    }
  };

  const handleConfirm = () => {
    if (parsedRows.length === 0) return;
    onBatchImport(parsedRows);
    onClose();
  };

  const handleFillSample = () => {
    setPasteText(`青柠剧场\t10\t3\t启用\n顶好剧场\t15\t3\t停用\n子诗剧场\t20\t3\t停用`);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-xl rounded-2xl shadow-2xl border border-black/[0.08] overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b border-black/[0.06] flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#1A1D2E] text-[#DDFD00] flex items-center justify-center">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#1A1D2E]">批量导入剧场</h3>
              <p className="text-xs text-[#64748B]">快速批量创建合作剧场及默认分成参数</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-4 text-xs">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="font-semibold text-[#1A1D2E]">
                粘贴多行剧场数据 (每行：剧场名称 默认分成% 默认税率% 启用状态)
              </label>
              <button
                type="button"
                onClick={handleFillSample}
                className="text-[11px] text-indigo-600 hover:underline font-medium cursor-pointer"
              >
                填入示例
              </button>
            </div>
            <textarea
              rows={4}
              placeholder="剧场名称  默认分成%  默认税率%  状态..."
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-mono text-[#1A1D2E] resize-none"
            />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-[#64748B]">格式示例：青柠剧场 10 3 启用</span>
              <button
                type="button"
                onClick={handleParse}
                className="px-3.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-[#1A1D2E] font-bold text-xs cursor-pointer"
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

          {parsedRows.length > 0 && (
            <div className="space-y-2">
              <span className="font-bold text-[#1A1D2E] flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                已识别 {parsedRows.length} 个剧场
              </span>
              <div className="border border-black/[0.08] rounded-xl overflow-hidden max-h-40 overflow-y-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-50 border-b border-black/[0.06] text-[#64748B] font-medium sticky top-0">
                    <tr>
                      <th className="py-2 px-3">剧场名称</th>
                      <th className="py-2 px-3 text-right">默认分成</th>
                      <th className="py-2 px-3 text-right">默认税率</th>
                      <th className="py-2 px-3 text-center">状态</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/[0.04]">
                    {parsedRows.map((r, i) => (
                      <tr key={i} className="hover:bg-slate-50/60">
                        <td className="py-2 px-3 font-semibold text-[#1A1D2E]">{r.name}</td>
                        <td className="py-2 px-3 text-right font-mono">{r.defaultCommissionRate}%</td>
                        <td className="py-2 px-3 text-right font-mono">{r.defaultTaxRate}%</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${r.status === '启用' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                            {r.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-black/[0.06] flex items-center justify-end gap-2.5 bg-slate-50/60">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold text-[#64748B] hover:bg-slate-100 cursor-pointer">
            取消
          </button>
          <button
            type="button"
            disabled={parsedRows.length === 0}
            onClick={handleConfirm}
            className={`flex items-center gap-1.5 px-5 py-2 rounded-xl text-xs font-bold transition-all shadow-xs ${
              parsedRows.length > 0
                ? 'bg-[#1A1D2E] text-[#DDFD00] hover:bg-black/90 active:scale-[0.98] cursor-pointer'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>确认导入 ({parsedRows.length})</span>
          </button>
        </div>
      </div>
    </div>
  );
};
