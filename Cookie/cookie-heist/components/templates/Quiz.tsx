'use client';

import { useState, useMemo, useEffect } from 'react';
import type { Site } from '@/lib/types';

interface QuizQ {
  q: string;
  options: string[];
  correct: number;
}

// サイトごとに固有の問題セット（重複なし）
const QUIZ_BY_SITE: Record<string, QuizQ[]> = {
  'ghost-site': [
    { q: 'Max-Age=0 のCookieはどうなる？', options: ['即座に削除される', '永続的に保存される', '1時間有効になる', 'サーバーが管理する'], correct: 0 },
    { q: 'Cookieの有効期限を設定しない場合は？', options: ['ブラウザを閉じると消える', '1年間保存される', '7日間保存される', 'サーバーが決める'], correct: 0 },
  ],
  'eternal-session': [
    { q: 'Cookieのドメイン属性の役割は？', options: ['指定ドメインにのみ送信する', 'Cookieを暗号化する', '有効期限を設定する', 'セッションを管理する'], correct: 0 },
    { q: 'サードパーティCookieとは？', options: ['現在表示中以外のドメインが設定するCookie', '暗号化されたCookie', '第三者が認証したCookie', 'セキュアなCookie'], correct: 0 },
  ],
  'mystery-omega': [
    { q: 'HTTPレスポンスでCookieを保存させるヘッダーは？', options: ['Set-Cookie', 'Cookie', 'Cookie-Store', 'Save-Cookie'], correct: 0 },
    { q: 'Cookie属性 "HttpOnly" の役割は？', options: ['JavaScriptからのアクセスを防ぐ', 'HTTPSのみで動作する', '永続化される', 'クロスサイトを防ぐ'], correct: 0 },
  ],
  'retro-arcade': [
    { q: 'XSS攻撃でCookieが盗まれるのを防ぐ属性は？', options: ['HttpOnly', 'Secure', 'SameSite', 'Path'], correct: 0 },
    { q: 'CSRF攻撃対策として有効なCookie属性は？', options: ['SameSite=Strict', 'HttpOnly', 'Secure', 'Max-Age'], correct: 0 },
  ],
};

const FALLBACK_POOL: QuizQ[] = [
  { q: '"SameSite=Strict" のCookieはいつ送信される？', options: ['同一サイトからのリクエストのみ', 'すべてのリクエスト', 'HTTPSのみ', 'GETのみ'], correct: 0 },
  { q: 'Cookie属性 "Secure" の効果は？', options: ['HTTPS接続のみ送信される', '暗号化して保存される', 'JavaScriptで読めなくなる', '有効期限が設定される'], correct: 0 },
  { q: 'セッションCookieとは？', options: ['ブラウザを閉じると消えるCookie', '暗号化されたCookie', '永続的なCookie', 'サーバー側の情報'], correct: 0 },
];

interface Props {
  site: Site;
  onComplete: (points?: number) => void;
  onCancel: () => void;
}

function shuffleQuestion(q: QuizQ): QuizQ {
  const order = q.options.map((_, i) => i).sort(() => Math.random() - 0.5);
  return {
    ...q,
    options: order.map(i => q.options[i]),
    correct: order.indexOf(q.correct),
  };
}

export default function Quiz({ site, onComplete, onCancel }: Props) {
  const questions = useMemo(() => {
    const pool = QUIZ_BY_SITE[site.id] ?? FALLBACK_POOL.slice(0, 2);
    return pool.map(shuffleQuestion);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [answers, setAnswers] = useState<number[]>([-1, -1]);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [allCorrect, setAllCorrect] = useState(false);
  const [result, setResult] = useState<'idle' | 'correct' | 'wrong'>('idle');

  const allAnswered = answers.every(a => a !== -1);

  useEffect(() => {
    if (result === 'idle') return;
    const t = setTimeout(() => {
      if (result === 'correct') onComplete();
      else onCancel();
    }, 1400);
    return () => clearTimeout(t);
  }, [result, onComplete, onCancel]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!allAnswered || submitting) return;
    setSubmitting(true);
    setSubmitted(true);
    const correct = answers.every((a, i) => a === questions[i].correct);
    setAllCorrect(correct);
    setResult(correct ? 'correct' : 'wrong');
  }

  const correctCount = submitted
    ? answers.filter((a, i) => a === questions[i].correct).length
    : 0;

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="bg-gray-800 border border-gray-600 rounded-2xl p-8 w-full max-w-lg text-white">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">{site.iconEmoji}</div>
          <h1 className="text-xl font-bold">{site.name}</h1>
          <p className="text-gray-400 text-sm mt-1">セキュリティ認証クイズ</p>
          <p className="text-xs text-gray-500 mt-0.5">
            全問正解でCookieを取得 — 1問でも間違えると失敗！
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-7">
          {questions.map((q, qi) => (
            <fieldset key={qi}>
              <legend className="text-sm font-semibold text-gray-200 mb-3">
                Q{qi + 1}. {q.q}
              </legend>
              <div className="flex flex-col gap-2">
                {q.options.map((opt, oi) => {
                  const isSelected = answers[qi] === oi;
                  const isCorrect = submitted && oi === q.correct;
                  const isWrong = submitted && isSelected && oi !== q.correct;

                  return (
                    <label
                      key={opt}
                      className={[
                        'flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors text-sm',
                        isCorrect ? 'border-green-500 bg-green-900/40 text-green-300' :
                        isWrong ? 'border-red-500 bg-red-900/40 text-red-300' :
                        isSelected ? 'border-blue-500 bg-blue-900/40 text-blue-300' :
                        'border-gray-600 hover:border-gray-400 text-gray-300',
                        submitted ? 'pointer-events-none' : '',
                      ].join(' ')}
                    >
                      <input
                        type="radio"
                        name={`q${qi}`}
                        value={oi}
                        checked={isSelected}
                        onChange={() => {
                          if (submitted) return;
                          const next = [...answers];
                          next[qi] = oi;
                          setAnswers(next);
                        }}
                        className="accent-blue-500"
                      />
                      {opt}
                      {isCorrect && <span className="ml-auto text-green-400 text-xs">✓ 正解</span>}
                      {isWrong && <span className="ml-auto text-red-400 text-xs">✗ 不正解</span>}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}

          {submitted ? (
            <div className="text-center py-2">
              {allCorrect ? (
                <>
                  <p className="text-2xl font-black text-green-400">🎉 全問正解！</p>
                  <p className="text-gray-400 text-sm mt-1">Cookie を取得中…</p>
                </>
              ) : (
                <>
                  <p className="text-2xl font-black text-red-400">❌ {correctCount}/{questions.length}問正解</p>
                  <p className="text-gray-400 text-sm mt-1">Cookie の取得に失敗… マップに戻ります</p>
                </>
              )}
            </div>
          ) : (
            <button
              type="submit"
              disabled={!allAnswered || submitting}
              className="w-full py-3 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-bold rounded-lg transition-colors text-sm"
            >
              回答して Cookie を取得
            </button>
          )}
        </form>

        {!submitted && (
          <button
            type="button"
            onClick={onCancel}
            className="w-full mt-3 py-2 text-gray-500 hover:text-gray-300 text-sm transition-colors"
          >
            ← 戻る（Cookie取得なし）
          </button>
        )}
      </div>
    </div>
  );
}
