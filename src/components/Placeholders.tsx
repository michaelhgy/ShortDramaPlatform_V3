import React from 'react';
import { NavTab } from '../types';
import { Layers, BarChart3, FolderGit2, Settings, ArrowLeft, Tv2, Sparkles } from 'lucide-react';

interface PlaceholderViewProps {
  tab: NavTab;
  onBackToWorkbench: () => void;
}

export const PlaceholderView: React.FC<PlaceholderViewProps> = ({
  tab,
  onBackToWorkbench,
}) => {
  const config = {
    production: {
      title: '生产中心',
      subtitle: '剪映自动化工程、素材切片混剪、批量转码渲染与小V猫对接队列',
      icon: Layers,
      tag: '后台制作模块',
    },
    analytics: {
      title: '数据分析',
      subtitle: '多账号收益沉淀、短剧分发转化漏斗、历史跑量模型归因',
      icon: BarChart3,
      tag: '数据决策模块',
    },
    assets: {
      title: '资料中心',
      subtitle: '短剧片源母带、剧集授权文书、高光切片脚本库与素材资产管理',
      icon: FolderGit2,
      tag: '资产存储模块',
    },
    settings: {
      title: '系统设置',
      subtitle: '剪映本端路径映射、小V猫助手连接密钥、视频号矩阵配置及导出参数',
      icon: Settings,
      tag: '系统环境配置',
    },
    workbench: {
      title: '工作台',
      subtitle: '今日决策与排期工作台',
      icon: Tv2,
      tag: '核心台',
    },
  }[tab];

  const IconComponent = config.icon;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-12 min-h-[70vh] text-center animate-in fade-in duration-200">
      <div className="w-20 h-20 rounded-3xl bg-white border border-black/5 shadow-[0_12px_36px_-6px_rgba(0,0,0,0.06)] flex items-center justify-center text-[#1A1D2E] mb-6">
        <IconComponent className="w-10 h-10 text-[#1A1D2E]" />
      </div>

      <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#1A1D2E] text-[#DDFD00] text-xs font-bold mb-3">
        <Sparkles className="w-3.5 h-3.5 fill-[#DDFD00]" />
        <span>{config.tag}</span>
      </div>

      <h2 className="text-2xl font-black text-[#1A1D2E] tracking-tight">
        {config.title}
      </h2>

      <p className="text-sm text-[#64748B] max-w-md mt-2 leading-relaxed">
        {config.subtitle}
      </p>

      <div className="mt-4 p-4 rounded-2xl bg-white/70 border border-[#E2E8F0] text-xs text-[#64748B] max-w-md">
        提示：本次原型重点验证「工作台」的视觉、布局与排期交互闭环。
      </div>

      <button
        onClick={onBackToWorkbench}
        className="mt-8 flex items-center gap-2 px-6 py-2.5 rounded-2xl bg-[#1A1D2E] text-[#DDFD00] hover:bg-black font-bold text-sm transition-all shadow-md active:scale-95"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>返回「工作台」主界面</span>
      </button>
    </div>
  );
};
