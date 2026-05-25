'use client';

import type { Player } from '@/lib/types';
import { SITES } from '@/lib/sites';

interface Props {
  players: Player[];
  myPlayerId: string;
}

const MEDALS = ['🥇', '🥈', '🥉'];

export default function Ranking({ players, myPlayerId }: Props) {
  const sorted = [...players].sort((a, b) => b.score - a.score);

  return (
    <div className="flex flex-col gap-1">
      <h2 className="text-sm font-bold text-gray-300 mb-1">🏆 ランキング</h2>
      {sorted.map((p, i) => {
        const isMe = p.id === myPlayerId;
        const ownedSites = [...p.cookies.keys()]
          .map(id => SITES.find(s => s.id === id))
          .filter(Boolean);

        return (
          <div
            key={p.id}
            className={[
              'rounded p-2 text-xs',
              isMe ? 'bg-blue-900 border border-blue-500' : 'bg-gray-800',
            ].join(' ')}
          >
            <div className="flex items-center gap-1 font-semibold">
              <span>{MEDALS[i] ?? `${i + 1}位`}</span>
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: p.color }}
              />
              <span className="text-white truncate max-w-[80px]">{p.name}</span>
              <span className="ml-auto text-green-300 font-bold">{p.score}pt</span>
            </div>
            {ownedSites.length > 0 && (
              <div className="text-gray-400 mt-0.5 truncate">
                {ownedSites.map(s => s!.iconEmoji ?? '🌐').join(' ')}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
