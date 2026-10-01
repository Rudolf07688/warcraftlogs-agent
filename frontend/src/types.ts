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
}

export interface InvestigateResponse {
  conversation_id: string;
  model: string;
  kickoff_prompt: string;
}
