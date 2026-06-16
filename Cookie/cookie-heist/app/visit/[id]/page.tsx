'use client';

import { useEffect, useCallback, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { useGameStore } from '@/store/gameStore';
import { getSiteById } from '@/lib/sites';
import { getSocket } from '@/lib/socket';

import ConsentButton from '@/components/templates/ConsentButton';
import AdPopup from '@/components/templates/AdPopup';
import LoginForm from '@/components/templates/LoginForm';
import Survey from '@/components/templates/Survey';
import Quiz from '@/components/templates/Quiz';
import Timer from '@/components/Timer';

export default function VisitPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const site = getSiteById(id);
  const completed = useRef(false);

  // 取得演出（Cookie獲得 / 罠だった）。表示中はマップへ戻るのを少し待つ。
  const [acquired, setAcquired] = useState<{ points: number } | null>(null);
  const navTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { phase, timeLeft, completeVisit, mode, onlineGameId } = useGameStore();
  const isOnline = mode === 'online';
  const returnUrl = isOnline ? `/multiplayer/${onlineGameId}` : '/single';

  const goBack = useCallback(() => {
    if (navTimer.current) { clearTimeout(navTimer.current); navTimer.current = null; }
    router.push(returnUrl);
  }, [router, returnUrl]);

  useEffect(() => () => { if (navTimer.current) clearTimeout(navTimer.current); }, []);

  // Local timer tick (local mode only)
  useEffect(() => {
    if (phase !== 'playing' || isOnline) return;
    const interval = setInterval(() => {
      useGameStore.getState().tickTimer();
    }, 200);
    return () => clearInterval(interval);
  }, [phase, isOnline]);

  // Local AI tick (local mode only)
  useEffect(() => {
    if (phase !== 'playing' || isOnline) return;
    const interval = setInterval(() => {
      const { phase: p, players, myPlayerId } = useGameStore.getState();
      if (p !== 'playing') return;
      for (const pid of players.keys()) {
        if (pid !== myPlayerId) useGameStore.getState().processAITick(pid);
      }
    }, 1800);
    return () => clearInterval(interval);
  }, [phase, isOnline]);

  // Online: emit visit-start on mount, visit-cancel on unmount if not completed
  useEffect(() => {
    if (!isOnline) return;
    completed.current = false;
    getSocket().emit('game:visit-start', { siteId: id });
    return () => {
      if (!completed.current) getSocket().emit('game:visit-cancel', { siteId: id });
    };
  }, [isOnline, id]);

  // Redirect when game ends
  useEffect(() => {
    if (phase === 'result') router.replace(returnUrl);
    if (phase === 'lobby') router.replace('/');
  }, [phase, router, returnUrl]);

  const handleComplete = useCallback(async (points?: number) => {
    completed.current = true;

    let cookieValue: string | undefined;
    try {
      const res = await fetch(`/api/sites/${id}`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        cookieValue = data.value as string;
      }
    } catch {}

    const earned = points ?? site?.cookie.points ?? 0;
    if (isOnline) {
      getSocket().emit('game:visit-complete', {
        siteId: id,
        siteName: site?.name ?? id,
        cookieName: site?.cookie.name ?? id,
        cookieValue: cookieValue ?? '',
        earnedPoints: earned,
      });
    } else {
      completeVisit(id, points, cookieValue);
    }
    // 取得演出を出してから少し遅れてマップへ戻る（タップで即スキップ可）
    setAcquired({ points: earned });
    navTimer.current = setTimeout(goBack, 800);
  }, [id, site, isOnline, completeVisit, goBack]);

  const handleCancel = useCallback(() => {
    completed.current = true;
    if (isOnline) getSocket().emit('game:visit-cancel', { siteId: id });
    router.push(returnUrl);
  }, [id, isOnline, returnUrl, router]);

  if (!site || phase !== 'playing') return null;

  return (
    <div className="relative">
      {/* Game HUD overlay */}
      <div className="fixed top-0 left-0 right-0 z-[200] bg-gray-950/90 backdrop-blur-sm flex items-center justify-between px-4 py-1.5 border-b border-gray-800">
        <span className="text-white text-sm font-bold">🍪 Cookie Heist</span>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span>
            {site.iconEmoji} <strong className="text-white">{site.name}</strong> を訪問中
          </span>
          <span className="text-gray-600">|</span>
          <Timer timeLeft={timeLeft} />
        </div>
        <button
          type="button"
          onClick={handleCancel}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          ← マップに戻る
        </button>
      </div>

      {/* Template content — push down below HUD */}
      <div className="pt-9">
        {site.template === 'consent-button' && (
          <ConsentButton site={site} onComplete={() => handleComplete()} onCancel={handleCancel} />
        )}
        {site.template === 'ad-popup' && (
          <AdPopup site={site} onComplete={() => handleComplete()} onCancel={handleCancel} />
        )}
        {site.template === 'login-form' && (
          <LoginForm site={site} onComplete={handleComplete} onCancel={handleCancel} />
        )}
        {site.template === 'survey' && (
          <Survey site={site} onComplete={(pts) => handleComplete(pts)} onCancel={handleCancel} />
        )}
        {site.template === 'quiz' && (
          <Quiz site={site} onComplete={handleComplete} onCancel={handleCancel} />
        )}
      </div>

      {/* 取得演出オーバーレイ（タップで即スキップ） */}
      {acquired && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          onClick={goBack}
          className="fixed inset-0 z-[300] flex items-center justify-center bg-black/80 cursor-pointer"
        >
          <motion.div
            initial={{ scale: 0.6, y: 16 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 18 }}
            className="text-center select-none"
          >
            {acquired.points >= 0 ? (
              <>
                <div className="text-7xl mb-3">🍪</div>
                <p className="text-3xl font-black text-green-400">Cookie獲得！</p>
                <p className="text-2xl font-black text-green-300 mt-1">+{acquired.points}pt</p>
              </>
            ) : (
              <>
                <div className="text-7xl mb-3">💀</div>
                <p className="text-3xl font-black text-red-400">罠だった…</p>
                <p className="text-2xl font-black text-red-300 mt-1">{acquired.points}pt</p>
              </>
            )}
            <p className="text-xs text-gray-400 mt-4">タップでマップへ</p>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
