'use client';

import { useState } from 'react';
import type { Player } from '@/lib/types';
import PlayerStatus from '@/components/PlayerStatus';

interface Props {
  players: Map<string, Player>;
  myPlayerId: string;
}

const MEDALS = ['🥇', '🥈', '🥉'];

// スマホ幅の下部バー。PCのサイドバーと情報を揃えるため、ランキングに加えて
// 「自分の状態」（所持Cookie・統計）をタップで開閉できるようにする。
export default function MobileStatusBar({ players, myPlayerId }: Props) {
  const [open, setOpen] = useState(false);
  const me = players.get(myPlayerId);
  const sorted = [...players.values()].sort((a, b) => b.score - a.score);

  return (
    <div className="md:hidden border-t border-gray-800 bg-gray-900">
      {/* 展開時: 自分の状態（PCサイドバーと同じ PlayerStatus を表示） */}
      {open && me && (
        <div className="p-3 border-b border-gray-800 max-h-[45vh] overflow-y-auto">
          <PlayerStatus player={me} />
        </div>
      )}

      <div className="px-3 py-2 flex items-center gap-2">
        <div className="flex items-center gap-2 overflow-x-auto flex-1">
          {sorted.map((p, i) => (
            <div key={p.id} className="flex items-center gap-1 whitespace-nowrap text-xs">
              <span>{MEDALS[i] ?? `${i + 1}.`}</span>
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color }} />
              <span className={p.id === myPlayerId ? 'text-blue-300 font-bold' : 'text-gray-300'}>{p.name}</span>
              <span className="text-green-300 font-bold">{p.score}pt</span>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="flex-shrink-0 text-xs font-bold px-2 py-1 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors"
        >
          {open ? '閉じる ▼' : '自分の状態 ▲'}
        </button>
      </div>
    </div>
  );
}
