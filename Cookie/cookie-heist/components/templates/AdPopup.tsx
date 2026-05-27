'use client';

import type { Site } from '@/lib/types';

interface Props {
  site: Site;
  onComplete: () => void;
  onCancel: () => void;
}

export default function AdPopup({ site, onComplete, onCancel }: Props) {
  if (site.isHoneypot) {
    return (
      <div className="min-h-screen bg-gray-100">
        <header className="bg-white border-b px-6 py-3 flex items-center gap-2">
          <span className="text-2xl">{site.iconEmoji}</span>
          <span className="text-xl font-bold">{site.name}</span>
        </header>

        {/* Deceptive popup overlay */}
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-8 max-w-sm w-full text-center shadow-2xl relative border-4 border-yellow-400">
            {/* Tiny close button – easy to miss */}
            <button
              onClick={onCancel}
              className="absolute top-2 right-3 text-gray-300 hover:text-gray-500 text-sm"
              title="閉じる"
            >
              ✕
            </button>

            <div className="text-6xl mb-3 animate-bounce">🎉</div>
            <h2 className="text-2xl font-black text-red-500 mb-1">おめでとうございます！</h2>
            <p className="text-yellow-600 font-bold text-sm mb-3">あなたは1万人に1人の当選者です！</p>
            <p className="text-gray-600 text-sm mb-6">
              特別プレゼントを今すぐお受け取りください。<br />
              <span className="text-xs text-gray-400">※期限切れに注意</span>
            </p>
            <button
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

  // Regular ad-popup site
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-2">
        <span className="text-2xl">{site.iconEmoji}</span>
        <span className="text-xl font-bold">{site.name}</span>
      </header>

      <main className="px-6 py-8 max-w-2xl text-gray-500 text-sm">
        {site.description}
      </main>

      {/* Normal ad notification popup */}
      <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-xl p-6 max-w-md w-full shadow-2xl">
          <h2 className="text-lg font-bold text-gray-800 mb-2">
            {site.iconEmoji} {site.name} からのお知らせ
          </h2>
          <p className="text-gray-600 text-sm mb-1">{site.description}</p>
          <p className="text-gray-500 text-xs mb-5">
            パーソナライズされた広告を表示するために Cookie を設定します。
            <br />
            <span className="font-mono text-gray-400">{site.cookie.name}</span> が保存されます。
          </p>
          <div className="flex gap-3 justify-end">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-gray-400 hover:text-gray-600 text-sm transition-colors"
            >
              後で
            </button>
            <button
              onClick={onComplete}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg text-sm transition-colors"
            >
              承認する
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
