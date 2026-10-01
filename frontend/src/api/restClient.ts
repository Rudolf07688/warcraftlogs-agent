import type { Conversation, ConversationDetail } from "../types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export async function getModels(): Promise<{ models: string[]; default: string }> {
  return json(await fetch("/api/models"));
}

export async function listConversations(): Promise<{ conversations: Conversation[] }> {
  return json(await fetch("/api/conversations"));
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return json(await fetch(`/api/conversations/${id}`));
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`/api/conversations/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(`${res.status}`);
}
