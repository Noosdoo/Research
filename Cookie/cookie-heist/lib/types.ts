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
  visitDuration: number;
  rarity: Rarity;
  isHoneypot?: boolean;
  iconEmoji?: string;
}

export interface OwnedCookie {
  siteId: SiteId;
  cookieName: string;
  cookieValue: string;
  acquiredAt: Date;
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

export interface CurrentVisit {
  siteId: SiteId;
  startTime: number;
  progress: number;
  cancelRequested: boolean;
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

export type AIPersonality = 'collector' | 'thief' | 'balanced';
