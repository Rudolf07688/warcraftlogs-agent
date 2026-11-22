import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import type { Message, ProfileProposal, SpellCardState } from "../types";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import { FollowUps } from "./FollowUps";
import { StreamMarkdown } from "./StreamMarkdown";
import { SpellCard } from "./SpellCard";
import { EncounterPicker } from "./EncounterPicker";
import { PlotlyArtifact } from "./PlotlyArtifact";
import { ProposalCard } from "./ProposalCard";
import { useStreamText } from "../lib/streamStore";
import { useTurnStatus } from "../lib/statusStore";
import { firstTokenRendered } from "../telemetry/chatEvents";
import { THINKING_DEFAULT, thinkingElapsedLabel } from "../toolLabels";

interface Props {
  messages: Message[];
  streaming: boolean;
  error: string | null;
  streamCards: SpellCardState[];
  selectedBosses: number[];
  onSelectBosses: (ids: number[]) => void;
  onPickSuggestion: (text: string) => void;
  onDownloadMessage: (messageId: string) => void;
  /** Feature 031: proposals not linked to a message (their turn never finished). */
  looseProposals: ProfileProposal[];
  /** Feature 031: append the line a confirmation card's decision saved. */
  onFollowUp: (conversationId: string, message: Message) => void;
  /** Rendered after the messages (feature 013: the welcome panel in a new chat). */
  footer?: ReactNode;
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

// Feature 080: after this long without any turn event, while no tool is casting and no thought
// line is showing, the status says "Thinking… Ns".
const GENERIC_AFTER_S = 3;

// Whole seconds since `since`, ticking once a second while `active`. Only the status re-renders.
function useQuietSeconds(since: number | undefined, active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [since, active]);
  return since === undefined ? 0 : Math.max(0, Math.floor((now - since) / 1000));
}

// Feature 080 (sc-569, sc-572): what the turn is doing while no answer text is showing. Before
// any tool card: the animated indicator; under the cards: one transient line, which also shows a
// model retry/fallback notice (085). Model text is rendered as a text node only, never as
// markdown or HTML, isolated from the surrounding text direction (dir="auto"). It reads the live
// status from `statusStore` (085), so a status change re-renders this alone.
function TurnStatus({ cards }: { cards: SpellCardState[] }) {
  const { status, thought, notice, quietSince } = useTurnStatus();
  const casting = cards.some((c) => c.status === "casting");
  const quiet = useQuietSeconds(quietSince, !thought && !casting);
  const generic =
    !thought && !casting && quiet >= GENERIC_AFTER_S ? thinkingElapsedLabel(quiet) : null;
  if (cards.length === 0) {
    const label = thought ?? (status === THINKING_DEFAULT && generic ? generic : status);
    const key = thought ? `t:${thought}` : generic && status === THINKING_DEFAULT ? "generic" : status;
    return (
      <div className="thinking" aria-label={label}>
        <span key={key} className="thinking-text" dir="auto">
          {label}
        </span>
        <span className="thinking-dots">
          <i />
          <i />
          <i />
        </span>
      </div>
    );
  }
  const line = thought ?? notice ?? generic;
  return line ? (
    <div key={thought ?? notice ?? "generic"} className="thinking-status" dir="auto">
      {line}
    </div>
  ) : null;
}

// PERF-010: the in-flight reply. It is the only component that subscribes to the token
// stream, so a token re-renders this message alone, not the list or the app.
function LiveMessage({ streamCards }: { streamCards: SpellCardState[] }) {
  const streamingText = useStreamText();
  const hasText = streamingText !== "";
  // Feature 060: client-side TTFT, after the first token was committed to the screen.
  useEffect(() => {
    if (hasText) firstTokenRendered();
  }, [hasText]);
  return (
    <div className="message agent arcane-border">
      <div className="message-role">Barnaby</div>
      {/* US6: live spellcasting cards for the in-flight turn. */}
      <Spellbook cards={streamCards} />
      {streamingText ? (
        <StreamMarkdown content={streamingText} streaming />
      ) : (
        <TurnStatus cards={streamCards} />
      )}
    </div>
  );
}

// sc-140: when a streamed answer completes, bring the top of the question that produced it
// to the top of the view, so the reader starts at the beginning. The rule: only when the
// reader was following the stream (stuck to the bottom when it last rendered while streaming),
// and only on the streaming -> done transition with an agent reply last. Reopening a chat,
// follow-up suggestions, a failed turn (a user message is still last) and a reader who
// scrolled away all leave the view alone.
// Releasing the stick-to-bottom lock to do that must not outlive the answer (BUG-006): when
// the next turn starts we re-engage it, so that turn is followed like any other. A reader who
// scrolled away on their own, not through us, is left where they are.
function ScrollToQuestion({ streaming, answered }: { streaming: boolean; answered: boolean }) {
  const { scrollRef, stopScroll, scrollToBottom, isAtBottom } = useStickToBottomContext();
  const following = useRef(true);
  const released = useRef(false); // we released the lock for the last answer
  const wasStreaming = useRef(streaming);

  useEffect(() => {
    if (streaming) following.current = isAtBottom;
  }, [streaming, isAtBottom]);

  useEffect(() => {
    const started = !wasStreaming.current && streaming;
    const finished = wasStreaming.current && !streaming;
    wasStreaming.current = streaming;
    if (started && released.current) {
      released.current = false;
      following.current = true;
      void scrollToBottom();
      return;
    }
    const view = scrollRef.current;
    if (!finished || !answered || !following.current || !view) return;
    const questions = view.querySelectorAll<HTMLElement>(".message.user");
    const question = questions[questions.length - 1];
    if (!question) return;
    // Release the stick-to-bottom lock, or it would snap straight back to the bottom.
    stopScroll();
    released.current = true;
    const top = question.getBoundingClientRect().top - view.getBoundingClientRect().top;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    view.scrollTo({
      top: Math.max(view.scrollTop + top - 8, 0),
      behavior: reduced ? "auto" : "smooth",
    });
  }, [streaming, answered, scrollRef, stopScroll, scrollToBottom]);

  return null;
}

function MessageListImpl({
  messages,
  streaming,
  error,
  streamCards,
  selectedBosses,
  onSelectBosses,
  onPickSuggestion,
  onDownloadMessage,
  looseProposals,
  onFollowUp,
  footer,
}: Props) {
  return (
    <StickToBottom className="message-list" resize="smooth" initial="smooth">
      {({ isAtBottom, scrollToBottom }) => (
        <>
          <ScrollToQuestion
            streaming={streaming}
            answered={messages[messages.length - 1]?.role === "agent"}
          />
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
                  {/* US2: interactive charts the agent produced this turn. */}
                  {m.role === "agent" &&
                    m.artifacts?.map((a) => (
                      <PlotlyArtifact key={a.artifact_id} artifact={a} />
                    ))}
                  {/* Feature 031: confirmation cards for the profile changes proposed this turn. */}
                  {m.role === "agent" &&
                    m.proposals?.map((p) => (
                      <ProposalCard key={p.id} proposal={p} onFollowUp={onFollowUp} />
                    ))}
                  {/* US5: export just this reply (its question + its charts) as a PDF. */}
                  {m.role === "agent" && m.id && (
                    <button
                      className="message-report-btn"
                      onClick={() => onDownloadMessage(m.id!)}
                      title="Download this reply as a PDF report"
                    >
                      ⬇ Report
                    </button>
                  )}
                  {m.role === "agent" && m.grounded && (
                    <div className="grounding-note" title="This reply used web search results.">
                      🌐 Used web search
                    </div>
                  )}
                  {/* Feature 021: the turn moved to the same-class sibling model. */}
                  {m.role === "agent" && m.fallback && (
                    <div
                      className="grounding-note"
                      title="The chosen model was rate-limited, so its sibling answered."
                    >
                      ⇄ Answered by {m.fallback.to} ({m.fallback.from} was rate-limited)
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

            {/* Feature 031: a proposal whose turn never finished still gets its card. */}
            {looseProposals.map((p) => (
              <div key={p.id} className="message agent">
                <div className="message-role">Barnaby</div>
                <ProposalCard proposal={p} onFollowUp={onFollowUp} />
              </div>
            ))}

            {streaming && (
              <LiveMessage streamCards={streamCards} />
            )}

            {error && <div className="message error">⚠️ {error}</div>}

            {footer}
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

// Re-renders only when its props change: new messages, turn start/end or tool cards, never per
// token (PERF-010) or per status change (085).
export const MessageList = memo(MessageListImpl);
