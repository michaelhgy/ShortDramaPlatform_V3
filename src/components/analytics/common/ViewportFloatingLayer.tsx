import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export type FloatingPlacement = 'top' | 'bottom' | 'left' | 'right';

export interface FloatingAnchorRect {
  left: number;
  top: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
}

interface ViewportFloatingLayerProps {
  getAnchorRect: () => FloatingAnchorRect | null;
  preferredPlacement?: FloatingPlacement;
  children: React.ReactNode;
}

const VIEWPORT_MARGIN = 8;
const GAP = 8;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const oppositePlacement: Record<FloatingPlacement, FloatingPlacement> = {
  top: 'bottom',
  bottom: 'top',
  left: 'right',
  right: 'left',
};

const availableSpace = (anchor: FloatingAnchorRect, placement: FloatingPlacement): number => {
  if (placement === 'top') return anchor.top - VIEWPORT_MARGIN;
  if (placement === 'bottom') return window.innerHeight - anchor.bottom - VIEWPORT_MARGIN;
  if (placement === 'left') return anchor.left - VIEWPORT_MARGIN;
  return window.innerWidth - anchor.right - VIEWPORT_MARGIN;
};

const requiredSpace = (layer: DOMRect, placement: FloatingPlacement) =>
  (placement === 'top' || placement === 'bottom' ? layer.height : layer.width) + GAP;

/** Renders transient UI into document.body so local overflow and stacking contexts cannot clip it. */
export const ViewportFloatingLayer: React.FC<ViewportFloatingLayerProps> = ({
  getAnchorRect,
  preferredPlacement = 'top',
  children,
}) => {
  const layerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const placementPreference: FloatingPlacement = preferredPlacement as FloatingPlacement;

  const updatePosition = useCallback(() => {
    const anchor = getAnchorRect();
    const layer = layerRef.current?.getBoundingClientRect();
    if (!anchor || !layer) return;

    const fallback = oppositePlacement[placementPreference];
    const placement: FloatingPlacement =
      availableSpace(anchor, placementPreference) >= requiredSpace(layer, placementPreference) ||
      availableSpace(anchor, placementPreference) >= availableSpace(anchor, fallback)
        ? placementPreference
        : fallback;

    let left = anchor.left + anchor.width / 2 - layer.width / 2;
    let top = anchor.top - layer.height - GAP;

    if (placement === 'bottom') top = anchor.bottom + GAP;
    if (placement === 'left') {
      left = anchor.left - layer.width - GAP;
      top = anchor.top + anchor.height / 2 - layer.height / 2;
    }
    if (placement === 'right') {
      left = anchor.right + GAP;
      top = anchor.top + anchor.height / 2 - layer.height / 2;
    }

    setPosition({
      left: clamp(left, VIEWPORT_MARGIN, Math.max(VIEWPORT_MARGIN, window.innerWidth - layer.width - VIEWPORT_MARGIN)),
      top: clamp(top, VIEWPORT_MARGIN, Math.max(VIEWPORT_MARGIN, window.innerHeight - layer.height - VIEWPORT_MARGIN)),
    });
  }, [getAnchorRect, placementPreference]);

  useLayoutEffect(() => {
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updatePosition);
    if (layerRef.current) observer?.observe(layerRef.current);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
      observer?.disconnect();
    };
  }, [updatePosition]);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      ref={layerRef}
      className="fixed z-[1000] pointer-events-none"
      style={{
        left: position?.left ?? 0,
        top: position?.top ?? 0,
        visibility: position ? 'visible' : 'hidden',
      }}
    >
      {children}
    </div>,
    document.body,
  );
};

export const svgPointAnchor = (
  svg: SVGSVGElement | null,
  x: number,
  y: number,
  viewBoxWidth: number,
  viewBoxHeight: number,
): FloatingAnchorRect | null => {
  if (!svg) return null;
  const rect = svg.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const left = rect.left + (x / viewBoxWidth) * rect.width;
  const top = rect.top + (y / viewBoxHeight) * rect.height;
  return { left, top, width: 0, height: 0, right: left, bottom: top };
};
