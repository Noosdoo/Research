'use client';

import { useEffect, useRef, useState, useCallback, useMemo, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useGameStore } from '@/store/gameStore';
import { SITES } from '@/lib/sites';

import SiteCard from '@/components/SiteCard';
import Timer from '@/components/Timer';
import GameSidebar from '@/components/GameSidebar';
import MobileStatusBar from '@/components/MobileStatusBar';
import StealNotification from '@/components/StealNotification';
import ResultSummary from '@/components/ResultSummary';
import Confetti from '@/components/Confetti';

function SingleGameInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const aiCount = Math.min(3, Math.max(1, Number(searchParams.get('ai') ?? '1')));
  const duration = Math.min(180, Math.max(30, Number(searchParams.get('duration') ?? '180')));

  const {
    phase, timeLeft, players, myPlayerId,
    sitesState, stealEvents, expireEvents,
    initGame, tickTimer, processAITick, clearStealEvent, clearExpireEvent,
  } = useGameStore();

  const [now, setNow] = useState(Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const aiRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const shakeRef = useRef<HTMLDivElement>(null);
  const lastEventId = useRef('');

  // 奪われたとき画面シェイク
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

  // /visit/[id] から戻ってきた場合はリセットしない
  useEffect(() => {
    if (useGameStore.getState().phase !== 'lobby') return;
    initGame(aiCount, duration);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // timer tick + now update (single interval drives both)
  useEffect(() => {
    if (phase !== 'playing') return;
    timerRef.current = setInterval(() => { tickTimer(); setNow(Date.now()); }, 200);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [phase, tickTimer]);

  // AI ticks — read player ids fresh from the store so the interval is not
  // torn down/recreated on every `players` change (which would starve AI turns)
  useEffect(() => {
    if (phase !== 'playing') return;
    aiRef.current = setInterval(() => {
      const { players: pl, myPlayerId: me } = useGameStore.getState();
      for (const id of pl.keys()) {
        if (id !== me) processAITick(id);
      }
    }, 1800);
    return () => { if (aiRef.current) clearInterval(aiRef.current); };
  }, [phase, processAITick]);

  // Navigate to visit page on card click
  const handleVisit = useCallback((siteId: string) => {
    router.push(`/visit/${siteId}`);
  }, [router]);

  // Shuffle once on mount — component remounts on every return from /visit, giving a fresh order
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

  const [cookieCleared, setCookieCleared] = useState(false);
  async function handleClearCookies() {
    await fetch('/api/clear-cookies', { method: 'POST' });
    // JS-accessible cookies も念のため消す
    document.cookie.split(';').forEach(c => {
      const name = c.split('=')[0].trim();
      document.cookie = `${name}=; Max-Age=0; path=/`;
    });
    setCookieCleared(true);
  }

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

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => {
                const s = useGameStore.getState();
                initGame(s.aiCount, s.gameDuration);
              }}
              className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-colors"
            >
              もう一度
            </button>
            <button
              type="button"
              onClick={() => { useGameStore.getState().resetToLobby(); router.push('/'); }}
              className="flex-1 py-3 bg-gray-700 hover:bg-gray-600 text-white font-bold rounded-xl transition-colors"
            >
              メニューへ
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={shakeRef} className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800">
        <span className="text-white font-black text-xl whitespace-nowrap">🍪<span className="hidden sm:inline"> Cookie Heist</span></span>
        <Timer timeLeft={timeLeft} />
        <div className="flex items-center gap-3">
          <span className="text-white font-black text-base">{me ? `${me.score}pt` : ''}</span>
          <button
            type="button"
            onClick={() => { useGameStore.getState().resetToLobby(); router.push('/'); }}
            className="text-xs font-bold px-3 py-1 rounded-lg bg-gray-700 hover:bg-red-700 text-gray-200 hover:text-white transition-colors"
          >
            退出
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Site map */}
        <div className="flex-1 flex flex-col overflow-hidden p-3 gap-3">
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2">
              {shuffledSites.map(site => {
                const ss = sitesState.get(site.id)!;
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
        <GameSidebar players={players} myPlayerId={myPlayerId} />
      </div>

      {/* Mobile bottom bar (ranking + expandable own status) */}
      <MobileStatusBar players={players} myPlayerId={myPlayerId} />

      <StealNotification
        events={stealEvents}
        expireEvents={expireEvents}
        players={players}
        myPlayerId={myPlayerId}
        onDismiss={clearStealEvent}
        onDismissExpire={clearExpireEvent}
      />
    </div>
  );
}

export default function SinglePage() {
  return (
    <Suspense>
      <SingleGameInner />
    </Suspense>
  );
}
