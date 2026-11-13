import React from 'react';
import { AnalyticsDashboard } from './AnalyticsDashboard';

interface DataAnalyticsViewProps {
  onScheduleToday: (dramaId?: string, accountId?: string) => void;
  showToast: (msg: string) => void;
}

/**
 * The analytics entry now owns one operations data center. The old modules
 * remain in the repository for migration reference, but are no longer
 * composed into this page.
 */
export const DataAnalyticsView: React.FC<DataAnalyticsViewProps> = ({ onScheduleToday, showToast }) => (
  <AnalyticsDashboard onScheduleToday={onScheduleToday} showToast={showToast} />
);
