'use client';

import { useState } from 'react';
import type { OwnedCookie } from '@/lib/types';
import { getSiteById } from '@/lib/sites';

interface BadgeProps {
  name: string;
  desc: string;
  color: string;
}

function AttributeBadge({ name, desc, color }: BadgeProps) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={e => { e.stopPropagation(); setOpen(v => !v); }}
        className={`px-2 py-0.5 rounded text-[10px] font-bold cursor-pointer ${color}`}
      >
        {name}
      </button>
      {open && (
        <span className="absolute bottom-full left-0 mb-1 w-48 bg-gray-950 border border-gray-600 text-gray-200 text-[10px] rounded p-2 z-50 shadow-xl leading-relaxed">
          {desc}
        </span>
      )}
    </span>
  );
}

function sameSiteDesc(v: string) {
  if (v === 'Strict') return '同じサイト内のリクエストにだけ送信。外部サイトのリンクから来た場合は送信されない。';
  if (v === 'Lax') return '画像やiframeなどの裏で飛ぶクロスサイトリクエストでは送信しないが、リンクをクリックして移動してきたときは送信する。';
  return 'どんなリクエストでも常に送信。ただしSecure属性（HTTPS）が必須。';
}

interface Props {
  cookies: Map<string, OwnedCookie>;
  // 'collected' = 手元に残ったCookie（既定） / 'lost' = ゲーム中に奪われたCookie
  variant?: 'collected' | 'lost';
}

export default function CookieInspector({ cookies, variant = 'collected' }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (cookies.size === 0) return null;

  const isLost = variant === 'lost';
  const title = isLost ? '💀 奪われたCookie' : '🍪 収集したCookie';
  const nameColor = isLost ? 'text-rose-300' : 'text-green-300';
  const pointColor = isLost ? 'text-rose-400' : 'text-green-400';

  return (
    <div className="flex flex-col gap-2">
      <p className="font-semibold text-white text-sm">{title}</p>
      <div className="flex flex-col gap-1">
        {[...cookies.entries()].map(([siteId, owned]) => {
          const site = getSiteById(siteId);
          const isOpen = selectedId === siteId;
          const attrs = site?.cookie.attributes ?? {};

          return (
            <div key={siteId} className="rounded-lg overflow-hidden border border-gray-700">
              <button
                type="button"
                onClick={() => setSelectedId(isOpen ? null : siteId)}
                className="w-full flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 text-left text-sm transition-colors"
              >
                <span className="text-base">{site?.iconEmoji ?? '🌐'}</span>
                <span className={`font-mono ${nameColor} flex-1 truncate`}>{owned.cookieName}</span>
                <span className={`${pointColor} font-bold text-xs shrink-0`}>{owned.points}pt</span>
                <span className="text-gray-500 text-xs">{isOpen ? '▲' : '▼'}</span>
              </button>

              {isOpen && (
                <div className="bg-gray-900 px-3 py-3 flex flex-col gap-2 border-t border-gray-700">
                  {/* value preview */}
                  <p className="font-mono text-[11px] text-gray-400 bg-gray-800 px-2 py-1 rounded break-all">
                    <span className="text-gray-500">値: </span>
                    {owned.cookieValue.length > 30
                      ? owned.cookieValue.slice(0, 30) + '…'
                      : owned.cookieValue}
                  </p>

                  {/* attributes */}
                  <div className="flex flex-wrap gap-1.5 items-start">
                    {attrs.httpOnly && (
                      <AttributeBadge
                        name="HttpOnly"
                        desc="JavaScriptからのアクセスを防ぐ。XSS攻撃によるCookieの盗難を防止。"
                        color="bg-red-900 text-red-300"
                      />
                    )}
                    {attrs.secure && (
                      <AttributeBadge
                        name="Secure"
                        desc="HTTPS接続のときのみCookieが送信される。通信の盗聴を防ぐ。"
                        color="bg-blue-900 text-blue-300"
                      />
                    )}
                    {attrs.sameSite && (
                      <AttributeBadge
                        name={`SameSite=${attrs.sameSite}`}
                        desc={sameSiteDesc(attrs.sameSite)}
                        color="bg-purple-900 text-purple-300"
                      />
                    )}
                    {attrs.maxAge != null && (
                      <AttributeBadge
                        name={`Max-Age ${Math.round(attrs.maxAge / 60).toLocaleString()}分`}
                        desc={`${Math.round(attrs.maxAge / 60).toLocaleString()}分（${attrs.maxAge.toLocaleString()}秒）後に自動削除される。設定がなければブラウザを閉じると消えるセッションCookie。`}
                        color="bg-amber-900 text-amber-300"
                      />
                    )}
                    {!attrs.httpOnly && !attrs.secure && !attrs.sameSite && !attrs.maxAge && (
                      <span className="text-[10px] text-gray-500">属性なし（無防備なCookie）</span>
                    )}
                  </div>

                  {/* site description */}
                  {site?.description && (
                    <p className="text-[11px] text-gray-500 leading-relaxed">{site.description}</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
