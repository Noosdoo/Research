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
    {
      q: 'CookieはどのHTTPヘッダでサーバからクライアントに送信されるか。',
      options: ['Set-Cookie', 'Cookie', 'Cache-Control', 'Content-Type'],
      correct: 0,
    },
    {
      q: 'HTTPとHTTPSの違いとして正しいものはどれか。',
      options: [
        'HTTPSはTLSを使って通信を暗号化する',
        'HTTPSは通信速度がHTTPの2倍になる',
        'HTTPSはポート番号80を使用する',
        'HTTPSではCookieを利用できない',
      ],
      correct: 0,
    },
  ],
  'tax-agency': [
    {
      q: 'フィッシング詐欺の説明として正しいものはどれか。',
      options: [
        '正規サービスに似せた偽サイトに誘導してIDやパスワードを詐取する手口',
        'サーバに大量のリクエストを送りサービスを妨害する攻撃',
        '通信を暗号化せず平文でやりとりする通信方式',
        'ソフトウェアの脆弱性を突いてシステムに侵入する攻撃',
      ],
      correct: 0,
    },
    {
      q: '行政Webサービスがセッション管理にCookieを使う主な目的はどれか。',
      options: [
        'ログイン状態をサーバとブラウザ間で維持するため',
        'ユーザのパスワードをブラウザに保存するため',
        'ページのデザインをカスタマイズするため',
        'サーバのIPアドレスをクライアントから隠すため',
      ],
      correct: 0,
    },
  ],
  'secure-bank': [
    {
      q: 'TLSハンドシェイクの目的として正しいものはどれか。',
      options: [
        '通信を暗号化するための共通鍵を安全に交換し、サーバ証明書を検証する',
        'サーバのIPアドレスをDNSで解決する',
        'パスワードをハッシュ化してサーバに送信する',
        'CookieをHTTPS通信のみに制限する',
      ],
      correct: 0,
    },
    {
      q: 'WebサイトのHTTPS証明書の役割として正しいものはどれか。',
      options: [
        'サーバの正当性を証明し、なりすましを防ぐ',
        'ページの表示速度を向上させる',
        'CookieをHTTPS通信のみに自動的に制限する',
        'XSS攻撃を自動的に検出・防止する',
      ],
      correct: 0,
    },
  ],
  'crypto-exchange': [
    {
      q: '公開鍵暗号方式でデータを暗号化・復号する組み合わせとして正しいものはどれか。',
      options: [
        '受信者の公開鍵で暗号化し、受信者の秘密鍵で復号する',
        '送信者の秘密鍵で暗号化し、送信者の公開鍵で復号する',
        '共通の秘密鍵で暗号化・復号する',
        '受信者の秘密鍵で暗号化し、公開鍵で復号する',
      ],
      correct: 0,
    },
    {
      q: 'ハッシュ関数の特性として正しいものはどれか。',
      options: [
        '同じ入力からは常に同じハッシュ値が得られ、ハッシュ値から元データを復元できない',
        'ハッシュ値から元のデータを復元できる',
        '入力の長さに比例した長さのハッシュ値が出力される',
        '異なる入力から必ず異なるハッシュ値が出力される',
      ],
      correct: 0,
    },
  ],
  'gold-vault': [
    {
      q: 'PKI（公開鍵基盤）における電子証明書の説明として正しいものはどれか。',
      options: [
        '認証局（CA）が公開鍵とその所有者の対応を保証する電子文書',
        '送信データを暗号化するための共通鍵そのもの',
        'パスワードを一方向に変換したハッシュ値',
        'セッション管理に使われる乱数値',
      ],
      correct: 0,
    },
    {
      q: 'CookieのSecure属性が設定されていない場合のリスクとして最も適切なものはどれか。',
      options: [
        'HTTP（平文）通信でもCookieが送信されるため、通信路上での盗聴・窃取が可能になる',
        'JavaScriptからCookieが読み取られる恐れがある',
        'Cookieが意図より早く期限切れになる恐れがある',
        'CSRF攻撃でCookieが悪用される恐れがある',
      ],
      correct: 0,
    },
  ],
  'online-casino': [
    {
      q: 'セッションIDを推測されにくくするための対策として最も適切なものはどれか。',
      options: [
        '十分な長さの暗号論的に安全な乱数を使用する',
        'ユーザIDをそのままセッションIDとして使用する',
        'タイムスタンプをセッションIDとして使用する',
        'ログイン回数をもとに連番のセッションIDを生成する',
      ],
      correct: 0,
    },
    {
      q: 'Webサービスのログアウト処理として適切な実装はどれか。',
      options: [
        'サーバ側のセッション情報を破棄し、クライアントのセッションCookieも削除する',
        'ブラウザのキャッシュをクリアするだけでよい',
        'セッションCookieの有効期限を過去の日時に変更するだけでよい',
        'クライアント側のCookieを削除するだけでよい',
      ],
      correct: 0,
    },
  ],
  'pro-network': [
    {
      q: 'トラッキングCookieの説明として正しいものはどれか。',
      options: [
        '複数のWebサイトをまたいでユーザの行動を追跡するサードパーティCookie',
        'ユーザのキーストロークを記録する悪意あるCookie',
        'ユーザのIPアドレスを記録するCookie',
        'セキュリティソフトが設置する安全確認用のCookie',
      ],
      correct: 0,
    },
    {
      q: 'SNSでの個人情報漏えいを防ぐための行動として最も適切なものはどれか。',
      options: [
        '投稿の公開範囲を適切に設定し、住所・電話番号などは非公開にする',
        'フォロワーが増えたら全ての投稿を公開する',
        '実名を使わなければどんな情報を投稿しても問題ない',
        '全投稿を非公開にすれば情報漏えいは完全に防げる',
      ],
      correct: 0,
    },
  ],
  'stock-ticker': [
    {
      q: 'WebAPIの認証で使用されるBearerトークンの説明として正しいものはどれか。',
      options: [
        'HTTPリクエストのAuthorizationヘッダに付与されるアクセストークン',
        'Cookieに保存されるセッションIDのこと',
        'TLSで通信を暗号化するための証明書のこと',
        'パスワードをBase64エンコードしたもの',
      ],
      correct: 0,
    },
    {
      q: 'CookieにSameSite属性を設定しない場合に生じる主なリスクはどれか。',
      options: [
        'CSRF（クロスサイトリクエストフォージェリ）攻撃に悪用される恐れがある',
        'XSS（クロスサイトスクリプティング）攻撃に悪用される恐れがある',
        'セッションが自動的に強制終了される恐れがある',
        'Cookieが暗号化されず平文で保存される恐れがある',
      ],
      correct: 0,
    },
  ],
  'loan-easy': [
    {
      q: 'URLの安全性を確認するうえで最も重要なことはどれか。',
      options: [
        'ドメイン名が正規サービスのものと完全に一致しているか確認する',
        'URLが長いほど安全とみなしてよい',
        'HTTPSであれば必ず正規のサイトである',
        'URLにIPアドレスが含まれていなければ安全である',
      ],
      correct: 0,
    },
    {
      q: 'Cookieの保存場所として正しいものはどれか。',
      options: [
        'ブラウザが管理するクライアント側のストレージに保存される',
        'Webサーバのデータベースに保存される',
        'OSのシステム領域に暗号化されて保存される',
        'RAMにのみ一時的に保存され電源を切ると消える',
      ],
      correct: 0,
    },
  ],
  'esports-hub': [
    {
      q: 'DoS攻撃（サービス拒否攻撃）の説明として正しいものはどれか。',
      options: [
        'サーバに大量のリクエストを送りつけ、正規ユーザが利用できない状態にする攻撃',
        'セッションIDを盗んで正規ユーザになりすます攻撃',
        'SQL文を不正に埋め込んでデータベースを操作する攻撃',
        'パスワードを総当たりで試すブルートフォース攻撃',
      ],
      correct: 0,
    },
    {
      q: 'オンラインゲームアカウントを守る対策として最も有効なものはどれか。',
      options: [
        '多要素認証（MFA）を有効にし、サービスごとに異なる強力なパスワードを使用する',
        '複雑なパスワードを1つだけ全サービスで使い回す',
        '生年月日をパスワードにして覚えやすくする',
        'ログアウトせずブラウザを閉じてセッションを維持する',
      ],
      correct: 0,
    },
  ],
};

const FALLBACK_EASY: Question[] = [
  {
    q: 'IPアドレスの説明として正しいものはどれか。',
    options: [
      'インターネット上の機器を識別するための数値アドレス',
      'Webサイトのドメイン名の別称',
      'ユーザのログインIDのこと',
      'パケットの送信順序を管理する番号',
    ],
    correct: 0,
  },
];

const FALLBACK_HARD: Question[] = [
  {
    q: '多要素認証（MFA）で「所持」に分類されるものはどれか。',
    options: [
      'スマートフォンの認証アプリが生成するワンタイムパスワード',
      'ユーザが設定したパスワード',
      '指紋や顔などの生体情報',
      '秘密の質問に対する回答',
    ],
    correct: 0,
  },
  {
    q: 'ポートスキャンの説明として正しいものはどれか。',
    options: [
      '対象サーバで稼働中のサービスを特定するために各ポートへの応答を確認する行為',
      'サーバのWebページを検索エンジンが収集するクロール処理',
      'ネットワーク上のIPアドレスを一覧化するスキャン',
      'ドメイン名をIPアドレスに変換するDNS解決処理',
    ],
    correct: 0,
  },
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
