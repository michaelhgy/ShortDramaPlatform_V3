import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

const layers: symbol[] = [];
let originalOverflow = '';

/** All cockpit details share one centered layout and top-layer dismissal. */
export function CockpitModal({ label, onClose, children, width = 'max-w-5xl', rounding = 'rounded-2xl', testId }: {
  label: string;
  onClose: () => void;
  children: React.ReactNode;
  width?: string;
  rounding?: 'rounded-2xl' | 'rounded-3xl';
  testId?: string;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const token = useRef(Symbol('cockpit-modal'));
  useEffect(() => {
    const id = token.current;
    const previous = document.activeElement as HTMLElement | null;
    if (!layers.length) {
      originalOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    layers.push(id);
    dialog.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (layers.at(-1) !== id || event.defaultPrevented) return;
      if (event.key === 'Escape') {
        // The badge reading panel consumes the first Escape before its containing detail.
        if (document.querySelector('[data-status-popover="true"]')) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        close.current();
      }
      if (event.key === 'Tab') {
        if (document.querySelector('[data-status-popover="true"]')) return;
        const items = dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]),[href],input,select,textarea,[tabindex="0"]');
        if (!items?.length) { event.preventDefault(); return; }
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) {
          event.preventDefault(); first.focus();
        }
      }
    };
    window.addEventListener('keydown', keydown, true);
    return () => {
      window.removeEventListener('keydown', keydown, true);
      const index = layers.indexOf(id);
      const wasTop = index === layers.length - 1;
      if (index !== -1) layers.splice(index, 1);
      if (!layers.length) document.body.style.overflow = originalOverflow;
      if (wasTop && previous?.isConnected) previous.focus();
    };
  }, []);
  return createPortal(
    <div data-testid={testId} className="fixed inset-0 z-[70] flex items-center justify-center overflow-hidden bg-slate-900/40 p-4 backdrop-blur-xs sm:p-6 animate-in fade-in duration-150"
      onClick={event => { event.stopPropagation(); if (event.target === event.currentTarget && layers.at(-1) === token.current) close.current(); }}>
      <div ref={dialog} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}
        className={`w-full ${width} ${rounding} max-h-[calc(100dvh-3rem)] flex flex-col overflow-hidden border border-slate-200 bg-white shadow-2xl outline-none animate-in zoom-in-95 duration-200`}>
        {children}
      </div>
    </div>, document.body);
}
