import { NextResponse } from 'next/server';
import { networkInterfaces } from 'os';

export async function GET() {
  // 本番環境ではフロントが window.location.origin を使う
  if (process.env.NODE_ENV === 'production') {
    return NextResponse.json({ ip: '', port: '', url: '' });
  }

  const nets = networkInterfaces();
  let localIp = '';

  outer: for (const ifaces of Object.values(nets)) {
    if (!ifaces) continue;
    for (const iface of ifaces) {
      if (iface.family === 'IPv4' && !iface.internal) {
        localIp = iface.address;
        break outer;
      }
    }
  }

  const port = process.env.PORT ?? '3000';
  return NextResponse.json({ ip: localIp, port, url: localIp ? `http://${localIp}:${port}` : '' });
}
