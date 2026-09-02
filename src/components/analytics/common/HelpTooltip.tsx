import React, { useState, useRef, useEffect } from 'react';
import { HelpCircle, Info } from 'lucide-react';
import { ViewportFloatingLayer } from './ViewportFloatingLayer';

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
  const triggerRef = useRef<HTMLSpanElement>(null);

  return (
    <span
      ref={triggerRef}
      className={`relative inline-flex items-center group cursor-help ${className}`}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children || <HelpCircle className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 transition-colors" />}
      
      {isVisible && (
        <ViewportFloatingLayer
          getAnchorRect={() => triggerRef.current?.getBoundingClientRect() ?? null}
          preferredPlacement={position}
        >
          <span className="block w-56 max-w-[calc(100vw-1rem)] p-2.5 bg-[#1A1D2E]/95 backdrop-blur-xs text-white rounded-xl shadow-xl text-xs font-normal leading-relaxed border border-white/10">
            {text}
          </span>
        </ViewportFloatingLayer>
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
