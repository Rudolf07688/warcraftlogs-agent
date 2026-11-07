import { send } from "./restClient";

// contract:raid-summary (sprint 2026-11-07b, stream 072): what is stored for one tracked raid.
// Each part may be missing on its own; has_data false means nothing is stored yet.
export type RaidSummaryRole = "tank" | "healer" | "dps" | null;

export interface RaidSummaryParticipant {
  name: string;
  class_name: string;
  spec: string | null;
  role: RaidSummaryRole;
}

export interface RaidSummaryParse {
  encounter: string;
  difficulty: string | null;
  percentile: number | null;
}

export interface RaidSummaryCharacter {
  name: string;
  class_name: string;
  spec: string | null;
  parses: RaidSummaryParse[];
}

export interface RaidSummary {
  report_code: string;
  has_data: boolean;
  duration_ms: number | null;
  participants: RaidSummaryParticipant[];
  my_characters: RaidSummaryCharacter[];
  fetched_at: string | null;
}

export async function getRaidSummary(reportCode: string): Promise<RaidSummary> {
  return send("GET", `/api/raids/${encodeURIComponent(reportCode)}/summary`);
}
