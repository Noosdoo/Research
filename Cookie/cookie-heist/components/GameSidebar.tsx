'use client';

import type { Player } from '@/lib/types';
import Ranking from '@/components/Ranking';
import PlayerStatus from '@/components/PlayerStatus';

interface Props {
  players: Map<string, Player>;
  myPlayerId: string;
}

// PC幅の右サイドバー（ランキング + 自分の状態）。シングル/オンライン共用。
export default function GameSidebar({ players, myPlayerId }: Props) {
  const allPlayers = [...players.values()];
  const me = players.get(myPlayerId);

  return (
    <div className="max-md:hidden w-56 flex-shrink-0 border-l border-gray-800 flex flex-col gap-3 p-3 overflow-y-auto">
      <Ranking players={allPlayers} myPlayerId={myPlayerId} />
      {me && <PlayerStatus player={me} />}
    </div>
  );
}
