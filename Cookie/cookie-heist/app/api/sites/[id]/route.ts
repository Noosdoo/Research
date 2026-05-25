import { NextResponse } from 'next/server';
import { getSiteById } from '@/lib/sites';
import type { CookieAttributes } from '@/lib/types';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const site = getSiteById(id);
  if (!site) {
    return new NextResponse('Not Found', { status: 404 });
  }

  const value = site.cookie.valueGenerator();
  const cookieStr = buildCookieString(site.cookie.name, value, site.cookie.attributes);

  return new NextResponse(JSON.stringify({ name: site.cookie.name, value }), {
    headers: {
      'Set-Cookie': cookieStr,
      'Content-Type': 'application/json',
    },
  });
}

function buildCookieString(name: string, value: string, attrs: CookieAttributes): string {
  const parts = [`${name}=${value}`, 'Path=/'];
  if (attrs.maxAge != null) parts.push(`Max-Age=${attrs.maxAge}`);
  if (attrs.sameSite) parts.push(`SameSite=${attrs.sameSite}`);
  if (attrs.secure) parts.push('Secure');
  if (attrs.httpOnly) parts.push('HttpOnly');
  return parts.join('; ');
}
