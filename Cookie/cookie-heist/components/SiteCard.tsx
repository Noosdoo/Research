'use client';

import { motion } from 'framer-motion';
import type { Site, SiteState, Player } from '@/lib/types';

const RARITY_BORDER: Record<string, string> = {
  common: 'border-gray-500',
  uncommon: 'border-blue-500',
  rare: 'border-purple-500',
  legendary: 'border-yellow-400',
};

const RARITY_BG: Record<string, string> = {
  common: 'bg-gray-800',
  uncommon: 'bg-blue-950',
  rare: 'bg-purple-950',
  legendary: 'bg-yellow-950',
};

const RARITY_LABEL: Record<string, string> = {
  common: '通常',
  uncommon: '中レア',
  rare: '高レア',
  legendary: '超レア',
};

const TEMPLATE_LABEL: Record<string, string> = {
  'consent-button': '同意',
  'ad-popup': '広告',
  'login-form': 'ログイン',
  'survey': 'アンケート',
  'quiz': 'クイズ',
};

interface Props {
  site: Site;
  siteState: SiteState;
  players: Map<string, Player>;
  myPlayerId: string;
  onVisit: () => void;
}

export default function SiteCard({
  site,
  siteState,
  players,
  myPlayerId,
  onVisit,
}: Props) {
  const owners = siteState.ownerIds.map(id => players.get(id)).filter(Boolean) as Player[];
  const visitors = siteState.currentVisitorIds.map(id => players.get(id)).filter(Boolean) as Player[];
  const isMine = siteState.ownerIds.includes(myPlayerId);

  return (
    <motion.button
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      onClick={onVisit}
      className={[
        'relative flex flex-col gap-1 p-2 rounded-lg border-2 text-left cursor-pointer hover:brightness-110 transition-all',
        RARITY_BORDER[site.rarity],
        RARITY_BG[site.rarity],
        isMine ? 'brightness-110' : '',
      ].join(' ')}
    >
      {/* rarity badge */}
      <span className="absolute top-1 right-1 text-[9px] text-gray-400">
        {RARITY_LABEL[site.rarity]}
      </span>

      {/* icon + name */}
      <div className="flex items-center gap-1">
        <span className="text-xl leading-none">{site.isMystery ? '❓' : (site.iconEmoji ?? '🌐')}</span>
        <span className="text-xs font-bold truncate max-w-[80px] text-white">
          {site.isMystery ? '???' : site.name}
        </span>
      </div>

      {/* points */}
      {site.isMystery || site.template === 'survey' ? (
        <span className="text-lg font-black leading-none text-yellow-300">???pt</span>
      ) : (
        <span
          className={[
            'text-lg font-black leading-none',
            site.cookie.points < 0 ? 'text-red-400' : 'text-green-300',
          ].join(' ')}
        >
          {site.cookie.points > 0 ? `+${site.cookie.points}` : site.cookie.points}pt
        </span>
      )}

      {/* template label */}
      <span className="text-[10px] text-gray-400">
        {TEMPLATE_LABEL[site.template]}
      </span>

      {/* owner avatars */}
      {owners.length > 0 && (
        <div className="flex gap-0.5 flex-wrap">
          {owners.map(p => (
            <span
              key={p.id}
              title={p.name}
              className="w-3 h-3 rounded-full border border-white"
              style={{ background: p.color }}
            />
          ))}
        </div>
      )}

      {/* visiting indicators (AI) */}
      {visitors.length > 0 && (
        <div className="flex gap-0.5 flex-wrap items-center">
          <span className="text-[9px] text-yellow-400 animate-pulse">訪問中</span>
          {visitors.map(p => (
            <span
              key={p.id}
              title={p.name}
              className="w-2 h-2 rounded-full border border-yellow-400 animate-pulse"
              style={{ background: p.color }}
            />
          ))}
        </div>
      )}
    </motion.button>
  );
}
