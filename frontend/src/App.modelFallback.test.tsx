import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import {
  getConversation,
  getGreeting,
  getModels,
  getRaids,
  getRecentRaids,
  listConversations,
} from "./api/restClient";
import type { ChatTurn } from "./api/wsClient";
import type { AuthState } from "./auth/useAuth";
import type { Conversation } from "./types";

// Feature 032 (D9, sc-249 AC 6): after a provider switch the browser never sends a model id
// that /api/models doesn't serve. The picker's selection and a reopened chat's stored model
// both fall back to the served default. App.tsx is exercised as-is (owned by feature 034).

const sent: ChatTurn[] = [];

vi.mock("./api/wsClient", () => ({
  ChatSocket: class {
    private onConnection: (up: boolean) => void;
    constructor(_onFrame: unknown, onConnection: (up: boolean) => void) {
      this.onConnection = onConnection;
    }
    connect() {
      this.onConnection(true);
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
}));

const SERVED = { models: ["claude-sonnet-5-5", "claude-haiku-5-5"], default: "claude-sonnet-5-5" };

// A chat created on Vertex before the switch to the Anthropic API.
const OLD_CHAT: Conversation = {
  id: "c-old",
  title: "Hunters on Heroic",
  model: "gemini-3.6-flash",
  created_at: "2026-10-30T10:00:00Z",
  updated_at: "2026-10-30T10:00:00Z",
  pinned_at: null,
};

// jsdom has no ResizeObserver; the chat's stick-to-bottom scroller needs one.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  sent.length = 0;
  vi.mocked(getModels).mockResolvedValue(SERVED);
  vi.mocked(listConversations).mockResolvedValue({ conversations: [OLD_CHAT] });
  vi.mocked(getConversation).mockResolvedValue({ ...OLD_CHAT, messages: [], proposals: [] });
  vi.mocked(getRaids).mockResolvedValue({ raids: [] });
  vi.mocked(getGreeting).mockResolvedValue({ greeting: "" });
  vi.mocked(getRecentRaids).mockRejectedValue(new Error("not under test"));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

async function renderApp() {
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await waitFor(() => expect(getModels).toHaveBeenCalled());
}

async function sendMessage(text: string) {
  const box = screen.getByLabelText<HTMLTextAreaElement>("Message");
  await waitFor(() => expect(box.disabled).toBe(false));
  fireEvent.change(box, { target: { value: text } });
  await act(async () => {
    fireEvent.keyDown(box, { key: "Enter" });
  });
  await waitFor(() => expect(sent).toHaveLength(1));
}

describe("model fallback after a provider switch", () => {
  it("sends the served default when the picker has no served selection", async () => {
    await renderApp();
    await sendMessage("How are hunters doing?");
    expect(sent[0].model).toBe("claude-sonnet-5-5");
    expect(SERVED.models).toContain(sent[0].model);
  });

  it("continues a chat stored on an unserved model on the served default", async () => {
    await renderApp();
    fireEvent.click(await screen.findByText(OLD_CHAT.title));
    await waitFor(() => expect(getConversation).toHaveBeenCalledWith(OLD_CHAT.id));
    await sendMessage("And on Mythic?");
    expect(sent[0].conversation_id).toBe(OLD_CHAT.id);
    expect(sent[0].model).toBe("claude-sonnet-5-5");
  });
});
