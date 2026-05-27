'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const COLORS = ['#f59e0b', '#3b82f6', '#ef4444', '#22c55e', '#a855f7', '#ec4899', '#06b6d4', '#f97316'];

interface Particle {
  id: number; x: number; color: string;
  size: number; delay: number; duration: number; rotate: number;
  isCircle: boolean;
}

export default function Confetti({ active }: { active: boolean }) {
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    if (!active) return;
    setParticles(
      Array.from({ length: 80 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        color: COLORS[i % COLORS.length],
        size: Math.random() * 8 + 5,
        delay: Math.random() * 1.4,
        duration: Math.random() * 1.5 + 2.5,
        rotate: Math.random() * 720 - 360,
        isCircle: Math.random() > 0.5,
      }))
    );
  }, [active]);

  if (!active || particles.length === 0) return null;

  return (
    <div className="fixed inset-0 pointer-events-none z-[999] overflow-hidden">
      {particles.map(p => (
        <motion.div
          key={p.id}
          className={p.isCircle ? 'absolute rounded-full' : 'absolute rounded-sm'}
          style={{ left: `${p.x}%`, top: -20, width: p.size, height: p.size, backgroundColor: p.color }}
          initial={{ y: -20, rotate: 0, opacity: 1 }}
          animate={{ y: '110vh', rotate: p.rotate, opacity: [1, 1, 1, 0] }}
          transition={{ duration: p.duration, delay: p.delay, ease: [0.2, 0, 1, 0.8] }}
        />
      ))}
    </div>
  );
}
