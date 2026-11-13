import React from 'react';
import { AlertTriangle } from 'lucide-react';
import type { EncoderStatus } from '../../api/encoderStatus';

export function EncoderNotice({ encoding, compact = false }: {
  encoding?: EncoderStatus | null; compact?: boolean;
}) {
  if (encoding?.encoder !== 'libx264' || !encoding.warning) return null;
  const { reason, action, diagnostic } = encoding.warning;
  return <div role="note" aria-label="显卡编码提示" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 space-y-1.5">
    <p className="flex items-start gap-1.5 font-bold">
      <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0" />
      <span>本次使用 CPU 编码，速度可能较慢</span>
    </p>
    <p className="break-words">{reason}</p>
    <p className="break-words">{action}</p>
    {!compact && diagnostic && <details className="pt-1">
      <summary className="cursor-pointer text-amber-800">查看本次检测详情</summary>
      <pre className="mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap break-all text-[11px]">{diagnostic}</pre>
    </details>}
  </div>;
}
