'use client';

import { useState } from 'react';
import type { Site } from '@/lib/types';

const TUS_EMAIL = /^\d{7}@ed\.tus\.ac\.jp$/;

interface Props {
  site: Site;
  onComplete: () => void;
  onCancel: () => void;
}

export default function LoginForm({ site, onComplete, onCancel }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const canSubmit = username.trim() !== '' && password.trim() !== '' && !loading;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError('');
    if (!TUS_EMAIL.test(username.trim())) {
      setError('メールアドレスの形式が違います（例: 1234567@ed.tus.ac.jp）');
      return;
    }
    setLoading(true);
    await new Promise(r => setTimeout(r, 500));
    onComplete();
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-sm">
        {/* Site branding */}
        <div className="text-center mb-7">
          <div className="text-5xl mb-2">{site.iconEmoji}</div>
          <h1 className="text-2xl font-bold text-gray-900">{site.name}</h1>
          <p className="text-gray-400 text-sm mt-1">{site.description}</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              大学メールアドレス
            </label>
            <input
              type="text"
              value={username}
              onChange={e => { setUsername(e.target.value); setError(''); }}
              placeholder="1234567@ed.tus.ac.jp"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              パスワード
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
            />
          </div>

          {error && (
            <p className="text-red-500 text-xs bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              ❌ {error}
            </p>
          )}

          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-200 disabled:text-gray-400 text-white font-bold rounded-lg transition-colors text-sm mt-1"
          >
            {loading ? 'ログイン中…' : 'ログイン'}
          </button>
        </form>

        <p className="text-center text-xs text-gray-400 mt-4">
          ログインすることで Cookie が保存されます
        </p>

        <button
          onClick={onCancel}
          className="w-full mt-3 py-2 text-gray-400 hover:text-gray-600 text-sm transition-colors"
        >
          ← 戻る
        </button>
      </div>
    </div>
  );
}
