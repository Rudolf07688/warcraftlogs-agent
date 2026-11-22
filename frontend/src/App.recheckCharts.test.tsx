import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import type { Frame } from "./api/wsClient";
import type { ChartArtifact } from "./types";

// 088b (PERF-003): the drop rechecks refetch the chat; a chart already on screen is plotted once,
// across rechecks that find nothing new and the one that finds the saved partial. Real
// MessageList and PlotlyArtifact; only Plotly's own component is a counting stub.

const h = vi.hoisted(() => ({
  onFrame: null as ((f: unknown) => void) | null,
  onStatus: null as ((connected: boolean) => void) | null,
  details: {} as Record<string, unknown>,
  plots: 0,
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
  // A fresh copy per fetch, as from the network.
  getConversation: vi.fn(async (id: string) => structuredClone(h.details[id])),
  deleteConversation: vi.fn(),
  downloadMessageReport: vi.fn(),
  downloadReport: vi.fn(),
  investigateRaid: vi.fn(),
  investigateMplusRun: vi.fn(),
  updateConversation: vi.fn(),
}));

vi.mock("./auth/useAuth", () => ({ useAuth: () => ({ identity: null, logout: vi.fn() }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn(), useMatch: () => null }));
vi.mock("./components/Sidebar", () => ({
  Sidebar: (p: { onSelect: (id: string) => void }) => (
    <button onClick={() => p.onSelect("A")}>open-A</button>
  ),
}));
vi.mock("./components/Composer", () => ({
  Composer: (p: { onSend: (t: string) => void }) => <button onClick={() => p.onSend("again")}>send</button>,
}));
vi.mock("./components/WelcomePanel", () => ({ WelcomePanel: () => null }));
vi.mock("./components/Ambient", () => ({ Ambient: () => null }));
vi.mock("./components/ModelSelect", () => ({ ModelSelect: () => null }));
vi.mock("plotly.js-dist-min", () => ({ default: {} }));
vi.mock("react-plotly.js/factory", () => ({
  default: () => () => {
    h.plots++;
    return null;
  },
}));

const CHART: ChartArtifact = {
  artifact_id: "a1",
  kind: "line",
  title: "DPS",
  figure: { data: [{ type: "scatter", x: [1], y: [2] }], layout: {} },
  message_seq: 2,
};
const ASKED = [
  { id: "u1", seq: 1, role: "user", content: "hi", status: "complete" },
  { id: "m1", seq: 2, role: "agent", content: "A chart.", status: "complete", artifacts: [CHART] },
];
const detail = (messages: unknown[]) => ({ id: "A", title: "A", model: "m", messages, proposals: [] });

async function wait(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("App: drop rechecks keep charts (088b)", () => {
  beforeEach(async () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    HTMLElement.prototype.scrollTo = vi.fn() as never;
    h.details = { A: detail(ASKED) };
    h.plots = 0;
    render(<App />);
    await act(async () => h.onStatus?.(true));
  });
  afterEach(() => {
    vi.useRealTimers();
    cleanup();
    vi.unstubAllGlobals();
  });

  it("a chart message renders once across rechecks", async () => {
    await act(async () => {
      fireEvent.click(screen.getByText("open-A"));
    });
    await screen.findByRole("img", { name: "Chart: DPS" });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0)); // the lazy Plot resolves
    });
    const plots = h.plots;
    expect(plots).toBeGreaterThan(0);

    await act(async () => {
      fireEvent.click(screen.getByText("send"));
    });
    act(() => h.onFrame?.({ type: "meta", conversation_id: "A", seq: 3 } satisfies Frame));
    act(() => h.onFrame?.({ type: "token", text: "Half" } satisfies Frame));
    const drop = h.plots;
    await act(async () => h.onStatus?.(false));
    h.details.A = detail([...ASKED, { id: "u2", seq: 3, role: "user", content: "again", status: "complete" }]);
    vi.useFakeTimers();
    await act(async () => h.onStatus?.(true));
    const reloaded = h.plots;
    await wait(2_000 + 4_000 + 8_000); // three rechecks, nothing new
    expect(h.plots).toBe(reloaded);
    h.details.A = detail([
      ...(h.details.A as { messages: unknown[] }).messages,
      { id: "m2", seq: 4, role: "agent", content: "(no response)", status: "partial" },
    ]);
    await wait(16_000); // the saved partial arrives
    expect(screen.getByText("(no response)")).toBeTruthy();
    expect(h.plots).toBe(reloaded);
    // The live turn and the drop re-render the list; the chart is not plotted again by them either.
    expect(reloaded).toBe(drop);
    expect(drop).toBe(plots);
  });
});
