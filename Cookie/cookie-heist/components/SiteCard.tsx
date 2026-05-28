'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import type { Site, SiteState, Player } from '@/lib/types';

const RARITY_BORDER: Record<string, string> = {
  common:    'border-gray-600',
  uncommon:  'border-blue-500',
  rare:      'border-purple-400',
  legendary: 'border-yellow-400',
};

const RARITY_BG: Record<string, string> = {
  common:    'bg-gray-800',
  uncommon:  'bg-blue-950',
  rare:      'bg-purple-950',
  legendary: 'bg-amber-950',
};

const RARITY_BADGE: Record<string, string> = {
  common:    'bg-gray-700 text-gray-300',
  uncommon:  'bg-blue-800 text-blue-200',
  rare:      'bg-purple-800 text-purple-200',
  legendary: 'bg-yellow-700 text-yellow-100',
};

const RARITY_LABEL: Record<string, string> = {
  common:    '通常',
  uncommon:  '中レア',
  rare:      '高レア',
  legendary: '超レア',
};

const TEMPLATE_LABEL: Record<string, string> = {
  'consent-button': '同意',
  'ad-popup':       '広告',
  'login-form':     'ログイン',
  'survey':         'アンケート',
  'quiz':           'クイズ',
};

interface Props {
  site: Site;
  siteState: SiteState;
  players: Map<string, Player>;
  myPlayerId: string;
  onVisit: () => void;
}

export default function SiteCard({ site, siteState, players, myPlayerId, onVisit }: Props) {
  const owners   = siteState.ownerIds.map(id => players.get(id)).filter(Boolean) as Player[];
  const visitors = siteState.currentVisitorIds.map(id => players.get(id)).filter(Boolean) as Player[];
  const isMine   = siteState.ownerIds.includes(myPlayerId);

  const isHoneypot  = !!site.isHoneypot;
  const isLegendary = site.rarity === 'legendary' && !isHoneypot;

  // Countdown for short-lived owned cookies (maxAge ≤ 120s)
  const myOwnedCookie = isMine ? players.get(myPlayerId)?.cookies.get(site.id) : undefined;
  const maxAge = site.cookie.attributes.maxAge;
  const showCountdown = myOwnedCookie != null && maxAge != null && maxAge <= 120;
  const acquiredAtMs = myOwnedCookie?.acquiredAt instanceof Date
    ? myOwnedCookie.acquiredAt.getTime()
    : myOwnedCookie?.acquiredAt != null
    ? new Date(myOwnedCookie.acquiredAt as unknown as string).getTime()
    : null;
  const [remaining, setRemaining] = useState<number | null>(null);
  useEffect(() => {
    if (!showCountdown || acquiredAtMs == null) { setRemaining(null); return; }
    const tick = () => setRemaining(Math.max(0, maxAge! - (Date.now() - acquiredAtMs) / 1000));
    tick();
    const id = setInterval(tick, 200);
    return () => clearInterval(id);
  }, [showCountdown, acquiredAtMs, maxAge]);

  const borderClass = isHoneypot ? 'border-red-700'  : RARITY_BORDER[site.rarity];
  const bgClass     = isHoneypot ? 'bg-red-950'      : RARITY_BG[site.rarity];
  const badgeClass  = isHoneypot ? 'bg-red-800 text-red-200' : RARITY_BADGE[site.rarity];
  const badgeLabel  = isHoneypot ? '⚠️ 危険' : RARITY_LABEL[site.rarity];

  const glowClass = isLegendary ? 'glow-legendary'
    : isMine      ? 'glow-mine'
    : isHoneypot  ? 'glow-honeypot'
    : '';

  return (
    <motion.button
      whileHover={{ scale: 1.04 }}
      whileTap={{ scale: 0.96 }}
      onClick={onVisit}
      className={[
        'relative flex flex-col gap-1 p-2 rounded-lg border-2 text-left cursor-pointer transition-all min-h-[96px]',
        borderClass, bgClass, glowClass,
        isLegendary ? 'animate-pulse-slow' : '',
      ].join(' ')}
    >
      {/* rarity / warning badge */}
      <span className={`absolute top-1 right-1 text-[9px] font-bold px-1 py-0.5 rounded ${badgeClass}`}>
        {badgeLabel}
      </span>

      {/* owned-by-me indicator */}
      {isMine && (
        <span className="absolute top-1 left-1 text-[10px] leading-none text-green-400 font-black">✓</span>
      )}

      {/* icon + name */}
      <div className="flex items-center gap-1 mt-1">
        <span className="text-xl leading-none">{site.isMystery ? '❓' : (site.iconEmoji ?? '🌐')}</span>
        <span className="text-xs font-bold truncate max-w-[72px] text-white leading-tight">
          {site.isMystery ? '???' : site.name}
        </span>
      </div>

      {/* points */}
      {site.isMystery || site.template === 'ad-popup' ? (
        <span className="text-base font-black leading-none text-yellow-300">???pt</span>
      ) : site.cookie.points < 0 ? (
        <span className="text-base font-black leading-none text-red-400">{site.cookie.points}pt</span>
      ) : (
        <span className={`text-base font-black leading-none ${isLegendary ? 'text-yellow-300' : 'text-green-300'}`}>
          +{site.cookie.points}pt
        </span>
      )}

      {/* expiry countdown */}
      {remaining !== null && (
        <span className={`text-[10px] font-black tabular-nums ${remaining <= 3 ? 'text-red-400 animate-pulse' : 'text-amber-300'}`}>
          ⏰ {Math.ceil(remaining)}秒
        </span>
      )}

      {/* template label */}
      <span className="text-[10px] text-gray-500 mt-auto">
        {TEMPLATE_LABEL[site.template]}
      </span>

      {/* owner avatars */}
      {owners.length > 0 && (
        <div className="flex gap-0.5 flex-wrap">
          {owners.map(p => (
            <span
              key={p.id}
              title={p.name}
              className={`w-3 h-3 rounded-full border ${isMine && p.id === myPlayerId ? 'border-green-400' : 'border-white/60'}`}
              style={{ '--dot-color': p.color, background: 'var(--dot-color)' } as React.CSSProperties}
            />
          ))}
        </div>
      )}

      {/* visiting indicators */}
      {visitors.length > 0 && (
        <div className="flex gap-0.5 flex-wrap items-center">
          <span className="text-[9px] text-yellow-400 animate-pulse">訪問中</span>
          {visitors.map(p => (
            <span
              key={p.id}
              title={p.name}
              className="w-2 h-2 rounded-full border border-yellow-400 animate-pulse"
              style={{ '--dot-color': p.color, background: 'var(--dot-color)' } as React.CSSProperties}
            />
          ))}
        </div>
      )}

      {/* loading bar */}
      {visitors.length > 0 && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 overflow-hidden rounded-b-md">
          <motion.div
            className="absolute inset-y-0 w-1/2 bg-yellow-400 opacity-80"
            animate={{ x: ['-100%', '200%'] }}
            transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
          />
        </div>
      )}
    </motion.button>
  );
}
