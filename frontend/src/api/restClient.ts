import type { Conversation, ConversationDetail, InvestigateResponse, Raid } from "../types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export async function getModels(): Promise<{
  models: string[];
  default: string;
  degraded?: boolean;
}> {
  return json(await fetch("/api/models"));
}

// US5: warm Barnaby greeting for a new chat (model-agnostic, served from a startup
// cache). Best-effort — a network failure should still open a clean chat, so callers catch.
export async function getGreeting(): Promise<{ greeting: string }> {
  return json(await fetch("/api/greeting"));
}

export async function getRaids(): Promise<{ raids: Raid[] }> {
  return json(await fetch("/api/raids"));
}

export async function investigateRaid(
  reportCode: string,
  model?: string,
): Promise<InvestigateResponse> {
  return json(
    await fetch(`/api/raids/${encodeURIComponent(reportCode)}/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: model ?? null }),
    }),
  );
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

export async function downloadReport(id: string): Promise<void> {
  const res = await fetch(`/api/conversations/${id}/report.pdf`);
  if (!res.ok) throw new Error(`${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `wcl-report-${id.slice(0, 8)}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
