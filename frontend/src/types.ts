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
  // Feature 019: when the chat was pinned; null/absent = not pinned.
  pinned_at: string | null;
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

// --- Recent raids (feature 013, contracts/rest-recent-raids.md) ---------------

export interface RecentRaidCharacter {
  name: string;
  server: string;
  region: string;
}

export interface RecentRaid {
  report_code: string;
  title: string;
  zone_name: string | null;
  started_at: string;
  /** WCL difficulty id: 1 LFR, 3 Normal, 4 Heroic, 5 Mythic. */
  difficulty: number | null;
  /** null until the raid's details have been fetched. */
  bosses_pulled: number | null;
  bosses_killed: number | null;
  is_final: boolean;
  characters: RecentRaidCharacter[];
}

export type RecentRaidsStatus = "idle" | "running" | "succeeded" | "failed";

export interface RecentRaidsRefresh {
  status: RecentRaidsStatus;
  last_success_at: string | null;
  /** wcl_unavailable | rate_limited | timeout | unknown */
  last_error: string | null;
}

export interface RecentMplusRun {
  report_code: string;
  fight_id: number;
  dungeon: string;
  key_level: number;
  started_at: string;
  timed: boolean;
  characters: RecentRaidCharacter[];
}

export interface RecentRaidsResponse {
  has_characters: boolean;
  raids: RecentRaid[];
  mplus_runs: RecentMplusRun[];
  refresh: RecentRaidsRefresh;
}

// --- Profile (feature 005 / US1) ---------------------------------------------

export type GuideStatus = "none" | "pending" | "ready" | "needs_review" | "failed";

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
  // Feature 015: guide status per content type, derived from the shared library.
  guides: CharacterGuides;
}

export interface CharacterGuides {
  raid: GuideStatus;
  mplus: GuideStatus;
}

export interface Guild {
  id: string;
  name: string;
  server: string;
  region: string;
  summary_status: GuideStatus;
}

export interface Profile {
  // Feature 012: the user's own characters (0..own_limit), in creation order.
  own: Character[];
  own_limit: number;
  friends: Character[];
  guild: Guild | null;
}

export interface CharacterInput {
  name: string;
  server: string;
  region: string;
  raid_role?: RaidRole | null;
}

// --- Class guides (features 008, 015) — the shared, global spec-guide library ---

// Feature 015: every guide is one content type of one spec.
export type ContentType = "raid" | "mplus";

// Read-time freshness vs the live patch / season (null unless a version is published).
export type GuideFreshness = "current" | "possibly_stale" | "unknown";

// What the viewer shows: the published version, an unverified draft, or nothing.
export type GuideDisplay = "published" | "draft" | "none";

export interface GuideSource {
  title: string | null;
  uri: string;
  tier: number | null; // 1 official, 2 Warcraft Logs, 3 guide site
  date: string | null;
}

// One content type of one spec, as the library lists it.
export interface GuideSummary {
  content_type: ContentType;
  status: GuideStatus; // the latest run ("none" = never generated)
  has_published: boolean;
  refreshing: boolean; // a run is pending while the published version is shown
  game_patch: string | null;
  season: string | null; // Mythic+ only
  generated_at: string | null;
  updated_at: string | null;
  freshness: GuideFreshness | null;
  stale_reason: string | null; // patch_changed | season_changed | hotfix | legacy
}

// One row per spec, with both content types.
export interface GuideListItem {
  class_name: string; // WCL filter value, e.g. "Paladin"
  class_display: string; // display name, e.g. "Death Knight"
  spec: string; // e.g. "BeastMastery"
  spec_display: string; // e.g. "Beast Mastery"
  role: RaidRole;
  raid: GuideSummary;
  mplus: GuideSummary;
}

export interface GuideListResponse {
  guides: GuideListItem[];
  roster_source: "game_data" | "fallback";
}

export interface Guide extends GuideSummary {
  class_name: string;
  spec: string;
  display: GuideDisplay;
  guide_markdown: string | null;
  sources: GuideSource[];
  unconfirmed: string[]; // areas left out because nothing current confirmed them
  review_issues: string[]; // only when display === "draft"
  failure_reason: string | null;
}

export interface GuideReport {
  id: string;
  status: "open" | "fixed" | "rejected";
  created_at: string;
}

// --- Backend boot / readiness (GET /api/health) -------------------------------

export interface StartupStep {
  key: string;
  label: string;
  status: "pending" | "running" | "done" | "skipped" | "failed";
  detail: string | null;
  ms: number | null;
}

export interface StartupSnapshot {
  phase: "booting" | "ready" | "failed";
  ready: boolean;
  error: string | null;
  elapsed_ms: number;
  current_step: string | null;
  steps: StartupStep[];
}

export interface BackendHealth {
  status: "ok" | "booting" | "error";
  db: "ok" | "error";
  /** null when the app runs without a lifespan (tests) — treated as ready. */
  startup: StartupSnapshot | null;
}
