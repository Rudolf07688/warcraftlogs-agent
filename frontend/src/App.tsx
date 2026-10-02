import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteConversation,
  downloadMessageReport,
  downloadReport,
  getConversation,
  getGreeting,
  getModels,
  getRaids,
  investigateRaid,
  listConversations,
} from "./api/restClient";
import { ChatSocket, type Frame } from "./api/wsClient";
import { Ambient } from "./components/Ambient";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { ModelSelect } from "./components/ModelSelect";
import { ProfilePanel } from "./components/ProfilePanel";
import { Sidebar } from "./components/Sidebar";
import { THINKING_DEFAULT, toolLabel } from "./toolLabels";
import type {
  ChartArtifact,
  Conversation,
  Encounter,
  Message,
  Raid,
  SpellCardState,
} from "./types";
import { clampSidebarWidth, getSidebarWidth, setSidebarWidth } from "./uiPrefs";

export default function App() {
  const [models, setModels] = useState<string[]>([]);
  const [modelsDegraded, setModelsDegraded] = useState(false);
  const [model, setModel] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [raids, setRaids] = useState<Raid[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [status, setStatus] = useState(THINKING_DEFAULT);
  const [error, setError] = useState<string | null>(null);

  // US6: live spellcasting cards for the in-flight turn.
  const [streamCards, setStreamCards] = useState<SpellCardState[]>([]);
  // US4: the boss ids the user has ticked on the latest sourcing turn (reset per turn).
  const [selectedBosses, setSelectedBosses] = useState<number[]>([]);

  // Refs to avoid stale closures inside the socket frame handler.
  const socketRef = useRef<ChatSocket | null>(null);
  const activeIdRef = useRef<string | null>(null);
  const streamRef = useRef("");
  const modelRef = useRef("");
  const groundedRef = useRef(false);
  const suggestionsRef = useRef<string[]>([]);
  const streamCardsRef = useRef<SpellCardState[]>([]);
  const pendingEncountersRef = useRef<Encounter[]>([]); // bosses surfaced this turn
  const pendingArtifactsRef = useRef<ChartArtifact[]>([]); // charts produced this turn
  const activeEncountersRef = useRef<Encounter[]>([]); // bosses shown by the live picker
  const selectedBossesRef = useRef<number[]>([]);
  const greetingReqId = useRef(0); // invalidates a late greeting if a turn/chat starts first

  // Keep refs in sync for use inside imperative handlers.
  useEffect(() => {
    selectedBossesRef.current = selectedBosses;
  }, [selectedBosses]);

  const setCards = useCallback((next: SpellCardState[]) => {
    streamCardsRef.current = next;
    setStreamCards(next);
  }, []);

  const refreshConversations = useCallback(async () => {
    const { conversations } = await listConversations();
    setConversations(conversations);
  }, []);

  const refreshRaids = useCallback(async () => {
    const { raids } = await getRaids();
    setRaids(raids);
  }, []);

  const handleFrame = useCallback(
    (f: Frame) => {
      switch (f.type) {
        case "meta":
          if (!activeIdRef.current) {
            activeIdRef.current = f.conversation_id;
            setActiveId(f.conversation_id);
          }
          break;
        case "tool_start": {
          setStatus(toolLabel(f.name));
          // US6: spawn a casting spell card (correlated to tool_end by name + FIFO order,
          // since the frames carry no call id).
          const key = `${f.name}-${streamCardsRef.current.length}`;
          setCards([
            ...streamCardsRef.current,
            { key, name: f.name, status: "casting", reportCode: f.report_code },
          ]);
          break;
        }
        case "tool_end": {
          // US6: resolve the oldest still-casting card for this tool.
          const cards = streamCardsRef.current;
          const idx = cards.findIndex((c) => c.status === "casting" && c.name === f.name);
          if (idx >= 0) {
            const next = cards.slice();
            next[idx] = {
              ...next[idx],
              status: f.ok ? "resolved" : "fizzled",
              summary: f.summary,
              ms: f.ms,
            };
            setCards(next);
          }
          break;
        }
        case "grounding":
          if (f.used) {
            groundedRef.current = true;
            setStatus("Searching the web…");
          }
          break;
        case "raid_tracked":
          void refreshRaids();
          break;
        case "encounters": {
          // US4: accumulate distinct bosses surfaced this turn (dedup by id).
          const merged = [...pendingEncountersRef.current];
          for (const e of f.encounters) {
            if (!merged.some((m) => m.encounter_id === e.encounter_id)) merged.push(e);
          }
          pendingEncountersRef.current = merged;
          break;
        }
        case "artifact":
          // US2: accumulate per-turn charts; attached to the agent message on `done`
          // (mirrors the encounters flow — no partial chart renders mid-stream).
          pendingArtifactsRef.current = [
            ...pendingArtifactsRef.current,
            {
              artifact_id: f.artifact_id,
              kind: f.kind,
              title: f.title,
              figure: f.figure,
            },
          ];
          break;
        case "token":
          streamRef.current += f.text;
          setStreamText(streamRef.current);
          break;
        case "suggestions":
          // US1: arrives just before `done`; attached to the agent message there.
          suggestionsRef.current = f.suggestions.slice(0, 3);
          break;
        case "done": {
          const text = streamRef.current || "(no response)";
          const grounded = groundedRef.current;
          const suggestions = suggestionsRef.current;
          const tools = streamCardsRef.current;
          const encounters = pendingEncountersRef.current;
          const artifacts = pendingArtifactsRef.current;
          activeEncountersRef.current = encounters; // the live picker tracks this turn's bosses
          setMessages((m) => [
            ...m,
            {
              id: f.message_id,
              role: "agent",
              content: text,
              grounded,
              suggestions,
              tools,
              encounters,
              artifacts,
            },
          ]);
          setStreaming(false);
          setStreamText("");
          setStatus(THINKING_DEFAULT);
          streamRef.current = "";
          groundedRef.current = false;
          suggestionsRef.current = [];
          setCards([]);
          pendingEncountersRef.current = [];
          pendingArtifactsRef.current = [];
          setSelectedBosses([]); // fresh picker, no stale selection (FR-020)
          void refreshConversations();
          void refreshRaids();
          break;
        }
        case "error":
          setError(f.message);
          setStreaming(false);
          setStreamText("");
          setStatus(THINKING_DEFAULT);
          streamRef.current = "";
          groundedRef.current = false;
          suggestionsRef.current = [];
          setCards([]);
          pendingEncountersRef.current = [];
          pendingArtifactsRef.current = [];
          break;
      }
    },
    [refreshConversations, refreshRaids, setCards],
  );

  // Keep a ref of the selected model so imperative sends never read a stale value.
  useEffect(() => {
    modelRef.current = model;
  }, [model]);

  // US5: restore the persisted sidebar width on load, then drag to resize.
  const applySidebarWidth = useCallback((px: number): number => {
    const w = clampSidebarWidth(px);
    document.documentElement.style.setProperty("--sidebar-width", `${w}px`);
    return w;
  }, []);

  useEffect(() => {
    applySidebarWidth(getSidebarWidth());
  }, [applySidebarWidth]);

  const startResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const onMove = (ev: MouseEvent) => applySidebarWidth(ev.clientX);
      const onUp = (ev: MouseEvent) => {
        setSidebarWidth(applySidebarWidth(ev.clientX));
        document.body.classList.remove("resizing");
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      document.body.classList.add("resizing");
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [applySidebarWidth],
  );

  // Initial load + socket lifecycle.
  useEffect(() => {
    getModels()
      .then((r) => {
        setModels(r.models);
        setModelsDegraded(!!r.degraded);
        setModel((cur) => cur || r.default);
      })
      .catch(() => setError("Could not load models (is the backend up?)"));
    void refreshConversations();
    void refreshRaids();

    const socket = new ChatSocket(handleFrame, setConnected);
    socketRef.current = socket;
    socket.connect();
    return () => socket.close();
  }, [handleFrame, refreshConversations, refreshRaids]);

  async function selectConversation(id: string) {
    greetingReqId.current++; // a late greeting must not land in another chat
    const detail = await getConversation(id);
    activeIdRef.current = id;
    setActiveId(id);
    setMessages(detail.messages.map((m) => ({ ...m })));
    setModel(detail.model);
    setError(null);
    setSelectedBosses([]);
    activeEncountersRef.current = [];
  }

  // US5: open a clean chat and (best-effort) inject a warm Barnaby greeting, unless
  // the user starts typing/sends or switches chats first (then a late greeting is ignored).
  function newChat() {
    activeIdRef.current = null;
    setActiveId(null);
    setMessages([]);
    setError(null);
    setCards([]);
    setSelectedBosses([]);
    activeEncountersRef.current = [];
    pendingEncountersRef.current = [];
    pendingArtifactsRef.current = [];

    const reqId = ++greetingReqId.current;
    getGreeting()
      .then(({ greeting }) => {
        if (!greeting || greetingReqId.current !== reqId) return;
        // Only inject into a still-empty new chat (the hidden kickoff is never shown).
        setMessages((m) => (m.length === 0 ? [{ role: "agent", content: greeting }] : m));
      })
      .catch(() => {
        /* no greeting — a clean chat is fine */
      });
  }

  async function removeConversation(id: string) {
    await deleteConversation(id);
    if (id === activeIdRef.current) newChat();
    await refreshConversations();
  }

  function sendText(
    text: string,
    opts?: { conversationId?: string | null; model?: string },
  ): boolean {
    if (streaming) return false;
    greetingReqId.current++; // a real turn started — drop any in-flight greeting
    const useModel = opts?.model ?? modelRef.current;
    const convId =
      opts && "conversationId" in opts ? opts.conversationId ?? null : activeIdRef.current;
    setError(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    streamRef.current = "";
    groundedRef.current = false;
    suggestionsRef.current = [];
    setCards([]);
    pendingEncountersRef.current = [];
    pendingArtifactsRef.current = [];
    setStreamText("");
    setStatus(THINKING_DEFAULT);
    setStreaming(true);
    const ok = socketRef.current?.send({
      conversation_id: convId,
      model: useModel,
      content: text,
    });
    if (!ok) {
      setStreaming(false);
      setError("Not connected to the server. Retrying…");
    }
    return !!ok;
  }

  // US4: fold the ticked bosses into the next message text (visible), then clear the
  // selection so it never reapplies to a later turn (FR-020).
  function composeWithFocus(text: string): string {
    const ids = selectedBossesRef.current;
    const encs = activeEncountersRef.current;
    if (!ids.length || !encs.length) return text;
    const names = encs.filter((e) => ids.includes(e.encounter_id)).map((e) => e.name);
    return names.length ? `${text}\n\n(Focus on: ${names.join(", ")})` : text;
  }

  function send(text: string) {
    const ok = sendText(composeWithFocus(text));
    if (ok) setSelectedBosses([]);
  }

  async function handleDownloadPdf() {
    if (!activeId) return;
    try {
      await downloadReport(activeId);
    } catch {
      setError("Could not generate the PDF report.");
    }
  }

  // US5: export a single agent reply (its question + its charts) as a PDF.
  async function handleDownloadMessage(messageId: string) {
    if (!activeIdRef.current) return;
    try {
      await downloadMessageReport(activeIdRef.current, messageId);
    } catch {
      setError("Could not generate the per-message PDF report.");
    }
  }

  // One-click raid investigation (US1): the server creates an empty conversation
  // and owns the kickoff wording; we send it as a normal first turn.
  async function handleInvestigateRaid(reportCode: string) {
    if (streaming) return;
    setError(null);
    try {
      const resp = await investigateRaid(reportCode, modelRef.current || undefined);
      activeIdRef.current = resp.conversation_id;
      setActiveId(resp.conversation_id);
      setMessages([]);
      setModel(resp.model);
      modelRef.current = resp.model;
      sendText(resp.kickoff_prompt, {
        conversationId: resp.conversation_id,
        model: resp.model,
      });
    } catch {
      setError("Could not start the investigation. Is the backend up?");
    }
  }

  return (
    <div className="app">
      <Ambient />
      <Sidebar
        conversations={conversations}
        raids={raids}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={newChat}
        onDelete={removeConversation}
        onInvestigateRaid={handleInvestigateRaid}
        onOpenProfile={() => setProfileOpen(true)}
      />
      <ProfilePanel open={profileOpen} onClose={() => setProfileOpen(false)} />
      <div
        className="resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        onMouseDown={startResize}
      />
      <main className="chat">
        <header className="chat-header">
          <span className="app-title">WCL Agent Chat</span>
          <ModelSelect
            models={models}
            value={model}
            onChange={setModel}
            disabled={streaming}
            degraded={modelsDegraded}
          />
          {activeId && messages.length > 0 && (
            <button
              className="download-pdf"
              onClick={handleDownloadPdf}
              disabled={streaming}
              title="Download this conversation as a PDF report"
            >
              ⬇ PDF
            </button>
          )}
          <span className={`conn ${connected ? "online" : "offline"}`}>
            {connected ? "● connected" : "● disconnected"}
          </span>
        </header>
        <MessageList
          messages={messages}
          streamingText={streamText}
          streaming={streaming}
          status={status}
          error={error}
          streamCards={streamCards}
          selectedBosses={selectedBosses}
          onSelectBosses={setSelectedBosses}
          onPickSuggestion={send}
          onDownloadMessage={handleDownloadMessage}
        />
        <Composer disabled={streaming || !connected} onSend={send} />
        <div className="attribution">
          Icons by{" "}
          <a href="https://game-icons.net" target="_blank" rel="noopener noreferrer">
            game-icons.net
          </a>{" "}
          contributors, CC BY 3.0
        </div>
      </main>
    </div>
  );
}
