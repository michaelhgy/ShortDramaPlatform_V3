import React from 'react';

export type StatusBadgeVariant = 
  | 'historical'     // 历史累计
  | 'current'        // 当前
  | 'estimated'      // 推测
  | 'insufficient'   // 数据不足
  | 'pending'        // 待补采
  | 'linked'         // 已关联
  | 'unlinked'       // 未关联
  | 'inapplicable'   // 不适用
  | 'direct'         // 直接收益
  | 'zero';          // 0收益

interface StatusBadgeProps {
  variant: StatusBadgeVariant;
  text?: string;
  tooltip?: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  variant,
  text,
  tooltip,
  className = '',
}) => {
  let defaultText = text;
  let defaultTooltip = tooltip;
  let colorClasses = '';

  switch (variant) {
    case 'historical':
      defaultText = defaultText || '历史累计';
      defaultTooltip = defaultTooltip || '展示长期全量历史数据，不受顶部时间筛选影响';
      colorClasses = 'bg-slate-100 text-slate-700 border-slate-200/80';
      break;

    case 'current':
      defaultText = defaultText || '当前';
      colorClasses = 'bg-[#1A1D2E] text-white border-transparent';
      break;

    case 'estimated':
      defaultText = defaultText || '推测';
      defaultTooltip = defaultTooltip || '该金额由既定规则估算，并非数据来源直接返回的收益。';
      colorClasses = 'bg-amber-50 text-amber-800 border-amber-200/80';
      break;

    case 'insufficient':
      defaultText = defaultText || '数据不足';
      defaultTooltip = defaultTooltip || '前一比较周期历史数据不足以可靠计算，暂不显示涨跌百分比。';
      colorClasses = 'bg-slate-100 text-slate-500 border-slate-200/80';
      break;

    case 'pending':
      defaultText = defaultText || '待补采';
      defaultTooltip = defaultTooltip || '本应存在数据，当前采集流程尚未成功完成。';
      colorClasses = 'bg-amber-100/90 text-amber-900 border-amber-300/80';
      break;

    case 'linked':
      defaultText = defaultText || '已关联';
      defaultTooltip = defaultTooltip || '已成功关联至内部生产成片与源素材';
      colorClasses = 'bg-emerald-50 text-emerald-700 border-emerald-200/70';
      break;

    case 'unlinked':
      defaultText = defaultText || '未关联';
      defaultTooltip = defaultTooltip || '尚未关联内部成片，可手动指定成片追溯源素材';
      colorClasses = 'bg-slate-100 text-slate-500 border-slate-200/70';
      break;

    case 'inapplicable':
      defaultText = defaultText || '不适用';
      defaultTooltip = defaultTooltip || '该账号与剧集分属不同剧场，业务上不存在这一组合。';
      colorClasses = 'bg-slate-50 text-slate-400 border-slate-200/50';
      break;

    case 'direct':
      defaultText = defaultText || '直接收益';
      defaultTooltip = defaultTooltip || '平台数据源直接采集并核对的收益';
      colorClasses = 'bg-emerald-50 text-emerald-700 border-emerald-200/60';
      break;

    case 'zero':
      defaultText = defaultText || '0收益';
      defaultTooltip = defaultTooltip || '周期收益明确为0，属于有效统计';
      colorClasses = 'bg-slate-100 text-slate-600 border-slate-200/70';
      break;
  }

  return (
    <span
      className={`inline-flex items-center justify-center text-[10px] sm:text-[11px] font-medium px-2 py-0.5 rounded-md border tracking-tight shrink-0 transition-colors ${colorClasses} ${className}`}
      title={defaultTooltip}
    >
      {defaultText}
    </span>
  );
};
