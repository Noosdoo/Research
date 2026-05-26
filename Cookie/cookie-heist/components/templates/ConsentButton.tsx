'use client';

import type { Site } from '@/lib/types';

interface Props {
  site: Site;
  onComplete: () => void;
  onCancel: () => void;
}

export default function ConsentButton({ site, onComplete, onCancel }: Props) {
  return (
    <div className="min-h-screen bg-white text-gray-800">
      {/* Fake site header */}
      <header className="border-b border-gray-200 px-6 py-3 flex items-center gap-2">
        <span className="text-2xl">{site.iconEmoji}</span>
        <span className="text-xl font-bold text-gray-900">{site.name}</span>
      </header>

      {/* Fake content */}
      <main className="px-6 py-8 max-w-2xl">
        <p className="text-gray-500 text-sm mb-6">{site.description}</p>
        <div className="space-y-3">
          {['記事を読み込み中...', '', ''].map((_, i) => (
            <div key={i} className="h-4 bg-gray-200 rounded animate-pulse" style={{ width: `${85 - i * 15}%` }} />
          ))}
        </div>
      </main>

      {/* Cookie consent banner */}
      <div className="fixed bottom-0 left-0 right-0 bg-gray-900 text-white px-6 py-4 shadow-2xl">
        <div className="max-w-2xl mx-auto">
          <p className="text-sm text-gray-300 mb-3">
            <strong>{site.name}</strong> はより良いユーザー体験のために Cookie を使用しています。
            「すべて受け入れる」を押すことで、Cookie の利用に同意したことになります。
            <br />
            <span className="text-xs text-gray-500">
              Cookie 名: <code className="bg-gray-700 px-1 rounded">{site.cookie.name}</code>
              &nbsp;|&nbsp;保存期間: {site.cookie.attributes.maxAge ? `${Math.round(site.cookie.attributes.maxAge / 86400)}日` : 'セッション'}
            </span>
          </p>
          <div className="flex gap-3 items-center">
            <button
              onClick={onComplete}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg transition-colors text-sm"
            >
              すべて受け入れる
            </button>
            <button
              onClick={onCancel}
              className="px-4 py-2 bg-transparent border border-gray-500 hover:border-gray-300 text-gray-300 hover:text-white rounded-lg transition-colors text-sm"
            >
              拒否する
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
