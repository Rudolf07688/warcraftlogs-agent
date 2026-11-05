import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { registerFaro, resetFaroForTests } from "../telemetry/context";
import { firstTokenRendered } from "../telemetry/chatEvents";
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
      setView: vi.fn(),
      pushEvent: vi.fn(),
      pushError: vi.fn(),
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

// Feature 060 (sc-416): the chat moments as Faro events, once each, at their moment.
describe("chat events", () => {
  function events() {
    const { faro } = fakeFaro();
    registerFaro(faro);
    const push = (faro as unknown as { api: { pushEvent: ReturnType<typeof vi.fn> } }).api.pushEvent;
    return { names: () => push.mock.calls.map((c) => c[0] as string), push };
  }

  it("sends message sent, first token rendered and response completed once each", () => {
    const { names, push } = events();
    const { socket, ws } = connected();
    socket.send(TURN);
    expect(names()).toEqual(["agent_message_sent"]);
    frame(ws, { type: "token", text: "a" });
    firstTokenRendered();
    firstTokenRendered();
    frame(ws, { type: "token", text: "b" });
    frame(ws, { type: "done", message_id: "m1" });
    frame(ws, { type: "done", message_id: "m1" });
    firstTokenRendered(); // the next render after done belongs to no turn
    expect(names()).toEqual(["agent_message_sent", "agent_first_token_rendered", "agent_response_completed"]);
    const [, ttft, done] = push.mock.calls;
    expect(ttft[1]).toEqual({ model: "m", ttft_ms: expect.stringMatching(/^\d+$/) });
    expect(done[1]).toEqual({ model: "m", duration_ms: expect.stringMatching(/^\d+$/) });
    // Bounded attributes: never the message text.
    expect(JSON.stringify(push.mock.calls)).not.toContain("hello");
  });

  it("reports stream_aborted when the connection drops mid-turn, once", () => {
    const { names, push } = events();
    vi.useFakeTimers();
    const { socket, ws } = connected();
    socket.send(TURN);
    ws.onclose!({ code: 1006 });
    ws.onclose!({ code: 1006 });
    vi.useRealTimers();
    socket.close();
    expect(names()).toEqual(["agent_message_sent", "stream_aborted"]);
    expect(push.mock.calls[1][1]).toMatchObject({ model: "m", reason: "connection_lost" });
  });

  it("reports a turn cut off by the app closing the socket as closed", () => {
    const { push } = events();
    const { socket, ws } = connected();
    socket.send(TURN);
    socket.close();
    ws.onclose!({ code: 1000 });
    expect(push.mock.calls[1]).toEqual(["stream_aborted", expect.objectContaining({ reason: "closed" })]);
  });

  it("does not report an abort for an error frame, a finished turn or an idle close", () => {
    const { names } = events();
    vi.useFakeTimers();
    const { socket, ws } = connected();
    socket.send(TURN);
    frame(ws, { type: "error", code: "x", message: "boom" });
    socket.send(TURN);
    frame(ws, { type: "done", message_id: "m2" });
    ws.onclose!({ code: 1006 });
    vi.useRealTimers();
    socket.close();
    expect(names()).toEqual(["agent_message_sent", "agent_message_sent", "agent_response_completed"]);
  });

  it("a closing second socket never aborts another socket's turn (StrictMode remount)", () => {
    const { names } = events();
    const first = connected();
    first.socket.close();
    const second = connected();
    second.socket.send(TURN);
    first.ws.onclose!({ code: 1000 });
    frame(second.ws, { type: "done", message_id: "m1" });
    expect(names()).toEqual(["agent_message_sent", "agent_response_completed"]);
  });

  it("sends nothing while Faro is off", () => {
    const { socket, ws } = connected();
    socket.send(TURN);
    frame(ws, { type: "done", message_id: "m1" });
    expect(JSON.parse(ws.sent[0])).toEqual(TURN);
  });
});
