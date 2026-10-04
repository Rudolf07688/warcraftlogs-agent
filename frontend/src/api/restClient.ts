import type {
  AdminUser,
  CharacterInput,
  Character,
  ChartArtifact,
  Conversation,
  ConversationDetail,
  Guild,
  Identity,
  Invitation,
  InvestigateResponse,
  Profile,
  RaidRole,
  Raid,
  Role,
} from "../types";

// Shape of a persisted artifact as returned by GET /api/conversations/{id}.
interface BackendArtifact {
  id: string;
  message_seq: number | null;
  kind: string;
  title: string;
  figure: { data: unknown[]; layout: Record<string, unknown> };
}

// --- Auth plumbing (feature 006) ---------------------------------------------
// The per-session CSRF token lives in memory only (never localStorage). AuthProvider
// sets it after login/accept/me; unsafe requests attach it as X-CSRF-Token.

let _csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  _csrfToken = token;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let message = res.statusText;
  let code: string | undefined;
  try {
    const body = await res.json();
    if (body?.error) {
      code = body.error.code;
      message = body.error.message ?? message;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    }
  } catch {
    /* non-JSON body */
  }
  return new ApiError(res.status, message, code);
}

// Credentialed JSON request (sends the session cookie; attaches CSRF on unsafe methods).
async function send<T>(
  method: string,
  url: string,
  body?: unknown,
  opts: { csrf?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.csrf && _csrfToken) headers["X-CSRF-Token"] = _csrfToken;
  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Auth endpoints ----------------------------------------------------------

export async function getMe(): Promise<Identity> {
  return send<Identity>("GET", "/api/auth/me");
}

export async function login(email: string, password: string): Promise<Identity> {
  return send<Identity>("POST", "/api/auth/login", { email, password });
}

export async function logout(): Promise<void> {
  return send<void>("POST", "/api/auth/logout", undefined, { csrf: true });
}

export async function acceptInvitation(
  token: string,
  password: string,
  passwordConfirmation: string,
): Promise<Identity> {
  return send<Identity>("POST", "/api/auth/accept-invitation", {
    token,
    password,
    password_confirmation: passwordConfirmation,
  });
}

export async function resetPassword(
  token: string,
  password: string,
  passwordConfirmation: string,
): Promise<{ message: string }> {
  return send("POST", "/api/auth/reset-password", {
    token,
    password,
    password_confirmation: passwordConfirmation,
  });
}

// --- Admin endpoints (platform admin only; all unsafe calls carry CSRF) -------

export async function createInvitation(email: string, role: Role): Promise<Invitation> {
  return send<Invitation>("POST", "/api/admin/invitations", { email, role }, { csrf: true });
}

export async function listUsers(): Promise<{ users: AdminUser[]; next_cursor: string | null }> {
  return send("GET", "/api/admin/users");
}

export async function listInvitations(): Promise<{ invitations: Invitation[] }> {
  return send("GET", "/api/admin/invitations");
}

export async function resendInvitation(id: string): Promise<Invitation> {
  return send<Invitation>("POST", `/api/admin/invitations/${id}/resend`, undefined, { csrf: true });
}

export async function revokeInvitation(id: string): Promise<void> {
  return send<void>("DELETE", `/api/admin/invitations/${id}`, undefined, { csrf: true });
}

export async function setUserStatus(id: string, status: "active" | "disabled"): Promise<AdminUser> {
  return send<AdminUser>("PATCH", `/api/admin/users/${id}`, { status }, { csrf: true });
}

export async function triggerReset(id: string): Promise<{ reset_link: string }> {
  return send("POST", `/api/admin/users/${id}/reset`, undefined, { csrf: true });
}

export async function getModels(): Promise<{
  models: string[];
  default: string;
  degraded?: boolean;
}> {
  return send("GET", "/api/models");
}

// US5: warm Barnaby greeting for a new chat (model-agnostic, served from a startup
// cache). Best-effort — a network failure should still open a clean chat, so callers catch.
export async function getGreeting(): Promise<{ greeting: string }> {
  return send("GET", "/api/greeting");
}

export async function getRaids(): Promise<{ raids: Raid[] }> {
  return send("GET", "/api/raids");
}

export async function investigateRaid(
  reportCode: string,
  model?: string,
): Promise<InvestigateResponse> {
  return send(
    "POST",
    `/api/raids/${encodeURIComponent(reportCode)}/investigate`,
    { model: model ?? null },
    { csrf: true },
  );
}

export async function listConversations(): Promise<{ conversations: Conversation[] }> {
  return send("GET", "/api/conversations");
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const raw = await send<ConversationDetail & { artifacts?: BackendArtifact[] }>(
    "GET",
    `/api/conversations/${id}`,
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
  await send("DELETE", `/api/conversations/${id}`, undefined, { csrf: true });
}

export async function downloadReport(id: string): Promise<void> {
  const res = await fetch(`/api/conversations/${id}/report.pdf`, { credentials: "include" });
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
  const res = await fetch(`/api/conversations/${convId}/messages/${messageId}/report.pdf`, {
    credentials: "include",
  });
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
  return send("GET", "/api/profile");
}

export async function putSelf(body: CharacterInput): Promise<Character> {
  return send("PUT", "/api/profile/self", body, { csrf: true });
}

export async function addFriend(body: CharacterInput): Promise<Character> {
  return send("POST", "/api/profile/friends", body, { csrf: true });
}

export async function deleteFriend(id: string): Promise<void> {
  await send("DELETE", `/api/profile/friends/${id}`, undefined, { csrf: true });
}

// US4: set/clear a friend's raid-role override in place (null reverts to inferred).
export async function updateFriend(
  id: string,
  raidRole: RaidRole | null,
): Promise<Character> {
  return send("PATCH", `/api/profile/friends/${id}`, { raid_role: raidRole }, { csrf: true });
}

export async function putGuild(body: CharacterInput): Promise<Guild> {
  return send("PUT", "/api/profile/guild", body, { csrf: true });
}

export async function deleteGuild(): Promise<void> {
  await send("DELETE", "/api/profile/guild", undefined, { csrf: true });
}
