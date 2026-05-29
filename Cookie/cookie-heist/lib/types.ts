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

export type SiteTemplate = 'consent-button' | 'ad-popup' | 'login-form' | 'survey' | 'quiz';

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
