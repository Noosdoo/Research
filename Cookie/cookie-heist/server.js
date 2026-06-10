const { createServer } = require('http');
const { parse } = require('url');
const next = require('next');
const { Server } = require('socket.io');

const dev = process.env.NODE_ENV !== 'production';
const port = parseInt(process.env.PORT || '3000', 10);

const PLAYER_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b'];
const GAME_DURATION = 180;
const MAX_PLAYERS = 4;
const ROOM_CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

// ── In-memory state ────────────────────────────────────────────────
const lobbies = new Map();      // lobbyId  → Lobby
const games   = new Map();      // gameId   → Game
const roomCodes = new Map();    // code     → lobbyId
const socketToLobby   = new Map(); // socketId → lobbyId
const socketToGame    = new Map(); // socketId → gameId
const socketToPlayer  = new Map(); // socketId → playerId

// ── Helpers ────────────────────────────────────────────────────────
function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

function generateRoomCode() {
  let code;
  do {
    code = Array.from({ length: 4 }, () =>
      ROOM_CODE_CHARS[Math.floor(Math.random() * ROOM_CODE_CHARS.length)]
    ).join('');
  } while (roomCodes.has(code));
  return code;
}

function serializePlayer(p) {
  return {
    id: p.id,
    name: p.name,
    color: p.color,
    score: p.score,
    cookies: Object.fromEntries(p.cookies),
    stats: p.stats,
    isVisiting: p.isVisiting,
  };
}
function serializePlayers(players) {
  const out = {};
  for (const [id, p] of players) out[id] = serializePlayer(p);
  return out;
}
function serializeSites(sitesState) {
  const out = {};
  for (const [id, ss] of sitesState) out[id] = ss;
  return out;
}

// ── Lobby ──────────────────────────────────────────────────────────
function createLobby(type, code = null) {
  const id = uid('lobby');
  const lobby = { id, type, code, players: new Map(), colorIdx: 0, status: 'waiting', countdownEnd: null, ticking: false };
  lobbies.set(id, lobby);
  if (code) roomCodes.set(code, id);
  return lobby;
}

function findQuickmatchLobby() {
  for (const [, l] of lobbies)
    if (l.type === 'quickmatch' && l.status === 'waiting' && l.players.size < MAX_PLAYERS) return l;
  return null;
}

function lobbyPlayerList(lobby) {
  return [...lobby.players.values()].map(({ id, name, color }) => ({ id, name, color }));
}

function addPlayerToLobby(lobby, socketId, name) {
  const id = `player-${socketId.slice(0, 8)}`;
  const color = PLAYER_COLORS[lobby.colorIdx++ % PLAYER_COLORS.length];
  const info = { id, name: name || 'プレイヤー', color };
  lobby.players.set(socketId, info);
  socketToLobby.set(socketId, lobby.id);
  socketToPlayer.set(socketId, id);
  return info;
}

function startCountdown(lobbyId, seconds, io) {
  const lobby = lobbies.get(lobbyId);
  if (!lobby) return;
  lobby.countdownEnd = Date.now() + seconds * 1000;
  // 既存の tick ループがあれば countdownEnd の更新だけで延長される（多重起動防止）
  if (lobby.ticking) return;
  lobby.ticking = true;

  function tick() {
    const l = lobbies.get(lobbyId);
    if (!l || l.status !== 'waiting') { if (l) l.ticking = false; return; }
    const secondsLeft = Math.max(0, Math.ceil((l.countdownEnd - Date.now()) / 1000));
    io.to(lobbyId).emit('lobby:countdown', { secondsLeft });
    if (secondsLeft > 0) { setTimeout(tick, 1000); return; }

    l.ticking = false;
    if (l.players.size >= 2) {
      startGameFromLobby(lobbyId, io);
    } else if (l.players.size === 1) {
      io.to(lobbyId).emit('lobby:lonely', { canExtend: true });
    } else {
      cleanupLobby(lobbyId);
    }
  }
  setTimeout(tick, 1000);
}

function cleanupLobby(lobbyId) {
  const lobby = lobbies.get(lobbyId);
  if (!lobby) return;
  if (lobby.code) roomCodes.delete(lobby.code);
  lobbies.delete(lobbyId);
}

// ── Game ───────────────────────────────────────────────────────────
function startGameFromLobby(lobbyId, io) {
  const lobby = lobbies.get(lobbyId);
  if (!lobby || lobby.status !== 'waiting') return;
  lobby.status = 'starting';

  const gameId = uid('game');
  const players = new Map();
  let ci = 0;

  for (const [socketId, info] of lobby.players) {
    players.set(info.id, {
      socketId,
      id: info.id,
      name: info.name,
      color: PLAYER_COLORS[ci++ % PLAYER_COLORS.length],
      score: 0,
      cookies: new Map(),
      stats: { visitCount: 0, stealCount: 0, stolenCount: 0 },
      isVisiting: false,
    });
    socketToGame.set(socketId, gameId);
  }

  // サイト状態は訪問時に遅延生成する（getSiteState）。lib/sites.ts との手動同期は不要。
  const sitesState = new Map();

  const game = { id: gameId, lobbyId, players, sitesState, startTime: null, phase: 'starting', ticker: null };
  games.set(gameId, game);

  io.to(lobbyId).emit('lobby:game-starting', {
    gameId,
    players: serializePlayers(players),
    sitesState: serializeSites(sitesState),
  });

  setTimeout(() => {
    const g = games.get(gameId);
    if (!g) return;
    g.phase = 'playing';
    g.startTime = Date.now();
    io.to(lobbyId).emit('game:started', { gameId, startTime: g.startTime, duration: GAME_DURATION });

    g.ticker = setInterval(() => {
      const elapsed = Math.floor((Date.now() - g.startTime) / 1000);
      const timeLeft = Math.max(0, GAME_DURATION - elapsed);
      io.to(lobbyId).emit('game:tick', { timeLeft });

      if (timeLeft === 0) {
        clearInterval(g.ticker);
        g.phase = 'result';
        io.to(lobbyId).emit('game:ended', {
          players: serializePlayers(g.players),
          sitesState: serializeSites(g.sitesState),
        });
      }
    }, 1000);
  }, 3000);
}

// サイト状態の遅延生成。siteId はクライアント申告なので形式だけ検証する。
function getSiteState(game, siteId) {
  if (typeof siteId !== 'string' || siteId.length === 0 || siteId.length > 64) return null;
  let ss = game.sitesState.get(siteId);
  if (!ss) {
    ss = { siteId, ownerIds: [], currentVisitorIds: [] };
    game.sitesState.set(siteId, ss);
  }
  return ss;
}

function handleVisitComplete(socket, { siteId, siteName, earnedPoints }, io) {
  const gameId = socketToGame.get(socket.id);
  if (!gameId) return;
  const game = games.get(gameId);
  if (!game || game.phase !== 'playing') return;

  const playerId = socketToPlayer.get(socket.id);
  const player = game.players.get(playerId);
  const ss = getSiteState(game, siteId);
  if (!player || !ss) return;

  ss.currentVisitorIds = ss.currentVisitorIds.filter(id => id !== playerId);
  player.isVisiting = false;

  const pts = Math.max(-500, Math.min(500, Number(earnedPoints) || 0));
  const stealEvents = [];

  for (const ownerId of [...ss.ownerIds]) {
    if (ownerId === playerId) continue;
    const owner = game.players.get(ownerId);
    if (!owner || !owner.cookies.has(siteId)) continue;
    const stolen = owner.cookies.get(siteId);
    owner.cookies.delete(siteId);
    owner.score -= stolen.points;
    owner.stats.stolenCount++;
    player.stats.stealCount++;
    stealEvents.push({
      id: `${Date.now()}-${Math.random()}`,
      from: ownerId, to: playerId, siteId,
      siteName: siteName || siteId,
      points: stolen.points, at: Date.now(),
    });
  }

  player.cookies.set(siteId, { siteId, cookieName: siteName || siteId, points: pts });
  player.score += pts;
  player.stats.visitCount++;
  ss.ownerIds = [playerId];

  io.to(game.lobbyId).emit('game:state-update', {
    players: serializePlayers(game.players),
    sitesState: serializeSites(game.sitesState),
    stealEvents,
  });
}

function handleVisitChange(socket, { siteId }, starting, io) {
  const gameId = socketToGame.get(socket.id);
  if (!gameId) return;
  const game = games.get(gameId);
  if (!game || game.phase !== 'playing') return;

  const playerId = socketToPlayer.get(socket.id);
  const player = game.players.get(playerId);
  const ss = getSiteState(game, siteId);
  if (!player || !ss) return;

  player.isVisiting = starting;
  if (starting) {
    if (!ss.currentVisitorIds.includes(playerId)) ss.currentVisitorIds.push(playerId);
  } else {
    ss.currentVisitorIds = ss.currentVisitorIds.filter(id => id !== playerId);
  }

  io.to(game.lobbyId).emit('game:state-update', {
    players: serializePlayers(game.players),
    sitesState: serializeSites(game.sitesState),
    stealEvents: [],
  });
}

function handleSocketDisconnect(socketId, io) {
  const lobbyId = socketToLobby.get(socketId);
  if (lobbyId) {
    const lobby = lobbies.get(lobbyId);
    if (lobby) {
      const info = lobby.players.get(socketId);
      lobby.players.delete(socketId);
      socketToLobby.delete(socketId);
      if (info) io.to(lobbyId).emit('lobby:player-left', { playerId: info.id });
      if (lobby.players.size === 0 && lobby.status === 'waiting') cleanupLobby(lobbyId);
    }
  }

  const gameId = socketToGame.get(socketId);
  if (gameId) {
    const game = games.get(gameId);
    if (game && game.phase === 'playing') {
      const playerId = socketToPlayer.get(socketId);
      if (playerId) {
        const player = game.players.get(playerId);
        if (player) {
          player.isVisiting = false;
          for (const [, ss] of game.sitesState)
            ss.currentVisitorIds = ss.currentVisitorIds.filter(id => id !== playerId);
          io.to(game.lobbyId).emit('game:state-update', {
            players: serializePlayers(game.players),
            sitesState: serializeSites(game.sitesState),
            stealEvents: [],
          });
        }
      }
    }
    socketToGame.delete(socketId);
    socketToPlayer.delete(socketId);
  }
}

// ── Bootstrap ──────────────────────────────────────────────────────
const app = next({ dev });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const httpServer = createServer((req, res) => handle(req, res, parse(req.url, true)));

  const io = new Server(httpServer, { cors: { origin: '*', methods: ['GET', 'POST'] } });

  io.on('connection', (socket) => {
    // Quick match
    socket.on('quickmatch:join', ({ playerName }) => {
      let lobby = findQuickmatchLobby() ?? createLobby('quickmatch');
      const info = addPlayerToLobby(lobby, socket.id, playerName);
      socket.join(lobby.id);

      socket.emit('lobby:joined', {
        lobbyId: lobby.id, playerId: info.id,
        players: lobbyPlayerList(lobby), countdownEnd: lobby.countdownEnd,
      });
      socket.to(lobby.id).emit('lobby:player-joined', info);

      if (lobby.players.size >= MAX_PLAYERS) {
        startGameFromLobby(lobby.id, io);
      } else if (lobby.players.size === 1) {
        startCountdown(lobby.id, 60, io);
      } else if (!lobby.ticking) {
        // カウントダウンが既に終了している（lonely 状態）ロビーに合流した場合は短い再カウントで自動開始
        startCountdown(lobby.id, 10, io);
      }
    });

    // Create room
    socket.on('room:create', ({ playerName }) => {
      const code = generateRoomCode();
      const lobby = createLobby('room', code);
      const info = addPlayerToLobby(lobby, socket.id, playerName);
      socket.join(lobby.id);

      socket.emit('lobby:joined', {
        lobbyId: lobby.id, playerId: info.id, code,
        players: lobbyPlayerList(lobby), countdownEnd: null,
      });
    });

    // Join room by code
    socket.on('room:join', ({ code, playerName }) => {
      const lobbyId = roomCodes.get((code || '').toUpperCase());
      const lobby = lobbyId ? lobbies.get(lobbyId) : null;

      if (!lobby || lobby.status !== 'waiting') {
        socket.emit('room:error', { message: lobby ? 'このルームはすでに開始されています' : 'コードが見つかりません' });
        return;
      }
      if (lobby.players.size >= MAX_PLAYERS) {
        socket.emit('room:error', { message: 'ルームが満員です（4/4）' });
        return;
      }

      const info = addPlayerToLobby(lobby, socket.id, playerName);
      socket.join(lobby.id);

      socket.emit('lobby:joined', {
        lobbyId: lobby.id, playerId: info.id, code: lobby.code,
        players: lobbyPlayerList(lobby), countdownEnd: lobby.countdownEnd,
      });
      socket.to(lobby.id).emit('lobby:player-joined', info);

      if (lobby.players.size >= MAX_PLAYERS) startGameFromLobby(lobby.id, io);
    });

    socket.on('lobby:leave', () => handleSocketDisconnect(socket.id, io));

    socket.on('lobby:start-now', () => {
      const lobbyId = socketToLobby.get(socket.id);
      const lobby = lobbyId ? lobbies.get(lobbyId) : null;
      if (lobby && lobby.players.size >= 2) startGameFromLobby(lobby.id, io);
    });

    socket.on('lobby:extend', () => {
      const lobbyId = socketToLobby.get(socket.id);
      if (!lobbyId) return;
      startCountdown(lobbyId, 30, io);
      io.to(lobbyId).emit('lobby:extended', { seconds: 30 });
    });

    socket.on('lobby:solo', () => {
      const lobbyId = socketToLobby.get(socket.id);
      if (lobbyId) handleSocketDisconnect(socket.id, io);
      socket.emit('lobby:solo-redirect');
    });

    // Game events
    socket.on('game:visit-start',    (data) => handleVisitChange(socket, data, true, io));
    socket.on('game:visit-cancel',   (data) => handleVisitChange(socket, data, false, io));
    socket.on('game:visit-complete', (data) => handleVisitComplete(socket, data, io));

    socket.on('disconnect', () => handleSocketDisconnect(socket.id, io));
  });

  httpServer.listen(port, () => {
    console.log(`> Ready on http://localhost:${port}`);
  });
});
