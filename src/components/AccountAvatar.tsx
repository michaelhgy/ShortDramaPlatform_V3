import React, { useEffect, useState } from 'react';

const retryDelays = [800, 2400];

function AvatarImage({ name, url }: { name: string; url: string; key?: string }) {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!failed) return;
    if (attempt < retryDelays.length) {
      const timer = window.setTimeout(() => { setAttempt(n => n + 1); setFailed(false); }, retryDelays[attempt]);
      return () => window.clearTimeout(timer);
    }
    // After bounded retries, try again when the connection/window returns.
    const retry = () => { setAttempt(0); setFailed(false); };
    window.addEventListener('online', retry);
    window.addEventListener('focus', retry);
    return () => { window.removeEventListener('online', retry); window.removeEventListener('focus', retry); };
  }, [failed, attempt]);
  // Only local cache URLs accept a retry query. Never alter signed remote URLs.
  const source = attempt && url.startsWith('/api/v3/drama-catalog/accounts/')
    ? `${url}${url.includes('?') ? '&' : '?'}avatar_retry=${attempt}` : url;
  return failed ? <>{name.slice(0, 1)}</> : <img key={attempt} src={source} alt={`${name}的头像`} loading="lazy" className="w-full h-full object-cover" onError={() => setFailed(true)} />;
}

export function AccountAvatar({ name, url, className = 'w-10 h-10' }: { name: string; url?: string; className?: string }) {
  return <span className={`${className} rounded-full overflow-hidden shrink-0 bg-slate-100 border border-black/[0.06] inline-flex items-center justify-center font-extrabold text-sm text-slate-700`}>
    {url ? <AvatarImage key={url} name={name} url={url} /> : name.slice(0, 1)}
  </span>;
}
