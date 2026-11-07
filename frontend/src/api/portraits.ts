import { send } from "./restClient";

// Feature 075 (contracts/portraits-api.md): the caller's profile characters with their Blizzard
// portrait, from their own request so the profile never waits on Blizzard. Types live here, not
// in types.ts (074 owns it this sprint).

export interface Portrait {
  character_id: string;
  name: string;
  server: string;
  region: string;
  class_name: string | null;
  /** https on Blizzard's render host, or null: show the initials. */
  portrait_url: string | null;
}

export async function getPortraits(): Promise<{ portraits: Portrait[] }> {
  return send("GET", "/api/profile/portraits");
}
