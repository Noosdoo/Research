'use client';

import type { Player } from '@/lib/types';
import { SITES } from '@/lib/sites';

interface Props {
  player: Player;
}

export default function PlayerStatus({ player }: Props) {
  const owned = [...player.cookies.values()];
  const ownedSites = owned.map(c => SITES.find(s => s.id === c.siteId)).filter(Boolean);

  return (
    <div className="bg-gray-800 rounded-lg p-3 flex flex-col gap-2 text-xs">
      <h2 className="text-sm font-bold text-gray-300">📊 あなたの状態</h2>

      <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-gray-300">
        <span>スコア</span>
        <span className="text-green-300 font-bold">{player.score}pt</span>
        <span>訪問回数</span>
        <span className="text-white">{player.stats.visitCount}</span>
        <span>奪取 / 奪われ</span>
        <span className="text-white">
          {player.stats.stealCount} / {player.stats.stolenCount}
        </span>
      </div>

      {ownedSites.length > 0 && (
        <>
          <hr className="border-gray-700" />
          <div>
            <p className="text-gray-400 mb-1">所持 Cookie</p>
            <div className="flex flex-col gap-0.5 max-h-40 overflow-y-auto">
              {owned.map(c => {
                const site = SITES.find(s => s.id === c.siteId);
                return (
                  <div key={c.siteId} className="flex justify-between items-center">
                    <span className="text-gray-200">
                      {site?.iconEmoji} {c.cookieName}
                    </span>
                    <span
                      className={c.points >= 0 ? 'text-green-300' : 'text-red-400'}
                    >
                      {c.points > 0 ? `+${c.points}` : c.points}pt
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
