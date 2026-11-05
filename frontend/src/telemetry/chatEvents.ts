import { pushTelemetryEvent } from "./context";

// Feature 060 (sc-416, spec §7.1): the chat moments as Faro events. One `TurnEvents` per sent
// turn, owned by the socket that sent it; every event fires at most once per turn. Attributes
// are the model (a served enum) and whole milliseconds: never message text or ids.
// `agent_feedback` is not sent: the app has no feedback feature (spec §7.5 is reserved).

export type AbortReason = "connection_lost" | "closed";

export interface TurnEvents {
  /** The first token of the answer is on screen. */
  firstTokenRendered(): void;
  /** The `done` frame arrived. */
  completed(): void;
  /** An `error` frame ended the turn: neither completed nor aborted. */
  failed(): void;
  /** The connection closed while the turn was streaming. */
  aborted(reason: AbortReason): void;
}

let live: TurnEvents | null = null; // the turn whose answer is streaming now

function ms(since: number): string {
  return String(Math.round(performance.now() - since));
}

export function startTurnEvents(model: string): TurnEvents {
  const sentAt = performance.now();
  let firstToken = false;
  let ended = false;
  const end = (name?: string, attributes: Record<string, string> = {}) => {
    if (ended) return;
    ended = true;
    if (live === turn) live = null;
    if (name) pushTelemetryEvent(name, { model, ...attributes });
  };
  const turn: TurnEvents = {
    firstTokenRendered() {
      if (ended || firstToken) return;
      firstToken = true;
      pushTelemetryEvent("agent_first_token_rendered", { model, ttft_ms: ms(sentAt) });
    },
    completed: () => end("agent_response_completed", { duration_ms: ms(sentAt) }),
    failed: () => end(),
    aborted: (reason) => end("stream_aborted", { reason, elapsed_ms: ms(sentAt) }),
  };
  live = turn;
  pushTelemetryEvent("agent_message_sent", { model });
  return turn;
}

/** Called once the streaming answer has text on screen (repeat calls are ignored). */
export function firstTokenRendered(): void {
  live?.firstTokenRendered();
}
