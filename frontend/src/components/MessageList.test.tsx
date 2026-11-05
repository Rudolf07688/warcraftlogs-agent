import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MessageList } from "./MessageList";
import { getConversation } from "../api/restClient";
import { streamStore } from "../lib/streamStore";

// jsdom can't run Plotly's WebGL/canvas code; the chart container is what is under test.
vi.mock("plotly.js-dist-min", () => ({ default: {} }));
vi.mock("react-plotly.js/factory", () => ({ default: () => () => null }));

// sc-213: reopening a chat shows the charts it made. The payload is shaped like
// GET /api/conversations/{id}; it goes through the real getConversation, then the list.

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MessageList: reopened chat", () => {
  it("renders the stored chart under its agent message", async () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    const m = (seq: number, role: string) => ({
      id: `m${seq}`, role, content: role, seq, status: "complete", created_at: "2026-10-31T10:00:00Z",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            id: "c1", title: "t", model: "m", pinned: false,
            created_at: "2026-10-31T10:00:00Z", updated_at: "2026-10-31T10:00:00Z",
            messages: [m(0, "user"), m(1, "agent")],
            artifacts: [
              {
                id: "a1", message_seq: 1, kind: "line", title: "DPS",
                figure: { data: [{ type: "scatter", mode: "lines", x: [1, 2], y: [3, 4] }], layout: {} },
              },
            ],
            proposals: [],
          }),
          { status: 200 },
        ),
      ),
    );

    const detail = await getConversation("c1");
    render(
      <MessageList
        messages={detail.messages}
        streaming={false}
        status=""
        error={null}
        streamCards={[]}
        selectedBosses={[]}
        onSelectBosses={() => {}}
        onPickSuggestion={() => {}}
        onDownloadMessage={() => {}}
        looseProposals={[]}
        onFollowUp={() => {}}
      />,
    );
    await waitFor(() => expect(screen.getAllByRole("img", { name: "Chart: DPS" })).toHaveLength(1));
  });
});

// Feature 060 (sc-416): client-side TTFT fires once the first token is on screen.
const firstToken = vi.hoisted(() => vi.fn());
vi.mock("../telemetry/chatEvents", () => ({ firstTokenRendered: firstToken }));

describe("MessageList: the streaming answer", () => {
  it("reports the first rendered token once, not while only thinking", async () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    const props = {
      messages: [{ role: "user" as const, content: "q" }],
      streaming: true,
      status: "Thinking…",
      error: null,
      streamCards: [],
      selectedBosses: [],
      onSelectBosses: () => {},
      onPickSuggestion: () => {},
      onDownloadMessage: () => {},
      looseProposals: [],
      onFollowUp: () => {},
    };
    render(<MessageList {...props} />);
    expect(firstToken).not.toHaveBeenCalled();
    act(() => streamStore.set("Hel"));
    act(() => streamStore.set("Hello"));
    expect(firstToken).toHaveBeenCalledTimes(1);
    act(() => streamStore.set(""));
  });
});
