'use client';

interface Props {
  timeLeft: number;
}

export default function Timer({ timeLeft }: Props) {
  const m = Math.floor(timeLeft / 60).toString().padStart(2, '0');
  const s = (timeLeft % 60).toString().padStart(2, '0');
  const urgent = timeLeft <= 30;

  return (
    <span
      className={[
        'font-mono font-bold text-xl tabular-nums',
        urgent ? 'text-red-400 animate-pulse' : 'text-white',
      ].join(' ')}
    >
      {m}:{s}
    </span>
  );
}
