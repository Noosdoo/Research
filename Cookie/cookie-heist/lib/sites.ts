import type { Site } from './types';

const rand = (len = 12) => Math.random().toString(36).slice(2, 2 + len);

export const SITES: Site[] = [
  // ── finance ──────────────────────────────────────────────────────
  {
    id: 'secure-bank',
    name: 'SecureBank',
    category: 'finance',
    description: '世界一安全な銀行（自称）。ログアウトしても Cookie は残る。',
    cookie: {
      name: 'bank_auth',
      valueGenerator: () => `bank_${rand(16)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 3600 },
      points: 150,
    },
    visitDuration: 3000,
    rarity: 'rare',
    iconEmoji: '🏦',
  },
  {
    id: 'crypto-exchange',
    name: 'CryptoExchange',
    category: 'finance',
    description: '24時間無休の仮想通貨取引所。セキュリティは最高水準（たぶん）。',
    cookie: {
      name: 'crypto_session',
      valueGenerator: () => `0x${rand(32)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 1800 },
      points: 130,
    },
    visitDuration: 3000,
    rarity: 'rare',
    iconEmoji: '₿',
  },
  {
    id: 'gold-vault',
    name: 'GoldVault',
    category: 'finance',
    description: '金の延べ棒をオンラインで購入できる謎の金融サービス。',
    cookie: {
      name: 'vault_token',
      valueGenerator: () => `gv_${rand(20)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Lax', maxAge: 7200 },
      points: 120,
    },
    visitDuration: 3000,
    rarity: 'rare',
    iconEmoji: '🪙',
  },

  // ── ecommerce ─────────────────────────────────────────────────────
  {
    id: 'shop-mart',
    name: 'ShopMart',
    category: 'ecommerce',
    description: 'なんでも売ってる世界最大のオンラインショッピングモール。',
    cookie: {
      name: 'cart_id',
      valueGenerator: () => `cart_${rand(12)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 60,
    },
    visitDuration: 2000,
    rarity: 'uncommon',
    iconEmoji: '🛒',
  },
  {
    id: 'electro-store',
    name: 'ElectroStore',
    category: 'ecommerce',
    description: '最新ガジェットが最安値で手に入る…とは限らない電子機器ショップ。',
    cookie: {
      name: 'electro_uid',
      valueGenerator: () => `eu_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 7 },
      points: 55,
    },
    visitDuration: 2000,
    rarity: 'uncommon',
    iconEmoji: '💻',
  },

  // ── social ────────────────────────────────────────────────────────
  {
    id: 'tweet-space',
    name: 'TweetSpace',
    category: 'social',
    description: '140文字で世界を変えようとする人々が集うSNS。',
    cookie: {
      name: 'tw_sess',
      valueGenerator: () => `twsess_${rand(24)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 70,
    },
    visitDuration: 2000,
    rarity: 'uncommon',
    iconEmoji: '🐦',
  },
  {
    id: 'face-connect',
    name: 'FaceConnect',
    category: 'social',
    description: '顔写真を公開することへの抵抗を消し去った元祖SNS。',
    cookie: {
      name: 'fc_token',
      valueGenerator: () => `fc_${rand(20)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 90 },
      points: 75,
    },
    visitDuration: 2000,
    rarity: 'uncommon',
    iconEmoji: '👤',
  },
  {
    id: 'photo-gram',
    name: 'PhotoGram',
    category: 'social',
    description: '盛れた写真だけ投稿するフォトシェアリングアプリ。',
    cookie: {
      name: 'pg_session',
      valueGenerator: () => `pg_${rand(18)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 14 },
      points: 65,
    },
    visitDuration: 2000,
    rarity: 'uncommon',
    iconEmoji: '📸',
  },

  // ── media ─────────────────────────────────────────────────────────
  {
    id: 'news-portal',
    name: 'NewsPortal',
    category: 'media',
    description: '速報 30% 誤報 70% のニュースサイト。登録メールは必須。',
    cookie: {
      name: 'np_reader',
      valueGenerator: () => `np_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 },
      points: 40,
    },
    visitDuration: 1000,
    rarity: 'common',
    iconEmoji: '📰',
  },
  {
    id: 'video-stream',
    name: 'VideoStream',
    category: 'media',
    description: 'バッファリングが十八番の動画ストリーミングサービス。',
    cookie: {
      name: 'vs_auth',
      valueGenerator: () => `vs_${rand(16)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 80,
    },
    visitDuration: 2000,
    rarity: 'uncommon',
    iconEmoji: '🎬',
  },

  // ── gaming ────────────────────────────────────────────────────────
  {
    id: 'game-zone',
    name: 'GameZone',
    category: 'gaming',
    description: '課金しないとクリアできないゲームが揃うポータル。',
    cookie: {
      name: 'gz_player',
      valueGenerator: () => `gz_${rand(14)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 7 },
      points: 90,
    },
    visitDuration: 2000,
    rarity: 'uncommon',
    iconEmoji: '🎮',
  },
  {
    id: 'online-casino',
    name: 'OnlineCasino',
    category: 'gaming',
    description: '「必勝法あります」という広告が絶えないオンラインカジノ。',
    cookie: {
      name: 'casino_chip',
      valueGenerator: () => `chip_${rand(16)}`,
      attributes: { secure: true, sameSite: 'Strict', maxAge: 86400 },
      points: 110,
    },
    visitDuration: 3000,
    rarity: 'rare',
    iconEmoji: '🎰',
  },

  // ── advertising ───────────────────────────────────────────────────
  {
    id: 'ad-network',
    name: 'AdNetwork',
    category: 'advertising',
    description: 'あなたの行動を24時間監視して広告を最適化する会社。',
    cookie: {
      name: 'ad_uid',
      valueGenerator: () => `adn_${rand(8)}`,
      attributes: { sameSite: 'None', maxAge: 86400 * 365 },
      points: 30,
    },
    visitDuration: 1000,
    rarity: 'common',
    iconEmoji: '📢',
  },
  {
    id: 'tracker-corp',
    name: 'TrackerCorp',
    category: 'advertising',
    description: 'トラッキングピクセルを10億サイトに設置している謎の企業。',
    cookie: {
      name: 'tc_track',
      valueGenerator: () => `tc_${rand(10)}`,
      attributes: { sameSite: 'None', maxAge: 86400 * 365 * 2 },
      points: 25,
    },
    visitDuration: 1000,
    rarity: 'common',
    iconEmoji: '👁️',
  },

  // ── government ────────────────────────────────────────────────────
  {
    id: 'tax-agency',
    name: 'TaxAgency',
    category: 'government',
    description: '確定申告ポータル。UIは2003年から更新されていない。',
    cookie: {
      name: 'tax_session',
      valueGenerator: () => `tax_${rand(20)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 1800 },
      points: 100,
    },
    visitDuration: 3000,
    rarity: 'rare',
    iconEmoji: '🏛️',
  },

  // ── niche ─────────────────────────────────────────────────────────
  {
    id: 'conspiracy-forum',
    name: 'ConspiracyForum',
    category: 'niche',
    description: 'あらゆる陰謀論を真剣に議論する掲示板。月面着陸は演出。',
    cookie: {
      name: 'cf_anon',
      valueGenerator: () => `cf_${rand(8)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 365 },
      points: 35,
    },
    visitDuration: 1000,
    rarity: 'common',
    iconEmoji: '👽',
  },
  {
    id: 'ghost-hunter',
    name: 'GhostHunter',
    category: 'niche',
    description: '全国の心霊スポット情報を集めたサイト。管理人は連絡不通。',
    cookie: {
      name: 'ghost_trace',
      valueGenerator: () => `gh_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 13 },
      points: 45,
    },
    visitDuration: 1000,
    rarity: 'common',
    iconEmoji: '👻',
  },

  // ── honeypot ─────────────────────────────────────────────────────
  {
    id: 'secuure-bank',
    name: 'SecuureBank',
    category: 'honeypot',
    description: '銀行っぽいサイト。よく見ると "u" が2つ…',
    cookie: {
      name: 'phish_trap',
      valueGenerator: () => `trap_${rand(8)}`,
      attributes: { sameSite: 'Lax', maxAge: 60 },
      points: -50,
    },
    visitDuration: 1000,
    rarity: 'common',
    isHoneypot: true,
    iconEmoji: '🏦',
  },
  {
    id: 'add-network',
    name: 'AddNetwork',
    category: 'honeypot',
    description: 'AdNetworkと似た名前の怪しいサイト。アクセスすると…',
    cookie: {
      name: 'malware_id',
      valueGenerator: () => `mal_${rand(6)}`,
      attributes: { maxAge: 86400 * 365 },
      points: -30,
    },
    visitDuration: 1000,
    rarity: 'common',
    isHoneypot: true,
    iconEmoji: '📢',
  },

  // ── special ───────────────────────────────────────────────────────
  {
    id: 'ghost-site',
    name: 'GhostSite',
    category: 'special',
    description: 'Cookieの有効期限が10秒の謎のサイト。取得してもすぐ消える…？',
    cookie: {
      name: 'ghost_cookie',
      valueGenerator: () => `👻${rand(12)}`,
      attributes: { sameSite: 'Lax', maxAge: 10 },
      points: 200,
    },
    visitDuration: 5000,
    rarity: 'legendary',
    iconEmoji: '👾',
  },
  {
    id: 'eternal-session',
    name: 'EternalSession',
    category: 'special',
    description: '100年有効なCookieを発行するサービス。孫の代まで追跡される。',
    cookie: {
      name: 'eternal_id',
      valueGenerator: () => `eternity_${rand(20)}`,
      attributes: { secure: true, sameSite: 'None', maxAge: 86400 * 365 * 100 },
      points: 180,
    },
    visitDuration: 5000,
    rarity: 'legendary',
    iconEmoji: '♾️',
  },
];

export function getSiteById(id: string): Site | undefined {
  return SITES.find(s => s.id === id);
}

export const CATEGORY_LABELS: Record<string, string> = {
  finance: '金融',
  ecommerce: 'EC',
  social: 'SNS',
  media: 'メディア',
  gaming: 'ゲーム',
  advertising: '広告',
  government: '政府',
  niche: 'ニッチ',
  honeypot: '罠',
  special: '特殊',
};
