import { NextResponse } from 'next/server';
import { SITES } from '@/lib/sites';

export async function POST() {
  const headers = new Headers();
  headers.set('Content-Type', 'application/json');

  const cookieNames = SITES.map(s => s.cookie.name);

  // Max-Age=0 で全Cookie を削除（Path とドメインのバリエーションを網羅）
  const setCookies: string[] = [];
  for (const name of cookieNames) {
    setCookies.push(`${name}=; Max-Age=0; Path=/`);
  }

  // Next.js は Headers.append で複数の Set-Cookie を設定できる
  const res = NextResponse.json({ cleared: cookieNames.length });
  for (const c of setCookies) {
    res.headers.append('Set-Cookie', c);
  }
  return res;
}
