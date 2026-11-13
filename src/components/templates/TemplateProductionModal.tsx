import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { TemplateProduction } from './TemplateProduction';

export function TemplateProductionModal({ showToast, onClose, onParameters }: {
  showToast: (message: string) => void; onClose: () => void; onParameters?: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.focus({ preventScroll: true });
    const key = (event: KeyboardEvent) => {
      // The existing generation/preview dialog consumes the first Escape.
      if (event.defaultPrevented || panel.current?.querySelector('[role="dialog"]')) return;
      if (event.key === 'Escape' && !event.repeat) {
        event.preventDefault(); event.stopPropagation(); close.current();
      }
      if (event.key === 'Tab') {
        const controls = [...(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]') || [])].filter(e => e.getClientRects().length > 0);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener('keydown', key);
    return () => {
      window.removeEventListener('keydown', key);
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);
  return createPortal(<div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm">
    <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label="模板制作" className="max-h-[94vh] w-full max-w-[1500px] overflow-y-auto rounded-3xl border border-slate-200 bg-[#F5F7FA] p-4 shadow-2xl outline-none">
      <TemplateProduction showToast={showToast} onParameters={onParameters} onClose={onClose} />
    </div>
  </div>, document.body);
}
