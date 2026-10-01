import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteConversation,
  downloadReport,
  getConversation,
  getModels,
  getRaids,
  investigateRaid,
  listConversations,
} from "./api/restClient";
import { ChatSocket, type Frame } from "./api/wsClient";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { ModelSelect } from "./components/ModelSelect";
import { Sidebar } from "./components/Sidebar";
import { THINKING_DEFAULT, toolLabel } from "./toolLabels";
import type { Conversation, Message, Raid } from "./types";

export default function App() {
  const [models, setModels] = useState<string[]>([]);
  const [modelsDegraded, setModelsDegraded] = useState(false);
  const [model, setModel] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [raids, setRaids] = useState<Raid[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);

  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [status, setStatus] = useState(THINKING_DEFAULT);
  const [error, setError] = useState<string | null>(null);

  // Refs to avoid stale closures inside the socket frame handler.
  const socketRef = useRef<ChatSocket | null>(null);
  const activeIdRef = useRef<string | null>(null);
  const streamRef = useRef("");
  const modelRef = useRef("");
  const groundedRef = useRef(false);

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
        case "tool_start":
          setStatus(toolLabel(f.name));
          break;
        case "grounding":
          if (f.used) {
            groundedRef.current = true;
            setStatus("Searching the web…");
          }
          break;
        case "raid_tracked":
          void refreshRaids();
          break;
        case "token":
          streamRef.current += f.text;
          setStreamText(streamRef.current);
          break;
        case "done": {
          const text = streamRef.current || "(no response)";
          const grounded = groundedRef.current;
          setMessages((m) => [...m, { role: "agent", content: text, grounded }]);
          setStreaming(false);
          setStreamText("");
          setStatus(THINKING_DEFAULT);
          streamRef.current = "";
          groundedRef.current = false;
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
          break;
      }
    },
    [refreshConversations, refreshRaids],
  );

  // Keep a ref of the selected model so imperative sends never read a stale value.
  useEffect(() => {
    modelRef.current = model;
  }, [model]);

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
    const detail = await getConversation(id);
    activeIdRef.current = id;
    setActiveId(id);
    setMessages(detail.messages.map((m) => ({ ...m })));
    setModel(detail.model);
    setError(null);
  }

  function newChat() {
    activeIdRef.current = null;
    setActiveId(null);
    setMessages([]);
    setError(null);
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
    const useModel = opts?.model ?? modelRef.current;
    const convId =
      opts && "conversationId" in opts ? opts.conversationId ?? null : activeIdRef.current;
    setError(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    streamRef.current = "";
    groundedRef.current = false;
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

  function send(text: string) {
    sendText(text);
  }

  async function handleDownloadPdf() {
    if (!activeId) return;
    try {
      await downloadReport(activeId);
    } catch {
      setError("Could not generate the PDF report.");
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
      <Sidebar
        conversations={conversations}
        raids={raids}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={newChat}
        onDelete={removeConversation}
        onInvestigateRaid={handleInvestigateRaid}
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
        />
        <Composer disabled={streaming || !connected} onSend={send} />
      </main>
    </div>
  );
}
