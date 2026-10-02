import type {
  CharacterInput,
  Character,
  ChartArtifact,
  Conversation,
  ConversationDetail,
  Guild,
  InvestigateResponse,
  Profile,
  Raid,
} from "../types";

// Shape of a persisted artifact as returned by GET /api/conversations/{id}.
interface BackendArtifact {
  id: string;
  message_seq: number | null;
  kind: string;
  title: string;
  figure: { data: unknown[]; layout: Record<string, unknown> };
}

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
  const raw = await json<ConversationDetail & { artifacts?: BackendArtifact[] }>(
    await fetch(`/api/conversations/${id}`),
  );
  // US2: attach persisted charts to their originating agent message (by seq) so the
  // conversation re-renders its artifacts on reload (FR-011).
  const bySeq = new Map<number, ChartArtifact[]>();
  for (const a of raw.artifacts ?? []) {
    if (a.message_seq == null) continue;
    const list = bySeq.get(a.message_seq) ?? [];
    list.push({
      artifact_id: a.id,
      kind: a.kind,
      title: a.title,
      figure: a.figure,
      message_seq: a.message_seq,
    });
    bySeq.set(a.message_seq, list);
  }
  const messages = raw.messages.map((m) =>
    m.seq != null && bySeq.has(m.seq) ? { ...m, artifacts: bySeq.get(m.seq) } : m,
  );
  return { ...raw, messages };
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

// US5: download a PDF scoped to a single agent reply (its question + its charts).
export async function downloadMessageReport(convId: string, messageId: string): Promise<void> {
  const res = await fetch(`/api/conversations/${convId}/messages/${messageId}/report.pdf`);
  if (!res.ok) throw new Error(`${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `wcl-message-${messageId.slice(0, 8)}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// --- Profile (feature 005 / US1) ---------------------------------------------

export async function getProfile(): Promise<Profile> {
  return json(await fetch("/api/profile"));
}

export async function putSelf(body: CharacterInput): Promise<Character> {
  return json(
    await fetch("/api/profile/self", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function addFriend(body: CharacterInput): Promise<Character> {
  return json(
    await fetch("/api/profile/friends", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteFriend(id: string): Promise<void> {
  const res = await fetch(`/api/profile/friends/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(`${res.status}`);
}

export async function putGuild(body: CharacterInput): Promise<Guild> {
  return json(
    await fetch("/api/profile/guild", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteGuild(): Promise<void> {
  const res = await fetch("/api/profile/guild", { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(`${res.status}`);
}
