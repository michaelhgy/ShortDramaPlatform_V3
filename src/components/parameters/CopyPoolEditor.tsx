import React, { useState } from 'react';
import { Check, ChevronDown, ChevronUp, Edit2, Plus, Trash2 } from 'lucide-react';

/**
 * 一个文案池（祝福语 / 引导语）的行内编辑器。
 *
 * 交互与样式刻意复用设置页「常用发布时间预设」那一组现成写法
 * （列表 + 行内编辑 + 增删 + 上下移），不自创 UI 体系——见 docs/UI迁移规则.md。
 *
 * 空池是**合法且有意义**的状态（= 不要这条文案轨道），所以这里不做"至少一条"的限制，
 * 只把含义明确写出来，避免用户以为"空 = 没填"。
 */
export interface CopyPoolEditorProps {
  /** 池里每一行的文字。 */
  items: string[];
  onChange: (items: string[]) => void;
  addPlaceholder: string;
  /** 空池时显示的说明，必须写清"留空 = 不要这条轨道"。 */
  emptyHint: string;
  addLabel: string;
  onNotify?: (message: string) => void;
}

export const CopyPoolEditor: React.FC<CopyPoolEditorProps> = ({
  items, onChange, addPlaceholder, emptyHint, addLabel, onNotify,
}) => {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const [newValue, setNewValue] = useState('');

  const handleAdd = () => {
    const value = newValue.trim();
    if (!value) {
      onNotify?.(`请先输入内容，再${addLabel}`);
      return;
    }
    if (items.includes(value)) {
      onNotify?.(`这条文案已存在：${value}`);
      return;
    }
    onChange([...items, value]);
    setNewValue('');
  };

  const handleStartEdit = (index: number) => {
    setEditingIndex(index);
    setEditingValue(items[index]);
  };

  const handleSaveEdit = () => {
    if (editingIndex === null) return;
    const value = editingValue.trim();
    if (!value) {
      onNotify?.('文案不能为空；不需要这一条请用删除。');
      return;
    }
    const next = [...items];
    next[editingIndex] = value;
    onChange(next);
    setEditingIndex(null);
    setEditingValue('');
  };

  const handleMove = (index: number, direction: 'up' | 'down') => {
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  const handleRemove = (index: number) => {
    onChange(items.filter((_, current) => current !== index));
  };

  return (
    <div className="space-y-2.5 text-xs">
      <div className="flex items-center gap-2">
        <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold">
          共 {items.length} 条
        </span>
        {items.length === 0 && (
          <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 text-[10px] font-bold border border-amber-200/60">
            这条轨道不会生成
          </span>
        )}
        <span className="text-[11px] text-[#64748B]">生成时从这个池里随机挑一句</span>
      </div>

      {items.length === 0 ? (
        <p className="rounded-xl bg-[#F8FAFC] border border-black/[0.06] px-3 py-2.5 text-[11px] text-[#64748B]">
          {emptyHint}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item, index) => {
            if (editingIndex === index) {
              return (
                <li key={`edit-${index}`} className="flex items-center gap-1.5 rounded-xl bg-white border border-[#1A1D2E] px-3 py-1.5 shadow-2xs">
                  <input
                    autoFocus
                    value={editingValue}
                    onChange={(event) => setEditingValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') handleSaveEdit();
                      if (event.key === 'Escape') setEditingIndex(null);
                    }}
                    className="flex-1 text-xs font-bold text-[#1A1D2E] focus:outline-none"
                  />
                  <button type="button" title="保存" onClick={handleSaveEdit} className="text-emerald-700 hover:text-emerald-900 p-0.5 cursor-pointer">
                    <Check className="w-3.5 h-3.5" />
                  </button>
                  <button type="button" title="取消" onClick={() => setEditingIndex(null)} className="text-slate-400 hover:text-slate-600 p-0.5 cursor-pointer">
                    ×
                  </button>
                </li>
              );
            }

            return (
              <li
                key={`item-${index}`}
                className="flex items-center justify-between gap-3 rounded-xl bg-slate-100 border border-black/[0.06] px-3 py-1.5 hover:border-black/[0.12] transition-all"
              >
                <span className="font-bold text-[#1A1D2E] break-all">{item}</span>
                <div className="flex items-center gap-0.5 text-slate-400 shrink-0">
                  <button
                    type="button"
                    title="上移"
                    disabled={index === 0}
                    onClick={() => handleMove(index, 'up')}
                    className="hover:text-slate-700 disabled:opacity-20 cursor-pointer disabled:cursor-not-allowed"
                  >
                    <ChevronUp className="w-3 h-3" />
                  </button>
                  <button
                    type="button"
                    title="下移"
                    disabled={index === items.length - 1}
                    onClick={() => handleMove(index, 'down')}
                    className="hover:text-slate-700 disabled:opacity-20 cursor-pointer disabled:cursor-not-allowed"
                  >
                    <ChevronDown className="w-3 h-3" />
                  </button>
                  <button type="button" title="修改" onClick={() => handleStartEdit(index)} className="hover:text-slate-700 ml-0.5 cursor-pointer">
                    <Edit2 className="w-2.5 h-2.5" />
                  </button>
                  <button type="button" title="删除" onClick={() => handleRemove(index)} className="hover:text-rose-600 ml-0.5 cursor-pointer">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex items-center gap-1.5">
        <input
          value={newValue}
          onChange={(event) => setNewValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') handleAdd();
          }}
          placeholder={addPlaceholder}
          className="flex-1 px-2.5 py-1.5 bg-[#F8FAFC] border border-black/[0.08] rounded-xl text-xs font-semibold focus:outline-none focus:bg-white"
        />
        <button
          type="button"
          onClick={handleAdd}
          className="px-3 py-1.5 rounded-xl bg-slate-200 hover:bg-slate-300 font-bold text-[#1A1D2E] cursor-pointer transition-colors flex items-center gap-1"
        >
          <Plus className="w-3 h-3" />
          <span>{addLabel}</span>
        </button>
      </div>
    </div>
  );
};
