import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LuPin } from "react-icons/lu";
import { useMatch, useNavigate } from "react-router-dom";
import {
  deleteConversation,
  downloadMessageReport,
  downloadReport,
  getConversation,
  getGreeting,
  getModels,
  getRaids,
  investigateRaid,
  investigateMplusRun,
  listConversations,
  updateConversation,
} from "./api/restClient";
import { ChatSocket, type Frame } from "./api/wsClient";
import { useAuth } from "./auth/useAuth";
import { Ambient } from "./components/Ambient";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { WelcomePanel } from "./components/WelcomePanel";
import { ModelSelect } from "./components/ModelSelect";
import { Sidebar } from "./components/Sidebar";
import { investigateErrorMessage } from "./lib/investigateError";
import { streamStore } from "./lib/streamStore";
import { statusStore, type TurnStatusState } from "./lib/statusStore";
import { Button } from "./components/ui/button";
import { Toggle } from "./components/ui/toggle";
import { fallbackLabel, retryLabel, toolLabel } from "./toolLabels";
import type {
  ChartArtifact,
  Conversation,
  Encounter,
  Message,
  ProfileProposal,
  Raid,
  SpellCardState,
} from "./types";
import { clampSidebarWidth, getSidebarWidth, setSidebarWidth } from "./uiPrefs";
import { TelemetryBoundary } from "./telemetry/ErrorBoundary";

// 073: the Raids page is its own chunk (PERF-011); it renders inside this shell so the chat
// socket and the investigate flow stay here.
const RaidsPage = lazy(() => import("./pages/RaidsPage"));

const CONNECTION_LOST = "Connection lost, the answer may be incomplete.";
// 085: after a drop, while the chat has no saved answer, check again after these delays. The
// server saves once its next send fails, which can come after a 180 s Claude call, its 180 s
// re-run and rate-limit waits (088b): 9 rechecks with growing gaps, 8 minutes in all.
const DROP_RECHECK_MS = [2_000, 4_000, 8_000, 16_000, 30_000, 60_000, 90_000, 120_000, 150_000];
// Frames that only make sense while a turn is streaming here.
const TURN_FRAMES = new Set<Frame["type"]>([
  "token",
  "tool_start",
  "tool_end",
  "thinking",
  "interim",
  "done",
]);

// 088b (PERF-003): a reload's messages, keeping each message that did not change as the object
// already shown (so its charts are not re-rendered), and the shown list itself if none changed.
const messageKey = (m: Message) =>
  JSON.stringify([m.role, m.id, m.seq, m.status, m.content, m.proposals?.map((p) => [p.id, p.status])]);
function keepUnchanged(shown: Message[], loaded: Message[]): Message[] {
  const next = loaded.map((m, i) => (shown[i] && messageKey(shown[i]) === messageKey(m) ? shown[i] : m));
  return next.length === shown.length && next.every((m, i) => m === shown[i]) ? shown : next;
}
function sameProposals(a: ProfileProposal[], b: ProfileProposal[]): boolean {
  return a.length === b.length && a.every((p, i) => p.id === b[i].id && p.status === b[i].status);
}

export default function App() {
  const [models, setModels] = useState<string[]>([]);
  const [modelsDegraded, setModelsDegraded] = useState(false);
  const [modelsProvider, setModelsProvider] = useState<"vertex" | "anthropic" | undefined>();
  const [model, setModel] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [raids, setRaids] = useState<Raid[]>([]);
  const [raidsStatus, setRaidsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const { identity, logout } = useAuth();
  const navigate = useNavigate();
  // 073: /app/raids/:reportCode? shows the Raids page in place of the chat body.
  const raidsMatch = useMatch("/app/raids/:reportCode?");
  const onRaidsPage = raidsMatch !== null;

  const [streaming, setStreamingState] = useState(false);
  // PERF-010: the streaming text lives in `streamStore`, not here, so a token never
  // re-renders the app; only the live message subscribes to it. 085: the same for the live
  // status (label, thought line, retry/fallback notice, last event time) in `statusStore`.
  const [error, setError] = useState<string | null>(null);

  // US6: live spellcasting cards for the in-flight turn.
  const [streamCards, setStreamCards] = useState<SpellCardState[]>([]);
  // US4: the boss ids the user has ticked on the latest sourcing turn (reset per turn).
  const [selectedBosses, setSelectedBosses] = useState<number[]>([]);
  // Feature 031: proposals with no agent message (reload of an unfinished turn, or a turn
  // that failed after proposing) still show as standalone cards.
  const [looseProposals, setLooseProposals] = useState<ProfileProposal[]>([]);

  // Refs to avoid stale closures inside the socket frame handler.
  const socketRef = useRef<ChatSocket | null>(null);
  const activeIdRef = useRef<string | null>(null);
  const streamRef = useRef("");
  const modelRef = useRef("");
  // The served set and default, for restoring a conversation whose model was retired.
  const servedModelsRef = useRef<{ models: string[]; default: string }>({ models: [], default: "" });
  const groundedRef = useRef(false);
  const fallbackRef = useRef<Message["fallback"]>(undefined); // set when the turn switched model
  const streamCardsRef = useRef<SpellCardState[]>([]);
  const pendingEncountersRef = useRef<Encounter[]>([]); // bosses surfaced this turn
  const pendingArtifactsRef = useRef<ChartArtifact[]>([]); // charts produced this turn
  const pendingProposalsRef = useRef<ProfileProposal[]>([]); // proposals made this turn
  const turnConvRef = useRef<string | null>(null); // sc-243: the chat the current turn belongs to
  const activeEncountersRef = useRef<Encounter[]>([]); // bosses shown by the live picker
  const selectedBossesRef = useRef<number[]>([]);
  const greetingReqId = useRef(0); // invalidates a late greeting if a turn/chat starts first
  // Mirrors `streaming` synchronously, so the stable callbacks below can read it.
  const streamingRef = useRef(false);
  // sc-376: set when the socket drops mid-answer, until the reconnect has reloaded that chat.
  const dropRef = useRef<{ conversationId: string; partial: string } | null>(null);
  const turnSeqRef = useRef(0); // counts sent turns, so a late reload can tell a newer one began
  // 085: the next drop recheck. 088b: `chain` counts started and stopped chains, so a recheck of
  // an older chain (timer or fetch in flight) does nothing: one chain at a time.
  const recheckRef = useRef<{ timer: ReturnType<typeof setTimeout> | null; chain: number }>({
    timer: null,
    chain: 0,
  });
  const stopRechecks = useCallback(() => {
    const r = recheckRef.current;
    if (r.timer !== null) clearTimeout(r.timer);
    r.timer = null;
    r.chain++;
  }, []);

  const setStreaming = useCallback((value: boolean) => {
    streamingRef.current = value;
    setStreamingState(value);
  }, []);

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
    try {
      const { raids } = await getRaids();
      setRaids(raids);
      setRaidsStatus("ready");
    } catch {
      setRaidsStatus("error");
    }
  }, []);

  const handleFrame = useCallback(
    (f: Frame) => {
      // sc-243: is the chat the current turn belongs to still the open one?
      const turnIsOpen = () =>
        turnConvRef.current !== null && turnConvRef.current === activeIdRef.current;
      // sc-376: a frame of a turn that was already ended locally (socket drop) is stale.
      // An `error` frame is not: it is shown even when idle (it never touches the messages).
      if (TURN_FRAMES.has(f.type) && !streamingRef.current) return;
      // 085: this frame's status change, applied once after the switch (only the live status
      // subscribes to it, so it never re-renders the app). 088b: answer text after a retry or
      // fallback notice clears it (a no-op in the store while there is none).
      const turnStatus: Partial<TurnStatusState> =
        f.type !== "token" ? { quietSince: Date.now() } : { notice: null };
      switch (f.type) {
        case "meta":
          turnConvRef.current = f.conversation_id;
          if (!activeIdRef.current) {
            activeIdRef.current = f.conversation_id;
            setActiveId(f.conversation_id);
          }
          break;
        case "tool_start": {
          Object.assign(turnStatus, { status: toolLabel(f.name), notice: null });
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
          // the model thinks afresh about the result
          Object.assign(turnStatus, { thought: null, notice: null });
          break;
        }
        case "thinking":
          // Feature 080: shown only while no answer text is (LiveMessage), and the backend
          // sends none once the answer has started.
          Object.assign(turnStatus, { thought: f.text, notice: null });
          break;
        case "interim":
          // Feature 080 (sc-572): the text so far was progress; the backend dropped it from the
          // answer it saves, so drop it here too and show its first sentence as status.
          streamRef.current = "";
          streamStore.set("");
          Object.assign(turnStatus, { thought: f.text, notice: null });
          break;
        case "model_retry":
          // Feature 011: the backend is waiting out a model rate limit; the next
          // tool_start/token replaces this status as usual. 085: shown under the cards too.
          {
            const label = retryLabel(f.attempt, f.max_attempts);
            Object.assign(turnStatus, { status: label, notice: label, thought: null });
          }
          break;
        case "model_fallback":
          // Feature 021: the turn continues on the same-class sibling; the answer is
          // marked with the model that gave it on `done`.
          fallbackRef.current = { from: f.from_model, to: f.to_model };
          {
            const label = fallbackLabel(f.from_model, f.to_model);
            Object.assign(turnStatus, { status: label, notice: label, thought: null });
          }
          break;
        case "grounding":
          if (f.used) {
            groundedRef.current = true;
            Object.assign(turnStatus, { status: "Searching the web…", notice: null });
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
        case "proposal":
          // Feature 031: like charts, the card attaches to the agent message on `done`.
          pendingProposalsRef.current = [...pendingProposalsRef.current, f.proposal];
          break;
        case "token":
          streamRef.current += f.text;
          streamStore.set(streamRef.current);
          break;
        case "conversation_title":
          // Feature 019: the title is already saved; reload the list so the sidebar shows it.
          void refreshConversations();
          break;
        case "suggestions": {
          // US1: arrives just after `done` (PERF-005), so the composer is already free.
          // Attach the follow-ups to the message they belong to. If that message isn't in
          // the open chat (the user switched chats meanwhile), drop them (PERF-104); only an
          // older backend without `message_id` falls back to the latest agent reply.
          const suggestions = f.suggestions.slice(0, 3);
          setMessages((m) => {
            const idx = f.message_id
              ? m.findIndex((x) => x.id === f.message_id)
              : m.map((x) => x.role).lastIndexOf("agent");
            if (idx < 0) return m;
            const next = m.slice();
            next[idx] = { ...next[idx], suggestions };
            return next;
          });
          break;
        }
        case "done": {
          const text = streamRef.current || "(no response)";
          const grounded = groundedRef.current;
          const fallback = fallbackRef.current;
          const tools = streamCardsRef.current;
          const encounters = pendingEncountersRef.current;
          const artifacts = pendingArtifactsRef.current;
          // sc-243: a proposal belongs to the chat that made it; if the user has moved to
          // another chat meanwhile it is not shown there (it reappears when its chat reopens).
          const proposals = turnIsOpen() ? pendingProposalsRef.current : [];
          if (proposals.length) {
            // A mid-turn reopen of this chat loaded the card as a loose one; drop that copy.
            setLooseProposals((l) => l.filter((x) => !proposals.some((p) => p.id === x.id)));
          }
          activeEncountersRef.current = encounters; // the live picker tracks this turn's bosses
          // Only into the chat that asked; another open chat must not get this answer (the
          // backend has it saved, so it shows when that chat is reopened).
          if (turnConvRef.current === activeIdRef.current) {
            setMessages((m) => [
              ...m,
              {
                id: f.message_id,
                role: "agent",
                content: text,
                grounded,
                fallback,
                tools,
                encounters,
                artifacts,
                proposals,
              },
            ]);
          }
          setStreaming(false);
          streamStore.set("");
          statusStore.reset();
          streamRef.current = "";
          groundedRef.current = false;
          fallbackRef.current = undefined;
          setCards([]);
          pendingEncountersRef.current = [];
          pendingArtifactsRef.current = [];
          pendingProposalsRef.current = [];
          setSelectedBosses([]); // fresh picker, no stale selection (FR-020)
          void refreshConversations();
          void refreshRaids();
          break;
        }
        case "error": {
          // Feature 031: a stored proposal is never invisible, even when its turn failed.
          // sc-243: only into the chat that made them, and not twice after a mid-turn reopen.
          const orphans = turnIsOpen() ? pendingProposalsRef.current : [];
          if (orphans.length) {
            setLooseProposals((l) => [...l, ...orphans.filter((o) => !l.some((x) => x.id === o.id))]);
          }
          pendingProposalsRef.current = [];
          setError(f.message);
          setStreaming(false);
          streamStore.set("");
          statusStore.reset();
          streamRef.current = "";
          groundedRef.current = false;
          fallbackRef.current = undefined;
          setCards([]);
          pendingEncountersRef.current = [];
          pendingArtifactsRef.current = [];
          break;
        }
      }
      statusStore.update(turnStatus);
    },
    [refreshConversations, refreshRaids, setCards, setStreaming],
  );

  // sc-376: the saved (partial) answer replaces the local copy after a drop. Only if the chat
  // is still open and no newer turn began meanwhile; a failed reload keeps the drop for the
  // next reconnect, until a new turn or opening a chat makes it stale.
  // 085 (SEC-001): the server learns of a drop only at its next send, which can come after this
  // reload (say, at the end of a tool call). Until it has saved, the chat has no agent message
  // and our copy is shown; it can be text the turn retracted. So while nothing is saved, check
  // again (DROP_RECHECK_MS); the saved partial then replaces our copy. A new turn, opening a chat
  // or a newer drop stops the rechecks (stopRechecks); a failed fetch counts as one and goes on.
  const reloadAfterDrop = useCallback((drop: { conversationId: string; partial: string }) => {
    stopRechecks();
    const chain = recheckRef.current.chain;
    const seq = turnSeqRef.current;
    const current = () =>
      recheckRef.current.chain === chain &&
      activeIdRef.current === drop.conversationId &&
      turnSeqRef.current === seq &&
      !streamingRef.current;
    const next = (attempt: number) => {
      if (attempt < DROP_RECHECK_MS.length) {
        recheckRef.current.timer = setTimeout(() => void load(attempt + 1), DROP_RECHECK_MS[attempt]);
      }
    };
    const load = async (attempt: number) => {
      recheckRef.current.timer = null;
      try {
        const detail = await getConversation(drop.conversationId);
        if (!current()) return;
        const loaded: Message[] = detail.messages.map((m) => ({ ...m }));
        const saved = loaded[loaded.length - 1]?.role === "agent";
        // The backend saved nothing of the cut-off answer (yet, or a restart lost it): our copy.
        if (drop.partial && !saved) {
          loaded.push({ role: "agent", content: drop.partial });
        }
        setMessages((shown) => keepUnchanged(shown, loaded));
        const loose = (detail.proposals ?? []).filter((p) => p.message_seq == null);
        setLooseProposals((shown) => (sameProposals(shown, loose) ? shown : loose));
        if (saved) {
          if (dropRef.current === drop) dropRef.current = null;
        } else {
          next(attempt);
        }
      } catch {
        // Not kept when a new turn began or the chat changed while the request was in flight.
        if (!current()) return;
        dropRef.current ??= drop; // the next reconnect tries again too
        next(attempt);
      }
    };
    return load(0);
  }, [stopRechecks]);
  useEffect(() => stopRechecks, [stopRechecks]);

  // The socket's connection changes. A drop while a turn streams ends that turn here: the
  // new socket has no turn running, so no done/error frame will ever arrive (sc-376).
  const handleStatus = useCallback(
    (up: boolean) => {
      setConnected(up);
      if (up) {
        const drop = dropRef.current;
        dropRef.current = null;
        if (drop && drop.conversationId === activeIdRef.current) void reloadAfterDrop(drop);
        return;
      }
      if (!streamingRef.current) return;
      const partial = streamRef.current;
      const conversationId = turnConvRef.current;
      if (conversationId !== null && conversationId === activeIdRef.current) {
        const orphans = pendingProposalsRef.current;
        if (orphans.length) {
          setLooseProposals((l) => [...l, ...orphans.filter((o) => !l.some((x) => x.id === o.id))]);
        }
        dropRef.current = { conversationId, partial };
      }
      // The partial belongs to the chat that asked; another open chat must not get it.
      if (partial && conversationId === activeIdRef.current) {
        setMessages((m) => [...m, { role: "agent", content: partial }]);
      }
      setError(CONNECTION_LOST);
      setStreaming(false);
      streamStore.set("");
      statusStore.reset();
      streamRef.current = "";
      groundedRef.current = false;
      fallbackRef.current = undefined;
      setCards([]);
      pendingEncountersRef.current = [];
      pendingArtifactsRef.current = [];
      pendingProposalsRef.current = [];
    },
    [reloadAfterDrop, setCards, setStreaming],
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
        servedModelsRef.current = { models: r.models, default: r.default };
        setModels(r.models);
        setModelsDegraded(!!r.degraded);
        setModelsProvider(r.provider);
        setModel((cur) => (cur && r.models.includes(cur) ? cur : r.default));
      })
      .catch(() => setError("Could not load models (is the backend up?)"));
    void refreshConversations();
    void refreshRaids();

    const socket = new ChatSocket(handleFrame, handleStatus);
    socketRef.current = socket;
    socket.connect();
    return () => socket.close();
  }, [handleFrame, handleStatus, refreshConversations, refreshRaids]);

  // PERF-010: the handlers below are stable (useCallback + refs), so the memoized
  // Sidebar, Composer and MessageList don't re-render when App does.
  const selectConversation = useCallback(async (id: string) => {
    greetingReqId.current++; // a late greeting must not land in another chat
    dropRef.current = null; // the chat is loaded from the backend now: no drop to replay
    stopRechecks();
    const detail = await getConversation(id);
    activeIdRef.current = id;
    setActiveId(id);
    setMessages(detail.messages.map((m) => ({ ...m })));
    setLooseProposals((detail.proposals ?? []).filter((p) => p.message_seq == null));
    // Discovery rotates models, so a chat may have been created on one no longer served:
    // continue it on the default instead of a model every send would reject.
    const served = servedModelsRef.current;
    const usable = !served.models.length || served.models.includes(detail.model);
    setModel(usable ? detail.model : served.default);
    setError(null);
    setSelectedBosses([]);
    activeEncountersRef.current = [];
  }, [stopRechecks]);

  // US5: open a clean chat and (best-effort) inject a warm Barnaby greeting, unless
  // the user starts typing/sends or switches chats first (then a late greeting is ignored).
  const newChat = useCallback(() => {
    stopRechecks(); // 088b: a chat switch ends a drop's rechecks
    activeIdRef.current = null;
    setActiveId(null);
    setMessages([]);
    setError(null);
    setCards([]);
    setSelectedBosses([]);
    activeEncountersRef.current = [];
    pendingEncountersRef.current = [];
    pendingArtifactsRef.current = [];
    pendingProposalsRef.current = [];
    setLooseProposals([]);

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
  }, [setCards, stopRechecks]);

  const removeConversation = useCallback(
    async (id: string) => {
      await deleteConversation(id);
      if (id === activeIdRef.current) newChat();
      await refreshConversations();
    },
    [newChat, refreshConversations],
  );

  // Feature 019: pin/unpin from the sidebar or the header. The returned row replaces the
  // list entry at once (SC-002); on failure the list is reloaded from the server.
  const togglePin = useCallback(
    async (id: string, pinned: boolean) => {
      try {
        const updated = await updateConversation(id, { pinned });
        setConversations((cs) => cs.map((c) => (c.id === id ? { ...c, ...updated } : c)));
      } catch {
        await refreshConversations().catch(() => undefined);
      }
    },
    [refreshConversations],
  );
  const activeConversation = useMemo(
    () => conversations.find((c) => c.id === activeId) ?? null,
    [conversations, activeId],
  );

  const sendText = useCallback(
    (text: string, opts?: { conversationId?: string | null; model?: string }): boolean => {
      if (streamingRef.current) return false;
      greetingReqId.current++; // a real turn started — drop any in-flight greeting
      const useModel = opts?.model ?? modelRef.current;
      const convId =
        opts && "conversationId" in opts ? opts.conversationId ?? null : activeIdRef.current;
      turnConvRef.current = convId;
      turnSeqRef.current++;
      dropRef.current = null; // a drop kept after a failed reload is stale once a turn follows
      stopRechecks();
      setError(null);
      setMessages((m) => [...m, { role: "user", content: text }]);
      streamRef.current = "";
      groundedRef.current = false;
      fallbackRef.current = undefined;
      setCards([]);
      pendingEncountersRef.current = [];
      pendingArtifactsRef.current = [];
      pendingProposalsRef.current = [];
      streamStore.set("");
      statusStore.reset();
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
    },
    [setCards, setStreaming, stopRechecks],
  );

  // US4: fold the ticked bosses into the next message text (visible), then clear the
  // selection so it never reapplies to a later turn (FR-020).
  function composeWithFocus(text: string): string {
    const ids = selectedBossesRef.current;
    const encs = activeEncountersRef.current;
    if (!ids.length || !encs.length) return text;
    const names = encs.filter((e) => ids.includes(e.encounter_id)).map((e) => e.name);
    return names.length ? `${text}\n\n(Focus on: ${names.join(", ")})` : text;
  }

  const send = useCallback(
    (text: string) => {
      const ok = sendText(composeWithFocus(text));
      if (ok) setSelectedBosses([]);
    },
    [sendText],
  );

  const handleDownloadPdf = useCallback(async () => {
    if (!activeIdRef.current) return;
    try {
      await downloadReport(activeIdRef.current);
    } catch {
      setError("Could not generate the PDF report.");
    }
  }, []);

  // US5: export a single agent reply (its question + its charts) as a PDF.
  const handleDownloadMessage = useCallback(async (messageId: string) => {
    if (!activeIdRef.current) return;
    try {
      await downloadMessageReport(activeIdRef.current, messageId);
    } catch {
      setError("Could not generate the per-message PDF report.");
    }
  }, []);

  // Feature 031: a confirmation card's decision saved a follow-up line; show it if its chat
  // is still the open one (otherwise it appears when that chat is opened).
  const appendFollowUp = useCallback((conversationId: string, message: Message) => {
    if (conversationId !== activeIdRef.current) return;
    setMessages((m) => [...m, message]);
  }, []);

  // One-click raid investigation (US1): the server creates an empty conversation
  // and owns the kickoff wording; we send it as a normal first turn.
  const handleInvestigateRaid = useCallback(async (reportCode: string) => {
    if (streamingRef.current) return;
    setError(null);
    try {
      const resp = await investigateRaid(reportCode, modelRef.current || undefined);
      activeIdRef.current = resp.conversation_id;
      setActiveId(resp.conversation_id);
      setMessages([]);
      setLooseProposals([]);
      setModel(resp.model);
      modelRef.current = resp.model;
      sendText(resp.kickoff_prompt, {
        conversationId: resp.conversation_id,
        model: resp.model,
      });
      // Feature 013: a recent raid becomes a tracked raid on investigation (FR-009).
      void refreshRaids();
    } catch (err) {
      setError(investigateErrorMessage(err));
    }
  }, [sendText, refreshRaids]);

  const handleInvestigateMplus = useCallback(
    async (reportCode: string, fightId: number) => {
      if (streamingRef.current) return;
      setError(null);
      try {
        const resp = await investigateMplusRun(reportCode, fightId, modelRef.current || undefined);
        activeIdRef.current = resp.conversation_id;
        setActiveId(resp.conversation_id);
        setMessages([]);
        setLooseProposals([]);
        setModel(resp.model);
        modelRef.current = resp.model;
        sendText(resp.kickoff_prompt, {
          conversationId: resp.conversation_id,
          model: resp.model,
        });
      } catch {
        setError("Could not start the investigation. Is the backend up?");
      }
    },
    [sendText],
  );

  // Feature 013: a fresh chat (no question asked yet) shows the user's recent raids under
  // Barnaby's greeting. Memoized so MessageList's memo holds across App re-renders.
  const showWelcome = activeId === null && !streaming && !messages.some((m) => m.role === "user");
  const welcome = useMemo(
    () =>
      showWelcome ? (
        <WelcomePanel
          onInvestigate={handleInvestigateRaid}
          onInvestigateMplus={handleInvestigateMplus}
          disabled={streaming}
        />
      ) : undefined,
    [showWelcome, handleInvestigateRaid, handleInvestigateMplus, streaming],
  );

  const openProfile = useCallback(() => navigate("/profile"), [navigate]);
  const openRaids = useCallback(() => {
    if (!streamingRef.current) setError(null); // a stale chat error is not the page's
    navigate("/app/raids");
  }, [navigate]);

  // 073: opening or starting a chat from the sidebar leaves the Raids page.
  const openConversation = useCallback(
    async (id: string) => {
      if (onRaidsPage) navigate("/app");
      await selectConversation(id);
    },
    [onRaidsPage, navigate, selectConversation],
  );
  const startNewChat = useCallback(() => {
    if (onRaidsPage) navigate("/app");
    newChat();
  }, [onRaidsPage, navigate, newChat]);

  // 073: "Analyze this raid" is the sidebar's old click: the same investigate + send flow,
  // then the chat replaces the page (only if a chat actually started).
  const analyzeRaid = useCallback(
    async (reportCode: string) => {
      const before = activeIdRef.current;
      await handleInvestigateRaid(reportCode);
      if (activeIdRef.current !== before) navigate("/app");
    },
    [handleInvestigateRaid, navigate],
  );

  return (
    <div className="app">
      <Ambient paused={streaming} />
      <TelemetryBoundary name="sidebar" resetKey={activeId}>
        <Sidebar
          conversations={conversations}
          raidCount={raids.length}
          raidsActive={onRaidsPage}
          activeId={activeId}
          onSelect={openConversation}
          onNew={startNewChat}
          onDelete={removeConversation}
          onTogglePin={togglePin}
          onOpenRaids={openRaids}
          onOpenProfile={openProfile}
        />
      </TelemetryBoundary>
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
            provider={modelsProvider}
          />
          {activeConversation && !onRaidsPage && (
            // FR-004a: keyboard reachable, named, and its pressed state is exposed.
            <Toggle
              variant="outline"
              size="sm"
              pressed={Boolean(activeConversation.pinned_at)}
              onPressedChange={(next) => void togglePin(activeConversation.id, next)}
              aria-label={activeConversation.pinned_at ? "Unpin chat" : "Pin chat"}
              title={activeConversation.pinned_at ? "Unpin chat" : "Pin chat"}
            >
              <LuPin />
            </Toggle>
          )}
          {activeId && messages.length > 0 && !onRaidsPage && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleDownloadPdf}
              disabled={streaming}
              title="Download this conversation as a PDF report"
            >
              ⬇ PDF
            </Button>
          )}
          <span className={`conn ${connected ? "online" : "offline"}`}>
            {connected ? "● connected" : "● disconnected"}
          </span>
          {identity?.is_platform_admin && (
            <Button asChild variant="secondary" size="sm">
              <a href="/admin/users" title="Manage users & invitations">
                Admin
              </a>
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={() => void logout()} title="Sign out">
            Sign out
          </Button>
        </header>
        {onRaidsPage ? (
          <TelemetryBoundary name="raids" resetKey={raidsMatch?.params.reportCode}>
            <Suspense fallback={null}>
              <RaidsPage
                raids={raids}
                status={raidsStatus}
                reportCode={raidsMatch?.params.reportCode}
                streaming={streaming}
                connected={connected}
                error={error}
                onAnalyze={analyzeRaid}
              />
            </Suspense>
          </TelemetryBoundary>
        ) : (
          <>
            <TelemetryBoundary name="messages" resetKey={activeId}>
              <MessageList
                messages={messages}
                streaming={streaming}
                error={error}
                streamCards={streamCards}
                selectedBosses={selectedBosses}
                onSelectBosses={setSelectedBosses}
                onPickSuggestion={send}
                onDownloadMessage={handleDownloadMessage}
                looseProposals={looseProposals}
                onFollowUp={appendFollowUp}
                footer={welcome}
              />
            </TelemetryBoundary>
            <TelemetryBoundary name="composer" resetKey={activeId}>
              <Composer disabled={streaming || !connected} onSend={send} />
            </TelemetryBoundary>
          </>
        )}
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
