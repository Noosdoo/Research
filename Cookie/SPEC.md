# Cookie Heist - 詳細設計書

> Webブラウザで動くリアルタイム Cookie 収集対戦ゲーム
> 情報ネットワーク特論 発表用プロジェクト

---

## 1. プロジェクト概要

### 1.1 コンセプト

プレイヤーは様々なWebサイトを訪問してCookieを集める。他プレイヤーが訪問済みのサイトに自分も訪問すると、相手のそのCookieを奪える。制限時間内に所持Cookieの合計ポイントが最も高いプレイヤーが勝利。

### 1.2 ネットワーク技術との関連

このゲームの肝は **実際のCookieを使用** すること。

- 各「サイト」ページに訪問すると、サーバーが本物の `Set-Cookie` ヘッダを返す
- プレイヤーのブラウザに本物のCookieが保存される
- ゲーム終了後、開発者ツール（F12 → Application → Cookies）で実際に保存されたCookieを確認できる
- 採点ロジックも、ブラウザが自動送信する `Cookie` リクエストヘッダを利用

これにより、教育的な題意（HTTP・Cookie・状態管理）と直接的に関連したゲームになる。

### 1.3 ターゲットプレイ環境

- 2〜4人プレイ
- シングルプレイヤー（AI対戦）+ オンライン対戦（WebSocket）
- 制限時間: 5分
- PC・タブレット推奨（スマホでも動くが画面狭い）

---

## 2. 技術スタック

| 種別 | 技術 | 用途 |
|---|---|---|
| 言語 | TypeScript | 全体 |
| フレームワーク | Next.js 15 (App Router) | フロント・APIサーバー |
| UIライブラリ | React 19 | コンポーネント |
| スタイリング | Tailwind CSS | UI |
| アニメーション | Framer Motion | カード演出、訪問プログレス |
| 状態管理 | Zustand | クライアント状態 |
| リアルタイム通信 | Socket.IO | オンライン対戦 |
| QRコード | qrcode.react | ルーム招待 |
| デプロイ（フロント） | Vercel | git push で自動デプロイ |
| デプロイ（Socket.IO） | Railway or Render | WebSocket 用 |

**重要**: Next.js本体はVercelにデプロイ可能だが、Socket.IOは長時間接続が必要なのでサーバーレス環境（Vercel）と相性が悪い。Socket.IOサーバーは別途Railway/Renderにデプロイする構成。

---

## 3. プロジェクト構造

```
cookie-heist/
├── apps/
│   ├── web/                     # Next.js アプリ（Vercel デプロイ）
│   │   ├── app/
│   │   │   ├── page.tsx                    # ロビー画面
│   │   │   ├── single/page.tsx             # シングルプレイヤー
│   │   │   ├── room/[id]/page.tsx          # オンライン対戦画面
│   │   │   ├── room/[id]/waiting/page.tsx  # 待機画面
│   │   │   ├── result/page.tsx             # 結果画面
│   │   │   └── api/
│   │   │       ├── sites/[id]/route.ts     # サイト訪問API（Cookie発行）
│   │   │       └── score/route.ts          # 採点API
│   │   ├── components/
│   │   │   ├── SiteCard.tsx                # サイトカード
│   │   │   ├── PlayerStatus.tsx            # 自分のステータス
│   │   │   ├── Ranking.tsx                 # ランキング表示
│   │   │   ├── VisitProgress.tsx           # 訪問中の進捗バー
│   │   │   ├── Timer.tsx                   # 残り時間
│   │   │   ├── CategoryFilter.tsx          # カテゴリフィルタ
│   │   │   └── ...
│   │   ├── lib/
│   │   │   ├── sites.ts                    # サイトデータ定義（50〜100個）
│   │   │   ├── gameLogic.ts                # ゲームロジック
│   │   │   ├── ai.ts                       # AI 対戦ロジック
│   │   │   └── socket.ts                   # Socket.IO クライアント
│   │   └── store/
│   │       └── gameStore.ts                # Zustand 状態管理
│   └── socket-server/           # Socket.IO サーバー（Railway デプロイ）
│       └── src/
│           ├── index.ts                    # サーバーエントリ
│           ├── room.ts                     # ルーム管理
│           └── gameEngine.ts               # サーバー側ゲームロジック
├── packages/
│   └── shared/                  # 共通型定義
│       └── types.ts                        # GameState, Player, Cookie 等
├── package.json
└── README.md
```

最初はシンプルに、apps/web 単体で開発を始めて、オンライン対戦実装時に socket-server を追加してOK。

---

## 4. ゲームルール詳細

### 4.1 基本ルール

1. ゲーム開始時、全プレイヤーは Cookie ゼロ、スコアゼロ
2. マップに50〜100個のサイトカードが表示される
3. プレイヤーはサイトをクリックして訪問
4. 訪問にかかる時間は Cookie のレア度による（後述）
5. 訪問完了でそのサイトの Cookie を取得（スコア加算）
6. 既に他プレイヤーが訪問済みのサイトに行くと、**相手のそのCookieを奪える**（相手はそのCookieを失う）
7. 5分経過でゲーム終了、所持 Cookie のポイント合計で勝者決定

### 4.2 訪問システム

- プレイヤーは同時に1つのサイトしか訪問できない
- 訪問中は他のアクション不可（プログレスバー表示）
- 訪問中に「中断」ボタンで諦めて他のサイトに移れる（Cookie 取得失敗）
- 訪問中のプレイヤーは他プレイヤーから見えるよう、サイトカードに表示する

### 4.3 訪問時間とレア度

| レア度 | ポイント範囲 | 訪問時間 | 例 |
|---|---|---|---|
| 通常 | 10〜50 pt | 1秒 | AdNetwork (30pt) |
| 中レア | 51〜100 pt | 2秒 | SocialNet (60pt) |
| 高レア | 101〜150 pt | 3秒 | SecureBank (150pt) |
| 超レア | 151〜200 pt | 5秒 | GhostSite (200pt) |

訪問時間が長いほどリスク（その間に他人に妨害される、追い抜かれる）が増えるバランス。

### 4.4 Cookie 奪取ルール

**奪取が発生する条件**: 自分が訪問完了したサイトに、他プレイヤーが既に同じサイトのCookieを持っている場合

**奪取の結果**:
- 自分: そのサイトのCookie取得（通常通り）
- 奪われた相手: そのサイトのCookieを失う（スコア減）
- ゲーム状態として奪取イベントを記録、画面に通知表示

**例**:
```
状態: プレイヤーA が SecureBank を訪問済み、bank_auth (150pt) を所持
プレイヤーB が SecureBank を訪問開始 (3秒)
[3秒後] 訪問完了
結果:
  プレイヤーB: bank_auth (150pt) を取得 (+150pt)
  プレイヤーA: bank_auth を失う (-150pt)
```

### 4.5 採点

ゲーム終了時、各プレイヤーの所持Cookieのポイント合計が最終スコア。

### 4.6 ハニーポット（罠サイト）

通常サイトと見た目を似せた偽サイトを混ぜる。訪問すると：
- マイナスポイントのCookieを取得
- 例: `SecuureBank`（よく見ると "u" が2つ）、訪問するとマイナス50pt

---

## 5. サイトデータ仕様

### 5.1 データ構造

```typescript
// lib/sites.ts
export interface SiteCookie {
  name: string;          // Cookie名（例: "bank_auth"）
  valueGenerator: () => string;  // Cookie値生成関数（例: ランダム文字列）
  attributes: CookieAttributes;
  points: number;        // ポイント
}

export interface CookieAttributes {
  secure?: boolean;
  httpOnly?: boolean;
  sameSite?: 'Strict' | 'Lax' | 'None';
  maxAge?: number;       // 秒
  path?: string;
  domain?: string;
}

export interface Site {
  id: string;            // URL用ID（例: "secure-bank"）
  name: string;          // 表示名（例: "SecureBank"）
  category: SiteCategory;
  description: string;   // フレーバーテキスト
  cookie: SiteCookie;
  visitDuration: number; // ミリ秒（1000, 2000, 3000, 5000）
  rarity: 'common' | 'uncommon' | 'rare' | 'legendary';
  isHoneypot?: boolean;
  iconEmoji?: string;
}

export type SiteCategory =
  | 'finance'      // 金融
  | 'ecommerce'    // EC
  | 'social'       // SNS
  | 'media'        // メディア
  | 'gaming'       // ゲーム
  | 'advertising'  // 広告
  | 'government'   // 政府/公共
  | 'niche'        // ニッチ
  | 'honeypot'     // 罠
  | 'special';     // 特殊

export const SITES: Site[] = [
  // ここに50〜100個のサイトを定義
];
```

### 5.2 カテゴリ別サイト例（各カテゴリ 5〜10個ずつ作成）

#### finance（金融、高レア寄り）
- SecureBank, GoldVault, CryptoExchange, InsurancePro, LoanCenter, InvestBank, StockMarket, TaxFiler, PaymentGateway, WireService

#### ecommerce（EC、中レア中心）
- ShopMart, ElectroStore, BookWorm, FashionMall, GroceryDelivery, AuctionHouse, FleaMarket, GiftShop, MusicStore, ToyLand

#### social（SNS、中レア中心）
- TweetSpace, FaceConnect, PhotoGram, ChatBox, MeetUp, ProNetwork, VideoMessenger, AnonForum, DatingApp, GroupChat

#### media（メディア、中レア）
- NewsPortal, BlogHub, VideoStream, MusicService, PodcastHub, EBookReader, DocumentSite, ImageGallery, NewsletterCorp, ResearchPapers

#### gaming（ゲーム、中〜高レア）
- GameZone, OnlineCasino, ArcadeHub, RPGSite, PuzzleWorld, MMOLobby, StreamPlatform, EsportsHub, GameStore, RetroGames

#### advertising（広告、低レア・大量）
- AdNetwork, TrackerCorp, RetargetX, AnalyticsHub, PixelPlace, ImpressionCo, AffiliateNet, DataBroker, ProfilerInc, BehaviorTrace

#### government（政府/公共、高レア・少ない）
- TaxAgency, CityHall, HealthService, PostOffice, DMVOnline, PassportSvc, CourtRecord, ElectionPortal, SocialSecurity, ImmigrationDB

#### niche（ニッチ、特徴ある）
- ConspiracyForum, MemeBoard, AlienWatcher, GhostHunter, CryptidsClub, UFOReports, TimeTravelers, OracleSite, FortuneTeller, MagicShop

#### honeypot（罠、マイナス）
- SecuureBank (Secureの偽物), AddNetwork (AdNetworkの偽物), ShоpMart (oがキリル文字), FaceCоnnect (oがキリル文字), Glthub, AmazOn, GoolgIe, PreyPaI, TweetSpacе, BingoCasinо

#### special（特殊効果）
- GhostSite (Max-Age短い、すぐ消える), MirrorSite (ランダムCookie発行), TimeCapsule (Max-Age 10年), EverlastingCorp (Max-Age 100年), QuantumServer, OracleNet, NullSite, VoidCorp, ZeroDay, EternalSession

### 5.3 サイトデータ生成

50〜100個のサイト定義は、規模が大きいので**TypeScriptのオブジェクト配列**として生成。

各サイトについて：
- 名前と説明文（ユーモア・パロディ要素歓迎）
- Cookie名と値（フレーバーテキスト性のあるもの推奨）
- 属性（実用的なCookie属性の組み合わせ）
- ポイント（カテゴリと整合）
- カテゴリ

Claude Code に「50個のサイト定義を生成」と依頼するのが効率的。生成例：

```typescript
{
  id: 'secure-bank',
  name: 'SecureBank',
  category: 'finance',
  description: '世界一安全な銀行（と自称）',
  cookie: {
    name: 'bank_auth',
    valueGenerator: () => `bank_${Math.random().toString(36).slice(2, 15)}`,
    attributes: {
      secure: true,
      httpOnly: true,
      sameSite: 'Strict',
      maxAge: 3600,
    },
    points: 150,
  },
  visitDuration: 3000,
  rarity: 'rare',
  iconEmoji: '🏦',
},
```

---

## 6. UI 仕様

### 6.1 ロビー画面（`/`）

シンプルなトップ画面：

- ゲームタイトル「🍪 Cookie Heist」
- ボタン: [シングルプレイヤー] [オンライン対戦]
- シングル選択 → AI数選択（1〜3人）→ ゲーム開始
- オンライン選択 → [ルーム作成] or [ルームコード入力]

### 6.2 待機画面（`/room/[id]/waiting`）※オンラインのみ

- ルームコード表示（4桁の英数字）
- QRコード表示（URLに room ID 埋め込み）
- 参加者リスト（リアルタイム更新）
- ホストのみ [ゲーム開始] ボタン
- 2〜4人で開始可能

### 6.3 ゲーム画面（`/room/[id]` or `/single`）

**画面レイアウト（左 70%: マップ、右 30%: ステータス&ランキング）**:

```
┌────────────────────────────────────────────────────────────┐
│ 🍪 Cookie Heist               残り 04:23                   │
├──────────────────────────────────────┬─────────────────────┤
│ [カテゴリフィルタ]                  │ 🏆 ランキング        │
│ [全て] [金融] [EC] [SNS] ...         │                    │
│                                      │ 🥇 AI Bot 1        │
│ [マップエリア]                       │   310pt           │
│ サイトカードのグリッド表示           │   bank, ghost, ...│
│ 4〜6列、スクロール可                  │                    │
│                                      │ 🥈 あなた          │
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ │   280pt           │
│ │🏦 Bk│ │📱Soc│ │🛒Shp│ │👻Gst│ │   bank, soc, ...  │
│ │ 150 │ │ 60  │ │ 60  │ │ 200 │ │                    │
│ │👥A B│ │👥C  │ │     │ │👥D  │ │ 🥉 AI Bot 2        │
│ │ 3秒 │ │ 2秒 │ │ 1秒 │ │ 5秒 │ │   220pt           │
│ └─────┘ └─────┘ └─────┘ └─────┘ │                    │
│ ...                                  │ 4位 AI Bot 3       │
│                                      │   190pt           │
│ [訪問中: SecureBank 60%]              ├─────────────────────┤
│ ████████░░░░  残り 2秒  [中断]       │ 📊 あなたの状態     │
│                                      │ スコア: 280pt      │
│                                      │ 訪問回数: 8        │
│                                      │ 奪取: 2 / 奪われ:1 │
│                                      │ 所持Cookie:        │
│                                      │  - bank (150pt)    │
│                                      │  - soc (60pt)      │
│                                      │  - news (50pt)     │
│                                      │  - ad (20pt)       │
└──────────────────────────────────────┴─────────────────────┘
```

### 6.4 サイトカード

各カードの表示要素:
- アイコン (emoji)
- サイト名
- ポイント数（大きく表示）
- 訪問時間
- 訪問中・訪問済みプレイヤー（アバター or 色）
- カテゴリ（色やアイコンで区別）
- レア度（枠の色: 通常=灰、中=青、高=紫、超=金）

クリック → 訪問開始（プログレスバー表示）

### 6.5 カテゴリフィルタ

画面上部に水平タブ:
[全て] [金融] [EC] [SNS] [メディア] [ゲーム] [広告] [政府] [ニッチ] [罠?] [特殊]

クリックで該当カテゴリのサイトのみ表示。

「罠」カテゴリは正体を隠す（実装次第で「全て」に紛れ込ませる方が自然）。

### 6.6 結果画面（`/result`）

- 最終ランキング表示（1位〜4位）
- 各プレイヤーの統計:
  - 最終スコア
  - 訪問回数
  - 奪取回数 / 奪われた回数
  - 集めた Cookie 種類数
- 「あなたのブラウザに保存されたCookie」セクション
  - 開発者ツールで確認するよう促す
  - 実際のCookie名のリスト表示
- [もう一度プレイ] [メニューに戻る] ボタン

---

## 7. ゲームロジック実装

### 7.1 状態管理（Zustand）

```typescript
// store/gameStore.ts
interface GameStore {
  // ゲーム全体
  gameId: string;
  startTime: Date | null;
  duration: number; // 秒
  isPlaying: boolean;
  
  // プレイヤー（自分含む全員）
  players: Map<PlayerId, Player>;
  myPlayerId: PlayerId;
  
  // サイト状態
  sitesState: Map<SiteId, SiteState>;
  
  // 現在の自分のアクション
  currentVisit: {
    siteId: SiteId;
    startTime: Date;
    progress: number; // 0-100
  } | null;
  
  // メソッド
  visitSite: (siteId: SiteId) => void;
  cancelVisit: () => void;
  // ...
}

interface Player {
  id: PlayerId;
  name: string;
  isAI: boolean;
  cookies: Map<SiteId, OwnedCookie>;
  score: number;
  stats: {
    visitCount: number;
    stealCount: number;
    stolenCount: number;
  };
}

interface SiteState {
  siteId: SiteId;
  visitorHistory: PlayerId[]; // 訪問順
  currentVisitors: Set<PlayerId>; // 訪問中
}

interface OwnedCookie {
  siteId: SiteId;
  cookieName: string;
  cookieValue: string;
  acquiredAt: Date;
  points: number;
}
```

### 7.2 訪問処理フロー

```typescript
async function visitSite(playerId: PlayerId, siteId: SiteId) {
  const site = SITES.find(s => s.id === siteId);
  
  // 1. 訪問開始
  gameStore.startVisit(playerId, siteId);
  emitToAll({ type: 'visit-start', playerId, siteId });
  
  // 2. 訪問時間待機（site.visitDuration ms）
  await sleep(site.visitDuration);
  
  // 3. 中断チェック
  if (gameStore.isCancelled(playerId, siteId)) {
    emitToAll({ type: 'visit-cancel', playerId, siteId });
    return;
  }
  
  // 4. Cookieをブラウザに発行（実Cookie）
  await fetch(`/api/sites/${siteId}`); // Set-Cookieが返ってくる
  
  // 5. ゲーム状態更新
  const cookie = generateCookie(site);
  
  // 5a. 既訪問プレイヤーから奪取
  const previousOwners = sitesState.get(siteId).visitorHistory
    .filter(pid => pid !== playerId);
  previousOwners.forEach(pid => {
    if (players.get(pid).cookies.has(siteId)) {
      players.get(pid).cookies.delete(siteId);
      players.get(pid).stats.stolenCount++;
      players.get(playerId).stats.stealCount++;
      emitToAll({ type: 'steal', from: pid, to: playerId, siteId });
    }
  });
  
  // 5b. 自分にCookie追加
  players.get(playerId).cookies.set(siteId, cookie);
  players.get(playerId).score = calculateScore(players.get(playerId));
  players.get(playerId).stats.visitCount++;
  sitesState.get(siteId).visitorHistory.push(playerId);
  
  // 6. 全クライアントに状態同期
  emitToAll({ type: 'state-update', state: serializeGameState() });
}
```

### 7.3 Cookie発行API

```typescript
// app/api/sites/[id]/route.ts
import { SITES } from '@/lib/sites';
import { NextResponse } from 'next/server';

export async function GET(
  request: Request,
  { params }: { params: { id: string } }
) {
  const site = SITES.find(s => s.id === params.id);
  if (!site) return new NextResponse('Not Found', { status: 404 });
  
  const cookieValue = site.cookie.valueGenerator();
  const cookieString = buildCookieString(site.cookie.name, cookieValue, site.cookie.attributes);
  
  return new NextResponse(`<html><body>Visited ${site.name}</body></html>`, {
    headers: {
      'Set-Cookie': cookieString,
      'Content-Type': 'text/html',
    },
  });
}

function buildCookieString(name: string, value: string, attrs: CookieAttributes): string {
  const parts = [`${name}=${value}`];
  if (attrs.secure) parts.push('Secure');
  if (attrs.httpOnly) parts.push('HttpOnly');
  if (attrs.sameSite) parts.push(`SameSite=${attrs.sameSite}`);
  if (attrs.maxAge) parts.push(`Max-Age=${attrs.maxAge}`);
  if (attrs.path) parts.push(`Path=${attrs.path}`);
  return parts.join('; ');
}
```

### 7.4 AI実装

```typescript
// lib/ai.ts
export class AIPlayer {
  constructor(
    public id: PlayerId,
    public personality: 'collector' | 'thief' | 'balanced' = 'balanced'
  ) {}
  
  // 毎秒判断してアクション決定
  decideAction(gameState: GameState): AIAction {
    const myState = gameState.players.get(this.id);
    if (myState.isVisiting) return { type: 'wait' };
    
    const candidates = this.evaluateSites(gameState);
    
    // 30%の確率でランダム選択（強すぎないように）
    if (Math.random() < 0.3) {
      const randomSite = candidates[Math.floor(Math.random() * candidates.length)];
      return { type: 'visit', siteId: randomSite.id };
    }
    
    // 70%の確率で最適選択
    const best = candidates.sort((a, b) => b.score - a.score)[0];
    return { type: 'visit', siteId: best.id };
  }
  
  private evaluateSites(gameState: GameState): SiteEvaluation[] {
    return SITES.map(site => {
      let score = site.cookie.points;
      
      // 訪問時間が長いほど減点
      score -= site.visitDuration / 100;
      
      // 性格別の調整
      if (this.personality === 'thief') {
        // 他人が持ってる Cookie ほど高得点（奪取狙い）
        const otherOwners = countOwners(gameState, site.id) - 
                            (gameState.players.get(this.id).cookies.has(site.id) ? 1 : 0);
        score += otherOwners * 50;
      } else if (this.personality === 'collector') {
        // 自分が持ってない Cookie を優先
        if (gameState.players.get(this.id).cookies.has(site.id)) score *= 0.5;
      }
      
      // ハニーポットは AI も避ける（完全じゃない）
      if (site.isHoneypot) score -= 200;
      
      return { id: site.id, score };
    });
  }
}
```

---

## 8. Socket.IO 通信仕様（オンライン対戦時）

### 8.1 イベント一覧

クライアント → サーバー:
- `room:create` - ルーム作成
- `room:join` - ルーム参加 (`{ roomId, playerName }`)
- `game:start` - ゲーム開始（ホストのみ）
- `game:visit-start` - 訪問開始 (`{ siteId }`)
- `game:visit-cancel` - 訪問中断
- `game:disconnect` - 切断

サーバー → クライアント:
- `room:joined` - ルーム参加完了
- `room:player-joined` - 新規プレイヤー参加
- `room:player-left` - プレイヤー退出
- `game:started` - ゲーム開始通知
- `game:state-update` - ゲーム状態更新（毎秒 or イベント時）
- `game:visit-start` - 誰かが訪問開始
- `game:visit-complete` - 誰かが訪問完了
- `game:steal` - 奪取発生 (`{ from, to, siteId }`)
- `game:ended` - ゲーム終了

### 8.2 同期戦略

- **イベント駆動**: アクション（訪問開始、完了、奪取など）が発生するたびに `game:state-update` を全員に配信
- **タイマー同期**: 残り時間はサーバーが管理、毎秒クライアントに送信
- **クライアント側予測なし**: 単純化のため、すべてサーバー権威モデル

---

## 9. 実装の優先順位

### Phase 1: コア機能（必須、優先度高）

1. **基本UI構築**
   - ロビー画面
   - ゲーム画面のレイアウト
   - サイトカード、ステータス、ランキングコンポーネント

2. **サイトデータ定義**
   - 最低 20〜30 サイトを TypeScript 配列で定義
   - 全カテゴリを網羅

3. **Cookie発行APIの実装**
   - `/api/sites/[id]` で実際にSet-Cookie

4. **シングルプレイヤーの基本動作**
   - サイト訪問、Cookie 取得、スコア計算
   - 制限時間管理

5. **AI実装**
   - 1 種類でいいので AI 対戦が成立する状態

### Phase 2: ゲームの深み（優先度中）

6. **Cookie 奪取ロジック**
7. **訪問時間のレア度別変動**
8. **AI の個性付け（3 種類）**
9. **ハニーポット実装**
10. **カテゴリフィルタ**
11. **結果画面・統計**

### Phase 3: オンライン対戦（優先度中）

12. **Socket.IO サーバー実装**
13. **ルーム機能、QRコード招待**
14. **複数プレイヤーの同期**

### Phase 4: ポリッシュ（優先度低、時間あれば）

15. **アニメーション（Framer Motion）**
16. **ターミナル風演出**
17. **サイト数を 50〜100 に増やす**
18. **観戦モード**
19. **トラップ機能（v2 で検討）**

---

## 10. 6.5週間スケジュール（5/25 〜 7/9）

| 週 | 期間 | やること |
|---|---|---|
| 1 | 5/26〜6/1 | 環境構築、Next.js/TypeScript 学習、設計確認 |
| 2 | 6/2〜6/8 | Phase 1: 基本UI + サイトデータ + Cookie発行API |
| 3 | 6/9〜6/15 | Phase 1完了: シングルプレイヤーの基本動作 + AI |
| 4 | 6/16〜6/22 | Phase 2: 奪取ロジック、レア度、AI個性、結果画面 |
| 5 | 6/23〜6/29 | Phase 3: オンライン対戦（Socket.IO） |
| 6 | 6/30〜7/6 | Phase 4: ポリッシュ、サイト数増加、デバッグ、デプロイ |
| 7 | 7/7〜7/8 | スライド作成、リハーサル |

---

## 11. デプロイ手順

### 11.1 フロント（Vercel）

1. GitHub にリポジトリ作成、コードプッシュ
2. Vercel でリポジトリを連携
3. 環境変数設定（Socket.IO サーバーURL）
4. デプロイ完了、`https://cookie-heist.vercel.app` のようなURL取得

### 11.2 Socket.IO サーバー（Railway）

1. Railway アカウント作成（GitHub連携可）
2. Node.js プロジェクトとして socket-server をデプロイ
3. 環境変数: ポート、CORS設定
4. デプロイ後の URL を Vercel の環境変数に設定

---

## 12. 発表時のデモ準備

### 12.1 シングルプレイのデモ
- スライドで仕組み解説後、実機でシングルプレイヤーを起動して見せる
- AI 対戦の様子を投影

### 12.2 オンライン対戦のデモ（観客参加）
- QRコード表示
- 観客にスマホでアクセスしてもらう
- 4人集まったら開始、リアルタイム対戦の様子を全員で見る

### 12.3 オチ:「あなたのブラウザに残ったCookie」
- ゲーム終了後、F12 → Application → Cookies を開いて見せる
- 「実際にこれだけのCookieが本物として保存されています」
- Webのバックグラウンドで日々起きていることを実感

### 12.4 補足:技術解説スライド
- Cookie の仕組み（Set-Cookie, Cookie ヘッダ）
- 属性（Secure, HttpOnly, SameSite, Max-Age）の意味
- 実世界での XSS / CSRF との関連性
- WebSocket によるリアルタイム同期

---

## 13. 注意事項・既知の課題

### 13.1 Cookie のドメイン制約
- すべての「サイト」を同じドメイン（例: `cookie-heist.vercel.app`）のパス配下に置く
- これにより全Cookieが同じドメインに集まり、採点APIで一括取得可能
- サブドメインを分けると Cookie 共有の問題が発生するので避ける

### 13.2 サードパーティ Cookie
- 現代のブラウザはサードパーティ Cookie をブロックする傾向
- 全部同じドメインで動かすので影響は最小限

### 13.3 ブラウザのCookie上限
- 1ドメインあたり通常 50 個程度の Cookie 上限
- 100 サイト全部訪問すると越える可能性
- 実装で Cookie 名が衝突しないよう注意

### 13.4 シークレットモード
- 「ゲーム後にF12でCookie確認」をしたい場合、通常モードでプレイすべき
- シークレットモードだとセッション終了でCookieが消える
- 発表時に観客への案内が必要

### 13.5 採点ロジックの位置
- ゲームスコア = サーバー上のゲーム状態（Map<PlayerId, Cookies>）で計算
- 実ブラウザの Cookie は「演出 + 発表のオチ」のためのもの
- 二者は独立して管理する（実Cookieは奪取で消さない、ゲーム状態だけが移動する）

---

## 14. Claude Code への依頼テンプレ

このプロジェクトを Claude Code に進めてもらう際のテンプレ:

```
Next.js 15 (App Router) + TypeScript + Tailwind CSS で
「Cookie Heist」というブラウザゲームを作りたい。

仕様書: SPEC.md を参照。

まず Phase 1 から進めて欲しい:
1. プロジェクト初期化（create-next-app）
2. 必要なライブラリ追加（zustand, qrcode.react, framer-motion, socket.io-client）
3. lib/sites.ts に最低20個のサイトデータを定義
4. /api/sites/[id]/route.ts でCookie発行API
5. app/single/page.tsx でシングルプレイヤー画面の基本UI
6. components/ にカードやランキング等のコンポーネント

質問があれば随時聞いて。実装する前に設計の確認をしながら進めて。
```

---

以上が仕様書の全体。ここに書ききれない判断は実装時に随時決める。
