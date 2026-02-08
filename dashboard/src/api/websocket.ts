type Handler = (data: any) => void;

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Handler[]> = new Map();
  private reconnectTimer: number | null = null;

  connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.ws = new WebSocket(`${proto}//${location.host}/ws`);
    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        const type = msg.type || 'message';
        this.handlers.get(type)?.forEach((h) => h(msg));
        this.handlers.get('*')?.forEach((h) => h(msg));
      } catch { /* ignore parse errors */ }
    };
    this.ws.onclose = () => {
      this.reconnectTimer = window.setTimeout(() => this.connect(), 3000);
    };
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }

  on(type: string, handler: Handler) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type)!.push(handler);
  }

  off(type: string, handler: Handler) {
    const arr = this.handlers.get(type);
    if (arr) this.handlers.set(type, arr.filter((h) => h !== handler));
  }
}

export const wsClient = new WebSocketClient();
