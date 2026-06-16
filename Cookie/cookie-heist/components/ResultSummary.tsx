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

      {/* ── F12 のオチ（発表のクライマックス） ───────────────────────── */}
      <div className="rounded-xl border border-amber-500/60 bg-gradient-to-b from-amber-950/60 to-gray-900 p-4 flex flex-col gap-2">
        <p className="text-amber-300 font-black text-base">🔍 ここからが本番です</p>
        <p className="text-gray-200 text-xs leading-relaxed">
          キーボードの <kbd className="px-1.5 py-0.5 bg-gray-700 rounded text-[10px] font-mono">F12</kbd>
          を押し、<span className="text-amber-200 font-semibold">Application → Cookies</span> を開いてみてください。
        </p>
        <p className="text-gray-200 text-xs leading-relaxed">
          あなたはこのゲームで <span className="text-amber-300 font-bold">{visitCount}回</span> サイトを訪問し、
          そのたびに <span className="text-amber-200 font-semibold">本物のCookie</span> がブラウザに保存されました。
        </p>
        <p className="text-gray-300 text-xs leading-relaxed">
          ゲーム中に<span className="text-rose-300 font-semibold">奪われた</span>Cookieも、
          <span className="text-rose-300 font-semibold">期限切れ</span>になったCookieも、
          ブラウザにはまだ残っています。
          <span className="text-amber-200">他人やサーバーは、あなたのブラウザのCookieを勝手に消せない</span>からです。
        </p>
        <p className="text-gray-400 text-[11px] leading-relaxed border-t border-gray-700 pt-2 mt-1">
          普段のWebブラウジングでも、これと同じことが毎日あなたのブラウザで起きています。
        </p>
        <button
          type="button"
          onClick={onClearCookies}
          disabled={cookieCleared}
          className="mt-1 w-full py-2 bg-red-700 hover:bg-red-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs font-bold rounded-lg transition-colors"
        >
          {cookieCleared ? '✅ Cookieをリセット済み' : '🗑️ 確認できたらブラウザのCookieをリセット'}
        </button>
      </div>
    </div>
  );
}
