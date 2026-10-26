import { useEffect, useRef } from "react";
import type { ProfileProposal } from "../types";

// Feature 031: "the profile changed" (an approved confirmation card), for every open tab of the
// app. A BroadcastChannel reaches the other tabs and a window event reaches this one; channel
// messages carry the sending tab's id so this tab doesn't handle its own change twice.
// Browser-side only (design #refresh).

export interface ProfileChange {
  proposal: ProfileProposal;
  targets: ("friend" | "own")[]; // which lists the approved changes touched
}

const CHANNEL = "wcl-profile";
const EVENT = "wcl-profile-changed";
const TAB_ID = Math.random().toString(36).slice(2);

interface ChannelMessage {
  tab: string;
  change: ProfileChange;
}

function openChannel(): BroadcastChannel | null {
  return typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(CHANNEL);
}

export function notifyProfileChanged(change: ProfileChange): void {
  const channel = openChannel();
  channel?.postMessage({ tab: TAB_ID, change } satisfies ChannelMessage);
  channel?.close();
  window.dispatchEvent(new CustomEvent<ProfileChange>(EVENT, { detail: change }));
}

/** Calls `callback` for every profile change, from this tab or another, while mounted. */
export function useProfileChanged(callback: (change: ProfileChange) => void): void {
  const ref = useRef(callback);
  ref.current = callback;

  useEffect(() => {
    const onEvent = (e: Event) => ref.current((e as CustomEvent<ProfileChange>).detail);
    const channel = openChannel();
    if (channel) {
      channel.onmessage = (e: MessageEvent<ChannelMessage>) => {
        if (e.data.tab !== TAB_ID) ref.current(e.data.change);
      };
    }
    window.addEventListener(EVENT, onEvent);
    return () => {
      window.removeEventListener(EVENT, onEvent);
      channel?.close();
    };
  }, []);
}
