import { useSyncExternalStore } from "react";
import { THINKING_DEFAULT } from "../toolLabels";
import { cleanStatus } from "./statusText";

/**
 * 085 (sc-583): the live turn status, kept outside React state like `streamStore`.
 *
 * Thinking frames arrive up to once a second and every non-token frame moves `quietSince`.
 * Held in `App` state, each one re-rendered the app and the message list; here only the live
 * status subscribes. All text goes through `cleanStatus` on the way in.
 */
export interface TurnStatusState {
  /** The indicator label before any spell card: tool, web search, retry or fallback. */
  status: string;
  /** The latest thought or interim line (model text). */
  thought: string | null;
  /** A model retry/fallback label; shown under the cards too, until the next status event. */
  notice: string | null;
  /** When the turn last reported anything (ms epoch), for "Thinking… Ns". */
  quietSince: number;
}

let state: TurnStatusState = {
  status: THINKING_DEFAULT,
  thought: null,
  notice: null,
  quietSince: 0,
};
const listeners = new Set<() => void>();

const clean = (text: string | null | undefined) => (text ? cleanStatus(text) || null : null);

export const statusStore = {
  get: () => state,
  update(patch: Partial<TurnStatusState>) {
    const next = { ...state, ...patch };
    if ("status" in patch) next.status = clean(patch.status) ?? THINKING_DEFAULT;
    if ("thought" in patch) next.thought = clean(patch.thought);
    if ("notice" in patch) next.notice = clean(patch.notice);
    if (
      next.status === state.status &&
      next.thought === state.thought &&
      next.notice === state.notice &&
      next.quietSince === state.quietSince
    ) {
      return;
    }
    state = next;
    for (const listener of listeners) listener();
  },
  /** A turn starts or ends: the default indicator, no line, quiet from now. */
  reset() {
    statusStore.update({ status: THINKING_DEFAULT, thought: null, notice: null, quietSince: Date.now() });
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function useTurnStatus(): TurnStatusState {
  return useSyncExternalStore(statusStore.subscribe, statusStore.get);
}
