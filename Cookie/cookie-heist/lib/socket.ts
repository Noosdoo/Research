import { io, type Socket } from 'socket.io-client';

let _socket: Socket | null = null;

export function getSocket(): Socket {
  if (!_socket) {
    const url = process.env.NEXT_PUBLIC_SOCKET_URL ?? '';
    _socket = io(url, { autoConnect: false });
  }
  return _socket;
}

export function connectSocket(): Socket {
  const s = getSocket();
  if (!s.connected) s.connect();
  return s;
}

export function disconnectSocket() {
  if (_socket) {
    _socket.disconnect();
    _socket = null;
  }
}
