import { useEffect, useMemo, useState } from "react";
import { getPortraits, type Portrait } from "../api/portraits";
import { useProfileChanged } from "../lib/profileEvents";

// Feature 075: one shared portraits request for every avatar on screen. Concurrent callers (a
// chat with several confirmation cards, the welcome page) share one in-flight request, and an
// answer is reused for a minute. A caller passing `version` (the profile's character ids) gets a
// fresh one when it changes; an approved profile change (any tab) refreshes every caller once.
// A failed request means "no portraits": every avatar keeps its initials.

const REUSE_MS = 60_000;

let shared: { at: number; version: string; promise: Promise<Portrait[]> } | null = null;
let lastChange: string | null = null; // the last profile change heard (another tab sends copies)

function load(version: string): Promise<Portrait[]> {
  const fresh = shared && Date.now() - shared.at < REUSE_MS;
  if (shared && fresh && (!version || shared.version === version)) return shared.promise;
  const promise = getPortraits().then(
    (res) => res.portraits,
    () => [] as Portrait[],
  );
  shared = { at: Date.now(), version, promise };
  return promise;
}

/** Test hook: forget the shared answer. */
export function resetPortraitsCache(): void {
  shared = null;
  lastChange = null;
}

// The same character in another response: names compare case-insensitively, realms without
// spaces, hyphens, apostrophes or case ("Kel'Thuzad" = "kelthuzad", "Tarren Mill" = "tarren-mill").
const realmKey = (server: string) => server.toLowerCase().replace(/[\s'-]/g, "");
const identityKey = (name: string, server: string, region: string) =>
  `${name.toLowerCase()}|${realmKey(server)}|${region.toLowerCase()}`;

export interface PortraitLookup {
  byId: (id: string | null | undefined) => Portrait | undefined;
  byIdentity: (name: string, server: string, region: string) => Portrait | undefined;
}

/** The caller's profile portraits. `enabled` false makes no request (nothing to match). */
export function usePortraits({ version = "", enabled = true }: { version?: string; enabled?: boolean } = {}): PortraitLookup {
  const [portraits, setPortraits] = useState<Portrait[]>([]);
  const [changes, setChanges] = useState(0);

  useProfileChanged((change) => {
    const key = `${change.proposal.id}@${change.proposal.applied_at ?? ""}`;
    if (key !== lastChange) {
      lastChange = key; // the first caller to hear this change drops the shared answer
      shared = null;
    }
    setChanges((n) => n + 1);
  });

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    void load(version).then((next) => {
      if (alive) setPortraits(next);
    });
    return () => {
      alive = false;
    };
  }, [version, enabled, changes]);

  return useMemo(() => {
    const ids = new Map(portraits.map((p) => [p.character_id, p]));
    const identities = new Map(portraits.map((p) => [identityKey(p.name, p.server, p.region), p]));
    return {
      byId: (id) => (id ? ids.get(id) : undefined),
      byIdentity: (name, server, region) => identities.get(identityKey(name, server, region)),
    };
  }, [portraits]);
}
