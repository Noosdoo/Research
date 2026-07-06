export type PlayerId = string;
export type SiteId = string;

export type SiteCategory =
  | 'finance'
  | 'ecommerce'
  | 'social'
  | 'media'
  | 'gaming'
  | 'advertising'
  | 'government'
  | 'niche'
  | 'honeypot'
  | 'special';

export type Rarity = 'common' | 'uncommon' | 'rare' | 'legendary';

export type SiteTemplate = 'consent-button' | 'ad-popup' | 'login-form' | 'survey' | 'quiz' | 'phishing';

export interface CookieAttributes {
  secure?: boolean;
  httpOnly?: boolean;
  sameSite?: 'Strict' | 'Lax' | 'None';
  maxAge?: number;
  path?: string;
}

export interface SiteCookie {
  name: string;
  valueGenerator: () => string;
  attributes: CookieAttributes;
  points: number;
  // カードに“見せる”得点（誘い）。実際に入る points と分離できる。
  // フィッシング詐欺サイトで「高得点に見せて実はマイナス」を作るために使う。
  displayPoints?: number;
}

export interface Site {
  id: SiteId;
  name: string;
  category: SiteCategory;
  description: string;
  cookie: SiteCookie;
  template: SiteTemplate;
  rarity: Rarity;
  isHoneypot?: boolean;
  isMystery?: boolean;
  iconEmoji?: string;
}

export interface OwnedCookie {
  siteId: SiteId;
  cookieName: string;
  cookieValue: string;
  acquiredAt: number; // ms since epoch (Date.now())
  points: number;
}

export interface PlayerStats {
  visitCount: number;
  stealCount: number;
  stolenCount: number;
}

export interface Player {
  id: PlayerId;
  name: string;
  isAI: boolean;
  color: string;
  cookies: Map<SiteId, OwnedCookie>;
  // 奪取されたが取り返せていないCookie（結果画面で表示／実ブラウザにはまだ残っている）
  lostCookies: Map<SiteId, OwnedCookie>;
  score: number;
  stats: PlayerStats;
  isVisiting: boolean;
}

export interface SiteState {
  siteId: SiteId;
  ownerIds: PlayerId[];
  currentVisitorIds: PlayerId[];
}

export interface StealEvent {
  id: string;
  from: PlayerId;
  to: PlayerId;
  siteId: SiteId;
  siteName: string;
  points: number;
  at: number;
}

export interface ExpireEvent {
  id: string;
  playerId: PlayerId;
  siteId: SiteId;
  siteName: string;
  cookieName: string;
  points: number;
  at: number;
}

export type AIPersonality = 'collector' | 'thief' | 'balanced';
