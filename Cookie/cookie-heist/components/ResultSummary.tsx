'use client';

import type { Player } from '@/lib/types';
import CookieInspector from '@/components/CookieInspector';

interface Props {
  me: Player;
  onClearCookies: () => void;
  cookieCleared: boolean;
}

// 結果画面の「自分の成績 + F12のオチ」ブロック。シングル/オンライン両画面で共用。
export default function ResultSummary({ me, onClearCookies, cookieCleared }: Props) {
  const { visitCount, stealCount, stolenCount } = me.stats;

  return (
    <div className="bg-gray-800 rounded-lg p-4 text-sm text-gray-300 flex flex-col gap-3">
      <div>
        <p className="font-semibold text-white mb-1">📊 あなたの成績</p>
        <p>訪問回数: {visitCount}</p>
        <p>奪取: {stealCount} / 喪失: {stolenCount}</p>
      </div>

      <CookieInspector cookies={me.cookies} />
      <CookieInspector cookies={me.lostCookies} variant="lost" />

      <div>
        <p className="text-xs text-gray-500 text-center">
          F12 → Application → Cookies で<br />ブラウザに保存されたCookieを確認できます
        </p>
        <button
          type="button"
          onClick={onClearCookies}
          disabled={cookieCleared}
          className="mt-2 w-full py-2 bg-red-700 hover:bg-red-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs font-bold rounded-lg transition-colors"
        >
          {cookieCleared ? '✅ Cookieをリセット済み' : '🗑️ ブラウザのCookieをリセット'}
        </button>
      </div>
    </div>
  );
}
