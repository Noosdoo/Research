'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { connectSocket, disconnectSocket } from '@/lib/socket';
import { useGameStore } from '@/store/gameStore';
import type { ServerPlayer } from '@/store/gameStore';
import type { SiteState } from '@/lib/types';

type Stage = 'form' | 'waiting' | 'starting';
type PlayerInfo = { id: string; name: string; color: string };

const DOT_COLORS = ['bg-blue-500', 'bg-red-500', 'bg-green-500', 'bg-yellow-500'];

export default function JoinRoomPage() {
  const router = useRouter();
  const { initOnlineGame } = useGameStore();

  const [stage, setStage] = useState<Stage>('form');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [roomCode, setRoomCode] = useState('');
  const [players, setPlayers] = useState<PlayerInfo[]>([]);
  const [error, setError] = useState('');
  const [startingIn, setStartingIn] = useState<number | null>(null);
  const myIdRef = useRef('');

  useEffect(() => {
    const socket = connectSocket();

    socket.on('lobby:joined', (data: { playerId: string; code: string; players: PlayerInfo[] }) => {
      myIdRef.current = data.playerId;
      setRoomCode(data.code);
      setPlayers(data.players);
      setStage('waiting');
    });

    socket.on('lobby:player-joined', (info: PlayerInfo) => {
      setPlayers(prev => [...prev.filter(p => p.id !== info.id), info]);
    });

    socket.on('lobby:player-left', ({ playerId }: { playerId: string }) => {
      setPlayers(prev => prev.filter(p => p.id !== playerId));
    });

    socket.on('room:error', ({ message }: { message: string }) => setError(message));

    socket.on('lobby:game-starting', (data: {
      gameId: string;
      players: Record<string, ServerPlayer>;
      sitesState: Record<string, SiteState>;
    }) => {
      setStage('starting');
      let c = 3;
      setStartingIn(c);
      const iv = setInterval(() => {
        c--;
        setStartingIn(c);
        if (c <= 0) {
          clearInterval(iv);
          initOnlineGame({ gameId: data.gameId, myPlayerId: myIdRef.current, players: data.players, sitesState: data.sitesState });
          router.push(`/multiplayer/${data.gameId}`);
        }
      }, 1000);
    });

    return () => {
      socket.off('lobby:joined');
      socket.off('lobby:player-joined');
      socket.off('lobby:player-left');
      socket.off('room:error');
      socket.off('lobby:game-starting');
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const join  = useCallback(() => {
    if (!name.trim() || code.length < 4) return;
    setError('');
    connectSocket().emit('room:join', { playerName: name.trim(), code: code.trim().toUpperCase() });
  }, [name, code]);

  const leave = useCallback(() => { connectSocket().emit('lobby:leave'); disconnectSocket(); router.push('/'); }, [router]);

  if (stage === 'starting') {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 text-lg mb-2">ゲーム開始まで…</p>
          <p className="text-8xl font-black text-white">{startingIn}</p>
        </div>
      </div>
    );
  }

  if (stage === 'waiting') {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
        <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md flex flex-col gap-6">
          <div className="text-center">
            <h1 className="text-xl font-black text-white mb-1">🚪 ルーム {roomCode}</h1>
            <p className="text-gray-500 text-sm">ホストがゲームを開始するまで待ってください</p>
          </div>

          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3].map(i => {
              const p = players[i];
              return (
                <div key={i} className={[
                  'flex items-center gap-3 px-4 py-3 rounded-lg',
                  p ? 'bg-gray-800' : 'bg-gray-800/40 border border-dashed border-gray-700',
                ].join(' ')}>
                  {p ? (
                    <>
                      <span className={`w-4 h-4 rounded-full flex-shrink-0 ${DOT_COLORS[i] ?? 'bg-gray-500'}`} />
                      <span className="text-white font-semibold">{p.name}</span>
                      {p.id === myIdRef.current && <span className="text-xs text-blue-400 ml-auto">あなた</span>}
                    </>
                  ) : (
                    <span className="text-gray-600 text-sm">参加待ち…</span>
                  )}
                </div>
              );
            })}
          </div>

          <button type="button" onClick={leave} className="py-2 text-gray-500 hover:text-gray-300 text-sm text-center">
            退出する
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-sm flex flex-col gap-5">
        <h1 className="text-2xl font-black text-white text-center">🚪 ルームに参加</h1>

        <div>
          <label className="block text-sm text-gray-400 mb-2">プレイヤー名</label>
          <input autoFocus value={name} onChange={e => setName(e.target.value)}
            placeholder="名前を入力…" maxLength={16}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-2">ルームコード（4文字）</label>
          <input
            value={code}
            onChange={e => { setCode(e.target.value.toUpperCase().slice(0, 4)); setError(''); }}
            onKeyDown={e => e.key === 'Enter' && join()}
            placeholder="ABCD"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-center text-2xl font-black tracking-widest uppercase"
          />
        </div>

        {error && (
          <p className="text-red-400 text-sm bg-red-900/30 border border-red-800 rounded-lg px-3 py-2">
            ❌ {error}
          </p>
        )}

        <button type="button" onClick={join} disabled={!name.trim() || code.length < 4}
          className="py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-bold rounded-xl transition-colors">
          参加する
        </button>
        <button type="button" onClick={() => router.push('/')} className="text-gray-500 hover:text-gray-300 text-sm text-center">
          ← 戻る
        </button>
      </div>
    </div>
  );
}
