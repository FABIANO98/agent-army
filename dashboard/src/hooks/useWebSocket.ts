import { useEffect, useState } from 'react';
import { wsClient } from '../api/websocket';

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  useEffect(() => {
    wsClient.connect();
    const handler = (msg: any) => {
      setMessages((prev) => [msg, ...prev].slice(0, 100));
      setConnected(true);
    };
    wsClient.on('*', handler);
    return () => {
      wsClient.off('*', handler);
    };
  }, []);

  return { connected, messages };
}
