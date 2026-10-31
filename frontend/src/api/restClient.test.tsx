import { afterEach, describe, expect, it, vi } from "vitest";
import { getConversation } from "./restClient";

// sc-213: a chart made in a chat must come back when the chat is reopened. The payload is
// shaped like GET /api/conversations/{id} (backend ConversationDetail, ArtifactOut).

afterEach(() => vi.unstubAllGlobals());

const FIGURE = {
  data: [{ type: "scatter", mode: "lines", name: "DPS", x: [1, 2], y: [10, 20] }],
  layout: { title: { text: "DPS" } },
};

function stub(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })),
  );
}

const base = {
  id: "c1",
  title: "t",
  model: "m",
  pinned: false,
  created_at: "2026-10-31T10:00:00Z",
  updated_at: "2026-10-31T10:00:00Z",
};
const msg = (seq: number, role: string) => ({
  id: `m${seq}`,
  role,
  content: role,
  seq,
  status: "complete",
  created_at: "2026-10-31T10:00:00Z",
});

describe("getConversation: stored charts", () => {
  it("attaches each artifact to the agent message with its message_seq", async () => {
    stub({
      ...base,
      messages: [msg(0, "user"), msg(1, "agent"), msg(2, "user"), msg(3, "agent")],
      artifacts: [
        { id: "a1", message_seq: 1, kind: "line", title: "DPS", figure: FIGURE },
        { id: "a2", message_seq: 3, kind: "bar", title: "Deaths", figure: FIGURE },
        { id: "a3", message_seq: 3, kind: "line", title: "More", figure: FIGURE },
      ],
      proposals: [],
    });
    const { messages } = await getConversation("c1");
    expect(messages[0].artifacts).toBeUndefined();
    expect(messages[1].artifacts?.map((a) => a.artifact_id)).toEqual(["a1"]);
    expect(messages[3].artifacts?.map((a) => a.artifact_id)).toEqual(["a2", "a3"]);
    expect(messages[1].artifacts?.[0].figure).toEqual(FIGURE);
  });

  it("leaves a chart with no message_seq (its turn never finished) off every message", async () => {
    stub({
      ...base,
      messages: [msg(0, "user"), msg(1, "agent")],
      artifacts: [{ id: "a1", message_seq: null, kind: "line", title: "DPS", figure: FIGURE }],
      proposals: [],
    });
    const { messages } = await getConversation("c1");
    expect(messages.every((m) => m.artifacts === undefined)).toBe(true);
  });
});
