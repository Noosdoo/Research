'use client';

import { useState, useMemo } from 'react';
import type { Site } from '@/lib/types';

interface Question {
  q: string;
  options: string[];
}

const QUESTIONS: Record<string, Question[]> = {
  'game-zone': [
    {
      q: '主にどのジャンルのゲームを遊びますか？',
      options: ['アクション・FPS', 'RPG・アドベンチャー', 'シミュレーション・パズル', 'スポーツ・レース'],
    },
    {
      q: '1日あたりのゲームプレイ時間は？',
      options: ['30分未満', '1〜2時間', '3〜4時間', '5時間以上'],
    },
  ],
  'tax-agency': [
    {
      q: '確定申告をしたことはありますか？',
      options: ['毎年している', '数回ある', 'まだしたことがない', 'わからない'],
    },
    {
      q: '税金や行政手続きのオンライン化についてどう思いますか？',
      options: ['便利で積極的に使いたい', '便利だが不安もある', 'あまり使いたくない', 'わからない'],
    },
  ],
  'secure-bank': [
    {
      q: 'インターネットバンキングを利用していますか？',
      options: ['毎日使う', '週に数回', '月に数回', '使ったことがない'],
    },
    {
      q: 'ネットバンキングのセキュリティに不安を感じますか？',
      options: ['全く感じない', '少し感じる', 'かなり感じる', '使わないようにしている'],
    },
  ],
  'crypto-exchange': [
    {
      q: '仮想通貨・暗号資産に興味はありますか？',
      options: ['すでに投資している', '興味はある', 'あまり興味ない', '全く興味ない'],
    },
    {
      q: 'ブロックチェーン技術についてどれくらい知っていますか？',
      options: ['よく知っている', '少し知っている', '聞いたことがある程度', '全く知らない'],
    },
  ],
  'gold-vault': [
    {
      q: '投資経験はありますか？',
      options: ['株・投資信託をやっている', '少額だけやっている', '興味はあるが未経験', '全く興味ない'],
    },
    {
      q: 'オンラインで金融商品を購入することに抵抗はありますか？',
      options: ['全くない', '少しある', 'かなりある', 'したことがない'],
    },
  ],
  'online-casino': [
    {
      q: 'ゲームやエンタメを楽しむ主な目的は？',
      options: ['暇つぶし・気分転換', '友人・仲間との交流', 'スキルアップ・競争', '賞品・報酬目当て'],
    },
    {
      q: 'オンラインサービスに課金したことはありますか？',
      options: ['よくする', 'たまにする', 'ほとんどしない', 'まったくしない'],
    },
  ],
  'pro-network': [
    {
      q: '希望する働き方は？',
      options: ['フルリモート', 'ハイブリッド（週2〜3出社）', 'ほぼ出社', '業種による'],
    },
    {
      q: 'ビジネスSNSを使う主な目的は？',
      options: ['転職・キャリアアップ', '情報収集・学習', '人脈・コネクション形成', '就職活動'],
    },
  ],
  'stock-ticker': [
    {
      q: '株式投資に興味はありますか？',
      options: ['すでにやっている', '興味がある', '少し気になる', '興味ない'],
    },
    {
      q: 'AI投資予測ツールを使ってみたいですか？',
      options: ['ぜひ使いたい', '参考程度なら', '信頼できないので使わない', 'わからない'],
    },
  ],
  'loan-easy': [
    {
      q: 'ローン・クレジットを利用したことはありますか？',
      options: ['定期的に使う', '数回使ったことがある', 'まだない', '使うつもりはない'],
    },
    {
      q: '「審査なし・即日融資」という広告を見たときどう思いますか？',
      options: ['便利そうと思う', '怪しいと感じる', '詐欺だと思う', '気にしない'],
    },
  ],
  'esports-hub': [
    {
      q: '好きなeスポーツ・ゲームジャンルは？',
      options: ['FPS・シューター', 'MOBA・チームバトル', '格闘ゲーム', 'ストラテジー・RTS'],
    },
    {
      q: 'eスポーツのどの側面に興味がありますか？',
      options: ['試合を観戦する', 'プレイして競う', 'コミュニティに参加', 'プロを目指したい'],
    },
  ],
  'mystery-delta': [
    {
      q: 'セキュリティ研究に興味はありますか？',
      options: ['非常に興味がある', '少し興味がある', 'あまり興味ない', '全く興味ない'],
    },
    {
      q: 'ネットセキュリティの知識はどれくらいだと思いますか？',
      options: ['詳しい方だと思う', '平均程度', 'あまり詳しくない', 'ほぼ知らない'],
    },
  ],
};

const FALLBACK: Question[] = [
  {
    q: 'インターネットを1日に何時間使いますか？',
    options: ['2時間未満', '2〜4時間', '4〜8時間', '8時間以上'],
  },
  {
    q: 'スマートフォンでよく使うアプリの種類は？',
    options: ['SNS・コミュニケーション', '動画・エンタメ', 'ニュース・情報収集', 'ゲーム・趣味'],
  },
];

interface Props {
  site: Site;
  onComplete: (points: number) => void;
  onCancel: () => void;
}

export default function Survey({ site, onComplete, onCancel }: Props) {
  const questions = useMemo(() => QUESTIONS[site.id] ?? FALLBACK, []);

  const [answers, setAnswers] = useState<string[]>(Array(questions.length).fill(''));
  const [submitting, setSubmitting] = useState(false);

  const allAnswered = answers.every(a => a !== '');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!allAnswered) return;
    setSubmitting(true);
    await new Promise(r => setTimeout(r, 400));
    onComplete(site.cookie.points);
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-md">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">{site.iconEmoji}</div>
          <h1 className="text-xl font-bold text-gray-900">{site.name}</h1>
          <p className="text-gray-400 text-sm mt-1">📋 ユーザーアンケート</p>
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
          type="button"
          onClick={onCancel}
          className="w-full mt-3 py-2 text-gray-400 hover:text-gray-600 text-sm transition-colors"
        >
          ← 戻る（Cookie取得なし）
        </button>
      </div>
    </div>
  );
}
