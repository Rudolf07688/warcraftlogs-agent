import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { registerFaro, resetFaroForTests } from "../telemetry/context";
import { ChatSocket } from "./wsClient";

// Feature 057 (sc-415): with Faro on, a sent turn carries the traceparent of its "chat send"
// span and the Faro session id; the span ends with the turn. Off, the frame is unchanged.

class FakeWebSocket {
  static OPEN = 1;
  static last: FakeWebSocket;
  readyState = FakeWebSocket.OPEN;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor() {
    FakeWebSocket.last = this;
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {}
}

const TURN = { conversation_id: null, model: "m", content: "hello" };

function fakeFaro() {
  const span = {
    spanContext: () => ({ traceId: "0af7651916cd43dd8448eb211c80319c", spanId: "b7ad6b7169203331", traceFlags: 1 }),
    setStatus: vi.fn(),
    end: vi.fn(),
  };
  const faro = {
    api: {
      getOTEL: () => ({ trace: { getTracer: () => ({ startSpan: vi.fn(() => span) }) } }),
      getSession: () => ({ id: "a1B2c3D4e5" }),
      setUser: vi.fn(),
      resetUser: vi.fn(),
    },
  };
  return { span, faro: faro as never };
}

function connected() {
  const socket = new ChatSocket(() => {}, () => {});
  socket.connect();
  return { socket, ws: FakeWebSocket.last };
}

const frame = (ws: FakeWebSocket, f: object) => ws.onmessage!({ data: JSON.stringify(f) });

beforeEach(() => vi.stubGlobal("WebSocket", FakeWebSocket));
afterEach(() => {
  resetFaroForTests();
  vi.unstubAllGlobals();
});

describe("ChatSocket.send", () => {
  it("sends the turn unchanged when Faro is off", () => {
    const { socket, ws } = connected();
    expect(socket.send(TURN)).toBe(true);
    expect(JSON.parse(ws.sent[0])).toEqual(TURN);
  });

  it("puts the span's traceparent and the Faro session id into the message", () => {
    const { faro } = fakeFaro();
    registerFaro(faro);
    const { socket, ws } = connected();
    socket.send(TURN);
    expect(JSON.parse(ws.sent[0])).toEqual({
      ...TURN,
      traceparent: "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
      faro_session_id: "a1B2c3D4e5",
    });
  });

  it("ends the span when the turn is done, not before", () => {
    const { faro, span } = fakeFaro();
    registerFaro(faro);
    const { socket, ws } = connected();
    socket.send(TURN);
    frame(ws, { type: "token", text: "hi" });
    expect(span.end).not.toHaveBeenCalled();
    frame(ws, { type: "done", message_id: "m1" });
    expect(span.end).toHaveBeenCalledTimes(1);
    expect(span.setStatus).not.toHaveBeenCalled();
  });

  it("ends the span as an error on an error frame", () => {
    const { faro, span } = fakeFaro();
    registerFaro(faro);
    const { socket, ws } = connected();
    socket.send(TURN);
    frame(ws, { type: "error", code: "x", message: "boom" });
    expect(span.setStatus).toHaveBeenCalledWith({ code: 2 });
    expect(span.end).toHaveBeenCalledTimes(1);
  });

  it("ends the span as an error when the socket closes mid-turn", () => {
    const { faro, span } = fakeFaro();
    registerFaro(faro);
    vi.useFakeTimers();
    const { socket, ws } = connected();
    socket.send(TURN);
    ws.onclose!({ code: 1006 });
    vi.useRealTimers();
    socket.close();
    expect(span.setStatus).toHaveBeenCalledWith({ code: 2 });
    expect(span.end).toHaveBeenCalledTimes(1);
  });
});
