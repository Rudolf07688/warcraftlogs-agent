import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteConversation,
  getConversation,
  getModels,
  listConversations,
} from "./api/restClient";
import { ChatSocket, type Frame } from "./api/wsClient";
import { Composer } from "./components/Composer";
import { MessageList } from "./components/MessageList";
import { ModelSelect } from "./components/ModelSelect";
import { Sidebar } from "./components/Sidebar";
import { THINKING_DEFAULT, toolLabel } from "./toolLabels";
import type { Conversation, Message } from "./types";

export default function App() {
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
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

  const refreshConversations = useCallback(async () => {
    const { conversations } = await listConversations();
    setConversations(conversations);
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
        case "token":
          streamRef.current += f.text;
          setStreamText(streamRef.current);
          break;
        case "done": {
          const text = streamRef.current || "(no response)";
          setMessages((m) => [...m, { role: "agent", content: text }]);
          setStreaming(false);
          setStreamText("");
          setStatus(THINKING_DEFAULT);
          streamRef.current = "";
          void refreshConversations();
          break;
        }
        case "error":
          setError(f.message);
          setStreaming(false);
          setStreamText("");
          setStatus(THINKING_DEFAULT);
          streamRef.current = "";
          break;
      }
    },
    [refreshConversations],
  );

  // Initial load + socket lifecycle.
  useEffect(() => {
    getModels()
      .then((r) => {
        setModels(r.models);
        setModel((cur) => cur || r.default);
      })
      .catch(() => setError("Could not load models (is the backend up?)"));
    void refreshConversations();

    const socket = new ChatSocket(handleFrame, setConnected);
    socketRef.current = socket;
    socket.connect();
    return () => socket.close();
  }, [handleFrame, refreshConversations]);

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

  function send(text: string) {
    if (streaming) return;
    setError(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    streamRef.current = "";
    setStreamText("");
    setStatus(THINKING_DEFAULT);
    setStreaming(true);
    const ok = socketRef.current?.send({
      conversation_id: activeIdRef.current,
      model,
      content: text,
    });
    if (!ok) {
      setStreaming(false);
      setError("Not connected to the server. Retrying…");
    }
  }

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={newChat}
        onDelete={removeConversation}
      />
      <main className="chat">
        <header className="chat-header">
          <span className="app-title">WCL Agent Chat</span>
          <ModelSelect models={models} value={model} onChange={setModel} disabled={streaming} />
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
