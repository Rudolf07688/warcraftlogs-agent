import { useSyncExternalStore } from "react";

/**
 * PERF-010: the text of the reply that is streaming right now, kept outside React state.
 *
 * Tokens arrive many times a second. Holding the text in `App` state re-rendered the whole
 * app (sidebar, header, composer, every message) on every token. Here only the live
 * message subscribes, so a token re-renders just that message.
 */
let text = "";
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export const streamStore = {
  get: () => text,
  set(next: string) {
    if (next === text) return;
    text = next;
    emit();
  },
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function useStreamText(): string {
  return useSyncExternalStore(streamStore.subscribe, streamStore.get);
}
