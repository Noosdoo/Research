'use client';

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { StealEvent, Player } from '@/lib/types';

interface Props {
  events: StealEvent[];
  players: Map<string, Player>;
  myPlayerId: string;
  onDismiss: (id: string) => void;
}

export default function StealNotification({ events, players, myPlayerId, onDismiss }: Props) {
  useEffect(() => {
    events.forEach(e => {
      const t = setTimeout(() => onDismiss(e.id), 3000);
      return () => clearTimeout(t);
    });
  }, [events, onDismiss]);

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
      </AnimatePresence>
    </div>
  );
}
