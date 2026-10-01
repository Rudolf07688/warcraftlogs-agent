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
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}
