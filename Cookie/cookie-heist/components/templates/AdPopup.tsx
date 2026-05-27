'use client';

import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import type { Site } from '@/lib/types';

interface Props {
  site: Site;
  onComplete: () => void;
  onCancel: () => void;
}

// ── Honeypot: dodging close button + auto-accept countdown ────────────
function HoneypotPopup({ site, onComplete, onCancel }: Props) {
  const [closePos, setClosePos] = useState({ top: 6, left: 88 });
  const [countdown, setCountdown] = useState(8);

  const shuffleClose = useCallback(() => {
    setClosePos({
      top:  Math.random() * 70 + 5,
      left: Math.random() * 70 + 5,
    });
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { onComplete(); return 0; }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [onComplete]);

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-2">
        <span className="text-2xl">{site.iconEmoji}</span>
        <span className="text-xl font-bold">{site.name}</span>
      </header>

      {/* Background click also triggers onComplete — can't escape! */}
      <div
        className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
        onClick={onComplete}
      >
        <div
          className="bg-white rounded-2xl p-8 max-w-sm w-full text-center shadow-2xl relative border-4 border-yellow-400 overflow-hidden"
          onClick={e => e.stopPropagation()}
        >
          {/* Dodging close button */}
          <motion.button
            type="button"
            onClick={onCancel}
            onMouseEnter={shuffleClose}
            animate={{ top: `${closePos.top}%`, left: `${closePos.left}%` }}
            transition={{ type: 'spring', stiffness: 400, damping: 22 }}
            className="absolute text-gray-500 hover:text-gray-700 text-sm font-bold z-10 select-none"
            title="閉じる"
          >
            ✕
          </motion.button>

          <div className="text-6xl mb-3 animate-bounce">🎉</div>
          <h2 className="text-2xl font-black text-red-500 mb-1">おめでとうございます！</h2>
          <p className="text-yellow-600 font-bold text-sm mb-3">あなたは1万人に1人の当選者です！</p>
          <p className="text-gray-600 text-sm mb-4">
            特別プレゼントを今すぐお受け取りください。<br />
            <span className="text-xs text-gray-400">※期限切れに注意</span>
          </p>

          {/* Countdown bar */}
          <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden mb-1">
            <div
              className="h-full bg-red-500 origin-left rounded-full"
              style={{ animation: 'countdown-bar 8s linear forwards' }}
            />
          </div>
          <p className="text-[11px] text-gray-400 mb-4">⏰ {countdown}秒後に自動受け取り</p>

          <button
            type="button"
            onClick={onComplete}
            className="w-full py-4 bg-gradient-to-r from-yellow-400 to-orange-500 text-white font-black text-lg rounded-xl shadow-lg hover:brightness-110 transition-all animate-pulse"
          >
            🎁 賞品を受け取る！
          </button>
          <p className="text-xs text-gray-300 mt-2">クリックすることで利用規約に同意します</p>
        </div>
      </div>
    </div>
  );
}

// ── Regular ad-popup site ─────────────────────────────────────────────
function RegularPopup({ site, onComplete, onCancel }: Props) {
  const [showSecond, setShowSecond] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setShowSecond(true), 2800);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-2">
        <span className="text-2xl">{site.iconEmoji}</span>
        <span className="text-xl font-bold">{site.name}</span>
      </header>

      <main className="px-6 py-8 max-w-2xl text-gray-500 text-sm">
        {site.description}
      </main>

      {/* Background click = accidental consent */}
      <div
        className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
        onClick={onComplete}
      >
        {/* Main popup */}
        <div
          className="bg-white rounded-xl p-6 max-w-md w-full shadow-2xl relative"
          onClick={e => e.stopPropagation()}
        >
          <h2 className="text-lg font-bold text-gray-800 mb-2">
            {site.iconEmoji} {site.name} からのお知らせ
          </h2>
          <p className="text-gray-600 text-sm mb-1">{site.description}</p>
          <p className="text-gray-500 text-xs mb-5">
            パーソナライズされた広告を表示するために Cookie を設定します。
            <br />
            <span className="font-mono text-gray-400">{site.cookie.name}</span> が保存されます。
          </p>
          <div className="flex gap-3 items-center justify-end">
            <button
              type="button"
              onClick={onCancel}
              className="text-[10px] text-gray-300 hover:text-gray-400 transition-colors"
            >
              後で
            </button>
            <button
              type="button"
              onClick={onComplete}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg text-sm transition-colors"
            >
              承認する
            </button>
          </div>
        </div>

        {/* Second popup appearing after delay */}
        {showSecond && (
          <motion.div
            initial={{ opacity: 0, y: 40, x: 60 }}
            animate={{ opacity: 1, y: 0, x: 0 }}
            className="absolute bottom-20 right-4 bg-white rounded-lg p-3 shadow-xl max-w-[220px] border border-gray-200"
            onClick={e => e.stopPropagation()}
          >
            <p className="text-xs font-bold text-gray-700 mb-1">🔔 通知を許可</p>
            <p className="text-[10px] text-gray-500 mb-2">
              最新のお得情報をお届けします
            </p>
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={onCancel}
                className="text-[9px] text-gray-300"
              >
                拒否
              </button>
              <button
                type="button"
                onClick={onComplete}
                className="px-2 py-1 bg-blue-500 text-white text-[10px] font-bold rounded"
              >
                許可
              </button>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

export default function AdPopup({ site, onComplete, onCancel }: Props) {
  if (site.isHoneypot) {
    return <HoneypotPopup site={site} onComplete={onComplete} onCancel={onCancel} />;
  }
  return <RegularPopup site={site} onComplete={onComplete} onCancel={onCancel} />;
}
