import { useState } from "react";
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

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// US2: show the raid's own date/time, falling back when the report start is unknown
// (older rows predating the column, or raids captured via a non-fight tool).
function raidWhen(r: Raid): string {
  return formatWhen(r.report_started_at ?? r.first_seen_at ?? r.last_asked_at);
}

// US2: a compact boss summary (kills marked), truncated for the narrow sidebar.
function bossSummary(r: Raid): string {
  const bosses = r.encounters ?? [];
  if (bosses.length === 0) return "";
  const names = bosses.map((e) => (e.kill ? `${e.name} ✓` : e.name));
  const shown = names.slice(0, 3).join(", ");
  return names.length > 3 ? `${shown} +${names.length - 3}` : shown;
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
  const [raidsOpen, setRaidsOpen] = useState(true);
  const [convsOpen, setConvsOpen] = useState(true);

  return (
    <aside className="sidebar">
      <button className="new-chat" onClick={onNew}>
        + New chat
      </button>

      <button
        className="sidebar-section-label"
        onClick={() => setRaidsOpen((o) => !o)}
        aria-expanded={raidsOpen}
      >
        <span className="section-chevron">{raidsOpen ? "▾" : "▸"}</span>
        Raids
        <span className="section-count">{raids.length}</span>
      </button>
      {raidsOpen && (
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
              <span className="raid-when">{raidWhen(r)}</span>
              {bossSummary(r) && <span className="raid-bosses">{bossSummary(r)}</span>}
            </button>
          ))}
        </div>
      )}

      <button
        className="sidebar-section-label"
        onClick={() => setConvsOpen((o) => !o)}
        aria-expanded={convsOpen}
      >
        <span className="section-chevron">{convsOpen ? "▾" : "▸"}</span>
        Conversations
        <span className="section-count">{conversations.length}</span>
      </button>
      {convsOpen && (
        <div className="conversation-list">
          {conversations.length === 0 && (
            <div className="sidebar-empty">No conversations yet</div>
          )}
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
      )}
    </aside>
  );
}
