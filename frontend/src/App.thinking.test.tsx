import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import type { Frame } from "./api/wsClient";

// Feature 080 (sc-569, sc-572): the live status line from `thinking` and `interim` frames, with
// the real MessageList, so the guard is checked where it acts: the DOM. Model text is hostile:
// it must render as plain text, capped, and never once the answer is showing.

const h = vi.hoisted(() => ({ onFrame: null as ((f: unknown) => void) | null }));

vi.mock("./api/wsClient", () => ({
  ChatSocket: class {
    constructor(onFrame: (f: unknown) => void, onStatus: (connected: boolean) => void) {
      h.onFrame = onFrame;
      setTimeout(() => onStatus(true), 0);
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
  getConversation: vi.fn(),
  deleteConversation: vi.fn(),
  downloadMessageReport: vi.fn(),
  downloadReport: vi.fn(),
  investigateRaid: vi.fn(),
  investigateMplusRun: vi.fn(),
  updateConversation: vi.fn(),
}));

vi.mock("./auth/useAuth", () => ({ useAuth: () => ({ identity: null, logout: vi.fn() }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn(), useMatch: () => null }));
vi.mock("./components/Sidebar", () => ({ Sidebar: () => null }));
vi.mock("./components/Composer", () => ({
  Composer: (p: { onSend: (t: string) => void }) => <button onClick={() => p.onSend("hi")}>send</button>,
}));
vi.mock("./components/WelcomePanel", () => ({ WelcomePanel: () => null }));
vi.mock("./components/Ambient", () => ({ Ambient: () => null }));
vi.mock("./components/ModelSelect", () => ({ ModelSelect: () => null }));
vi.mock("plotly.js-dist-min", () => ({ default: {} }));
vi.mock("react-plotly.js/factory", () => ({ default: () => () => null }));

function frame(f: Frame) {
  act(() => h.onFrame?.(f));
}
const live = () => document.querySelector(".message.agent.arcane-border");
const statusLine = () => document.querySelector(".thinking-status")?.textContent ?? null;
const indicator = () => document.querySelector(".thinking-text")?.textContent ?? null;

async function askWithACard() {
  await act(async () => {
    fireEvent.click(screen.getByText("send"));
  });
  frame({ type: "meta", conversation_id: "c1", seq: 1 });
  frame({ type: "tool_start", name: "get_report_fights" });
  frame({ type: "tool_end", name: "get_report_fights", ok: true });
}

describe("App: live thinking status (080)", () => {
  beforeEach(async () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    HTMLElement.prototype.scrollTo = vi.fn() as never; // jsdom lacks it; the answer scrolls into view
    render(<App />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it.each([
    "<img src=x onerror=alert(1)>",
    "[x](javascript:alert(1))",
    "**bold**",
    "```js\nalert(1)\n```",
  ])("renders hostile thought text inert, as plain text: %s", async (text) => {
    await askWithACard();
    frame({ type: "thinking", text });
    expect(statusLine()).toBe(text);
    const node = live()!;
    expect(node.querySelector("img, a, strong, code, pre, script")).toBeNull();
  });

  it("caps a long status line", async () => {
    await askWithACard();
    frame({ type: "thinking", text: "z".repeat(10_000) });
    expect(statusLine()?.length).toBe(120);
  });

  it("shows the thought before any card in the indicator", async () => {
    await act(async () => {
      fireEvent.click(screen.getByText("send"));
    });
    frame({ type: "thinking", text: "Reading the fight." });
    expect(indicator()).toBe("Reading the fight.");
  });

  it("hides the status once the answer starts and ignores a late thought", async () => {
    await askWithACard();
    frame({ type: "thinking", text: "Comparing the pulls." });
    frame({ type: "token", text: "Vagxsu topped damage." });
    expect(statusLine()).toBeNull();
    frame({ type: "thinking", text: "A late thought." });
    expect(statusLine()).toBeNull();
    expect(live()?.textContent).not.toContain("A late thought.");
  });

  it("turns interim text into status and keeps only the final answer", async () => {
    await act(async () => {
      fireEvent.click(screen.getByText("send"));
    });
    frame({ type: "meta", conversation_id: "c1", seq: 1 });
    frame({ type: "token", text: "WCL errors on report aB3xY9. I'll retry." });
    frame({ type: "interim", text: "WCL errors on report aB3xY9." });
    frame({ type: "tool_start", name: "get_report_participants" });
    expect(statusLine()).toBe("WCL errors on report aB3xY9.");
    expect(live()?.textContent).not.toContain("I'll retry");
    frame({ type: "tool_end", name: "get_report_participants", ok: false });
    frame({ type: "token", text: "Her deaths came from Gravebound." });
    frame({ type: "done", message_id: "a1" });
    const answers = [...document.querySelectorAll(".message.agent")].map((m) => m.textContent ?? "");
    expect(answers.some((t) => t.includes("Her deaths came from Gravebound."))).toBe(true);
    expect(answers.some((t) => t.includes("aB3xY9") || t.includes("retry"))).toBe(false);
    expect(statusLine()).toBeNull();
  });

  it("says Thinking… with seconds after 3 s without events while no tool casts", async () => {
    vi.useFakeTimers();
    await askWithACard();
    expect(statusLine()).toBeNull();
    act(() => vi.advanceTimersByTime(2000));
    expect(statusLine()).toBeNull();
    act(() => vi.advanceTimersByTime(2000));
    expect(statusLine()).toBe("Thinking… 4s");
    frame({ type: "thinking", text: "Comparing the pulls." });
    expect(statusLine()).toBe("Comparing the pulls.");
  });

  it("shows no generic line while a tool is casting", async () => {
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByText("send"));
    });
    frame({ type: "tool_start", name: "get_report_fights" });
    act(() => vi.advanceTimersByTime(10_000));
    expect(statusLine()).toBeNull();
  });
});
