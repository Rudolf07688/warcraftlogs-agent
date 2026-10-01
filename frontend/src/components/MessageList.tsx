import { useEffect, useRef } from "react";
import type { Message } from "../types";

interface Props {
  messages: Message[];
  streamingText: string;
  streaming: boolean;
  tools: string[];
  error: string | null;
}

export function MessageList({ messages, streamingText, streaming, tools, error }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  // Keep the latest message in view as content grows.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, streaming, tools, error]);

  return (
    <div className="message-list">
      {messages.map((m, i) => (
        <div key={m.id ?? i} className={`message ${m.role}`}>
          <div className="message-role">{m.role === "user" ? "You" : "Agent"}</div>
          <div className="message-content">{m.content}</div>
        </div>
      ))}

      {streaming && (
        <div className="message agent">
          <div className="message-role">Agent</div>
          {tools.length > 0 && (
            <div className="tool-activity">
              {tools.map((t, i) => (
                <span key={i} className="tool-chip">
                  🔧 {t}
                </span>
              ))}
            </div>
          )}
          <div className="message-content">
            {streamingText || <span className="working">working…</span>}
          </div>
        </div>
      )}

      {error && <div className="message error">⚠️ {error}</div>}

      <div ref={endRef} />
    </div>
  );
}
