'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { QRCodeSVG } from 'qrcode.react';
import { useGameStore } from '@/store/gameStore';

type View = 'top' | 'ai-select' | 'online' | 'qr';

// ── QR コード画面 ──────────────────────────────────────────────────
function QrView({ autoUrl, onBack }: { autoUrl: string; onBack: () => void }) {
  const qrUrl = autoUrl ? autoUrl.replace(/\/$/, '') : '';

  return (
    <motion.div key="qr" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="flex flex-col items-center gap-4 w-full">
      <p className="text-gray-300 text-sm font-semibold">🔗 友達を招待しよう！</p>

      {qrUrl ? (
        <div className="bg-white p-4 rounded-2xl">
          <QRCodeSVG value={qrUrl} size={200} />
        </div>
      ) : (
        <div className="w-[232px] h-[232px] bg-gray-800 rounded-2xl animate-pulse" />
      )}

      <p className="text-gray-500 text-xs font-mono break-all max-w-[280px] text-center">
        {qrUrl || '取得中…'}
      </p>

      <button type="button" onClick={onBack} className="text-gray-500 hover:text-gray-300 text-sm">
        ← 戻る
      </button>
    </motion.div>
  );
}

function formatDuration(s: number) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return sec === 0 ? `${m}分` : `${m}:${sec.toString().padStart(2, '0')}`;
}

export default function LobbyPage() {
  const router = useRouter();
  const [view, setView] = useState<View>('top');
  const [autoUrl, setAutoUrl] = useState('');
  const [aiCount, setAiCount] = useState(1);
  const [duration, setDuration] = useState(180);

  // どの経路（メニューへボタン・ブラウザ戻る等）でメニューに戻っても、
  // 終了済み/進行中のゲーム状態を破棄して次のプレイが正しく初期化されるようにする
  useEffect(() => {
    if (useGameStore.getState().phase !== 'lobby') {
      useGameStore.getState().exitOnlineMode();
    }
  }, []);

  useEffect(() => {
    fetch('/api/local-ip')
      .then(r => r.json())
      .then(({ url }) => setAutoUrl(url || window.location.origin))
      .catch(() => setAutoUrl(window.location.origin));
  }, []);

  const floatingCookies = [
    { emoji: '🍪', x: '8%',  delay: 0,   dur: 7 },
    { emoji: '🍪', x: '22%', delay: 1.5, dur: 9 },
    { emoji: '🔐', x: '38%', delay: 0.8, dur: 8 },
    { emoji: '🍪', x: '55%', delay: 2.2, dur: 6 },
    { emoji: '🛡️', x: '70%', delay: 0.4, dur: 10 },
    { emoji: '🍪', x: '83%', delay: 1.8, dur: 7 },
    { emoji: '🍪', x: '93%', delay: 3,   dur: 8 },
  ];

  return (
    <main className="min-h-screen bg-gray-950 flex items-center justify-center p-4 overflow-hidden relative">
      {/* floating background decorations */}
      {floatingCookies.map((c, i) => (
        <motion.span
          key={i}
          className="absolute text-2xl select-none pointer-events-none opacity-10"
          style={{ left: c.x, bottom: '-10%' }}
          animate={{ y: [0, -900], opacity: [0, 0.15, 0.15, 0] }}
          transition={{ duration: c.dur, delay: c.delay, repeat: Infinity, ease: 'linear' }}
        >
          {c.emoji}
        </motion.span>
      ))}

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center flex flex-col items-center gap-8 w-full max-w-sm relative z-10"
      >
        <div>
          <h1 className="text-4xl sm:text-6xl font-black text-white tracking-tight whitespace-nowrap">🍪 Cookie Heist</h1>
          <p className="text-gray-400 mt-2 text-lg">
            Webサイトを訪問してCookieを盗め。
          </p>
        </div>

        <AnimatePresence mode="wait">
          {/* ── Top menu ────────────────────────────────────────── */}
          {view === 'top' && (
            <motion.div key="top" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="flex flex-col gap-3 w-full">
              <button type="button" onClick={() => setView('ai-select')}
                className="px-8 py-4 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xl rounded-xl transition-colors">
                🤖 シングルプレイヤー
              </button>
              <button type="button" onClick={() => setView('online')}
                className="px-8 py-4 bg-purple-600 hover:bg-purple-500 text-white font-bold text-xl rounded-xl transition-colors">
                🌐 オンライン対戦
              </button>
              <button type="button" onClick={() => setView('qr')}
                className="px-8 py-4 bg-gray-700 hover:bg-gray-600 text-white font-bold text-lg rounded-xl transition-colors">
                📱 QR コードを表示
              </button>
            </motion.div>
          )}

          {/* ── AI count select ─────────────────────────────────── */}
          {view === 'ai-select' && (
            <motion.div key="ai" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-5 w-full">
              <div className="w-full">
                <p className="text-gray-300 text-sm font-semibold mb-3 text-center">AI の人数</p>
                <div className="flex gap-3 justify-center">
                  {[1, 2, 3].map(n => (
                    <button type="button" key={n} onClick={() => setAiCount(n)}
                      className={[
                        'w-20 h-20 border-2 text-white font-black text-3xl rounded-xl transition-all',
                        aiCount === n
                          ? 'bg-blue-600 border-blue-400'
                          : 'bg-gray-800 hover:bg-gray-700 border-gray-600 hover:border-blue-500',
                      ].join(' ')}>
                      {n}
                    </button>
                  ))}
                </div>
              </div>

              <div className="w-full">
                <p className="text-gray-300 text-sm font-semibold mb-2 text-center">
                  制限時間：<span className="text-white font-black text-lg">{formatDuration(duration)}</span>
                </p>
                <input
                  type="range"
                  min={30}
                  max={180}
                  step={10}
                  value={duration}
                  onChange={e => setDuration(Number(e.target.value))}
                  aria-label="制限時間"
                  className="w-full accent-blue-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>30秒</span>
                  <span>3分</span>
                </div>
              </div>

              <button type="button"
                onClick={() => router.push(`/single?ai=${aiCount}&duration=${duration}`)}
                className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold text-lg rounded-xl transition-colors">
                ゲーム開始
              </button>
              <button type="button" onClick={() => setView('top')} className="text-gray-500 hover:text-gray-300 text-sm">
                ← 戻る
              </button>
            </motion.div>
          )}

          {/* ── Online mode select ──────────────────────────────── */}
          {view === 'online' && (
            <motion.div key="online" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="flex flex-col gap-3 w-full">
              <button type="button" onClick={() => router.push('/quick-match')}
                className="px-6 py-4 bg-purple-600 hover:bg-purple-500 text-white font-bold text-lg rounded-xl transition-colors flex items-center gap-3 justify-center">
                <span className="text-2xl">🔍</span>
                <div className="text-left">
                  <div>クイックマッチ</div>
                  <div className="text-xs font-normal text-purple-200">ランダムにマッチング</div>
                </div>
              </button>
              <button type="button" onClick={() => router.push('/create-room')}
                className="px-6 py-4 bg-green-700 hover:bg-green-600 text-white font-bold text-lg rounded-xl transition-colors flex items-center gap-3 justify-center">
                <span className="text-2xl">🏠</span>
                <div className="text-left">
                  <div>ルームを作成</div>
                  <div className="text-xs font-normal text-green-200">4桁コードで友達を招待</div>
                </div>
              </button>
              <button type="button" onClick={() => router.push('/join-room')}
                className="px-6 py-4 bg-gray-700 hover:bg-gray-600 text-white font-bold text-lg rounded-xl transition-colors flex items-center gap-3 justify-center">
                <span className="text-2xl">🚪</span>
                <div className="text-left">
                  <div>ルームに参加</div>
                  <div className="text-xs font-normal text-gray-300">コードを入力して参加</div>
                </div>
              </button>
              <button type="button" onClick={() => setView('top')} className="text-gray-500 hover:text-gray-300 text-sm mt-1">
                ← 戻る
              </button>
            </motion.div>
          )}

          {/* ── QR code ─────────────────────────────────────────── */}
          {view === 'qr' && (
            <QrView autoUrl={autoUrl} onBack={() => setView('top')} />
          )}
        </AnimatePresence>

        <p className="text-gray-600 text-xs max-w-sm">
          ゲーム中に本物のCookieがブラウザに保存されます。<br />
          終了後はF12→Application→Cookiesで確認できます。
        </p>
      </motion.div>
    </main>
  );
}
