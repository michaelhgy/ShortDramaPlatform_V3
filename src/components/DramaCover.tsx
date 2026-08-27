import React, { useState } from 'react';

interface DramaCoverProps {
  name: string;
  coverUrl?: string;
  colorPlaceholder?: {
    bg: string;
    text: string;
    tag: string;
  };
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const DramaCover: React.FC<DramaCoverProps> = ({
  name,
  coverUrl,
  colorPlaceholder,
  size = 'md',
  className = '',
}) => {
  const [imgError, setImgError] = useState(false);

  // Dimension presets (Vertical 3:4 or 9:16 aspect ratio standard for short dramas)
  const sizeClasses = {
    sm: 'w-10 h-14 rounded-lg text-[10px]',
    md: 'w-14 h-20 rounded-xl text-xs',
    lg: 'w-20 h-28 rounded-2xl text-sm',
  }[size];

  const hasValidImage = coverUrl && !imgError;

  return (
    <div
      className={`relative overflow-hidden shrink-0 select-none shadow-sm flex flex-col justify-between p-1.5 ${sizeClasses} ${className}`}
      style={{
        background: !hasValidImage
          ? (colorPlaceholder?.bg || 'linear-gradient(135deg, #1E293B 0%, #0F172A 100%)')
          : '#111827',
      }}
    >
      {hasValidImage ? (
        <>
          <img
            src={coverUrl}
            alt={name}
            onError={() => setImgError(true)}
            className="absolute inset-0 w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/20" />
          <div className="relative z-10 text-[9px] font-medium text-white/90 truncate leading-tight mt-auto">
            {name.slice(0, 4)}...
          </div>
        </>
      ) : (
        <>
          <div className="relative z-10 flex items-center justify-between w-full">
            <span
              className="text-[9px] px-1 py-0.5 rounded font-bold uppercase tracking-wider"
              style={{
                backgroundColor: 'rgba(255,255,255,0.15)',
                color: colorPlaceholder?.text || '#DDFD00',
              }}
            >
              {colorPlaceholder?.tag || '剧集'}
            </span>
          </div>

          <div
            className="relative z-10 font-bold leading-tight line-clamp-2 tracking-tight text-white/95"
            style={{ fontSize: size === 'sm' ? '9px' : size === 'md' ? '10px' : '12px' }}
          >
            {name}
          </div>
        </>
      )}
    </div>
  );
};
