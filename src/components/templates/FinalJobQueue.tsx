import React from 'react';
import type { FinalSnapshot } from '../../api/finalComposition';
import { FfmpegQueue } from '../taskcenter/FfmpegQueue';

export const FinalJobQueue: React.FC<{snapshot?: FinalSnapshot; showToast: (message: string) => void}> = props =>
  <FfmpegQueue kind="final" {...props} />;
