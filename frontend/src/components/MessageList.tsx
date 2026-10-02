import { useState } from "react";
import type { Message, SpellCardState } from "../types";
import { StickToBottom } from "use-stick-to-bottom";
import { FollowUps } from "./FollowUps";
import { StreamMarkdown } from "./StreamMarkdown";
import { SpellCard } from "./SpellCard";
import { EncounterPicker } from "./EncounterPicker";

interface Props {
  messages: Message[];
  streamingText: string;
  streaming: boolean;
  status: string;
  error: string | null;
  streamCards: SpellCardState[];
  selectedBosses: number[];
  onSelectBosses: (ids: number[]) => void;
  onPickSuggestion: (text: string) => void;
}

// Persisted tool calls collapse into a one-line disclosure so completed messages stay
// tidy; the live (streaming) spellbook renders expanded so the user can watch the cast.
function Spellbook({ cards, instant }: { cards: SpellCardState[]; instant?: boolean }) {
  const [open, setOpen] = useState(false);
  if (cards.length === 0) return null;

  if (!instant) {
    return (
      <div className="spellbook">
        {cards.map((c) => (
          <SpellCard key={c.key} card={c} />
        ))}
      </div>
    );
  }

  const label = `📖 ${cards.length} ${cards.length === 1 ? "spell" : "spells"} cast`;
  return (
    <div className="spellbook">
      <button
        className="spellbook-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span>{label}</span>
        <span className="spellbook-chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="spellbook-chips">
          {cards.map((c) => (
            <SpellCard key={c.key} card={c} instant />
          ))}
        </div>
      )}
    </div>
  );
}

export function MessageList({
  messages,
  streamingText,
  streaming,
  status,
  error,
  streamCards,
  selectedBosses,
  onSelectBosses,
  onPickSuggestion,
}: Props) {
  return (
    <StickToBottom className="message-list" resize="smooth" initial="smooth">
      {({ isAtBottom, scrollToBottom }) => (
        <>
          <StickToBottom.Content className="message-list-content">
            {messages.map((m, i) => {
              const isLast = i === messages.length - 1;
              return (
                <div
                  key={m.id ?? i}
                  className={`message ${m.role}${
                    m.role === "agent" && isLast && !streaming ? " sheen-once" : ""
                  }`}
                >
                  <div className="message-role">{m.role === "user" ? "You" : "Barnaby"}</div>
                  {/* US6: the resolved "spellbook" of tool calls for this turn. */}
                  {m.role === "agent" && m.tools && <Spellbook cards={m.tools} instant />}
                  {m.role === "agent" ? (
                    <StreamMarkdown content={m.content} />
                  ) : (
                    <div className="message-content">{m.content}</div>
                  )}
                  {m.role === "agent" && m.grounded && (
                    <div className="grounding-note" title="This reply used web search results.">
                      🌐 Used web search
                    </div>
                  )}
                  {m.status === "partial" && (
                    <div
                      className="partial-note"
                      title="This reply was interrupted before it finished."
                    >
                      ⚠️ Interrupted — partial response
                    </div>
                  )}
                  {/* US4: boss focus checkboxes under the latest sourcing turn only. */}
                  {m.role === "agent" &&
                    isLast &&
                    !streaming &&
                    m.encounters &&
                    m.encounters.length > 0 && (
                      <EncounterPicker
                        encounters={m.encounters}
                        selected={selectedBosses}
                        onChange={onSelectBosses}
                      />
                    )}
                  {/* US1: only the latest agent turn shows follow-ups (never stale ones). */}
                  {m.role === "agent" &&
                    isLast &&
                    !streaming &&
                    m.suggestions &&
                    m.suggestions.length > 0 && (
                      <FollowUps
                        suggestions={m.suggestions}
                        disabled={streaming}
                        onPick={onPickSuggestion}
                      />
                    )}
                </div>
              );
            })}

            {streaming && (
              <div className="message agent arcane-border">
                <div className="message-role">Barnaby</div>
                {/* US6: live spellcasting cards for the in-flight turn. */}
                <Spellbook cards={streamCards} />
                {streamingText ? (
                  <StreamMarkdown content={streamingText} streaming />
                ) : (
                  streamCards.length === 0 && (
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
                  )
                )}
              </div>
            )}

            {error && <div className="message error">⚠️ {error}</div>}
          </StickToBottom.Content>

          {!isAtBottom && (
            <button
              className="back-to-bottom"
              onClick={() => scrollToBottom()}
              title="Scroll to the latest message"
            >
              ↓ Back to bottom
            </button>
          )}
        </>
      )}
    </StickToBottom>
  );
}
