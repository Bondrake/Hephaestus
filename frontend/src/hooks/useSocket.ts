import { useWebSocket } from '@/context/WebSocketContext';

export function useSocket() {
  const { isConnected, lastMessage } = useWebSocket();
  return { isConnected, lastMessage };
}