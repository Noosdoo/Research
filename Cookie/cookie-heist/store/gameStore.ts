'use client';

import { create } from 'zustand';
import { SITES } from '@/lib/sites';
import type {
  Player,
  PlayerId,
  SiteId,
  SiteState,
  OwnedCookie,
  StealEvent,
  Rarity,
} from '@/lib/types';

const GAME_DURATION = 3 * 60; // seconds

const PLAYER_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b'];

const RARITY_MS: Record<Rarity, number> = {
  common: 1000,
  uncommon: 2000,
  rare: 3000,
  legendary: 5000,
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

  // actions
  initGame: (aiCount: number) => void;
  tickTimer: () => void;
  completeVisit: (siteId: SiteId, pointOverride?: number) => void;
  processAITick: (aiId: PlayerId) => void;
  endGame: () => void;
  clearStealEvent: (id: string) => void;

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
}

export const useGameStore = create<GameStore>((set, get) => ({
  gameId: '',
  phase: 'lobby',
  startTime: null,
  timeLeft: GAME_DURATION,
  aiCount: 1,
  mode: 'local',
  onlineGameId: null,
  players: new Map(),
  myPlayerId: 'player-human',
  sitesState: initSiteStates(),
  stealEvents: [],

  initGame(aiCount: number) {
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
      timeLeft: GAME_DURATION,
      aiCount,
      players,
      myPlayerId: 'player-human',
      sitesState: initSiteStates(),
      stealEvents: [],
    });
  },

  tickTimer() {
    const { startTime, phase } = get();
    if (phase !== 'playing' || !startTime) return;
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const timeLeft = Math.max(0, GAME_DURATION - elapsed);
    if (timeLeft === 0) {
      get().endGame();
    } else {
      set({ timeLeft });
    }
  },

  completeVisit(siteId: SiteId, pointOverride?: number) {
    const { phase, myPlayerId } = get();
    if (phase !== 'playing') return;
    finishVisit(get, set, siteId, myPlayerId, true, pointOverride);
  },

  processAITick(aiId: PlayerId) {
    const { players, sitesState, phase } = get();
    if (phase !== 'playing') return;
    const ai = players.get(aiId);
    if (!ai || ai.isVisiting) return;

    const candidates = SITES
      .filter(s => !s.isHoneypot)
      .map(s => {
        let score = s.cookie.points;
        score -= RARITY_MS[s.rarity] / 100;
        if (ai.cookies.has(s.id)) score *= 0.3;
        const othersOwn = sitesState.get(s.id)!.ownerIds.filter(id => id !== aiId).length;
        score += othersOwn * 20;
        return { id: s.id, score, rarity: s.rarity };
      })
      .sort((a, b) => b.score - a.score);

    const pick = Math.random() < 0.25
      ? candidates[Math.floor(Math.random() * Math.min(5, candidates.length))]
      : candidates[0];

    if (!pick) return;
    aiVisitSite(get, set, aiId, pick.id);
  },

  endGame() {
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
      stealEvents: [], startTime: Date.now(),
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
}));

// ── helpers ────────────────────────────────────────────────────────

function finishVisit(
  get: () => GameStore,
  set: (s: Partial<GameStore>) => void,
  siteId: SiteId,
  playerId: PlayerId,
  success: boolean,
  pointOverride?: number,
) {
  const { players, sitesState } = get();
  const site = SITES.find(s => s.id === siteId)!;

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
  const cookieValue = site.cookie.valueGenerator();
  const owned: OwnedCookie = {
    siteId,
    cookieName: site.cookie.name,
    cookieValue,
    acquiredAt: new Date(),
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
    stealEvents: [...get().stealEvents, ...newStealEvents],
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
  const site = SITES.find(s => s.id === siteId);
  if (!ai || !site) return;

  const newPlayers = new Map(players);
  const newSites = new Map(sitesState);
  newPlayers.set(aiId, { ...ai, isVisiting: true });
  const ss = newSites.get(siteId)!;
  newSites.set(siteId, { ...ss, currentVisitorIds: [...ss.currentVisitorIds, aiId] });
  set({ players: newPlayers, sitesState: newSites });

  const delay = RARITY_MS[site.rarity] + Math.random() * 500;
  setTimeout(() => {
    if (get().phase !== 'playing') {
      finishVisit(get, set, siteId, aiId, false);
      return;
    }
    finishVisit(get, set, siteId, aiId, true);
  }, delay);
}
