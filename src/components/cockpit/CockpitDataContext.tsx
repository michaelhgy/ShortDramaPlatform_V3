import React, { createContext, useContext } from 'react';
import type { CockpitModel } from '../../services/cockpitModel';

export const CockpitDataContext = createContext<CockpitModel | null>(null);

export function useCockpitData(): CockpitModel {
  const value = useContext(CockpitDataContext);
  if (!value) throw new Error('驾驶舱数据尚未加载');
  return value;
}
