export type Frame =
  | { type: "meta"; conversation_id: string; seq: number }
  | { type: "token"; text: string }
  | { type: "tool_start"; name: string; report_code?: string }
  | { type: "tool_end"; name: string; ok: boolean }
  | { type: "grounding"; used: boolean; sources?: { title?: string; uri?: string }[] }
  | { type: "raid_tracked"; report_code: string; label: string }
  | { type: "done"; message_id: string }
  | { type: "error"; code: string; message: string };

export interface ChatTurn {
  conversation_id: string | null;
  model: string;
  content: string;
}

/**
 * A single long-lived chat WebSocket with basic auto-reconnect. Frames are
 * delivered to onFrame; connection changes to onStatus.
 */
export class ChatSocket {
  private ws: WebSocket | null = null;
  private readonly url: string;
  private shouldReconnect = true;

  constructor(
    private readonly onFrame: (f: Frame) => void,
    private readonly onStatus: (connected: boolean) => void,
  ) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.url = `${proto}://${location.host}/ws/chat`;
  }

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => this.onStatus(true);
    this.ws.onclose = () => {
      this.onStatus(false);
      if (this.shouldReconnect) setTimeout(() => this.connect(), 1500);
    };
    this.ws.onmessage = (e) => this.onFrame(JSON.parse(e.data) as Frame);
  }

  send(turn: ChatTurn): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(turn));
      return true;
    }
    return false;
  }

  close(): void {
    this.shouldReconnect = false;
    this.ws?.close();
  }
}
