import type { Faro } from "@grafana/faro-react";

// Feature 057: what the rest of the app may ask of Faro. This module never imports the Faro
// packages (type-only import above), so the chat socket and the REST client stay light and
// every function is a no-op until `registerFaro` ran, i.e. whenever Faro is off.

type FaroApi = { api: Pick<Faro["api"], "getOTEL" | "getSession" | "setUser" | "resetUser"> };

let faro: FaroApi | null = null;
let userHash: string | null = null;

export function registerFaro(instance: FaroApi): void {
  faro = instance;
  applyUser();
}

/** Test seam: forget the instance and the user. */
export function resetFaroForTests(): void {
  faro = null;
  userHash = null;
}

function applyUser(): void {
  if (!faro) return;
  if (userHash) faro.api.setUser({ id: userHash });
  else faro.api.resetUser();
}

/** The pseudonymous user id hash, or null on sign-out. Applied now or when Faro is ready. */
export function setTelemetryUser(hash: string | null): void {
  userHash = hash;
  applyUser();
}

/** The Faro session id, for the `x-faro-session-id` header and the chat message. */
export function faroSessionId(): string | undefined {
  return faro?.api.getSession()?.id;
}

export interface ChatTraceFields {
  traceparent?: string;
  faro_session_id?: string;
}

export interface ChatSend {
  fields: ChatTraceFields;
  /** Ends the client span: when the turn finished, or `failed` when it errored or dropped. */
  end(failed?: boolean): void;
}

const SPAN_STATUS_ERROR = 2; // OTel SpanStatusCode.ERROR, without importing the API package

/**
 * Opens the "chat send" span when the user sends a message. Its W3C `traceparent` and the
 * Faro session id go into the message, so the backend's "chat turn" joins this trace (a
 * browser WebSocket cannot send headers). Null when Faro is off; an unsampled span sends no
 * traceparent, only the session id.
 */
export function startChatSend(): ChatSend | null {
  const otel = faro?.api.getOTEL();
  if (!faro || !otel) return null;
  const span = otel.trace.getTracer("wcl-web").startSpan("chat send");
  const { traceId, spanId, traceFlags } = span.spanContext();
  const fields: ChatTraceFields = {};
  const sessionId = faroSessionId();
  if (sessionId) fields.faro_session_id = sessionId;
  if (traceFlags & 1) fields.traceparent = `00-${traceId}-${spanId}-01`;
  let ended = false;
  return {
    fields,
    end(failed = false) {
      if (ended) return;
      ended = true;
      if (failed) span.setStatus({ code: SPAN_STATUS_ERROR });
      span.end();
    },
  };
}
