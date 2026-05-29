'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useGameStore } from '@/store/gameStore';
import { SITES } from '@/lib/sites';
import { getSocket } from '@/lib/socket';
import type { SiteCategory } from '@/lib/types';

import SiteCard from '@/components/SiteCard';

const COLOR_BG: Record<string, string> = {
  '#3b82f6': 'bg-blue-500',
  '#ef4444': 'bg-red-500',
  '#22c55e': 'bg-green-500',
  '#f59e0b': 'bg-amber-500',
};
import Timer from '@/components/Timer';
import Ranking from '@/components/Ranking';
import PlayerStatus from '@/components/PlayerStatus';
import CategoryFilter from '@/components/CategoryFilter';
import StealNotification from '@/components/StealNotification';

export default function MultiplayerGamePage() {
  const { gameId } = useParams<{ gameId: string }>();
  const router = useRouter();

  const {
    phase, timeLeft, players, myPlayerId,
    sitesState, stealEvents, onlineGameId,
    applyServerUpdate, setTimeLeft, exitOnlineMode, clearStealEvent,
  } = useGameStore();

  const [category, setCategory] = useState<SiteCategory | 'all'>('all');
  const [now, setNow] = useState(Date.now());
  const socket = getSocket();

  // now tick for SiteCard countdown (single shared interval)
  useEffect(() => {
    if (phase !== 'playing') return;
    const id = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(id);
  }, [phase]);

  // Redirect if not in the right game
  useEffect(() => {
    if (onlineGameId !== gameId) {
      router.replace('/');
    }
  }, [gameId, onlineGameId, router]);

  // Socket event listeners for game state
  useEffect(() => {
    function onStateUpdate(data: Parameters<typeof applyServerUpdate>[0]) {
      useGameStore.getState().applyServerUpdate(data);
    }
    function onTick({ timeLeft }: { timeLeft: number }) {
      useGameStore.getState().setTimeLeft(timeLeft);
    }
    function onEnded(data: Parameters<typeof applyServerUpdate>[0]) {
      useGameStore.getState().applyServerUpdate(data);
      useGameStore.getState().endGame();
    }

    socket.on('game:state-update', onStateUpdate);
    socket.on('game:tick', onTick);
    socket.on('game:ended', onEnded);

    return () => {
      socket.off('game:state-update', onStateUpdate);
      socket.off('game:tick', onTick);
      socket.off('game:ended', onEnded);
    };
  }, [socket, applyServerUpdate, setTimeLeft]);

  const handleVisit = useCallback((siteId: string) => {
    router.push(`/visit/${siteId}`);
  }, [router]);

  const filteredSites = SITES.filter(s => category === 'all' || s.category === category);
  const me = players.get(myPlayerId);
  const allPlayers = [...players.values()];

  // Result screen
  if (phase === 'result') {
    const sorted = [...allPlayers].sort((a, b) => b.score - a.score);
    const iWon = sorted[0]?.id === myPlayerId;

    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
        <div className="max-w-lg w-full bg-gray-900 rounded-2xl p-8 flex flex-col gap-6">
          <h1 className="text-3xl font-black text-white text-center">
            {iWon ? '🎉 勝利！' : '😢 ゲーム終了'}
          </h1>

          <div className="flex flex-col gap-2">
            {sorted.map((p, i) => (
              <div
                key={p.id}
                className={[
                  'flex items-center gap-3 p-3 rounded-lg',
                  p.id === myPlayerId ? 'bg-blue-900 border border-blue-500' : 'bg-gray-800',
                ].join(' ')}
              >
                <span className="text-xl">{['🥇', '🥈', '🥉'][i] ?? `${i + 1}`}</span>
                <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: p.color }} />
                <span className="text-white font-semibold flex-1">{p.name}</span>
                <span className="text-green-300 font-bold">{p.score}pt</span>
                <span className="text-gray-400 text-sm">{p.cookies.size}種</span>
              </div>
            ))}
          </div>

          {me && (
            <div className="bg-gray-800 rounded-lg p-4 text-sm text-gray-300">
              <p className="font-semibold text-white mb-2">📊 あなたの統計</p>
              <p>訪問回数: {me.stats.visitCount}</p>
              <p>奪取: {me.stats.stealCount} / 喪失: {me.stats.stolenCount}</p>
            </div>
          )}

          <button
            onClick={() => { exitOnlineMode(); router.push('/'); }}
            className="py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-colors"
          >
            トップに戻る
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800">
        <span className="text-white font-black text-xl whitespace-nowrap">🍪 Cookie Heist</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-purple-400 font-bold bg-purple-900/40 px-2 py-0.5 rounded">
            オンライン
          </span>
          <Timer timeLeft={timeLeft} />
        </div>
        <span className="text-gray-400 text-sm">{me ? `${me.score}pt` : ''}</span>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden p-3 gap-3">
          <CategoryFilter selected={category} onChange={setCategory} />
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2">
              {filteredSites.map(site => {
                const ss = sitesState.get(site.id);
                if (!ss) return null;
                return (
                  <SiteCard
                    key={site.id}
                    site={site}
                    siteState={ss}
                    players={players}
                    myPlayerId={myPlayerId}
                    onVisit={() => handleVisit(site.id)}
                    now={now}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {/* Sidebar: PC only */}
        <div className="max-md:hidden w-56 flex-shrink-0 border-l border-gray-800 flex flex-col gap-3 p-3 overflow-y-auto">
          <Ranking players={allPlayers} myPlayerId={myPlayerId} />
          {me && <PlayerStatus player={me} />}
        </div>
      </div>

      {/* Mobile ranking bar */}
      <div className="md:hidden border-t border-gray-800 bg-gray-900 px-3 py-2 flex items-center gap-2 overflow-x-auto">
        {[...allPlayers].sort((a, b) => b.score - a.score).map((p, i) => (
          <div key={p.id} className="flex items-center gap-1 whitespace-nowrap text-xs">
            <span>{['🥇','🥈','🥉'][i] ?? `${i+1}.`}</span>
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${COLOR_BG[p.color] ?? 'bg-gray-400'}`} />
            <span className={p.id === myPlayerId ? 'text-blue-300 font-bold' : 'text-gray-300'}>{p.name}</span>
            <span className="text-green-300 font-bold">{p.score}pt</span>
          </div>
        ))}
      </div>

      <StealNotification
        events={stealEvents}
        expireEvents={[]}
        players={players}
        myPlayerId={myPlayerId}
        onDismiss={clearStealEvent}
        onDismissExpire={() => {}}
      />
    </div>
  );
}
