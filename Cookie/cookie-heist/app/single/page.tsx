'use client';

import { useEffect, useRef, useState, useCallback, useMemo, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useGameStore } from '@/store/gameStore';
import { SITES } from '@/lib/sites';
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
import CookieInspector from '@/components/CookieInspector';

function SingleGameInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const aiCount = Math.min(3, Math.max(1, Number(searchParams.get('ai') ?? '1')));
  const duration = Math.min(180, Math.max(30, Number(searchParams.get('duration') ?? '180')));

  const {
    phase, timeLeft, players, myPlayerId,
    sitesState, stealEvents,
    initGame, tickTimer, processAITick, clearStealEvent,
  } = useGameStore();

  const [category, setCategory] = useState<SiteCategory | 'all'>('all');
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
      if (!el) return;
      el.classList.remove('screen-shake');
      void el.offsetWidth; // reflow でアニメーションをリセット
      el.classList.add('screen-shake');
      setTimeout(() => el.classList.remove('screen-shake'), 600);
    }
  }, [stealEvents, myPlayerId]);

  // /visit/[id] から戻ってきた場合はリセットしない
  useEffect(() => {
    if (useGameStore.getState().phase !== 'lobby') return;
    initGame(aiCount, duration);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // timer tick
  useEffect(() => {
    if (phase !== 'playing') return;
    timerRef.current = setInterval(() => tickTimer(), 200);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [phase, tickTimer]);

  // AI ticks
  useEffect(() => {
    if (phase !== 'playing') return;
    const aiIds = [...players.keys()].filter(id => id !== myPlayerId);
    aiRef.current = setInterval(() => {
      aiIds.forEach(id => processAITick(id));
    }, 3000);
    return () => { if (aiRef.current) clearInterval(aiRef.current); };
  }, [phase, players, myPlayerId, processAITick]);

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

  const filteredSites = shuffledSites.filter(s =>
    category === 'all' || s.category === category
  );

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
                <span className={`w-3 h-3 rounded-full flex-shrink-0 ${COLOR_BG[p.color] ?? 'bg-gray-400'}`} />
                <span className="text-white font-semibold flex-1">{p.name}</span>
                <span className="text-green-300 font-bold">{p.score}pt</span>
                <span className="text-gray-400 text-sm">{p.cookies.size}種</span>
              </div>
            ))}
          </div>

          {me && (
            <div className="bg-gray-800 rounded-lg p-4 text-sm text-gray-300 flex flex-col gap-3">
              <div>
                <p className="font-semibold text-white mb-1">📊 あなたの統計</p>
                <p>訪問回数: {me.stats.visitCount}</p>
                <p>奪取: {me.stats.stealCount} / 喪失: {me.stats.stolenCount}</p>
              </div>

              <CookieInspector cookies={me.cookies} />

              <div>
                <p className="text-xs text-gray-500 text-center">
                  F12 → Application → Cookies で<br />ブラウザに保存されたCookieを確認できます
                </p>
                <button
                  type="button"
                  onClick={handleClearCookies}
                  disabled={cookieCleared}
                  className="mt-2 w-full py-2 bg-red-700 hover:bg-red-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs font-bold rounded-lg transition-colors"
                >
                  {cookieCleared ? '✅ Cookieをリセット済み' : '🗑️ ブラウザのCookieをリセット'}
                </button>
              </div>
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => initGame(aiCount, duration)}
              className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-colors"
            >
              もう一度
            </button>
            <button
              type="button"
              onClick={() => router.push('/')}
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
        <span className="text-white font-black text-xl whitespace-nowrap">🍪 Cookie Heist</span>
        <Timer timeLeft={timeLeft} />
        <span className="text-gray-400 text-sm">{me ? `${me.score}pt` : ''}</span>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Site map */}
        <div className="flex-1 flex flex-col overflow-hidden p-3 gap-3">
          <CategoryFilter selected={category} onChange={setCategory} />

          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-2">
              {filteredSites.map(site => {
                const ss = sitesState.get(site.id)!;
                return (
                  <SiteCard
                    key={site.id}
                    site={site}
                    siteState={ss}
                    players={players}
                    myPlayerId={myPlayerId}
                    onVisit={() => handleVisit(site.id)}
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
        players={players}
        myPlayerId={myPlayerId}
        onDismiss={clearStealEvent}
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
