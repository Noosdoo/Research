'use client';

import { CATEGORY_LABELS } from '@/lib/sites';
import type { SiteCategory } from '@/lib/types';

const CATEGORIES: Array<SiteCategory | 'all'> = [
  'all', 'finance', 'ecommerce', 'social', 'media',
  'gaming', 'advertising', 'government', 'niche', 'special',
];

interface Props {
  selected: SiteCategory | 'all';
  onChange: (c: SiteCategory | 'all') => void;
}

export default function CategoryFilter({ selected, onChange }: Props) {
  return (
    <div className="flex gap-1 flex-wrap">
      {CATEGORIES.map(cat => (
        <button
          key={cat}
          onClick={() => onChange(cat)}
          className={[
            'px-2 py-0.5 rounded text-xs font-medium transition-colors',
            selected === cat
              ? 'bg-blue-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600',
          ].join(' ')}
        >
          {cat === 'all' ? '全て' : CATEGORY_LABELS[cat]}
        </button>
      ))}
    </div>
  );
}
