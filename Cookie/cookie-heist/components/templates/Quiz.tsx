'use client';

import { useState, useMemo, useEffect } from 'react';
import type { Site } from '@/lib/types';

interface QuizQ {
  q: string;
  options: string[];
  correct: number;
}

// 基本情報技術者試験スタイルの問題セット（サイトごとに固有）
const QUIZ_BY_SITE: Record<string, QuizQ[]> = {
  'ghost-site': [
    {
      q: 'HTTPレスポンスヘッダの Set-Cookie フィールドの説明として適切なものはどれか。',
      options: [
        'サーバがクライアントにCookieの保存を指示するために使用するヘッダである',
        'クライアントがサーバにCookieを送信するために使用するヘッダである',
        'Cookieの暗号化方式を指定するために使用するヘッダである',
        'Cookieの優先度を設定するために使用するヘッダである',
      ],
      correct: 0,
    },
    {
      q: 'CookieにMax-Age=0を設定した場合の動作として正しいものはどれか。',
      options: [
        'そのCookieをブラウザに即座に削除させる',
        'Cookieを永続的に保存させる',
        'Cookieの有効期限を無制限にする',
        'Cookieへのスクリプトからのアクセスを禁止する',
      ],
      correct: 0,
    },
    {
      q: 'Cookieに有効期限（Expires/Max-Age）を指定しない場合、そのCookieはいつ削除されるか。',
      options: [
        'ブラウザのセッションが終了したとき（ブラウザを閉じたとき）',
        '発行から24時間後',
        'サーバが削除命令を送信したとき',
        '発行から7日後',
      ],
      correct: 0,
    },
  ],
  'eternal-session': [
    {
      q: 'CookieのDomain属性の説明として適切なものはどれか。',
      options: [
        'Cookieを送信するドメインの範囲を制限する属性である',
        'Cookieを暗号化するためのドメインを指定する属性である',
        'CookieのDNS解決に使用するドメインを指定する属性である',
        'Cookieの発行元ドメインを記録する属性である',
      ],
      correct: 0,
    },
    {
      q: 'サードパーティCookieの説明として適切なものはどれか。',
      options: [
        'ユーザが訪問しているサイトとは異なるドメインが発行するCookieである',
        '第三者認証機関によって署名されたCookieである',
        'セキュアなサードパーティサーバに保存されるCookieである',
        '暗号化された通信でのみ送信されるCookieである',
      ],
      correct: 0,
    },
    {
      q: 'CookieのPath属性の説明として適切なものはどれか。',
      options: [
        'Cookieを送信するURLのパスの範囲を制限する属性である',
        'サーバ上のCookieの保存先ファイルパスを指定する属性である',
        'Cookieの暗号化に使用するパスフレーズを指定する属性である',
        'クライアントのファイルシステム上の保存場所を指定する属性である',
      ],
      correct: 0,
    },
  ],
  'mystery-omega': [
    {
      q: 'サーバがWebブラウザにCookieを保存させるときに使用するHTTPレスポンスヘッダはどれか。',
      options: ['Set-Cookie', 'Cookie', 'Cache-Control', 'Content-Security-Policy'],
      correct: 0,
    },
    {
      q: 'CookieのHttpOnly属性を設定する主な目的はどれか。',
      options: [
        'JavaScriptからのCookieへのアクセスを禁止し、XSS攻撃によるCookie窃取を防ぐ',
        'CookieをHTTP通信でのみ送信し、HTTPS通信では送信しないようにする',
        'HTTP GETリクエスト時のみCookieを送信するようにする',
        'CookieへのアクセスをHTTPSプロトコルのみに制限する',
      ],
      correct: 0,
    },
    {
      q: 'WebブラウザがサーバにHTTPリクエストを送信するとき、Cookieを送信するために使用するヘッダはどれか。',
      options: ['Cookie', 'Set-Cookie', 'Authorization', 'X-Forwarded-Cookie'],
      correct: 0,
    },
  ],
  'retro-arcade': [
    {
      q: 'クロスサイトスクリプティング（XSS）攻撃の説明として適切なものはどれか。',
      options: [
        'Webアプリケーションに悪意あるスクリプトを埋め込み、利用者のブラウザ上で実行させる攻撃',
        'ログイン済み利用者を誘導して意図しない操作をWebアプリに実行させる攻撃',
        'SQL文を不正に埋め込んでデータベースを操作する攻撃',
        'サーバに大量のリクエストを送りサービスを停止させる攻撃',
      ],
      correct: 0,
    },
    {
      q: 'クロスサイトリクエストフォージェリ（CSRF）攻撃への対策として最も適切なものはどれか。',
      options: [
        'リクエストごとにトークンを埋め込み、サーバ側で正規の送信元からのものか検証する',
        'パスワードを複雑な文字列にする',
        'CookieにHttpOnly属性を付与する',
        'TLS/SSLを使って通信を暗号化する',
      ],
      correct: 0,
    },
    {
      q: 'XSS攻撃によるセッションCookieの窃取を防ぐために設定すべきCookie属性はどれか。',
      options: ['HttpOnly', 'Secure', 'SameSite=Lax', 'Max-Age'],
      correct: 0,
    },
  ],
  'whitehat-forum': [
    {
      q: 'CookieのSameSite属性を Strict に設定する効果として適切なものはどれか。',
      options: [
        '他サイトを起点とするリクエストにCookieを付与せず、CSRF攻撃のリスクを低減する',
        'Cookieの値を暗号化して通信の盗聴を防ぐ',
        'JavaScriptからCookieを参照できなくする',
        'HTTPS通信のときだけCookieを送信する',
      ],
      correct: 0,
    },
    {
      q: '多要素認証（MFA）の説明として適切なものはどれか。',
      options: [
        '知識・所持・生体など異なる種類の認証要素を組み合わせて本人確認を行う',
        'パスワードを定期的に変更させることで安全性を高める方式である',
        '複数のパスワードを順番に入力させる認証方式である',
        '同じパスワードを複数のサーバで照合する方式である',
      ],
      correct: 0,
    },
  ],
  'esports-hub': [
    {
      q: 'セッションハイジャック攻撃の説明として適切なものはどれか。',
      options: [
        'セッションIDを盗み出し、正規ユーザになりすましてシステムを利用する攻撃',
        'セッション管理機能を無効化してシステムに侵入する攻撃',
        'セッション情報をデータベースに不正に書き込む攻撃',
        'セッション数を増やしてサーバをリソース枯渇状態にする攻撃',
      ],
      correct: 0,
    },
    {
      q: 'セッション固定攻撃（セッションフィクセーション）の対策として適切なものはどれか。',
      options: [
        'ログイン成功後にセッションIDを新たに発行し直す',
        'セッションIDを長い文字列にする',
        'セッションIDをURLパラメータではなくCookieで管理する',
        'セッションの有効期限を短く設定する',
      ],
      correct: 0,
    },
  ],
};

const FALLBACK_POOL: QuizQ[] = [
  {
    q: 'CookieのSecure属性の説明として適切なものはどれか。',
    options: [
      'HTTPS（TLS）通信のときのみCookieをサーバに送信する',
      'Cookieの内容を暗号化してブラウザに保存する',
      'JavaScriptからCookieを読み取れなくする',
      'Cookieの有効期限を安全な範囲に制限する',
    ],
    correct: 0,
  },
  {
    q: 'SameSite=Strictが設定されたCookieが送信される条件として正しいものはどれか。',
    options: [
      'リクエストの送信元URLが同一サイト（同じドメイン）の場合のみ送信される',
      'HTTPSを使用したリクエストの場合のみ送信される',
      'GETメソッドのリクエストの場合のみ送信される',
      'すべてのリクエストで条件なく送信される',
    ],
    correct: 0,
  },
  {
    q: 'TLS（Transport Layer Security）の説明として適切なものはどれか。',
    options: [
      'インターネット上の通信を暗号化し、通信相手の認証と改ざん検出を行うプロトコルである',
      'Webサーバとデータベースサーバ間の通信を保護するプロトコルである',
      'メール送信を暗号化するための専用プロトコルである',
      'ファイル転送を安全に行うために開発されたプロトコルである',
    ],
    correct: 0,
  },
  {
    q: 'SQLインジェクション攻撃への最も根本的な対策はどれか。',
    options: [
      'プリペアドステートメント（バインド機構）を使用してSQL文を構築する',
      'WebアプリケーションへのアクセスをHTTPSに限定する',
      'データベースへの接続を専用の低権限IDで行う',
      'ログイン機能に多要素認証を導入する',
    ],
    correct: 0,
  },
  {
    q: 'DNSキャッシュポイズニング攻撃の説明として適切なものはどれか。',
    options: [
      'DNSサーバのキャッシュに不正な情報を書き込み、利用者を偽サイトに誘導する攻撃',
      'DNSサーバに大量のリクエストを送りサービス不能にする攻撃',
      'DNS通信を盗聴してドメイン情報を収集する攻撃',
      'DNSサーバに侵入してゾーンファイルを改ざんする攻撃',
    ],
    correct: 0,
  },
  {
    q: 'ディジタル署名の説明として適切なものはどれか。',
    options: [
      '送信者が秘密鍵で署名し、受信者が公開鍵で検証することでなりすましと改ざんを防ぐ',
      '共通鍵暗号方式を使ってデータを暗号化し、通信内容の盗聴を防ぐ',
      'ハッシュ値を比較することでデータの完全性のみを確認する仕組み',
      '認証局が発行する電子証明書そのものを指す',
    ],
    correct: 0,
  },
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
            全問正解でCookieを取得
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
