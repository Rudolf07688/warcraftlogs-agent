import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import type { Frame } from "./api/wsClient";
import type { ConversationDetail, Message, ProfileProposal, SpellCardState } from "./types";

// sc-376 (feature 063): a socket drop mid-answer ends the turn locally (composer unlocked,
// partial text kept, a short note), and the reconnect reloads the chat so the saved partial
// answer replaces the local copy. The socket is driven by hand, as in App.test.tsx.

const h = vi.hoisted(() => ({
  onFrame: null as ((f: unknown) => void) | null,
  onStatus: null as ((connected: boolean) => void) | null,
  details: {} as Record<string, unknown>,
  getConversation: null as null | ((id: string) => Promise<unknown>),
  sent: 0,
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
      h.sent++;
      return true;
    }
  },
}));

vi.mock("./api/restClient", () => ({
  getModels: vi.fn(async () => ({ models: ["m"], default: "m" })),
  listConversations: vi.fn(async () => ({ conversations: [] })),
  getRaids: vi.fn(async () => ({ raids: [] })),
  getGreeting: vi.fn(async () => ({ greeting: "" })),
  getConversation: vi.fn((id: string) => (h.getConversation ?? (async (i: string) => h.details[i]))(id)),
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
  Sidebar: (p: { onSelect: (id: string) => void }) => (
    <div>
      <button onClick={() => p.onSelect("A")}>open-A</button>
      <button onClick={() => p.onSelect("B")}>open-B</button>
    </div>
  ),
}));
vi.mock("./components/MessageList", () => ({
  MessageList: (p: {
    messages: Message[];
    streaming: boolean;
    error: string | null;
    streamCards: SpellCardState[];
    looseProposals: ProfileProposal[];
  }) => (
    <div>
      <div data-testid="messages">{p.messages.map((m) => `${m.role}:${m.content}`).join("|")}</div>
      <div data-testid="error">{p.error ?? ""}</div>
      <div data-testid="cards">{p.streamCards.map((c) => `${c.name}:${c.status}`).join(",")}</div>
      <div data-testid="loose">{p.looseProposals.map((x) => x.id).join(",")}</div>
    </div>
  ),
}));
vi.mock("./components/Composer", () => ({
  Composer: (p: { disabled: boolean; onSend: (t: string) => void }) => (
    <button disabled={p.disabled} onClick={() => p.onSend("hi")}>
      send
    </button>
  ),
}));
vi.mock("./components/WelcomePanel", () => ({ WelcomePanel: () => null }));
vi.mock("./components/Ambient", () => ({ Ambient: () => null }));
vi.mock("./components/ModelSelect", () => ({ ModelSelect: () => null }));

const NOTE = "Connection lost, the answer may be incomplete.";

function detail(id: string, messages: Partial<Message>[]): ConversationDetail {
  return { id, title: id, model: "m", messages, proposals: [] } as unknown as ConversationDetail;
}
function frame(f: Frame) {
  act(() => h.onFrame?.(f));
}
async function status(up: boolean) {
  await act(async () => {
    h.onStatus?.(up);
  });
}
async function click(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByText(name));
  });
}
const text = (id: string) => screen.getByTestId(id).textContent;
// What the backend holds for chat A after the drop: the user's question, nothing of the answer.
const savedQuestion = () => (h.details.A = detail("A", [{ role: "user", content: "hi" }]));
const sendDisabled = () => (screen.getByText("send") as HTMLButtonElement).disabled;

// Open A, ask, and let some of the answer stream in.
async function streamingInA() {
  await click("open-A");
  await click("send");
  frame({ type: "meta", conversation_id: "A", seq: 1 });
  frame({ type: "token", text: "Half an " });
  frame({ type: "token", text: "answer" });
}

describe("App: a dropped socket ends the turn locally (sc-376)", () => {
  beforeEach(async () => {
    h.details = { A: detail("A", []), B: detail("B", [{ role: "agent", content: "b-msg" }]) };
    h.getConversation = null;
    h.sent = 0;
    render(<App />);
    await status(true);
  });
  afterEach(cleanup);

  it("send, socket close, composer enabled again with the partial text and a note", async () => {
    await streamingInA();
    expect(sendDisabled()).toBe(true);
    await status(false);
    await status(true);
    expect(sendDisabled()).toBe(false);
    expect(text("error")).toBe(NOTE);
  });

  it("keeps the partial text as one agent message while the backend has nothing saved", async () => {
    await streamingInA();
    await status(false);
    expect(text("messages")).toBe("user:hi|agent:Half an answer");
    h.details.A = detail("A", [{ role: "user", content: "hi" }]); // restart: nothing was saved
    await status(true);
    expect(text("messages")).toBe("user:hi|agent:Half an answer");
    expect(text("error")).toBe(NOTE);
  });

  it("the reload replaces the local copy with the saved partial answer", async () => {
    await streamingInA();
    await status(false);
    h.details.A = detail("A", [
      { role: "user", content: "hi" },
      { role: "agent", content: "Half an answer, saved", status: "partial" },
    ]);
    await status(true);
    expect(text("messages")).toBe("user:hi|agent:Half an answer, saved");
  });

  it("(1) a close while not streaming changes nothing and reloads nothing", async () => {
    await click("open-A");
    const { getConversation } = await import("./api/restClient");
    const calls = vi.mocked(getConversation).mock.calls.length;
    await status(false);
    await status(true);
    expect(text("error")).toBe("");
    expect(vi.mocked(getConversation).mock.calls.length).toBe(calls);
  });

  it("(2) switching chat before the reconnect reloads nothing and keeps the other chat", async () => {
    await streamingInA();
    await status(false);
    await click("open-B");
    const { getConversation } = await import("./api/restClient");
    const calls = vi.mocked(getConversation).mock.calls.length;
    await status(true);
    expect(vi.mocked(getConversation).mock.calls.length).toBe(calls);
    expect(text("messages")).toBe("agent:b-msg");
  });

  it("(3) flapping closes give one note and one reload", async () => {
    await streamingInA();
    await status(false);
    await status(false);
    await status(false);
    savedQuestion();
    const { getConversation } = await import("./api/restClient");
    const calls = vi.mocked(getConversation).mock.calls.length;
    await status(true);
    await status(true);
    expect(vi.mocked(getConversation).mock.calls.length).toBe(calls + 1);
    expect(text("messages")).toBe("user:hi|agent:Half an answer");
  });

  it("(4) stray frames after the local end neither re-lock the composer nor duplicate the message", async () => {
    await streamingInA();
    await status(false);
    savedQuestion();
    await status(true);
    frame({ type: "token", text: " late" });
    frame({ type: "done", message_id: "m1" });
    expect(sendDisabled()).toBe(false);
    expect(text("messages")).toBe("user:hi|agent:Half an answer");
    expect(text("error")).toBe(NOTE);
  });

  it("an error frame while idle shows its text and leaves the messages alone", async () => {
    await click("open-B");
    frame({ type: "error", code: "unauthorized", message: "Session expired" });
    expect(text("error")).toBe("Session expired");
    expect(text("messages")).toBe("agent:b-msg");
    expect(sendDisabled()).toBe(false);
  });

  it("(5) a tool in progress stops casting, and a pending proposal is not lost", async () => {
    await streamingInA();
    frame({ type: "tool_start", name: "get_report_fights" });
    frame({
      type: "proposal",
      proposal: { id: "P", conversation_id: "A", items: [] } as unknown as ProfileProposal,
    });
    expect(text("cards")).toBe("get_report_fights:casting");
    await status(false);
    expect(text("cards")).toBe("");
    expect(text("loose")).toBe("P");
  });

  it("(6) a failed reload keeps the partial and the note, and the next open retries", async () => {
    await streamingInA();
    await status(false);
    h.getConversation = async () => {
      throw new Error("backend down");
    };
    await status(true);
    expect(text("messages")).toBe("user:hi|agent:Half an answer");
    expect(text("error")).toBe(NOTE);
    await status(false);
    h.getConversation = null;
    h.details.A = detail("A", [
      { role: "user", content: "hi" },
      { role: "agent", content: "saved" },
    ]);
    await status(true);
    expect(text("messages")).toBe("user:hi|agent:saved");
  });

  it("a reload that lands after the user started a new turn is dropped", async () => {
    await streamingInA();
    await status(false);
    let release: (v: unknown) => void = () => {};
    h.getConversation = () => new Promise((r) => (release = r));
    await status(true);
    await click("send");
    frame({ type: "done", message_id: "m2" }); // the new turn is already over when the reload lands
    await act(async () => release(detail("A", [{ role: "user", content: "old" }])));
    expect(text("messages")).toBe("user:hi|agent:Half an answer|user:hi|agent:(no response)");
  });

  it("(7) the streamed text becomes a message exactly once", async () => {
    await streamingInA();
    await status(false);
    savedQuestion();
    await status(true);
    const parts = text("messages")!.split("|");
    expect(parts.filter((p) => p === "agent:Half an answer").length).toBe(1);
  });

  it("a drop before any token ends the turn with the note and no empty message", async () => {
    await click("open-A");
    await click("send");
    await status(false);
    expect(text("messages")).toBe("user:hi");
    expect(text("error")).toBe(NOTE);
  });

  // Mid-turn the player opens chat B; the turn keeps streaming in A.
  async function switchedToBMidTurn() {
    await streamingInA();
    await click("open-B");
    expect(text("messages")).toBe("agent:b-msg");
  }

  it("a drop after switching chat mid-turn leaves the other chat untouched", async () => {
    await switchedToBMidTurn();
    await status(false);
    await status(true);
    expect(text("messages")).toBe("agent:b-msg");
    expect(sendDisabled()).toBe(false);
  });

  it("a finished answer after switching chat mid-turn is not appended to the other chat", async () => {
    await switchedToBMidTurn();
    frame({ type: "done", message_id: "m1" });
    expect(text("messages")).toBe("agent:b-msg");
    expect(sendDisabled()).toBe(false);
    // Reopened, chat A shows the answer from the backend.
    h.details.A = detail("A", [
      { role: "user", content: "hi" },
      { role: "agent", content: "Half an answer" },
    ]);
    await click("open-A");
    expect(text("messages")).toBe("user:hi|agent:Half an answer");
  });

  it("a drop kept after a failed reload is not replayed after a newer turn", async () => {
    await streamingInA();
    await status(false);
    h.getConversation = async () => {
      throw new Error("backend down");
    };
    await status(true); // the reload fails: the drop is kept for a retry
    h.getConversation = null;
    await click("send"); // a newer turn
    frame({ type: "meta", conversation_id: "A", seq: 3 });
    frame({ type: "error", code: "rate_limited", message: "slow down" }); // nothing saved
    h.details.A = detail("A", [
      { role: "user", content: "hi" },
      { role: "user", content: "hi" },
    ]);
    await status(false);
    await status(true);
    expect(text("messages")).toBe("user:hi|agent:Half an answer|user:hi");
  });

  it("a drop kept after a failed reload is not replayed after the chat is reopened", async () => {
    await streamingInA();
    await status(false);
    h.getConversation = async () => {
      throw new Error("backend down");
    };
    await status(true);
    h.getConversation = null;
    savedQuestion();
    await click("open-B");
    await click("open-A");
    await status(false);
    await status(true);
    expect(text("messages")).toBe("user:hi");
  });

  it("a reload that fails after a newer turn began does not keep the drop", async () => {
    await streamingInA();
    await status(false);
    let fail: (e: unknown) => void = () => {};
    h.getConversation = () => new Promise((_, reject) => (fail = reject));
    await status(true);
    await click("send"); // a newer turn while the reload is still in flight
    frame({ type: "meta", conversation_id: "A", seq: 3 });
    frame({ type: "error", code: "rate_limited", message: "slow down" });
    await act(async () => fail(new Error("backend down")));
    h.getConversation = null;
    h.details.A = detail("A", [
      { role: "user", content: "hi" },
      { role: "user", content: "hi" },
    ]);
    await status(false);
    await status(true);
    expect(text("messages")).toBe("user:hi|agent:Half an answer|user:hi");
  });
});
