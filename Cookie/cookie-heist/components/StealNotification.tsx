'use client';

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { StealEvent, ExpireEvent, Player } from '@/lib/types';

interface Props {
  events: StealEvent[];
  expireEvents: ExpireEvent[];
  players: Map<string, Player>;
  myPlayerId: string;
  onDismiss: (id: string) => void;
  onDismissExpire: (id: string) => void;
}

export default function StealNotification({ events, expireEvents, players, myPlayerId, onDismiss, onDismissExpire }: Props) {
  useEffect(() => {
    events.forEach(e => {
      const t = setTimeout(() => onDismiss(e.id), 3000);
      return () => clearTimeout(t);
    });
  }, [events, onDismiss]);

  useEffect(() => {
    expireEvents.forEach(e => {
      const t = setTimeout(() => onDismissExpire(e.id), 3500);
      return () => clearTimeout(t);
    });
  }, [expireEvents, onDismissExpire]);

  return (
    <div className="fixed top-16 right-4 flex flex-col gap-2 z-50 pointer-events-none">
      <AnimatePresence>
        {events.map(e => {
          const isVictim = e.from === myPlayerId;
          const isThief = e.to === myPlayerId;
          const thief = players.get(e.to);
          const victim = players.get(e.from);

          return (
            <motion.div
              key={e.id}
              initial={{ opacity: 0, x: 60 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 60 }}
              className={[
                'px-3 py-2 rounded-lg text-sm font-semibold shadow-lg',
                isVictim ? 'bg-red-800 text-red-100 border border-red-500' :
                isThief ? 'bg-green-800 text-green-100 border border-green-500' :
                'bg-gray-700 text-gray-200',
              ].join(' ')}
            >
              {isThief && `🎉 ${e.siteName} を奪取! +${e.points}pt`}
              {isVictim && `💀 ${thief?.name ?? '?'} に ${e.siteName} を奪われた!`}
              {!isThief && !isVictim &&
                `🗡️ ${thief?.name} が ${victim?.name} から ${e.siteName} を奪取`}
            </motion.div>
          );
        })}
        {expireEvents.filter(e => e.playerId === myPlayerId).map(e => (
          <motion.div
            key={e.id}
            initial={{ opacity: 0, x: 60 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 60 }}
            className="px-3 py-2 rounded-lg text-sm font-semibold shadow-lg bg-amber-900 text-amber-100 border border-amber-500"
          >
            ⏰ {e.cookieName} が期限切れ! {e.points > 0 ? `-${e.points}pt` : `+${-e.points}pt`}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
