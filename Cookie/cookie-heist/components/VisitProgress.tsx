'use client';

import type { CurrentVisit } from '@/lib/types';
import { SITES } from '@/lib/sites';

interface Props {
  visit: CurrentVisit;
  onCancel: () => void;
}

export default function VisitProgress({ visit, onCancel }: Props) {
  const site = SITES.find(s => s.id === visit.siteId);
  const remaining = site
    ? Math.max(0, site.visitDuration - (Date.now() - visit.startTime)) / 1000
    : 0;

  return (
    <div className="bg-gray-800 border border-gray-600 rounded-lg p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-white font-semibold">
          訪問中: {site?.iconEmoji} {site?.name}
        </span>
        <span className="text-gray-400 text-xs">残り {remaining.toFixed(1)}秒</span>
      </div>

      <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-green-500 transition-all duration-100 rounded-full"
          style={{ width: `${visit.progress}%` }}
        />
      </div>

      <button
        onClick={onCancel}
        className="text-xs text-red-400 hover:text-red-300 self-end transition-colors"
      >
        中断
      </button>
    </div>
  );
}
