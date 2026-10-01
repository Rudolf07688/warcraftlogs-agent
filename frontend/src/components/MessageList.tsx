import { useEffect, useRef } from "react";
import type { Message } from "../types";
import { Markdown } from "./Markdown";

interface Props {
  messages: Message[];
  streamingText: string;
  streaming: boolean;
  status: string;
  error: string | null;
}

export function MessageList({ messages, streamingText, streaming, status, error }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  // Only auto-scroll when the user is already near the bottom, so scrolling up to
  // read earlier content isn't interrupted while new tokens stream in.
  function onScroll() {
    const el = containerRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  useEffect(() => {
    const el = containerRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, streamingText, streaming, status, error]);

  return (
    <div className="message-list" ref={containerRef} onScroll={onScroll}>
      {messages.map((m, i) => (
        <div key={m.id ?? i} className={`message ${m.role}`}>
          <div className="message-role">{m.role === "user" ? "You" : "Agent"}</div>
          {m.role === "agent" ? (
            <Markdown content={m.content} />
          ) : (
            <div className="message-content">{m.content}</div>
          )}
        </div>
      ))}

      {streaming && (
        <div className="message agent">
          <div className="message-role">Agent</div>
          {streamingText ? (
            <div className="streaming-body">
              <Markdown content={streamingText} />
              <span className="cursor" />
            </div>
          ) : (
            <div className="thinking" aria-label={status}>
              <span key={status} className="thinking-text">
                {status}
              </span>
              <span className="thinking-dots">
                <i />
                <i />
                <i />
              </span>
            </div>
          )}
        </div>
      )}

      {error && <div className="message error">⚠️ {error}</div>}
    </div>
  );
}
