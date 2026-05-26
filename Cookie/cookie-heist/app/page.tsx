'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { QRCodeSVG } from 'qrcode.react';

type View = 'top' | 'ai-select' | 'online' | 'qr';

// ── QR コード画面 ──────────────────────────────────────────────────
function QrView({ autoUrl, onBack }: { autoUrl: string; onBack: () => void }) {
  const qrUrl = autoUrl ? autoUrl.replace(/\/$/, '') : '';

  return (
    <motion.div key="qr" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="flex flex-col items-center gap-4 w-full">
      <p className="text-gray-300 text-sm font-semibold">📱 スマホでスキャンして参加！</p>

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

export default function LobbyPage() {
  const router = useRouter();
  const [view, setView] = useState<View>('top');
  const [autoUrl, setAutoUrl] = useState('');

  useEffect(() => {
    fetch('/api/local-ip')
      .then(r => r.json())
      .then(({ url }) => setAutoUrl(url || window.location.origin))
      .catch(() => setAutoUrl(window.location.origin));
  }, []);

  return (
    <main className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center flex flex-col items-center gap-8 w-full max-w-sm"
      >
        <div>
          <h1 className="text-4xl sm:text-6xl font-black text-white tracking-tight whitespace-nowrap">🍪 Cookie Heist</h1>
          <p className="text-gray-400 mt-2 text-lg">
            Webサイトを訪問してCookieを盗め。<br />制限時間は3分。
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
              className="flex flex-col items-center gap-4 w-full">
              <p className="text-gray-300 text-lg font-semibold">AI の人数を選んでください</p>
              <div className="flex gap-3">
                {[1, 2, 3].map(n => (
                  <button type="button" key={n} onClick={() => router.push(`/single?ai=${n}`)}
                    className="w-20 h-20 bg-gray-800 hover:bg-gray-700 border-2 border-gray-600 hover:border-blue-500 text-white font-black text-3xl rounded-xl transition-all">
                    {n}
                  </button>
                ))}
              </div>
              <button type="button" onClick={() => setView('top')} className="text-gray-500 hover:text-gray-300 text-sm mt-2">
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
          終了後はF12 → Application → Cookies で確認できます。
        </p>
      </motion.div>
    </main>
  );
}
