import React, { useState } from 'react';
import { DramaBusinessItem } from '../../../assetsTypes';
import { X, FileSpreadsheet, CheckCircle2, AlertCircle, Plus } from 'lucide-react';

interface DramaBatchImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  theaters: { id: string; name: string }[];
  defaultTheaterId?: string;
  onBatchImport: (dramas: Omit<DramaBusinessItem, 'id' | 'createdAt' | 'hasContentProfile'>[]) => void;
}

export const DramaBatchImportModal: React.FC<DramaBatchImportModalProps> = ({
  isOpen,
  onClose,
  theaters,
  defaultTheaterId,
  onBatchImport,
}) => {
  const [targetTheaterId, setTargetTheaterId] = useState(defaultTheaterId || theaters[0]?.id || 'th-01');
  const [pasteText, setPasteText] = useState('');
  const [parsedRows, setParsedRows] = useState<{ currentName: string; theaterName: string; theaterId: string; historyNames: string[] }[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);

  const selectedTheater = theaters.find(t => t.id === targetTheaterId) || theaters[0];

  if (!isOpen) return null;

  const handleParse = () => {
    if (!pasteText.trim()) {
      setParseError('请先粘贴剧集名称');
      return;
    }

    const lines = pasteText.trim().split('\n').filter(l => l.trim().length > 0);
    const results: { currentName: string; theaterName: string; theaterId: string; historyNames: string[] }[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (i === 0 && (line.includes('剧名') || line.includes('剧集'))) {
        continue;
      }

      // Excel 复制格式：当前剧名<TAB>历史剧名；所属剧场统一使用上方选择。
      const parts = line.split(/\t|,|;|\s{2,}/).map(p => p.trim()).filter(Boolean);
      if (parts.length < 1) continue;

      const currentName = parts[0];
      const effectiveTheater = selectedTheater;
      const rawHistories = parts[1] ? parts[1].split('|').map(h => h.trim()).filter(Boolean) : [];

      results.push({
        currentName,
        theaterId: effectiveTheater.id,
        theaterName: effectiveTheater.name,
        historyNames: rawHistories,
      });
    }

    if (results.length === 0) {
      setParseError('未能识别到有效的剧集名称');
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
    setPasteText(`逆袭从首富开始\t重返首富之路\n千亿总裁的契约娇妻\t总裁别虐了\n绝代神帅下山\t\n九零年代商战大亨\t`);
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
              <h3 className="font-bold text-sm text-[#1A1D2E]">批量导入剧集</h3>
              <p className="text-xs text-[#64748B]">批量建立剧集业务档案，所属剧场使用上方选择</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-black/5 transition-colors cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-4 text-xs">
          <div>
            <label className="block font-semibold text-[#1A1D2E] mb-1.5">
              默认归属剧场
            </label>
            <select
              value={targetTheaterId}
              onChange={e => setTargetTheaterId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-semibold text-[#1A1D2E]"
            >
              {theaters.map(t => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="font-semibold text-[#1A1D2E]">
                粘贴多行剧集名称 (每行一个剧名，支持附加所属剧场与历史名)
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
              placeholder="当前剧名    历史剧名（可留空，多个历史剧名用 | 分隔）"
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-black/[0.1] bg-slate-50/50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1A1D2E]/20 text-xs font-mono text-[#1A1D2E] resize-none"
            />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-[#64748B]">
                每行：当前剧名［Tab］历史剧名；历史剧名可留空
              </span>
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
                已识别 {parsedRows.length} 部剧集
              </span>
              <div className="border border-black/[0.08] rounded-xl overflow-hidden max-h-40 overflow-y-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-50 border-b border-black/[0.06] text-[#64748B] font-medium sticky top-0">
                    <tr>
                      <th className="py-2 px-3">剧集名称</th>
                      <th className="py-2 px-3">所属剧场</th>
                      <th className="py-2 px-3">历史剧名</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/[0.04]">
                    {parsedRows.map((r, i) => (
                      <tr key={i} className="hover:bg-slate-50/60">
                        <td className="py-2 px-3 font-semibold text-[#1A1D2E]">{r.currentName}</td>
                        <td className="py-2 px-3 text-slate-600">{r.theaterName}</td>
                        <td className="py-2 px-3 text-slate-400">
                          {r.historyNames.length > 0 ? r.historyNames.join(' / ') : '-'}
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
