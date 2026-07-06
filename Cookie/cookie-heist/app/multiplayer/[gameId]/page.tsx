'use client';

import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useGameStore } from '@/store/gameStore';
import { SITES } from '@/lib/sites';
import { getSocket } from '@/lib/socket';

import SiteCard from '@/components/SiteCard';
import Timer from '@/components/Timer';
import GameSidebar from '@/components/GameSidebar';
import MobileStatusBar from '@/components/MobileStatusBar';
import StealNotification from '@/components/StealNotification';
import ResultSummary from '@/components/ResultSummary';
import Confetti from '@/components/Confetti';

export default function MultiplayerGamePage() {
  const { gameId } = useParams<{ gameId: string }>();
  const router = useRouter();

  const {
    phase, timeLeft, players, myPlayerId,
    sitesState, stealEvents, onlineGameId,
    applyServerUpdate, setTimeLeft, exitOnlineMode, clearStealEvent,
  } = useGameStore();

  const [now, setNow] = useState(Date.now());
  const [cookieCleared, setCookieCleared] = useState(false);
  const socket = getSocket();
  const shakeRef = useRef<HTMLDivElement>(null);
  const lastEventId = useRef('');

  // 奪われたとき画面シェイク（スマホは端末も振動）
  useEffect(() => {
    if (stealEvents.length === 0) return;
    const last = stealEvents[stealEvents.length - 1];
    if (last.id === lastEventId.current) return;
    lastEventId.current = last.id;
    if (last.from === myPlayerId) {
      const el = shakeRef.current;
      if (el) {
        el.classList.remove('screen-shake');
        void el.offsetWidth; // reflow でアニメーションをリセット
        el.classList.add('screen-shake');
        setTimeout(() => el.classList.remove('screen-shake'), 600);
      }
      if (typeof navigator !== 'undefined' && navigator.vibrate) navigator.vibrate(120);
    }
  }, [stealEvents, myPlayerId]);

  async function handleClearCookies() {
    await fetch('/api/clear-cookies', { method: 'POST' });
    document.cookie.split(';').forEach(c => {
      const name = c.split('=')[0].trim();
      document.cookie = `${name}=; Max-Age=0; path=/`;
    });
    setCookieCleared(true);
  }

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
    // マウント時（/visit から戻った直後を含む）に最新状態を要求する。
    // 訪問中はこのページがアンマウントされ state-update を取りこぼすため、
    // 戻った直後に所持Cookie等の表示が古いままになるのを防ぐ。
    socket.emit('game:request-sync');

    return () => {
      socket.off('game:state-update', onStateUpdate);
      socket.off('game:tick', onTick);
      socket.off('game:ended', onEnded);
    };
  }, [socket, applyServerUpdate, setTimeLeft]);

  const handleVisit = useCallback((siteId: string) => {
    router.push(`/visit/${siteId}`);
  }, [router]);

  // 訪問から戻るたびに再マウントされるので、シングル（AI対戦）と同様にマップ順をシャッフルする
  const shuffledSites = useMemo(() => {
    const arr = [...SITES];
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const me = players.get(myPlayerId);
  const allPlayers = [...players.values()];

  // Result screen
  if (phase === 'result') {
    const sorted = [...allPlayers].sort((a, b) => b.score - a.score);
    const iWon = sorted[0]?.id === myPlayerId;

    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
        <Confetti active={iWon} />
        <div className="max-w-lg w-full bg-gray-900 rounded-2xl p-8 flex flex-col gap-6 max-h-[90vh] overflow-y-auto">
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
                <span className="text-xl w-8 text-center flex-shrink-0">{['🥇', '🥈', '🥉'][i] ?? `${i + 1}`}</span>
                <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: p.color }} />
                <span className="text-white font-semibold flex-1">{p.name}</span>
                <span className="text-green-300 font-bold">{p.score}pt</span>
                <span className="text-gray-400 text-sm">{p.cookies.size}種</span>
              </div>
            ))}
          </div>

          {me && (
            <ResultSummary me={me} onClearCookies={handleClearCookies} cookieCleared={cookieCleared} />
          )}

          <button
            type="button"
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
    <div ref={shakeRef} className="min-h-screen bg-gray-950 flex flex-col">
      <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800">
        <span className="text-white font-black text-xl whitespace-nowrap">🍪<span className="hidden sm:inline"> Cookie Heist</span></span>
        <Timer timeLeft={timeLeft} />
        <div className="flex items-center gap-3">
          <span className="text-xs text-purple-400 font-bold bg-purple-900/40 px-2 py-0.5 rounded">
            オンライン
          </span>
          <span className="text-white font-black text-base">{me ? `${me.score}pt` : ''}</span>
          <button
            type="button"
            onClick={() => { exitOnlineMode(); router.push('/'); }}
            className="text-xs font-bold px-3 py-1 rounded-lg bg-gray-700 hover:bg-red-700 text-gray-200 hover:text-white transition-colors"
          >
            退出
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden p-3 gap-3">
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2">
              {shuffledSites.map(site => {
                // サーバーはサイト状態を訪問時に遅延生成するため、未訪問サイトは空状態で描画する
                const ss = sitesState.get(site.id) ?? { siteId: site.id, ownerIds: [], currentVisitorIds: [] };
                return (
                  <SiteCard
                    key={site.id}
                    site={site}
                    siteState={ss}
                    players={players}
                    myPlayerId={myPlayerId}
                    onVisit={() => handleVisit(site.id)}
                    now={now}
                    showExpiryCountdown={false}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {/* Sidebar: PC only */}
        <GameSidebar players={players} myPlayerId={myPlayerId} />
      </div>

      {/* Mobile bottom bar (ranking + expandable own status) */}
      <MobileStatusBar players={players} myPlayerId={myPlayerId} />

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
