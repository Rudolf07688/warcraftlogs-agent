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
