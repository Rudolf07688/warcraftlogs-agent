import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "./App";
import {
  getConversation,
  getGreeting,
  getModels,
  getRaids,
  getRecentRaids,
  investigateRaid,
  listConversations,
} from "./api/restClient";
import type { ChatTurn } from "./api/wsClient";
import type { AuthState } from "./auth/useAuth";
import type { Raid } from "./types";

// 073: the Raids page lives in the app shell. The sidebar's single Raids entry opens it (it no
// longer starts a chat); "Analyze this raid" reuses the investigate + send flow and leaves it.

const sent: ChatTurn[] = [];
let socketUp = true;

vi.mock("./api/wsClient", () => ({
  ChatSocket: class {
    private onConnection: (up: boolean) => void;
    constructor(_onFrame: unknown, onConnection: (up: boolean) => void) {
      this.onConnection = onConnection;
    }
    connect() {
      this.onConnection(socketUp);
    }
    send(turn: ChatTurn) {
      sent.push(turn);
      return true;
    }
    close() {}
  },
}));

const auth = {
  identity: {
    user_id: "u1",
    email: "owner@example.com",
    is_platform_admin: false,
    active_tenant: null,
    memberships: [],
    csrf_token: "csrf",
  },
  loading: false,
  login: async () => {},
  logout: async () => {},
  refresh: async () => {},
} satisfies AuthState;

vi.mock("./auth/useAuth", () => ({ useAuth: () => auth }));

// The ambient backdrop draws on an OffscreenCanvas, which jsdom lacks; it isn't under test.
vi.mock("./components/Ambient", () => ({ Ambient: () => null }));

vi.mock("./api/restClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/restClient")>()),
  getModels: vi.fn(),
  listConversations: vi.fn(),
  getConversation: vi.fn(),
  getRaids: vi.fn(),
  getGreeting: vi.fn(),
  getRecentRaids: vi.fn(),
  investigateRaid: vi.fn(),
}));

vi.mock("./api/raidSummary", () => ({
  getRaidSummary: vi.fn(async () => ({
    report_code: "x",
    has_data: false,
    duration_ms: null,
    participants: [],
    my_characters: [],
    fetched_at: null,
  })),
}));

const RAIDS: Raid[] = ["RAIDONE", "RAIDTWO"].map((code, i) => ({
  report_code: code,
  label: `Raid ${i + 1}`,
  zone: null,
  guild: null,
  report_started_at: `2026-11-0${i + 1}T19:00:00Z`,
  last_asked_at: "2026-11-06T19:00:00Z",
  first_seen_at: "2026-11-01T19:00:00Z",
  encounters: [],
}));

// jsdom has no ResizeObserver; the chat's stick-to-bottom scroller needs one.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  sent.length = 0;
  socketUp = true;
  vi.mocked(getModels).mockResolvedValue({ models: ["m"], default: "m" });
  vi.mocked(listConversations).mockResolvedValue({ conversations: [] });
  vi.mocked(getConversation).mockResolvedValue({} as never);
  vi.mocked(getRaids).mockResolvedValue({ raids: RAIDS });
  vi.mocked(getGreeting).mockResolvedValue({ greeting: "" });
  vi.mocked(getRecentRaids).mockRejectedValue(new Error("not under test"));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderApp(path = "/app") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <Where />
    </MemoryRouter>,
  );
}

describe("Raids page in the app shell", () => {
  it("the sidebar has one Raids entry with the count; clicking it opens the page, no chat starts", async () => {
    renderApp();
    const entry = await screen.findByRole("button", { name: /Raids\s*2/ });
    fireEvent.click(entry);
    await screen.findAllByRole("tab");
    expect(screen.getByTestId("where").textContent).toBe("/app/raids");
    expect(investigateRaid).not.toHaveBeenCalled();
    expect(sent).toHaveLength(0);
  });

  it("Analyze this raid starts the chat for that raid and leaves the page", async () => {
    vi.mocked(investigateRaid).mockResolvedValue({
      conversation_id: "c1",
      model: "m",
      kickoff_prompt: "Analyze this raid please",
    });
    renderApp("/app/raids/RAIDONE");
    fireEvent.click(await screen.findByRole("button", { name: "Analyze this raid" }));
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/app"));
    expect(vi.mocked(investigateRaid).mock.calls[0][0]).toBe("RAIDONE");
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].conversation_id).toBe("c1");
    expect(sent[0].content).toBe("Analyze this raid please");
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });

  it("Analyze this raid is disabled while the socket is disconnected", async () => {
    socketUp = false;
    renderApp("/app/raids/RAIDONE");
    const btn = (await screen.findByRole("button", { name: "Analyze this raid" })) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(investigateRaid).not.toHaveBeenCalled();
  });

  it("a failed investigation keeps the user on the page with the error shown", async () => {
    vi.mocked(investigateRaid).mockRejectedValue(new Error("down"));
    renderApp("/app/raids/RAIDTWO");
    fireEvent.click(await screen.findByRole("button", { name: "Analyze this raid" }));
    await screen.findByText(/Could not start the investigation/);
    expect(screen.getByTestId("where").textContent).toBe("/app/raids/RAIDTWO");
    expect(sent).toHaveLength(0);
  });

  it("an address naming an untracked raid shows not found", async () => {
    renderApp("/app/raids/..%2Fsecret");
    await screen.findByText(/Raid not found/);
  });
});
