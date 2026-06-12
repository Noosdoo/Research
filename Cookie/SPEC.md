# Cookie Heist - 設計書

> Webブラウザで動くリアルタイム Cookie 収集対戦ゲーム
> 情報ネットワーク特論 発表用プロジェクト

この文書は実装済みのシステムを反映した現行版の設計書。初期構想からの主な変更点は末尾の「初期設計からの変更履歴」にまとめている。

---

## 1. プロジェクト概要

### 1.1 コンセプト

プレイヤーは様々なWebサイトを訪問してCookieを集める。他プレイヤーが所有しているサイトに自分も訪問すると、相手のそのCookieを奪える。制限時間（3分）内に所持Cookieの合計ポイントが最も高いプレイヤーが勝利。

### 1.2 ネットワーク技術との関連

このゲームの肝は **実際のCookieを使用** すること。

- サイト訪問を完了すると、サーバーが本物の `Set-Cookie` ヘッダを返す
- プレイヤーのブラウザに本物のCookieが保存される
- ゲーム終了後、開発者ツール（F12 → Application → Cookies）で実際に保存されたCookieを確認できる
- Cookie の属性（Secure / HttpOnly / SameSite / Max-Age）はサイトの性格に対応させて定義し、結果画面の CookieInspector で属性の意味を解説する

これにより、教育的な題意（HTTP・Cookie・状態管理）と直接的に関連したゲームになる。

### 1.3 プレイ環境

- シングルプレイ（AI 1〜3体と対戦）+ オンライン対戦（2〜4人、Socket.IO）
- 制限時間: 3分（シングルは30秒〜3分で可変）
- PC・タブレット推奨（スマホでも動作）

---

## 2. 技術スタック

| 種別 | 技術 | 用途 |
|---|---|---|
| 言語 | TypeScript | 全体（server.js のみ JavaScript） |
| フレームワーク | Next.js 15 (App Router) | フロント・Cookie発行API |
| UIライブラリ | React 19 | コンポーネント |
| スタイリング | Tailwind CSS 4 | UI |
| アニメーション | Framer Motion | カード演出・画面遷移 |
| 状態管理 | Zustand | クライアント状態（ローカル対戦のゲームエンジンを兼ねる） |
| リアルタイム通信 | Socket.IO | オンライン対戦・ロビー |
| QRコード | qrcode.react | ルーム招待 |
| デプロイ | Render | main ブランチへの push で自動デプロイ |

### 2.1 単一サーバー構成

Next.js と Socket.IO は `server.js`（Node.js カスタムサーバー）で **同一の HTTP サーバーに同居** させ、Render に1サービスとしてデプロイする。

```
ブラウザ
  │  HTTP …… ページ表示・Cookie発行API
  │  WebSocket …… オンライン対戦の同期
  ▼
server.js（Render 上の常駐プロセス）
  ├── Next.js（画面・/api/sites/[id]）
  └── Socket.IO（ロビー・ゲーム進行・状態配信）
```

この構成にした理由:

1. **WebSocket は常時接続が必要** で、サーバーレス環境（Vercel）と相性が悪い
2. **Cookie はドメイン単位** で管理されるため、フロントとAPIのドメインが分かれると実Cookieの発行・確認が複雑になる。1ドメインに集約すると全Cookieが同じ場所に保存され、デモで見せやすい

---

## 3. プロジェクト構造（実際のファイル構成）

```
cookie-heist/
├── server.js                        # カスタムサーバー（Next.js + Socket.IO、ロビー/ゲーム管理）
├── app/
│   ├── page.tsx                     # ロビー画面（モード選択）
│   ├── single/page.tsx              # シングルプレイ画面
│   ├── quick-match/page.tsx         # クイックマッチ待機
│   ├── create-room/page.tsx         # ルーム作成（QRコード表示）
│   ├── join-room/page.tsx           # ルームコード入力
│   ├── multiplayer/[gameId]/page.tsx# オンライン対戦画面
│   ├── visit/[id]/page.tsx          # サイト訪問ページ（ミニゲーム表示）
│   └── api/
│       ├── sites/[id]/route.ts      # Cookie発行API（Set-Cookie）
│       ├── clear-cookies/route.ts   # ゲームCookieの一括削除
│       └── local-ip/route.ts        # LAN内デモ用のIP取得
├── components/
│   ├── SiteCard.tsx                 # サイトカード
│   ├── PlayerStatus.tsx             # 自分のステータス
│   ├── Ranking.tsx                  # ランキング
│   ├── Timer.tsx                    # 残り時間
│   ├── CategoryFilter.tsx           # カテゴリフィルタ
│   ├── CookieInspector.tsx          # 取得Cookieの属性解説（教育コンテンツ）
│   ├── StealNotification.tsx        # 奪取通知
│   ├── Confetti.tsx                 # 勝利演出
│   └── templates/                   # 訪問ミニゲーム5種
│       ├── ConsentButton.tsx        # Cookie同意バナー
│       ├── AdPopup.tsx              # 広告ポップアップ
│       ├── LoginForm.tsx            # ログインフォーム
│       ├── Survey.tsx               # アンケート
│       └── Quiz.tsx                 # クイズ
├── lib/
│   ├── sites.ts                     # サイトデータ定義（42サイト）
│   ├── types.ts                     # 共通型定義
│   └── socket.ts                    # Socket.IO クライアント（シングルトン）
└── store/
    └── gameStore.ts                 # Zustand ストア（ローカル対戦のゲームエンジン + AI）
```

---

## 4. ゲームルール

### 4.1 基本ルール

1. ゲーム開始時、全プレイヤーは Cookie ゼロ、スコアゼロ
2. マップに42個のサイトカードが表示される
3. プレイヤーはサイトをクリックすると訪問ページ（`/visit/[id]`）に遷移する
4. 訪問ページのミニゲームをクリアすると Cookie を取得（スコア加算）
5. 他プレイヤーが所有するサイトを訪問完了すると、**相手のそのCookieを奪える**（相手はスコア減）
6. Cookie には Max-Age があり、**期限が切れるとゲーム中でも失効** してスコアが減る
7. 制限時間で終了、所持 Cookie のポイント合計で勝者決定

### 4.2 訪問システム（ミニゲーム方式）

訪問は「待ち時間」ではなく **サイトの実ページでミニゲームを遊ぶ** 方式。レア度が高いほど手間のかかるテンプレートが割り当てられ、「高得点サイトは滞在時間が長い = その間に他プレイヤーに動かれる」というリスクが操作として生まれる。

| テンプレート | 内容 | 主な割当 |
|---|---|---|
| consent-button | Cookie同意バナーの「すべて受け入れる」を押す | common |
| ad-popup | 広告ポップアップを閉じる | common |
| login-form | ログインフォームに入力 | uncommon |
| survey | アンケートに回答 | rare |
| quiz | クイズに正解する | legendary |

- 訪問ページから戻る（中断）と Cookie は取得できない
- 訪問中のプレイヤーはサイトカード上に表示される

### 4.3 Cookie 奪取ルール

- 各サイトは「現在の所有者」を1人だけ持つ（最後に訪問完了した者勝ち）
- 訪問完了時、既存所有者がそのサイトの Cookie を持っていれば没収し、奪取イベントとして全員に通知
- 奪われた側はポイント減、奪った側は通常の取得 + 奪取統計が加算

### 4.4 Cookie 失効（Max-Age のゲーム化）

各 Cookie はサイト定義の `Max-Age` を持ち、取得時刻からの経過で失効する。

- 例: GhostSite は Max-Age=10秒 → 取っても10秒で消える（終盤に取れば実質持ち越し）
- 例: TimeCapsule / EverlastingCorp は超長寿命 → 一度取れば安全
- 銀行系は Max-Age=3600 なので3分ゲームでは失効しないが、属性として本物らしさを担う

### 4.5 ハニーポット（罠サイト）

本物に似せた名前の偽サイト（例: `SecuureBank`、`AddNetwork`）。訪問するとマイナスポイントの Cookie を取得する。タイポスクワッティング（typosquatting）の体験が目的。AI も40%の確率で引っかかる。

---

## 5. サイトデータ

`lib/sites.ts` に **42サイト** を TypeScript のオブジェクト配列として定義。

```typescript
export interface Site {
  id: SiteId;            // URL用ID（例: 'secure-bank'）
  name: string;          // 表示名（例: 'SecureBank'）
  category: SiteCategory; // finance | ecommerce | social | media | gaming |
                          // advertising | government | niche | honeypot | special
  description: string;   // フレーバーテキスト（1文）
  cookie: {
    name: string;                 // Cookie名（例: 'bank_auth'）
    valueGenerator: () => string; // ランダム値の生成関数
    attributes: CookieAttributes; // secure / httpOnly / sameSite / maxAge / path
    points: number;
  };
  template: SiteTemplate; // 訪問ミニゲームの種類
  rarity: Rarity;         // common | uncommon | rare | legendary
  isHoneypot?: boolean;
  isMystery?: boolean;
  iconEmoji?: string;
}
```

設計方針:

- **Cookie 属性はサイトの性格と対応させる**。銀行 = `Secure; HttpOnly; SameSite=Strict; Max-Age=3600`、EC = `SameSite=Lax; Max-Age=30日`（カート保持）、広告 = 長寿命トラッキングCookie、など現実のWebの慣習を反映
- レア度とポイント・テンプレートの難しさを連動させる
- description は1文で簡潔に

---

## 6. Cookie 発行 API

`app/api/sites/[id]/route.ts`。訪問完了時にクライアントが `fetch('/api/sites/<id>')` を呼び、レスポンスの `Set-Cookie` ヘッダで本物の Cookie がブラウザに保存される。

```
GET /api/sites/secure-bank
→ Set-Cookie: bank_auth=bank_x7k2…; Path=/; Max-Age=3600; SameSite=Strict; Secure; HttpOnly
```

- Cookie 値はリクエストごとにランダム生成し、JSON でも返す（ゲーム状態の表示用）
- **開発環境フォールバック**: `http://localhost` では `Secure` 属性付き Cookie が保存されないため、開発時のみ `Secure` を外し `SameSite=None` は `Lax` に落とす（= Secure 属性が HTTPS でしか機能しないことの実例）

**採点ロジックとの分離**: ゲームのスコアはメモリ上のゲーム状態で計算する。実ブラウザの Cookie は「演出 + 発表のオチ + 教材」であり、奪取が起きても相手のブラウザの実 Cookie は消えない（HTTP では他人のブラウザの Cookie を消せないという制約そのもの）。

---

## 7. シングルプレイ（クライアント完結のゲームエンジン）

`store/gameStore.ts` の Zustand ストアがゲームエンジン。サーバー不要で全てブラウザ内で完結する。

### 7.1 状態

- プレイヤー（人間 + AI 1〜3体）: 所持Cookie・スコア・統計（訪問/奪取/被奪取）・訪問中フラグ
- サイト状態: `ownerIds`（現在の所有者）と `currentVisitorIds`（訪問中の人）
- イベントキュー: 奪取通知・失効通知
- タイマー: 残り時間（30秒〜3分で可変、デフォルト3分）

### 7.2 ゲームループ

`setInterval` 2本のシンプルな構成:

- **200ms ごと**: タイマー更新 + 全プレイヤーの Cookie 失効チェック（`取得時刻 + Max-Age` 超過で没収）
- **1.5秒ごと**: 各 AI の思考ルーチン `processAITick` を実行

### 7.3 AI（評価関数 + 個性パラメータ）

AI は全サイトをスコアリングする評価関数で行動を決める:

1. **サボり判定**: 5〜11%の確率で何もしない（人間らしいゆらぎ）
2. **採点**: 基礎点 = ポイント − レア度コスト。所持済みは×0.3。同意サイトに `+30 × consentBias`。**人間所有サイトに `+200 × aggression`**（人間から奪いに来る緊張感の源）。他AIが訪問中のサイトは −35/人（殺到防止）。ハニーポットは60%の確率で回避
3. **選択**: 60%は最高スコア、40%は上位5件からランダム
4. **訪問**: レア度に応じた時間をかけて完了 → 奪取発動

```
AI訪問時間: common 3秒 / uncommon 6秒 / rare 8秒 / legendary 20秒（+ 0〜0.5秒のゆらぎ）
```

**個性プロファイル**: `aggression`（奪取の強さ）と `consentBias`（同意サイト巡回の強さ）の組を AI ごとに割り当てる。複数体のときは「巡回型 / バランス型 / 奪取型」を散らし、1体のときはバランス型。

---

## 8. オンライン対戦（Socket.IO・サーバー権威モデル）

### 8.1 サーバー側の管理（server.js）

すべてメモリ上の `Map` で管理（DBなし。デモ用途のため再起動で消えてよい）:

- `lobbies` / `games` / `roomCodes` / socketId→lobby/game/player の対応表
- ゲーム定数: 制限時間180秒、最大4人

### 8.2 マッチング（3方式）

| 方式 | 流れ |
|---|---|
| クイックマッチ | 待機中ロビーがあれば合流、なければ作成。1人目で60秒カウントダウン開始。4人で即開始、時間切れで2人以上なら開始、1人なら延長（30秒）かソロへ誘導 |
| ルーム作成 | 紛らわしい文字（I/O/0/1）を除いた4文字コードを生成し、QRコードで表示。2人以上でホストが手動開始可 |
| コード参加 | コードを入力して合流。満員・開始済みはエラー |

### 8.3 イベント一覧（実装準拠）

クライアント → サーバー:

- `quickmatch:join` / `room:create` / `room:join` — マッチング
- `lobby:start-now` / `lobby:extend` / `lobby:solo` / `lobby:leave` — ロビー操作
- `game:visit-start` / `game:visit-cancel` / `game:visit-complete` — ゲーム中の3操作

サーバー → クライアント:

- `lobby:joined` / `lobby:player-joined` / `lobby:player-left` / `lobby:countdown` / `lobby:lonely` / `lobby:extended` / `lobby:game-starting`
- `game:started` / `game:tick`（毎秒の残り時間） / `game:state-update`（全状態 + 奪取イベント） / `game:ended`

### 8.4 同期戦略（サーバー権威）

- クライアントが送るのは「訪問開始・中断・完了」の3イベントのみ
- スコア計算・奪取判定・タイマーは **すべてサーバー側** で実行し、結果の全状態をルーム全員にブロードキャスト。クライアントは受け取った状態を Zustand に流し込んで描画するだけ
- 獲得ポイントはクライアント申告値を ±500 にクランプして受ける（簡易的な不正対策）
- サイト状態はサーバー側で遅延生成（訪問されて初めて作る）ので、`lib/sites.ts` との手動同期は不要
- 切断時はロビー退出通知・訪問中表示の掃除を行い、他プレイヤーの画面を整合させる

サーバー権威にした理由: (1) クライアント改ざんによるスコア偽装への耐性、(2) 「奪取」のような競合操作の順序がサーバーで一意に決まり同期バグが起きにくい。クライアント側予測は複雑になるため意図的に採用しない。

### 8.5 シングルとマルチのコード共有

Zustand ストアに `mode: 'local' | 'online'` を持たせる。ローカルでは自前ロジックで状態を更新し、オンラインではサーバーからの状態をそのまま反映する。サイトカード・ランキング・通知などの UI コンポーネントは両モード完全共通。訪問ページ（`/visit/[id]`）も共通で、完了時の通知先（ストア直接 or Socket.IO emit）だけが分岐する。

---

## 9. デプロイ

- GitHub の main ブランチに push → Render が自動でビルド・公開
- `npm run dev` = `node server.js`（開発）、`npm start` = `NODE_ENV=production node server.js`（本番）
- 環境変数 `NEXT_PUBLIC_SOCKET_URL` で Socket.IO 接続先を上書き可能（既定は同一オリジン）

---

## 10. 発表時のデモ構成

1. **スライドで仕組み解説** → シングルプレイを実機で投影（AI対戦）
2. **観客参加デモ**: ルーム作成のQRコードを投影し、観客がスマホで参加してリアルタイム対戦
3. **オチ**: ゲーム終了後に F12 → Application → Cookies を開き、「今のゲームでこれだけの本物の Cookie が保存されました。普段のWebブラウジングでは、これが裏で毎日起きています」
4. 結果画面の CookieInspector で Secure / HttpOnly / SameSite の意味を解説

注意: シークレットモードだとセッション終了で Cookie が消えるため、F12 デモは通常モードで行う。

---

## 11. 注意事項・既知の制約

- **同一ドメイン必須**: 全サイトを同一ドメインのパス配下に置くことで、Cookie が1箇所に集まり一括確認できる。サブドメイン分割はしない
- **Cookie 上限**: 1ドメインあたり概ね50個程度の上限があるため、サイト数42 + Cookie 名の重複なしで運用
- **サーバー状態はメモリのみ**: Render の再起動・再デプロイで進行中のゲームは消える（許容）
- **実Cookieとゲーム状態は独立**: 奪取・失効はゲーム状態のみで処理し、実ブラウザの Cookie は触らない（`/api/clear-cookies` で任意に一括削除は可能）

---

## 12. 初期設計からの変更履歴

| 項目 | 初期構想 | 実装 | 理由 |
|---|---|---|---|
| デプロイ | Vercel（フロント）+ Railway（Socket.IO）の分離 | Render 1サービスに統合（server.js） | WebSocket の常時接続と Cookie のドメイン制約 |
| 訪問システム | クリック → プログレスバーで待つ | 実ページに遷移してミニゲーム5種 | 「待ち時間」を実際の操作に変え、Cookie同意バナー等のパロディも教材化 |
| 制限時間 | 5分 | 3分（シングルは可変） | プレイテストの結果、テンポ優先 |
| サイト数 | 50〜100 | 42 | Cookie 上限と画面密度のバランス |
| Max-Age | 属性として持つのみ | ゲーム中の失効メカニクスとして実装 | 属性を「読む」だけでなく「体験」させる |
| AI | 3性格（collector/thief/balanced） | 評価関数 + 連続値プロファイル（aggression / consentBias） | 殺到防止・人間を狙う緊張感などバランス調整の自由度 |
| ホスト概念 | ホストのみ開始ボタン | クイックマッチは自動開始、ルームは誰でも開始可 | 授業デモでの進行を簡略化 |
