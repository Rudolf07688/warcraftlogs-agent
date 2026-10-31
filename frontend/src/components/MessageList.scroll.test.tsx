import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MessageList } from "./MessageList";
import type { Message } from "../types";

// sc-140: scroll to the question when the answer completes. The stick-to-bottom library is
// replaced by a hand-driven context, so "the reader scrolled away" can be set directly.

const ctx = vi.hoisted(() => ({
  escapedFromLock: false,
  isAtBottom: true,
  stopScroll: vi.fn(),
  scrollToBottom: vi.fn(),
  scrollRef: { current: null as HTMLElement | null },
}));

vi.mock("use-stick-to-bottom", async () => {
  const React = await import("react");
  const StickToBottom = ({ children, className }: { children: unknown; className?: string }) =>
    React.createElement(
      "div",
      { className, ref: (el: HTMLElement | null) => (ctx.scrollRef.current = el) },
      (typeof children === "function" ? (children as (c: typeof ctx) => unknown)(ctx) : children) as never,
    );
  StickToBottom.Content = ({ children, className }: { children: unknown; className?: string }) =>
    React.createElement("div", { className }, children as never);
  return { StickToBottom, useStickToBottomContext: () => ctx };
});
vi.mock("./PlotlyArtifact", () => ({ PlotlyArtifact: () => null }));

const scrollTo = vi.fn();
beforeEach(() => {
  ctx.escapedFromLock = false;
  ctx.stopScroll.mockClear();
  scrollTo.mockClear();
  HTMLElement.prototype.scrollTo = scrollTo as never;
});
afterEach(cleanup);

const user = (id: string): Message => ({ id, role: "user", content: `q ${id}` }) as Message;
const agent = (id: string): Message => ({ id, role: "agent", content: `a ${id}` }) as Message;

function props(over: Partial<ComponentProps<typeof MessageList>>): ComponentProps<typeof MessageList> {
  return {
    messages: [],
    streaming: false,
    status: "",
    error: null,
    streamCards: [],
    selectedBosses: [],
    onSelectBosses: () => {},
    onPickSuggestion: () => {},
    onDownloadMessage: () => {},
    looseProposals: [],
    onFollowUp: () => {},
    ...over,
  };
}

const asking = [agent("a0"), user("q1")];
const answered = [agent("a0"), user("q1"), agent("a1")];

describe("MessageList: scroll to the question when the answer completes", () => {
  it("scrolls once, releasing the bottom lock, when a followed stream completes", () => {
    const { rerender } = render(<MessageList {...props({ messages: asking, streaming: true })} />);
    rerender(<MessageList {...props({ messages: answered, streaming: false })} />);
    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(ctx.stopScroll).toHaveBeenCalledTimes(1);
  });

  it("does nothing if the reader scrolled away while it streamed", () => {
    const { rerender } = render(<MessageList {...props({ messages: asking, streaming: true })} />);
    ctx.escapedFromLock = true;
    rerender(<MessageList {...props({ messages: asking, streaming: true, status: "x" })} />);
    rerender(<MessageList {...props({ messages: answered, streaming: false })} />);
    expect(scrollTo).not.toHaveBeenCalled();
    expect(ctx.stopScroll).not.toHaveBeenCalled();
  });

  it("does nothing when a chat is opened or another one is reopened", () => {
    const { rerender } = render(<MessageList {...props({ messages: answered })} />);
    rerender(<MessageList {...props({ messages: [user("b0"), agent("b1")] })} />);
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("does nothing when follow-up suggestions arrive", () => {
    const { rerender } = render(<MessageList {...props({ messages: answered })} />);
    const withSuggestions = answered.map((m, i) =>
      i === 2 ? { ...m, suggestions: ["and the healers?"] } : m,
    );
    rerender(<MessageList {...props({ messages: withSuggestions })} />);
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("does nothing when the turn ends without an answer", () => {
    const { rerender } = render(<MessageList {...props({ messages: asking, streaming: true })} />);
    rerender(<MessageList {...props({ messages: asking, streaming: false, error: "boom" })} />);
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("scrolls again after the next answer, to that answer's question", () => {
    const { rerender } = render(<MessageList {...props({ messages: asking, streaming: true })} />);
    rerender(<MessageList {...props({ messages: answered, streaming: false })} />);
    const next = [...answered, user("q2")];
    rerender(<MessageList {...props({ messages: next, streaming: true })} />);
    rerender(<MessageList {...props({ messages: [...next, agent("a2")], streaming: false })} />);
    expect(scrollTo).toHaveBeenCalledTimes(2);
  });
});
