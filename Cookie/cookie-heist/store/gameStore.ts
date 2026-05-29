'use client';

import { create } from 'zustand';
import { SITES, SITES_MAP } from '@/lib/sites';

// Module-level set to track and cancel pending AI visit timers
const aiTimers = new Set<ReturnType<typeof setTimeout>>();
import type {
  Player,
  PlayerId,
  SiteId,
  SiteState,
  OwnedCookie,
  StealEvent,
  ExpireEvent,
  Rarity,
} from '@/lib/types';

const GAME_DURATION = 3 * 60; // seconds

const PLAYER_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b'];

const RARITY_MS: Record<Rarity, number> = {
  common: 8000,
  uncommon: 12000,
  rare: 18000,
  legendary: 25000,
};

function makePlayer(id: PlayerId, name: string, isAI: boolean, colorIdx: number): Player {
  return {
    id,
    name,
    isAI,
    color: PLAYER_COLORS[colorIdx % PLAYER_COLORS.length],
    cookies: new Map(),
    score: 0,
    stats: { visitCount: 0, stealCount: 0, stolenCount: 0 },
    isVisiting: false,
  };
}

function initSiteStates(): Map<SiteId, SiteState> {
  const m = new Map<SiteId, SiteState>();
  for (const s of SITES) {
    m.set(s.id, { siteId: s.id, ownerIds: [], currentVisitorIds: [] });
  }
  return m;
}

// Serialized player shape coming from server (cookies as plain object)
export interface ServerPlayer {
  id: string; name: string; color: string;
  score: number; isVisiting: boolean;
  cookies: Record<string, OwnedCookie>;
  stats: { visitCount: number; stealCount: number; stolenCount: number };
}

interface GameStore {
  // meta
  gameId: string;
  phase: 'lobby' | 'playing' | 'result';
  startTime: number | null;
  timeLeft: number;
  gameDuration: number;
  aiCount: number;

  // online mode
  mode: 'local' | 'online';
  onlineGameId: string | null;

  // players
  players: Map<PlayerId, Player>;
  myPlayerId: PlayerId;

  // sites
  sitesState: Map<SiteId, SiteState>;

  // notifications
  stealEvents: StealEvent[];
  expireEvents: ExpireEvent[];

  // actions
  initGame: (aiCount: number, duration?: number) => void;
  tickTimer: () => void;
  completeVisit: (siteId: SiteId, pointOverride?: number, cookieValue?: string) => void;
  processAITick: (aiId: PlayerId) => void;
  endGame: () => void;
  clearStealEvent: (id: string) => void;
  clearExpireEvent: (id: string) => void;

  // online-mode actions
  initOnlineGame: (data: {
    gameId: string;
    myPlayerId: string;
    players: Record<string, ServerPlayer>;
    sitesState: Record<string, SiteState>;
  }) => void;
  applyServerUpdate: (data: {
    players: Record<string, ServerPlayer>;
    sitesState: Record<string, SiteState>;
    stealEvents: StealEvent[];
  }) => void;
  setTimeLeft: (t: number) => void;
  exitOnlineMode: () => void;
  resetToLobby: () => void;
}

export const useGameStore = create<GameStore>((set, get) => ({
  gameId: '',
  phase: 'lobby',
  startTime: null,
  timeLeft: GAME_DURATION,
  gameDuration: GAME_DURATION,
  aiCount: 1,
  mode: 'local',
  onlineGameId: null,
  players: new Map(),
  myPlayerId: 'player-human',
  sitesState: initSiteStates(),
  stealEvents: [],
  expireEvents: [],

  initGame(aiCount: number, duration?: number) {
    const dur = Math.min(180, Math.max(30, duration ?? GAME_DURATION));
    const players = new Map<PlayerId, Player>();
    players.set('player-human', makePlayer('player-human', 'あなた', false, 0));
    const aiNames = ['AI Bot 1', 'AI Bot 2', 'AI Bot 3'];
    for (let i = 0; i < aiCount; i++) {
      const id = `ai-${i}`;
      players.set(id, makePlayer(id, aiNames[i], true, i + 1));
    }
    set({
      gameId: `game-${Date.now()}`,
      phase: 'playing',
      startTime: Date.now(),
      timeLeft: dur,
      gameDuration: dur,
      aiCount,
      players,
      myPlayerId: 'player-human',
      sitesState: initSiteStates(),
      stealEvents: [],
      expireEvents: [],
    });
  },

  tickTimer() {
    const { startTime, phase, gameDuration } = get();
    if (phase !== 'playing' || !startTime) return;
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const timeLeft = Math.max(0, gameDuration - elapsed);
    if (timeLeft === 0) {
      get().endGame();
      return;
    }

    // Check cookie expiry for all players
    const now = Date.now();
    const { players, sitesState, expireEvents } = get();
    const newPlayers = new Map(players);
    const newSites = new Map(sitesState);
    const newExpireEvents: ExpireEvent[] = [];
    let changed = false;

    for (const [pid, player] of players) {
      for (const [sid, owned] of player.cookies) {
        const site = SITES_MAP.get(sid);
        const maxAge = site?.cookie.attributes.maxAge;
        if (!maxAge) continue;
        if (now - owned.acquiredAt < maxAge * 1000) continue;

        const cur = newPlayers.get(pid)!;
        const newCookies = new Map(cur.cookies);
        newCookies.delete(sid);
        newPlayers.set(pid, { ...cur, cookies: newCookies, score: cur.score - owned.points });

        const ss = newSites.get(sid);
        if (ss?.ownerIds.includes(pid)) {
          newSites.set(sid, { ...ss, ownerIds: ss.ownerIds.filter(id => id !== pid) });
        }

        newExpireEvents.push({
          id: `expire-${now}-${Math.random()}`,
          playerId: pid, siteId: sid,
          siteName: site!.name, cookieName: owned.cookieName,
          points: owned.points, at: now,
        });
        changed = true;
      }
    }

    set({
      timeLeft,
      ...(changed ? {
        players: newPlayers,
        sitesState: newSites,
        expireEvents: [...expireEvents, ...newExpireEvents].slice(-10),
      } : {}),
    });
  },

  completeVisit(siteId: SiteId, pointOverride?: number, cookieValue?: string) {
    const { phase, myPlayerId } = get();
    if (phase !== 'playing') return;
    finishVisit(get, set, siteId, myPlayerId, true, pointOverride, cookieValue);
  },

  processAITick(aiId: PlayerId) {
    const { players, sitesState, phase } = get();
    if (phase !== 'playing') return;
    const ai = players.get(aiId);
    if (!ai || ai.isVisiting) return;

    // 30%の確率でサボる
    if (Math.random() < 0.3) return;

    const candidates = SITES
      .map(s => {
        // ハニーポットを40%の確率で踏む
        if (s.isHoneypot && Math.random() > 0.4) return null;
        let score = s.cookie.points;
        score -= RARITY_MS[s.rarity] / 1000;
        if (ai.cookies.has(s.id)) score *= 0.3;
        const ss = sitesState.get(s.id)!;
        const ownerIds = ss.ownerIds;
        // 人間プレイヤーが所有している同意サイトを積極的に奪う
        const humanOwns = ownerIds.filter(id => {
          const p = players.get(id);
          return p && !p.isAI && id !== aiId;
        }).length;
        if (s.template === 'consent-button' && humanOwns > 0) score += humanOwns * 50;
        // 他プレイヤー所有サイトの一般奪取インセンティブ
        const othersOwn = ownerIds.filter(id => id !== aiId).length;
        score += othersOwn * 15;
        // 他のAIが訪問中のサイトを避ける
        const visiting = ss.currentVisitorIds.filter(id => id !== aiId).length;
        score -= visiting * 20;
        return { id: s.id, score, rarity: s.rarity, template: s.template };
      })
      .filter(Boolean)
      .sort((a, b) => b!.score - a!.score) as { id: string; score: number; rarity: Rarity; template: string }[];

    // 40%でランダム選択（上位5件から）
    const pick = Math.random() < 0.4
      ? candidates[Math.floor(Math.random() * Math.min(5, candidates.length))]
      : candidates[0];

    if (!pick) return;
    aiVisitSite(get, set, aiId, pick.id);
  },

  endGame() {
    // Cancel all pending AI visit timers
    for (const id of aiTimers) clearTimeout(id);
    aiTimers.clear();
    // Reset any AI isVisiting flags so result screen is clean
    const { players } = get();
    const newPlayers = new Map(players);
    for (const [id, p] of newPlayers) {
      if (p.isVisiting) newPlayers.set(id, { ...p, isVisiting: false });
    }
    set({ phase: 'result', players: newPlayers });
  },

  clearStealEvent(id: string) {
    set(s => ({ stealEvents: s.stealEvents.filter(e => e.id !== id) }));
  },

  clearExpireEvent(id: string) {
    set(s => ({ expireEvents: s.expireEvents.filter(e => e.id !== id) }));
  },

  // ── Online mode ───────────────────────────────────────────────────
  initOnlineGame({ gameId, myPlayerId, players: pObj, sitesState: ssObj }) {
    const players = new Map<PlayerId, Player>();
    for (const [id, p] of Object.entries(pObj)) {
      players.set(id, {
        ...p, isAI: false,
        cookies: new Map(Object.entries(p.cookies || {})) as Map<SiteId, OwnedCookie>,
      });
    }
    const sitesState = new Map<SiteId, SiteState>();
    for (const [id, ss] of Object.entries(ssObj)) sitesState.set(id, ss);

    set({
      mode: 'online', onlineGameId: gameId,
      gameId, myPlayerId, players, sitesState,
      phase: 'playing', timeLeft: GAME_DURATION,
      stealEvents: [], expireEvents: [], startTime: Date.now(),
    });
  },

  applyServerUpdate({ players: pObj, sitesState: ssObj, stealEvents: newEvents }) {
    const players = new Map<PlayerId, Player>();
    for (const [id, p] of Object.entries(pObj)) {
      players.set(id, {
        ...p, isAI: false,
        cookies: new Map(Object.entries(p.cookies || {})) as Map<SiteId, OwnedCookie>,
      });
    }
    const prev = get().sitesState;
    const sitesState = Object.keys(ssObj).length > 0
      ? (() => {
          const m = new Map<SiteId, SiteState>();
          for (const [id, ss] of Object.entries(ssObj)) m.set(id, ss);
          return m;
        })()
      : prev;

    set({
      players, sitesState,
      stealEvents: [...get().stealEvents, ...(newEvents || [])].slice(-20),
    });
  },

  setTimeLeft(t: number) {
    if (t <= 0 && get().phase === 'playing') get().endGame();
    else set({ timeLeft: t });
  },

  exitOnlineMode() {
    set({ mode: 'local', onlineGameId: null, phase: 'lobby' });
  },

  resetToLobby() {
    set({ phase: 'lobby' });
  },
}));

// ── helpers ────────────────────────────────────────────────────────

function finishVisit(
  get: () => GameStore,
  set: (s: Partial<GameStore>) => void,
  siteId: SiteId,
  playerId: PlayerId,
  success: boolean,
  pointOverride?: number,
  cookieValueOverride?: string,
) {
  const { players, sitesState } = get();
  const site = SITES_MAP.get(siteId)!;

  const newPlayers = new Map(players);
  const newSites = new Map(sitesState);
  const ss = newSites.get(siteId)!;

  // remove from currentVisitors
  newSites.set(siteId, {
    ...ss,
    currentVisitorIds: ss.currentVisitorIds.filter(id => id !== playerId),
  });

  const player = newPlayers.get(playerId);
  if (!player) { set({ sitesState: newSites }); return; }

  if (!success) {
    newPlayers.set(playerId, { ...player, isVisiting: false });
    set({ players: newPlayers, sitesState: newSites });
    return;
  }

  // steal from previous owners
  const newStealEvents: StealEvent[] = [];
  const latestSS = newSites.get(siteId)!;
  for (const ownerId of [...latestSS.ownerIds]) {
    if (ownerId === playerId) continue;
    const owner = newPlayers.get(ownerId);
    if (!owner || !owner.cookies.has(siteId)) continue;

    const stolenCookie = owner.cookies.get(siteId)!;
    const newCookies = new Map(owner.cookies);
    newCookies.delete(siteId);
    newPlayers.set(ownerId, {
      ...owner,
      cookies: newCookies,
      score: owner.score - stolenCookie.points,
      stats: { ...owner.stats, stolenCount: owner.stats.stolenCount + 1 },
    });

    const thief = newPlayers.get(playerId)!;
    newPlayers.set(playerId, {
      ...thief,
      stats: { ...thief.stats, stealCount: thief.stats.stealCount + 1 },
    });

    newStealEvents.push({
      id: `${Date.now()}-${Math.random()}`,
      from: ownerId,
      to: playerId,
      siteId,
      siteName: site.name,
      points: stolenCookie.points,
      at: Date.now(),
    });
  }

  // add cookie to player
  const earnedPoints = pointOverride ?? site.cookie.points;
  const cookieValue = cookieValueOverride ?? site.cookie.valueGenerator();
  const owned: OwnedCookie = {
    siteId,
    cookieName: site.cookie.name,
    cookieValue,
    acquiredAt: Date.now(),
    points: earnedPoints,
  };

  const freshPlayer = newPlayers.get(playerId)!;
  const newCookies = new Map(freshPlayer.cookies);
  newCookies.set(siteId, owned);

  newPlayers.set(playerId, {
    ...freshPlayer,
    isVisiting: false,
    cookies: newCookies,
    score: freshPlayer.score + earnedPoints,
    stats: { ...freshPlayer.stats, visitCount: freshPlayer.stats.visitCount + 1 },
  });

  // site now owned solely by this player (last visitor wins)
  newSites.set(siteId, { ...newSites.get(siteId)!, ownerIds: [playerId] });

  set({
    players: newPlayers,
    sitesState: newSites,
    stealEvents: [...get().stealEvents, ...newStealEvents].slice(-20),
  });
}

function aiVisitSite(
  get: () => GameStore,
  set: (s: Partial<GameStore>) => void,
  aiId: PlayerId,
  siteId: SiteId,
) {
  const { players, sitesState } = get();
  const ai = players.get(aiId);
  const site = SITES_MAP.get(siteId);
  if (!ai || !site) return;

  const newPlayers = new Map(players);
  const newSites = new Map(sitesState);
  newPlayers.set(aiId, { ...ai, isVisiting: true });
  const ss = newSites.get(siteId)!;
  newSites.set(siteId, { ...ss, currentVisitorIds: [...ss.currentVisitorIds, aiId] });
  set({ players: newPlayers, sitesState: newSites });

  const isConsent = site.template === 'consent-button';
  const delay = isConsent
    ? RARITY_MS[site.rarity] * 0.3 + Math.random() * 1500
    : RARITY_MS[site.rarity] * 0.6 + Math.random() * 3000;
  const timerId = setTimeout(() => {
    aiTimers.delete(timerId);
    if (get().phase !== 'playing') {
      finishVisit(get, set, siteId, aiId, false);
      return;
    }
    finishVisit(get, set, siteId, aiId, true);
  }, delay);
  aiTimers.add(timerId);
}
