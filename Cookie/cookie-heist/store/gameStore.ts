'use client';

import { create } from 'zustand';
import { SITES } from '@/lib/sites';
import type {
  Player,
  PlayerId,
  SiteId,
  SiteState,
  CurrentVisit,
  OwnedCookie,
  StealEvent,
} from '@/lib/types';

const GAME_DURATION = 5 * 60; // seconds

const PLAYER_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b'];

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

interface GameStore {
  // meta
  gameId: string;
  phase: 'lobby' | 'playing' | 'result';
  startTime: number | null;
  timeLeft: number;

  // players
  players: Map<PlayerId, Player>;
  myPlayerId: PlayerId;

  // sites
  sitesState: Map<SiteId, SiteState>;

  // current human visit
  currentVisit: CurrentVisit | null;

  // notifications
  stealEvents: StealEvent[];

  // actions
  initGame: (aiCount: number) => void;
  startTimer: () => void;
  tickTimer: () => void;
  visitSite: (siteId: SiteId) => Promise<void>;
  cancelVisit: () => void;
  processAITick: (aiId: PlayerId) => void;
  endGame: () => void;
  clearStealEvent: (id: string) => void;
}

export const useGameStore = create<GameStore>((set, get) => ({
  gameId: '',
  phase: 'lobby',
  startTime: null,
  timeLeft: GAME_DURATION,
  players: new Map(),
  myPlayerId: 'player-human',
  sitesState: initSiteStates(),
  currentVisit: null,
  stealEvents: [],

  initGame(aiCount: number) {
    const players = new Map<PlayerId, Player>();
    const human = makePlayer('player-human', 'あなた', false, 0);
    players.set('player-human', human);
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
      players,
      myPlayerId: 'player-human',
      sitesState: initSiteStates(),
      currentVisit: null,
      stealEvents: [],
    });
  },

  startTimer() {
    // called once after initGame; actual ticking is done by the component via tickTimer
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

  async visitSite(siteId: SiteId) {
    const { players, myPlayerId, sitesState, phase } = get();
    if (phase !== 'playing') return;
    const me = players.get(myPlayerId);
    if (!me || me.isVisiting) return;

    const site = SITES.find(s => s.id === siteId);
    if (!site) return;

    // mark as visiting
    const newPlayers = new Map(players);
    newPlayers.set(myPlayerId, { ...me, isVisiting: true });
    const newSites = new Map(sitesState);
    const ss = newSites.get(siteId)!;
    newSites.set(siteId, { ...ss, currentVisitorIds: [...ss.currentVisitorIds, myPlayerId] });

    set({
      players: newPlayers,
      sitesState: newSites,
      currentVisit: {
        siteId,
        startTime: Date.now(),
        progress: 0,
        cancelRequested: false,
      },
    });

    // wait for visit duration
    await new Promise<void>(resolve => {
      const interval = setInterval(() => {
        const cv = get().currentVisit;
        if (!cv || cv.cancelRequested) {
          clearInterval(interval);
          resolve();
          return;
        }
        const elapsed = Date.now() - cv.startTime;
        const progress = Math.min(100, (elapsed / site.visitDuration) * 100);
        set({ currentVisit: { ...cv, progress } });
        if (progress >= 100) {
          clearInterval(interval);
          resolve();
        }
      }, 50);
    });

    const state = get();
    const cv = state.currentVisit;
    if (!cv || cv.cancelRequested || state.phase !== 'playing') {
      // cancelled or game ended — remove from currentVisitors
      finishVisit(get, set, siteId, myPlayerId, false);
      return;
    }

    // complete visit
    finishVisit(get, set, siteId, myPlayerId, true);
  },

  cancelVisit() {
    const { currentVisit } = get();
    if (!currentVisit) return;
    set({ currentVisit: { ...currentVisit, cancelRequested: true } });
  },

  processAITick(aiId: PlayerId) {
    const { players, sitesState, phase } = get();
    if (phase !== 'playing') return;
    const ai = players.get(aiId);
    if (!ai || ai.isVisiting) return;

    // simple balanced AI: pick highest-point unowned site
    const candidates = SITES
      .filter(s => !s.isHoneypot)
      .map(s => {
        let score = s.cookie.points;
        score -= s.visitDuration / 100;
        if (ai.cookies.has(s.id)) score *= 0.3; // low priority if already owned
        const othersOwn = sitesState.get(s.id)!.ownerIds.filter(id => id !== aiId).length;
        score += othersOwn * 20; // bonus for stealing
        return { id: s.id, score };
      })
      .sort((a, b) => b.score - a.score);

    const pick = Math.random() < 0.25
      ? candidates[Math.floor(Math.random() * Math.min(5, candidates.length))]
      : candidates[0];

    if (!pick) return;
    aiVisitSite(get, set, aiId, pick.id);
  },

  endGame() {
    const { currentVisit, players, myPlayerId } = get();
    if (currentVisit) {
      const cv = currentVisit;
      const newPlayers = new Map(players);
      const me = newPlayers.get(myPlayerId);
      if (me) newPlayers.set(myPlayerId, { ...me, isVisiting: false });
      set({ currentVisit: null, players: newPlayers });
    }
    set({ phase: 'result' });
  },

  clearStealEvent(id: string) {
    set(s => ({ stealEvents: s.stealEvents.filter(e => e.id !== id) }));
  },
}));

// ── helpers ────────────────────────────────────────────────────────

function finishVisit(
  get: () => GameStore,
  set: (s: Partial<GameStore>) => void,
  siteId: SiteId,
  playerId: PlayerId,
  success: boolean,
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
  if (!player) { set({ sitesState: newSites, currentVisit: null }); return; }

  if (!success) {
    newPlayers.set(playerId, { ...player, isVisiting: false });
    set({ players: newPlayers, sitesState: newSites, currentVisit: null });
    return;
  }

  // steal from previous owners
  const newStealEvents: StealEvent[] = [];
  const updatedSS = newSites.get(siteId)!;
  for (const ownerId of [...updatedSS.ownerIds]) {
    if (ownerId === playerId) continue;
    const owner = newPlayers.get(ownerId);
    if (!owner || !owner.cookies.has(siteId)) continue;

    const stolenCookie = owner.cookies.get(siteId)!;
    const newCookies = new Map(owner.cookies);
    newCookies.delete(siteId);
    const newScore = owner.score - stolenCookie.points;
    newPlayers.set(ownerId, {
      ...owner,
      cookies: newCookies,
      score: newScore,
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

  // fetch real cookie (fire-and-forget, only for human player)
  if (playerId === 'player-human') {
    fetch(`/api/sites/${siteId}`).catch(() => {});
  }

  // add cookie to player
  const cookieValue = site.cookie.valueGenerator();
  const owned: OwnedCookie = {
    siteId,
    cookieName: site.cookie.name,
    cookieValue,
    acquiredAt: new Date(),
    points: site.cookie.points,
  };

  const freshPlayer = newPlayers.get(playerId)!;
  const newCookies = new Map(freshPlayer.cookies);
  newCookies.set(siteId, owned);
  const newScore = freshPlayer.score + site.cookie.points;

  newPlayers.set(playerId, {
    ...freshPlayer,
    isVisiting: false,
    cookies: newCookies,
    score: newScore,
    stats: { ...freshPlayer.stats, visitCount: freshPlayer.stats.visitCount + 1 },
  });

  // update owner list
  const finalSS = newSites.get(siteId)!;
  const ownerIds = finalSS.ownerIds.filter(id => id === playerId);
  if (!ownerIds.includes(playerId)) ownerIds.push(playerId);
  // keep only current owner (last visitor takes it)
  newSites.set(siteId, { ...finalSS, ownerIds: [playerId] });

  const isHuman = playerId === 'player-human';
  set({
    players: newPlayers,
    sitesState: newSites,
    ...(isHuman ? { currentVisit: null } : {}),
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

  setTimeout(() => {
    if (get().phase !== 'playing') {
      finishVisit(get, set, siteId, aiId, false);
      return;
    }
    finishVisit(get, set, siteId, aiId, true);
  }, site.visitDuration + Math.random() * 500);
}
