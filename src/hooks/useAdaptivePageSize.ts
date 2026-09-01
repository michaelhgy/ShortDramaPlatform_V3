import { useEffect, useState } from 'react';

/**
 * Calculates a page size from the real vertical space below a list/table.
 * The reserved footer leaves room for the existing pagination controls.
 */
export function useAdaptivePageSize(
  element: HTMLElement | null,
  rowHeight: number,
  options: { minimum?: number; footerHeight?: number } = {},
): number {
  const minimum = options.minimum ?? 3;
  const footerHeight = options.footerHeight ?? 62;
  const [pageSize, setPageSize] = useState(minimum);

  useEffect(() => {
    if (!element) return;
    const update = () => {
      const top = element.getBoundingClientRect().top;
      const available = Math.max(rowHeight * minimum, window.innerHeight - top - footerHeight);
      setPageSize(Math.max(minimum, Math.floor(available / rowHeight)));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    window.addEventListener('resize', update);
    return () => { observer.disconnect(); window.removeEventListener('resize', update); };
  }, [element, footerHeight, minimum, rowHeight]);

  return pageSize;
}
