import type { Site } from './types';

const rand = (len = 12) => Math.random().toString(36).slice(2, 2 + len);

// ポイントはレア度の帯で体系化している（端数なし・帯ごとに10刻み、帯内で相対順位を維持）。
//   common    : 20–50   （訪問3秒）
//   uncommon  : 60–100  （訪問6秒）
//   rare      : 120–160 （訪問8秒）
//   legendary : 180–200 （訪問20秒）
//   honeypot  : -30 / -40 / -50（マイナス）
// レア度 → 訪問時間 / Max-Age の対応は gameStore.ts の RARITY_MS / AI_VISIT_MS が担当。
export const SITES: Site[] = [
  // ── finance (rare → survey hard) ─────────────────────────────────
  {
    id: 'secure-bank',
    name: 'SecureBank',
    category: 'finance',
    description: '世界一安全な銀行（自称）。',
    cookie: {
      name: 'bank_auth',
      valueGenerator: () => `bank_${rand(16)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 3600 },
      points: 150,
    },
    template: 'survey',
    rarity: 'rare',
    iconEmoji: '🏦',
  },
  {
    id: 'crypto-exchange',
    name: 'CryptoExchange',
    category: 'finance',
    description: '24時間無休の仮想通貨取引所。',
    cookie: {
      name: 'crypto_session',
      valueGenerator: () => `0x${rand(32)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 1800 },
      points: 130,
    },
    template: 'survey',
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
      points: 130,
    },
    template: 'survey',
    rarity: 'rare',
    iconEmoji: '🪙',
  },

  // ── ecommerce (uncommon → login-form) ────────────────────────────
  {
    id: 'shop-mart',
    name: 'ShopMart',
    category: 'ecommerce',
    description: 'なんでも売ってるショッピングモール。',
    cookie: {
      name: 'cart_id',
      valueGenerator: () => `cart_${rand(12)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 60,
    },
    template: 'login-form',
    rarity: 'uncommon',
    iconEmoji: '🛒',
  },
  {
    id: 'electro-store',
    name: 'ElectroStore',
    category: 'ecommerce',
    description: '最新ガジェット専門店。',
    cookie: {
      name: 'electro_uid',
      valueGenerator: () => `eu_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 7 },
      points: 60,
    },
    template: 'login-form',
    rarity: 'uncommon',
    iconEmoji: '💻',
  },

  // ── social (uncommon → login-form) ───────────────────────────────
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
    template: 'login-form',
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
      points: 80,
    },
    template: 'login-form',
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
      points: 70,
    },
    template: 'login-form',
    rarity: 'uncommon',
    iconEmoji: '📸',
  },

  // ── media ─────────────────────────────────────────────────────────
  {
    id: 'news-portal',
    name: 'NewsPortal',
    category: 'media',
    description: '24時間速報を流し続けるニュースサイト。',
    cookie: {
      name: 'np_reader',
      valueGenerator: () => `np_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 },
      points: 40,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '📰',
  },
  {
    id: 'video-stream',
    name: 'VideoStream',
    category: 'media',
    description: '動画ストリーミングサービス。',
    cookie: {
      name: 'vs_auth',
      valueGenerator: () => `vs_${rand(16)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 80,
    },
    template: 'login-form',
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
    template: 'survey',
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
      points: 120,
    },
    template: 'survey',
    rarity: 'rare',
    iconEmoji: '🎰',
  },

  // ── advertising (common → ad-popup / consent-button) ─────────────
  {
    id: 'ad-network',
    name: 'AdNetwork',
    category: 'advertising',
    description: 'あなたの行動を24時間監視して広告を最適化する会社。',
    cookie: {
      name: 'ad_uid',
      valueGenerator: () => `adn_${rand(8)}`,
      attributes: { secure: true, sameSite: 'None', maxAge: 86400 * 365 },
      points: 20,
    },
    template: 'ad-popup',
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
      attributes: { secure: true, sameSite: 'None', maxAge: 86400 * 365 * 2 },
      points: 20,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '👁️',
  },

  // ── government (uncommon → survey) ───────────────────────────────
  {
    id: 'tax-agency',
    name: 'TaxAgency',
    category: 'government',
    description: '確定申告ポータル。',
    cookie: {
      name: 'tax_session',
      valueGenerator: () => `tax_${rand(20)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 1800 },
      points: 100,
    },
    template: 'survey',
    rarity: 'uncommon',
    iconEmoji: '🏛️',
  },

  // ── niche (common → consent-button) ──────────────────────────────
  {
    id: 'conspiracy-forum',
    name: 'ConspiracyForum',
    category: 'niche',
    description: 'あらゆる陰謀論を真剣に議論する掲示板。',
    cookie: {
      name: 'cf_anon',
      valueGenerator: () => `cf_${rand(8)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 365 },
      points: 30,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '👽',
  },
  {
    id: 'ghost-hunter',
    name: 'GhostHunter',
    category: 'niche',
    description: '全国の心霊スポット情報を集めたサイト。',
    cookie: {
      name: 'ghost_trace',
      valueGenerator: () => `gh_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 13 },
      points: 40,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '👻',
  },

  // ── social (追加) ────────────────────────────────────────────────
  {
    id: 'video-tube',
    name: 'VideoTube',
    category: 'social',
    description: '動画を見ながらいつの間にか3時間経っている動画プラットフォーム。',
    cookie: {
      name: 'vt_session',
      valueGenerator: () => `vt_${rand(18)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 70,
    },
    template: 'consent-button',
    rarity: 'uncommon',
    iconEmoji: '📺',
  },
  {
    id: 'short-clip',
    name: 'ShortClip',
    category: 'social',
    description: '15秒で世界が変わるショート動画アプリ。',
    cookie: {
      name: 'sc_uid',
      valueGenerator: () => `sc_${rand(14)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 60 },
      points: 50,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '🎵',
  },
  {
    id: 'pro-network',
    name: 'ProNetwork',
    category: 'social',
    description: 'ビジネス人脈を「つながり」で広げるSNS。',
    cookie: {
      name: 'pn_auth',
      valueGenerator: () => `pn_${rand(20)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 80,
    },
    template: 'survey',
    rarity: 'uncommon',
    iconEmoji: '💼',
  },

  // ── finance (追加) ────────────────────────────────────────────────
  {
    id: 'pay-ez',
    name: 'PayEZ',
    category: 'finance',
    description: 'QRコードをかざすだけで決済完了。',
    cookie: {
      name: 'pez_token',
      valueGenerator: () => `pez_${rand(16)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 3600 },
      points: 50,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '💳',
  },
  {
    id: 'stock-ticker',
    name: 'StockTicker',
    category: 'finance',
    description: 'AIによる相場予測を売りにした投資プラットフォーム。',
    cookie: {
      name: 'st_investor',
      valueGenerator: () => `sti_${rand(22)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 7200 },
      points: 140,
    },
    template: 'survey',
    rarity: 'rare',
    iconEmoji: '📈',
  },
  {
    id: 'loan-easy',
    name: 'LoanEasy',
    category: 'finance',
    description: '審査なし・即日融資。',
    cookie: {
      name: 'loan_sess',
      valueGenerator: () => `le_${rand(18)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 1800 },
      points: 90,
    },
    template: 'survey',
    rarity: 'uncommon',
    iconEmoji: '💰',
  },

  // ── gaming (追加) ────────────────────────────────────────────────
  {
    id: 'live-cast',
    name: 'LiveCast',
    category: 'gaming',
    description: 'ゲーム配信者と視聴者が盛り上がるライブ配信プラットフォーム。',
    cookie: {
      name: 'lc_viewer',
      valueGenerator: () => `lc_${rand(16)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 7 },
      points: 90,
    },
    template: 'consent-button',
    rarity: 'uncommon',
    iconEmoji: '🎥',
  },
  {
    id: 'retro-arcade',
    name: 'RetroArcade',
    category: 'gaming',
    description: '80年代の名作ゲームが遊べるアーカイブ。',
    cookie: {
      name: 'retro_pass',
      valueGenerator: () => `ra_${rand(20)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 86400 },
      points: 160,
    },
    template: 'quiz',
    rarity: 'rare',
    iconEmoji: '🕹️',
  },
  {
    id: 'esports-hub',
    name: 'EsportsHub',
    category: 'gaming',
    description: 'プロゲーマーの試合結果が集まるeスポーツポータル。',
    cookie: {
      name: 'eh_profile',
      valueGenerator: () => `eh_${rand(14)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 14 },
      points: 80,
    },
    template: 'survey',
    rarity: 'uncommon',
    iconEmoji: '🏆',
  },

  // ── niche (追加) ──────────────────────────────────────────────────
  {
    id: 'astro-scope',
    name: 'AstroScope',
    category: 'niche',
    description: '今日の運勢を星の配置で導く占いサイト。',
    cookie: {
      name: 'astro_sign',
      valueGenerator: () => `as_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 },
      points: 30,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '⭐',
  },
  {
    id: 'recipe-share',
    name: 'RecipeShare',
    category: 'niche',
    description: '主婦（主夫）が集うレシピ共有サイト。',
    cookie: {
      name: 'rs_user',
      valueGenerator: () => `rs_${rand(10)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 30,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '🍳',
  },

  // ── F12確認用サイト ───────────────────────────────────────────────
  {
    id: 'dev-tools-lab',
    name: 'DevToolsLab',
    category: 'special',
    description: 'Cookieの中身を隠さない開発者向けサイト。',
    cookie: {
      name: 'devlab_visible',
      valueGenerator: () => `VISIBLE_${rand(16).toUpperCase()}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 },
      points: 60,
    },
    template: 'consent-button',
    rarity: 'uncommon',
    iconEmoji: '🔧',
  },

  // ── 追加サイト（第2弾） ───────────────────────────────────────────
  {
    id: 'map-navi',
    name: 'MapNavi',
    category: 'media',
    description: '無料の地図ナビアプリ。',
    cookie: {
      name: 'navi_geo',
      valueGenerator: () => `geo_${rand(14)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 * 30 },
      points: 40,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '🗺️',
  },
  {
    id: 'cloud-drive',
    name: 'CloudDrive',
    category: 'ecommerce',
    description: '容量無制限を謳うクラウドストレージ。',
    cookie: {
      name: 'cd_session',
      valueGenerator: () => `cds_${rand(22)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Lax', maxAge: 86400 * 180 },
      points: 100,
    },
    template: 'login-form',
    rarity: 'uncommon',
    iconEmoji: '☁️',
  },
  {
    id: 'dating-match',
    name: 'DatingMatch',
    category: 'social',
    description: '運命の相手をAIが探すマッチングアプリ。',
    cookie: {
      name: 'dm_token',
      valueGenerator: () => `dm_${rand(18)}`,
      attributes: { secure: true, sameSite: 'Lax', maxAge: 86400 * 14 },
      points: 70,
    },
    template: 'survey',
    rarity: 'uncommon',
    iconEmoji: '💘',
  },
  {
    id: 'whitehat-forum',
    name: 'WhiteHatForum',
    category: 'niche',
    description: '善良なハッカーが脆弱性を議論する掲示板。',
    cookie: {
      name: 'wh_member',
      valueGenerator: () => `wh_${rand(20)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 86400 * 7 },
      points: 140,
    },
    template: 'quiz',
    rarity: 'rare',
    iconEmoji: '🛡️',
  },

  // ── honeypot (ad-popup, negative points) ─────────────────────────
  {
    id: 'secuure-bank',
    name: 'SecuureBank',
    category: 'honeypot',
    description: '銀行っぽいサイト。',
    cookie: {
      name: 'phish_trap',
      valueGenerator: () => `trap_${rand(8)}`,
      // 罠サイトは保護属性なし＝無防備なCookie（正規サイトとの対比用）
      attributes: { maxAge: 60 },
      points: -50,
    },
    template: 'ad-popup',
    rarity: 'common',
    isHoneypot: true,
    iconEmoji: '🏦',
  },
  {
    id: 'add-network',
    name: 'AddNetwork',
    category: 'honeypot',
    description: 'AdNetworkに似た名前の怪しいサイト。',
    cookie: {
      name: 'malware_id',
      valueGenerator: () => `mal_${rand(6)}`,
      attributes: { maxAge: 86400 * 365 },
      points: -30,
    },
    template: 'ad-popup',
    rarity: 'common',
    isHoneypot: true,
    iconEmoji: '📢',
  },

  // ── mystery (shown as ??? until visited) ─────────────────────────
  {
    id: 'mystery-alpha',
    name: 'MysteryBox',
    category: 'niche',
    description: '中身がわからない箱を売っているらしいサイト。',
    cookie: {
      name: 'mystery_alpha',
      valueGenerator: () => `mx_${rand(12)}`,
      attributes: { sameSite: 'Lax', maxAge: 86400 },
      points: 50,
    },
    template: 'consent-button',
    rarity: 'common',
    iconEmoji: '❓',
    isMystery: true,
  },
  {
    id: 'mystery-beta',
    name: 'CryptoMail',
    category: 'special',
    description: 'エンドツーエンド暗号化を謳うメールサービス。',
    cookie: {
      name: 'mystery_beta',
      valueGenerator: () => `mb_${rand(16)}`,
      attributes: { secure: true, sameSite: 'Strict', maxAge: 3600 },
      points: 90,
    },
    template: 'login-form',
    rarity: 'uncommon',
    iconEmoji: '🔐',
    isMystery: true,
  },
  {
    id: 'mystery-gamma',
    name: 'PrizeWinner',
    category: 'honeypot',
    description: '派手なポップアップで「あなたが選ばれました」と表示するサイト。',
    cookie: {
      name: 'mystery_gamma',
      valueGenerator: () => `mg_${rand(8)}`,
      attributes: { maxAge: 60 },
      points: -40,
    },
    template: 'ad-popup',
    rarity: 'common',
    iconEmoji: '💀',
    isHoneypot: true,
    isMystery: true,
  },
  {
    id: 'mystery-delta',
    name: 'SecurityLab',
    category: 'special',
    description: '研究機関を名乗るサイト。',
    cookie: {
      name: 'mystery_delta',
      valueGenerator: () => `md_${rand(14)}`,
      attributes: { httpOnly: true, sameSite: 'Strict', maxAge: 7200 },
      points: 120,
    },
    template: 'survey',
    rarity: 'rare',
    iconEmoji: '🔬',
    isMystery: true,
  },
  {
    id: 'mystery-omega',
    name: 'CyberLegend',
    category: 'special',
    description: 'ネットの都市伝説サイト。',
    cookie: {
      name: 'mystery_omega',
      valueGenerator: () => `mo_${rand(20)}`,
      attributes: { secure: true, httpOnly: true, sameSite: 'Strict', maxAge: 86400 * 30 },
      points: 180,
    },
    template: 'quiz',
    rarity: 'legendary',
    iconEmoji: '🌀',
    isMystery: true,
  },

  // ── special (legendary → quiz) ────────────────────────────────────
  {
    id: 'ghost-site',
    name: 'GhostSite',
    category: 'special',
    description: 'Max-Age=10秒のCookieを発行する。',
    cookie: {
      name: 'ghost_cookie',
      valueGenerator: () => `👻${rand(12)}`,
      attributes: { sameSite: 'Lax', maxAge: 10 },
      points: 200,
    },
    template: 'quiz',
    rarity: 'legendary',
    iconEmoji: '👾',
  },
  {
    id: 'eternal-session',
    name: 'EternalSession',
    category: 'special',
    description: '100年有効なCookieを発行するサービス。',
    cookie: {
      name: 'eternal_id',
      valueGenerator: () => `eternity_${rand(20)}`,
      attributes: { secure: true, sameSite: 'None', maxAge: 86400 * 365 * 100 },
      points: 180,
    },
    template: 'quiz',
    rarity: 'legendary',
    iconEmoji: '♾️',
  },
];

export const SITES_MAP: ReadonlyMap<string, Site> = new Map(SITES.map(s => [s.id, s]));

export function getSiteById(id: string): Site | undefined {
  return SITES_MAP.get(id);
}

// Max-Age（秒）を読みやすい単位に整形する。値の大きさで秒/分/時間/日/年を自動選択。
// 例: 10→「10秒」, 1800→「30分」, 3600→「1時間」, 86400*30→「30日」, 86400*365*100→「約100年」。
// 正確な秒数が要る箇所（CookieInspector の説明文など）では呼び出し側で別途併記する。
export function formatMaxAge(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}分`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)}時間`;
  const days = hours / 24;
  if (days < 365) return `${Math.round(days)}日`;
  return `約${Math.round(days / 365).toLocaleString()}年`;
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
