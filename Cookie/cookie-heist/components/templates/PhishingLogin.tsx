'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import type { Site } from '@/lib/types';

interface Props {
  site: Site;
  onComplete: () => void;
  onCancel: () => void;
}

// サイトIDごとの“本物っぽい”ブランド見た目＋なりすまし対象の正規名（real）。
// 名前(site.name)はわざと綴りを崩してあり、よく見れば正規名と違うと気づける。
const BRAND: Record<string, { color: string; bg: string; tagline: string; real: string }> = {
  'phish-amazon':  { color: '#ff9900', bg: '#131a22', tagline: 'アカウントにサインイン', real: 'Amazon' },
  'phish-youtube': { color: '#ff0033', bg: '#0f0f0f', tagline: 'ログインして続行',       real: 'YouTube' },
  'phish-google':  { color: '#4285f4', bg: '#202124', tagline: 'ログイン',               real: 'Google' },
};

export default function PhishingLogin({ site, onComplete, onCancel }: Props) {
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [busted, setBusted] = useState(false);

  const brand = BRAND[site.id] ?? { color: '#3b82f6', bg: '#111827', tagline: 'ログイン', real: site.name };
  const penalty = site.cookie.points; // 実際に入る点（マイナス）
  const canSubmit = email.trim() !== '' && pw !== '';

  // ── 種明かし画面（フィッシングの正体） ────────────────────────────
  if (busted) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          className="bg-gray-900 border border-red-700 rounded-2xl p-7 w-full max-w-md text-white flex flex-col gap-4"
        >
          <div className="text-center">
            <div className="text-6xl mb-2">🎣</div>
            <h1 className="text-2xl font-black text-red-400">フィッシング詐欺でした！</h1>
          </div>
          <p className="text-sm text-gray-200 leading-relaxed">
            このサイトは <strong>本物の {brand.real} ではありません</strong>。
            名前をよく見ると「<span className="text-amber-300 font-semibold">{site.name}</span>」——
            正規の <span className="text-amber-300 font-semibold">{brand.real}</span> とは<span className="text-amber-300 font-semibold">綴りが違います</span>。
          </p>
          <p className="text-sm text-gray-300 leading-relaxed">
            いま入力した<span className="text-red-300 font-semibold">メール・パスワードは攻撃者に盗まれました</span>。
            見た目がそっくりでも、<span className="text-amber-300 font-semibold">名前とURL（ドメイン）の綴り</span>を必ず確認するのが防御になります。
          </p>
          <div className="bg-red-950/60 border border-red-800 rounded-lg px-4 py-3 text-center">
            <p className="text-xs text-gray-400">スコア</p>
            <p className="text-2xl font-black text-red-400">{penalty}pt</p>
          </div>
          <button
            type="button"
            onClick={onComplete}
            className="w-full py-3 bg-gray-700 hover:bg-gray-600 text-white font-bold rounded-xl transition-colors"
          >
            マップに戻る
          </button>
        </motion.div>
      </div>
    );
  }

  // ── 偽ブランドログイン画面（本物そっくり） ──────────────────────────
  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: brand.bg }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-8 flex flex-col gap-5">
        <div className="text-center">
          <div className="text-4xl mb-1">{site.iconEmoji ?? '🔒'}</div>
          <h1 className="text-2xl font-black" style={{ color: brand.color }}>{site.name}</h1>
          <p className="text-gray-500 text-sm mt-1">{brand.tagline}</p>
        </div>

        <form
          className="flex flex-col gap-3"
          onSubmit={e => { e.preventDefault(); if (canSubmit) setBusted(true); }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-gray-600">メールアドレス</span>
            <input
              type="email"
              autoFocus
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="1234567@ed.tus.ac.jp"
              className="border border-gray-300 rounded-lg px-3 py-2.5 text-gray-900 text-sm focus:outline-none focus:ring-2"
              style={{ ['--tw-ring-color' as string]: brand.color }}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-gray-600">パスワード</span>
            <input
              type="password"
              value={pw}
              onChange={e => setPw(e.target.value)}
              placeholder="••••••••"
              className="border border-gray-300 rounded-lg px-3 py-2.5 text-gray-900 text-sm focus:outline-none focus:ring-2"
              style={{ ['--tw-ring-color' as string]: brand.color }}
            />
          </label>

          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full py-2.5 rounded-lg text-white font-bold text-sm transition-opacity disabled:opacity-40"
            style={{ background: brand.color }}
          >
            サインイン
          </button>
          <p className="text-[11px] text-center" style={{ color: brand.color }}>パスワードをお忘れですか？</p>
        </form>

        <button
          type="button"
          onClick={onCancel}
          className="w-full py-2 text-gray-400 hover:text-gray-600 text-xs transition-colors"
        >
          ← 戻る（Cookie取得なし）
        </button>
      </div>
    </div>
  );
}
