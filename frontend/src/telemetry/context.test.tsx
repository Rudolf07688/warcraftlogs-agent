import { afterEach, describe, expect, it, vi } from "vitest";
import { faroSessionId, registerFaro, resetFaroForTests, setTelemetryUser, startChatSend } from "./context";

// Feature 057 (sc-414/415): the pieces the chat socket and the REST client ask of Faro. With
// no Faro registered every one of them is a no-op.

const TRACE_ID = "0af7651916cd43dd8448eb211c80319c";
const SPAN_ID = "b7ad6b7169203331";

function fakeFaro(opts: { sampled?: boolean; otel?: boolean; session?: string | null } = {}) {
  const { sampled = true, otel = true, session = "a1B2c3D4e5" } = opts;
  const span = {
    spanContext: () => ({ traceId: TRACE_ID, spanId: SPAN_ID, traceFlags: sampled ? 1 : 0 }),
    setStatus: vi.fn(),
    end: vi.fn(),
  };
  const api = {
    getOTEL: vi.fn(() => (otel ? { trace: { getTracer: () => ({ startSpan: () => span }) } } : undefined)),
    getSession: vi.fn(() => (session ? { id: session } : undefined)),
    setUser: vi.fn(),
    resetUser: vi.fn(),
  };
  return { span, api, faro: { api } as never };
}

afterEach(() => resetFaroForTests());

describe("with Faro off", () => {
  it("has no session id, starts no chat span and ignores the user", () => {
    expect(faroSessionId()).toBeUndefined();
    expect(startChatSend()).toBeNull();
    expect(() => setTelemetryUser("abc")).not.toThrow();
  });
});

describe("startChatSend", () => {
  it("opens a span and hands out its traceparent and the Faro session id", () => {
    const { faro } = fakeFaro();
    registerFaro(faro);
    const send = startChatSend();
    expect(send?.fields).toEqual({
      traceparent: `00-${TRACE_ID}-${SPAN_ID}-01`,
      faro_session_id: "a1B2c3D4e5",
    });
  });

  it("ends the span once, marking a failed turn as an error", () => {
    const { faro, span } = fakeFaro();
    registerFaro(faro);
    const send = startChatSend()!;
    send.end(true);
    send.end(false);
    expect(span.end).toHaveBeenCalledTimes(1);
    expect(span.setStatus).toHaveBeenCalledWith({ code: 2 });
  });

  it("ends a finished turn's span without an error status", () => {
    const { faro, span } = fakeFaro();
    registerFaro(faro);
    startChatSend()!.end();
    expect(span.end).toHaveBeenCalledTimes(1);
    expect(span.setStatus).not.toHaveBeenCalled();
  });

  it("sends no traceparent for an unsampled span, only the session id", () => {
    registerFaro(fakeFaro({ sampled: false }).faro);
    expect(startChatSend()?.fields).toEqual({ faro_session_id: "a1B2c3D4e5" });
  });

  it("sends no session id when Faro has none", () => {
    registerFaro(fakeFaro({ session: null }).faro);
    expect(startChatSend()?.fields).toEqual({ traceparent: `00-${TRACE_ID}-${SPAN_ID}-01` });
  });

  it("is null while Faro's tracing is not initialised yet", () => {
    registerFaro(fakeFaro({ otel: false }).faro);
    expect(startChatSend()).toBeNull();
  });
});

describe("the user", () => {
  it("is set on Faro as the hash only, also when it arrives before Faro", () => {
    setTelemetryUser("0123456789abcdef");
    const { faro, api } = fakeFaro();
    registerFaro(faro);
    expect(api.setUser).toHaveBeenCalledWith({ id: "0123456789abcdef" });
  });

  it("is reset on sign-out", () => {
    const { faro, api } = fakeFaro();
    registerFaro(faro);
    setTelemetryUser("0123456789abcdef");
    setTelemetryUser(null);
    expect(api.resetUser).toHaveBeenCalled();
  });
});
