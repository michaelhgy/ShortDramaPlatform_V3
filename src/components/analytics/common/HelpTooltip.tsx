import React, { useState, useRef, useEffect } from 'react';
import { HelpCircle, Info } from 'lucide-react';

interface HelpTooltipProps {
  text: string;
  children?: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  className?: string;
}

export const HelpTooltip: React.FC<HelpTooltipProps> = ({
  text,
  children,
  position = 'top',
  className = '',
}) => {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <span 
      className={`relative inline-flex items-center group cursor-help ${className}`}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children || <HelpCircle className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 transition-colors" />}
      
      {isVisible && (
        <span 
          className={`absolute z-50 pointer-events-none w-56 p-2.5 bg-[#1A1D2E]/95 backdrop-blur-xs text-white rounded-xl shadow-xl text-xs font-normal leading-relaxed border border-white/10 ${
            position === 'top' 
              ? 'bottom-full left-1/2 -translate-x-1/2 mb-2' 
              : position === 'bottom'
              ? 'top-full left-1/2 -translate-x-1/2 mt-2'
              : position === 'left'
              ? 'right-full top-1/2 -translate-y-1/2 mr-2'
              : 'left-full top-1/2 -translate-y-1/2 ml-2'
          }`}
        >
          {text}
        </span>
      )}
    </span>
  );
};

interface ModuleInfoPopoverProps {
  title: string;
  content: React.ReactNode;
  className?: string;
}

export const ModuleInfoPopover: React.FC<ModuleInfoPopoverProps> = ({
  title,
  content,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  return (
    <div className={`relative inline-block ${className}`} ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="p-1 rounded-md text-slate-400 hover:text-[#1A1D2E] hover:bg-slate-100 transition-colors flex items-center justify-center"
        aria-label="查看模块说明"
      >
        <Info className="w-3.5 h-3.5" />
      </button>

      {isOpen && (
        <div className="absolute left-0 top-full mt-2 z-50 w-72 sm:w-80 p-3.5 bg-[#1A1D2E] text-white rounded-xl shadow-2xl border border-white/10 text-xs space-y-2 animate-in fade-in zoom-in-95 duration-100">
          <div className="flex items-center justify-between border-b border-white/10 pb-1.5 text-[#DDFD00] font-bold">
            <span className="flex items-center gap-1.5">
              <Info className="w-4 h-4" />
              {title}
            </span>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-white text-xs px-1"
            >
              ✕
            </button>
          </div>
          <div className="text-slate-300 leading-relaxed text-[11px] space-y-1.5">
            {content}
          </div>
        </div>
      )}
    </div>
  );
};
