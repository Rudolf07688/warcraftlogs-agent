// --- Auth / tenancy (feature 006) --------------------------------------------

export type Role = "tenant_admin" | "member";

export interface TenantRef {
  id: string;
  name: string;
}

export interface Membership {
  tenant_id: string;
  name: string;
  role: Role;
}

// Mirrors the backend MeOut payload (contracts/auth-api.md).
export interface Identity {
  user_id: string;
  email: string;
  is_platform_admin: boolean;
  active_tenant: TenantRef | null;
  memberships: Membership[];
  csrf_token: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  status: string; // "open" | "accepted" | "revoked" | "expired"
  expires_at: string;
  invite_link?: string; // returned once on create/resend only
}

export interface AdminUser {
  id: string;
  email: string;
  status: string;
  last_login_at: string | null;
  memberships: Membership[];
}

export interface Conversation {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id?: string;
  role: "user" | "agent";
  content: string;
  seq?: number;
  status?: "complete" | "partial";
  grounded?: boolean;
  suggestions?: string[];
  // US6: the resolved "spellbook" of tool calls made during this turn.
  tools?: SpellCardState[];
  // US4: distinct bosses surfaced on this turn, for the focus picker.
  encounters?: Encounter[];
  // US2: interactive charts the agent produced during this turn.
  artifacts?: ChartArtifact[];
}

// US2: an agent-declared chart, rendered inline as an interactive Plotly figure.
export interface ChartArtifact {
  artifact_id: string;
  kind: string;
  title: string;
  figure: { data: unknown[]; layout: Record<string, unknown> };
  message_seq?: number | null;
}

// US2/US4: a distinct boss encounter from a report's fight list.
export interface Encounter {
  encounter_id: number;
  name: string;
  difficulty?: number;
  kill?: boolean;
}

// US6: per-tool-call spellcasting card state, derived from WS frames.
export type SpellStatus = "casting" | "resolved" | "fizzled";

export interface SpellCardState {
  key: string;
  name: string;
  status: SpellStatus;
  summary?: string;
  ms?: number;
  reportCode?: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface Raid {
  report_code: string;
  label: string;
  zone: string | null;
  guild: string | null;
  report_started_at: string | null;
  last_asked_at: string;
  first_seen_at: string;
  encounters: Encounter[];
}

export interface InvestigateResponse {
  conversation_id: string;
  model: string;
  kickoff_prompt: string;
}

// --- Profile (feature 005 / US1) ---------------------------------------------

export type GuideStatus = "none" | "pending" | "ready" | "failed";

// US4 (feature 007): a character's raid role. `raid_role` is the stored user override
// (null = unset); `effective_role` is the override or the spec-inferred default.
export type RaidRole = "tank" | "healer" | "dps";

export interface Character {
  id: string;
  role: "self" | "friend";
  name: string;
  server: string;
  region: string;
  class_name: string | null;
  active_spec: string | null;
  raid_role: RaidRole | null;
  effective_role: RaidRole | null;
  guide_status: GuideStatus;
  guide_updated_at: string | null;
}

export interface Guild {
  id: string;
  name: string;
  server: string;
  region: string;
  summary_status: GuideStatus;
}

export interface Profile {
  self: Character | null;
  friends: Character[];
  guild: Guild | null;
}

export interface CharacterInput {
  name: string;
  server: string;
  region: string;
  raid_role?: RaidRole | null;
}
