'use client';

import { useState, useMemo } from 'react';
import type { Site } from '@/lib/types';

interface Question {
  q: string;
  options: string[];
  correct?: number; // index of correct option; undefined = preference (always correct)
}

const QUESTIONS: Record<string, Question[]> = {
  'game-zone': [
    { q: '好きなゲームジャンルは？', options: ['RPG', 'FPS', 'パズル', 'スポーツ'] },
  ],
  'tax-agency': [
    { q: '確定申告を自分でやりますか？', options: ['はい、毎年', 'たまにやる', '税理士に依頼', 'やったことがない'] },
  ],
  'secure-bank': [
    { q: 'オンライン取引で最も重要なセキュリティ対策は？', options: ['2段階認証を使う', 'パスワードを使い回す', '誕生日をパスワードにする', '特に対策しない'], correct: 0 },
    { q: 'フィッシング詐欺を見分けるには？', options: ['URLをよく確認する', 'サイトデザインで判断する', '大手企業名なら安全', '特に確認しない'], correct: 0 },
  ],
  'crypto-exchange': [
    { q: '秘密鍵（シードフレーズ）は誰と共有すべき？', options: ['誰とも共有しない', 'サポートには共有する', '家族なら共有してよい', '必要に応じて共有'], correct: 0 },
    { q: '最も安全な仮想通貨の保管方法は？', options: ['ハードウェアウォレット', '取引所に預ける', 'スクリーンショットで保存', 'メモ帳に書いておく'], correct: 0 },
  ],
  'gold-vault': [
    { q: '投資でリスク分散として有効なのは？', options: ['異なる資産クラスに分散する', '1つの銘柄に集中投資', '売らずに持ち続ける', 'タイミングを見計らう'], correct: 0 },
    { q: '貴金属投資の主なメリットは？', options: ['インフレヘッジになる', '株より利回りが高い', 'リスクがゼロ', '税金がかからない'], correct: 0 },
  ],
  'online-casino': [
    { q: 'ギャンブルで最も重要なことは？', options: ['予算を決めて守る', '必勝法を使う', '負けを取り返すまで続ける', '完全に運に任せる'], correct: 0 },
    { q: 'オンラインカジノ利用時に確認すべきことは？', options: ['ライセンスの有無', 'ボーナスの大きさだけ', 'サイトデザインの好み', '知人の口コミだけ'], correct: 0 },
  ],
  'pro-network': [
    { q: 'ビジネスSNSで個人情報を守るための行動は？', options: ['公開範囲を適切に設定する', '全情報を公開する', '実名以外すべて非公開', '全部削除する'], correct: 0 },
    { q: 'プロフィールに載せるべきでない情報は？', options: ['生年月日や自宅住所', '職歴・経歴', 'スキル・資格', '自己紹介文'], correct: 0 },
  ],
  'stock-ticker': [
    { q: '株式投資で最も重要なリスク管理は？', options: ['分散投資でリスクを分散する', '1銘柄に集中投資する', '損失が出たら即売却する', 'すべて現金で持つ'], correct: 0 },
    { q: 'インサイダー取引とは？', options: ['非公開情報を使った株取引', '外国株の取引', '自動売買システムの利用', '信用取引'], correct: 0 },
  ],
  'loan-easy': [
    { q: 'ローン契約で最も確認すべき項目は？', options: ['実質年率（APR）', 'パンフレットのデザイン', '会社のロゴ', 'ウェブサイトの見た目'], correct: 0 },
    { q: '多重債務を防ぐための正しい行動は？', options: ['借り入れ前に返済計画を立てる', '複数の会社から借りる', '最低返済額だけ払う', '借り続ける'], correct: 0 },
  ],
  'esports-hub': [
    { q: 'eスポーツ選手の個人情報が狙われる主な理由は？', options: ['フォロワーが多く知名度が高いため', 'ゲームが上手いため', '練習時間が長いため', 'チームに所属しているため'] },
  ],
};

const FALLBACK_EASY: Question[] = [
  { q: 'このサービスをどこで知りましたか？', options: ['SNS', '友人の紹介', '検索して', 'CM・広告'] },
];

const FALLBACK_HARD: Question[] = [
  { q: 'セキュリティリスクとして最も深刻なものは？', options: ['フィッシング詐欺', '弱いパスワード', 'ソフトウェア未更新', 'すべて同程度'], correct: 0 },
  { q: '個人情報の管理として正しい行動は？', options: ['必要最小限の情報のみ提供する', '便利なので全部入力する', 'SNSで共有する', '特に気にしない'], correct: 0 },
];

function shuffleQuestion(q: Question): Question {
  const order = q.options.map((_, i) => i).sort(() => Math.random() - 0.5);
  return {
    ...q,
    options: order.map(i => q.options[i]),
    correct: q.correct !== undefined ? order.indexOf(q.correct) : undefined,
  };
}

function calcPoints(base: number, questions: Question[], answers: string[]): number {
  const scored = questions.filter(q => q.correct !== undefined);
  if (scored.length === 0) return base;
  const correctCount = questions.filter((q, i) =>
    q.correct === undefined || answers[i] === q.options[q.correct]
  ).length;
  const ratio = correctCount / questions.length;
  return Math.max(Math.floor(base * ratio), Math.floor(base * 0.2));
}

interface Props {
  site: Site;
  onComplete: (points: number) => void;
  onCancel: () => void;
}

export default function Survey({ site, onComplete, onCancel }: Props) {
  const questions = useMemo(() => {
    const base = QUESTIONS[site.id] ?? (site.rarity === 'rare' ? FALLBACK_HARD : FALLBACK_EASY);
    return base.map(shuffleQuestion);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [answers, setAnswers] = useState<string[]>(Array(questions.length).fill(''));
  const [submitting, setSubmitting] = useState(false);

  const allAnswered = answers.every(a => a !== '');
  const hasScored = questions.some(q => q.correct !== undefined);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!allAnswered) return;
    setSubmitting(true);
    await new Promise(r => setTimeout(r, 400));
    onComplete(calcPoints(site.cookie.points, questions, answers));
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-md">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">{site.iconEmoji}</div>
          <h1 className="text-xl font-bold text-gray-900">{site.name}</h1>
          <p className="text-gray-400 text-sm mt-1">
            {hasScored ? 'セキュリティ確認（正解率でポイントが変わります）' : 'ユーザーアンケート'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-6">
          {questions.map((q, qi) => (
            <fieldset key={qi}>
              <legend className="text-sm font-semibold text-gray-800 mb-3">
                Q{qi + 1}. {q.q}
              </legend>
              <div className="flex flex-col gap-2">
                {q.options.map(opt => (
                  <label
                    key={opt}
                    className={[
                      'flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors text-sm',
                      answers[qi] === opt
                        ? 'border-blue-500 bg-blue-50 text-blue-800'
                        : 'border-gray-200 hover:border-gray-300 text-gray-700',
                    ].join(' ')}
                  >
                    <input
                      type="radio"
                      name={`q${qi}`}
                      value={opt}
                      checked={answers[qi] === opt}
                      onChange={() => {
                        const next = [...answers];
                        next[qi] = opt;
                        setAnswers(next);
                      }}
                      className="accent-blue-600"
                    />
                    {opt}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}

          <button
            type="submit"
            disabled={!allAnswered || submitting}
            className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-200 disabled:text-gray-400 text-white font-bold rounded-lg transition-colors text-sm"
          >
            {submitting ? '送信中…' : '回答を送信する'}
          </button>
        </form>

        <button
          onClick={onCancel}
          className="w-full mt-3 py-2 text-gray-400 hover:text-gray-600 text-sm transition-colors"
        >
          ← 戻る（Cookie取得なし）
        </button>
      </div>
    </div>
  );
}
