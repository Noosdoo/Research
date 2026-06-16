'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { connectSocket, disconnectSocket } from '@/lib/socket';
import { useGameStore } from '@/store/gameStore';
import type { ServerPlayer } from '@/store/gameStore';
import type { SiteState } from '@/lib/types';

type Stage = 'name' | 'waiting' | 'starting';
type PlayerInfo = { id: string; name: string; color: string };

export default function CreateRoomPage() {
  const router = useRouter();
  const { initOnlineGame } = useGameStore();

  const [stage, setStage] = useState<Stage>('name');
  const [name, setName] = useState('');
  const [roomCode, setRoomCode] = useState('');
  const [players, setPlayers] = useState<PlayerInfo[]>([]);
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
      socket.off('lobby:game-starting');
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create   = useCallback(() => { if (name.trim()) connectSocket().emit('room:create', { playerName: name.trim() }); }, [name]);
  const leave    = useCallback(() => { connectSocket().emit('lobby:leave'); disconnectSocket(); router.push('/'); }, [router]);
  const startNow = useCallback(() => connectSocket().emit('lobby:start-now'), []);

  if (stage === 'name') {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
        <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-sm flex flex-col gap-6">
          <h1 className="text-2xl font-black text-white text-center">🏠 ルーム作成</h1>
          <div>
            <label className="block text-sm text-gray-400 mb-2">プレイヤー名</label>
            <input autoFocus value={name} onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && create()}
              placeholder="名前を入力…" maxLength={16}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
          <button type="button" onClick={create} disabled={!name.trim()}
            className="py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-bold rounded-xl transition-colors">
            ルームを作成
          </button>
          <button type="button" onClick={() => router.push('/')} className="text-gray-500 hover:text-gray-300 text-sm text-center">
            ← 戻る
          </button>
        </div>
      </div>
    );
  }

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

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-md flex flex-col gap-6">
        <div className="text-center">
          <h1 className="text-xl font-black text-white mb-3">🏠 ルーム待機中</h1>
          <div className="inline-flex flex-col items-center bg-gray-800 rounded-2xl px-8 py-4">
            <p className="text-gray-400 text-xs mb-1">ルームコード</p>
            <p className="text-5xl font-black text-white tracking-widest">{roomCode}</p>
            <p className="text-gray-500 text-xs mt-1">参加者はこのコードを入力</p>
          </div>
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
                    <span className="w-4 h-4 rounded-full flex-shrink-0" style={{ background: p.color }} />
                    <span className="text-white font-semibold">{p.name}</span>
                    {p.id === myIdRef.current && <span className="text-xs text-blue-400 ml-auto">あなた（ホスト）</span>}
                  </>
                ) : (
                  <span className="text-gray-600 text-sm">参加待ち…</span>
                )}
              </div>
            );
          })}
        </div>

        <div className="flex flex-col gap-2">
          {players.length >= 2 && (
            <button type="button" onClick={startNow}
              className="py-3 bg-green-600 hover:bg-green-500 text-white font-bold rounded-xl transition-colors">
              今すぐ開始 ({players.length}人)
            </button>
          )}
          <button type="button" onClick={leave} className="py-2 text-gray-500 hover:text-gray-300 text-sm text-center">
            ルームを解散
          </button>
        </div>
      </div>
    </div>
  );
}
