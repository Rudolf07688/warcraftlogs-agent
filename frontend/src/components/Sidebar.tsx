import type { Conversation, Raid } from "../types";

interface Props {
  conversations: Conversation[];
  raids: Raid[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onInvestigateRaid: (reportCode: string) => void;
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Sidebar({
  conversations,
  raids,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onInvestigateRaid,
}: Props) {
  return (
    <aside className="sidebar">
      <button className="new-chat" onClick={onNew}>
        + New chat
      </button>

      <div className="sidebar-section-label">Raids</div>
      <div className="raid-list">
        {raids.length === 0 && <div className="sidebar-empty">No raids tracked yet</div>}
        {raids.map((r) => (
          <button
            key={r.report_code}
            className="raid-item"
            title={`Investigate ${r.label}`}
            onClick={() => onInvestigateRaid(r.report_code)}
          >
            <span className="raid-label">{r.label}</span>
            <span className="raid-when">{formatWhen(r.last_asked_at)}</span>
          </button>
        ))}
      </div>

      <div className="sidebar-section-label">Conversations</div>
      <div className="conversation-list">
        {conversations.length === 0 && <div className="sidebar-empty">No conversations yet</div>}
        {conversations.map((c) => (
          <div
            key={c.id}
            className={`conversation-item ${c.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(c.id)}
          >
            <span className="conversation-title">{c.title || "Untitled"}</span>
            <button
              className="conversation-delete"
              title="Delete"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(c.id);
              }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
