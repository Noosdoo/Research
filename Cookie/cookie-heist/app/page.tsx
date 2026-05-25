'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';

export default function LobbyPage() {
  const router = useRouter();
  const [showAiSelect, setShowAiSelect] = useState(false);

  function startSingle(count: number) {
    router.push(`/single?ai=${count}`);
  }

  return (
    <main className="min-h-screen bg-gray-950 flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center flex flex-col items-center gap-8"
      >
        <div>
          <h1 className="text-6xl font-black text-white tracking-tight">
            🍪 Cookie Heist
          </h1>
          <p className="text-gray-400 mt-2 text-lg">
            Webサイトを訪問してCookieを盗め。制限時間は5分。
          </p>
        </div>

        {!showAiSelect ? (
          <div className="flex flex-col gap-4">
            <button
              onClick={() => setShowAiSelect(true)}
              className="px-8 py-4 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xl rounded-xl transition-colors"
            >
              🤖 シングルプレイヤー
            </button>
            <button
              disabled
              className="px-8 py-4 bg-gray-700 text-gray-500 font-bold text-xl rounded-xl cursor-not-allowed"
              title="Phase 3 で実装予定"
            >
              🌐 オンライン対戦（準備中）
            </button>
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center gap-4"
          >
            <p className="text-gray-300 text-lg font-semibold">AI の人数を選んでください</p>
            <div className="flex gap-3">
              {[1, 2, 3].map(n => (
                <button
                  key={n}
                  onClick={() => startSingle(n)}
                  className="w-20 h-20 bg-gray-800 hover:bg-gray-700 border-2 border-gray-600 hover:border-blue-500 text-white font-black text-3xl rounded-xl transition-all"
                >
                  {n}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowAiSelect(false)}
              className="text-gray-500 hover:text-gray-300 text-sm mt-2 transition-colors"
            >
              ← 戻る
            </button>
          </motion.div>
        )}

        <p className="text-gray-600 text-xs max-w-sm">
          ゲーム中に本物のCookieがブラウザに保存されます。
          終了後はF12 → Application → Cookies で確認してみてください。
        </p>
      </motion.div>
    </main>
  );
}
