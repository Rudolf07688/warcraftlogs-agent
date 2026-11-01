import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import { DEFAULT_SPELL, spellFor } from "./lib/spells";
import { toolLabel } from "./toolLabels";
import type { Frame } from "./api/wsClient";
import type { ConversationDetail, Message, ProfileProposal } from "./types";

// sc-243 (feature 034): a proposal made in chat A must never show up in chat B when the user
// switches chats (or starts a new one) while A's turn is still streaming. The children are
// mocked down to the props that carry the proposals, and the socket is driven by hand.

const h = vi.hoisted(() => ({
  onFrame: null as ((f: unknown) => void) | null,
  onStatus: null as ((connected: boolean) => void) | null,
  details: {} as Record<string, unknown>,
}));

vi.mock("./api/wsClient", () => ({
  ChatSocket: class {
    constructor(onFrame: (f: unknown) => void, onStatus: (connected: boolean) => void) {
      h.onFrame = onFrame;
      h.onStatus = onStatus;
    }
    connect() {}
    close() {}
    send() {
      return true;
    }
  },
}));

vi.mock("./api/restClient", () => ({
  getModels: vi.fn(async () => ({ models: ["m"], default: "m" })),
  listConversations: vi.fn(async () => ({ conversations: [] })),
  getRaids: vi.fn(async () => ({ raids: [] })),
  getGreeting: vi.fn(async () => ({ greeting: "" })),
  getConversation: vi.fn(async (id: string) => h.details[id]),
  deleteConversation: vi.fn(),
  downloadMessageReport: vi.fn(),
  downloadReport: vi.fn(),
  investigateRaid: vi.fn(),
  investigateMplusRun: vi.fn(),
  updateConversation: vi.fn(),
}));

vi.mock("./auth/useAuth", () => ({ useAuth: () => ({ identity: null, logout: vi.fn() }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));

vi.mock("./components/Sidebar", () => ({
  Sidebar: (p: { onSelect: (id: string) => void; onNew: () => void }) => (
    <div>
      <button onClick={() => p.onSelect("A")}>open-A</button>
      <button onClick={() => p.onSelect("B")}>open-B</button>
      <button onClick={() => p.onNew()}>new-chat</button>
    </div>
  ),
}));
vi.mock("./components/MessageList", () => ({
  MessageList: (p: { messages: Message[]; looseProposals: ProfileProposal[]; status: string }) => (
    <div>
      <div data-testid="attached">
        {p.messages.flatMap((m) => m.proposals ?? []).map((x) => x.id).join(",")}
      </div>
      <div data-testid="loose">{p.looseProposals.map((x) => x.id).join(",")}</div>
      <div data-testid="status">{p.status}</div>
    </div>
  ),
}));
vi.mock("./components/Composer", () => ({
  Composer: (p: { onSend: (t: string) => void }) => <button onClick={() => p.onSend("hi")}>send</button>,
}));
vi.mock("./components/WelcomePanel", () => ({ WelcomePanel: () => null }));
vi.mock("./components/Ambient", () => ({ Ambient: () => null }));
vi.mock("./components/ModelSelect", () => ({ ModelSelect: () => null }));

function proposal(id: string, conversationId: string): ProfileProposal {
  return {
    id,
    conversation_id: conversationId,
    message_seq: null,
    status: "pending",
    created_at: "2026-10-31T10:00:00Z",
    expires_at: "2026-10-31T11:00:00Z",
    applied_at: null,
    items: [],
  };
}

function detail(id: string, proposals: ProfileProposal[] = []): ConversationDetail {
  return {
    id,
    title: id,
    model: "m",
    messages: [],
    proposals,
  } as unknown as ConversationDetail;
}

const P = proposal("P", "A");

function frame(f: Frame) {
  act(() => h.onFrame?.(f));
}
async function click(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByText(name));
  });
}
const attached = () => screen.getByTestId("attached").textContent;
const loose = () => screen.getByTestId("loose").textContent;

// Open chat A, send a turn, and let A's proposal arrive.
async function startTurnInA() {
  await click("open-A");
  await click("send");
  frame({ type: "meta", conversation_id: "A", seq: 1 });
  frame({ type: "proposal", proposal: P });
}

describe("App: a streamed proposal belongs to its own chat (sc-243)", () => {
  beforeEach(async () => {
    h.details = { A: detail("A"), B: detail("B") };
    render(<App />);
    await act(async () => {
      h.onStatus?.(true);
    });
  });
  afterEach(cleanup);

  it("(a) done after switching to chat B shows no card in B", async () => {
    await startTurnInA();
    await click("open-B");
    frame({ type: "done", message_id: "m1" });
    expect(attached()).toBe("");
    expect(loose()).toBe("");
  });

  it("(b) error after switching to chat B shows no loose card in B", async () => {
    await startTurnInA();
    await click("open-B");
    frame({ type: "error", code: "x", message: "boom" });
    expect(attached()).toBe("");
    expect(loose()).toBe("");
  });

  it("(c) done after New chat shows no card, even for a proposal arriving after it", async () => {
    await startTurnInA();
    await click("new-chat");
    frame({ type: "proposal", proposal: proposal("Q", "A") });
    frame({ type: "done", message_id: "m1" });
    expect(attached()).toBe("");
    expect(loose()).toBe("");
  });

  it("(d) switching away and back mid-turn shows the card exactly once on done", async () => {
    await startTurnInA();
    await click("open-B");
    h.details.A = detail("A", [P]); // reopening A loads P, unfinished, as a loose card
    await click("open-A");
    await waitFor(() => expect(loose()).toBe("P"));
    frame({ type: "done", message_id: "m1" });
    expect(attached()).toBe("P");
    expect(loose()).toBe("");
  });

  it("(e) done without switching attaches the card to the agent message", async () => {
    await startTurnInA();
    frame({ type: "done", message_id: "m1" });
    expect(attached()).toBe("P");
    expect(loose()).toBe("");
  });

  it("(f) the status line names the profile tool while it runs", async () => {
    await click("open-A");
    await click("send");
    frame({ type: "tool_start", name: "propose_profile_changes" });
    expect(screen.getByTestId("status").textContent).toBe("Preparing profile changes");
  });
});

describe("spells", () => {
  it("(g) propose_profile_changes has its own spell", () => {
    expect(spellFor("propose_profile_changes")).not.toBe(DEFAULT_SPELL);
  });

  const STORED_TOOLS = [
    "search_knowledge",
    "list_stored_fights",
    "get_stored_fight_table",
    "list_stored_reports_for_character",
  ];

  it.each(STORED_TOOLS)("(h) %s has its own spell and label, not the Warcraft Logs default", (name) => {
    expect(spellFor(name)).not.toBe(DEFAULT_SPELL);
    expect(toolLabel(name)).not.toBe(toolLabel("an_unknown_tool"));
    expect(toolLabel(name)).not.toMatch(/Warcraft Logs/);
  });
});
