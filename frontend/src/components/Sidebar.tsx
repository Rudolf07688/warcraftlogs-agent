import { memo, useState } from "react";
import type { Conversation, Raid } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { Button } from "./ui/button";

interface Props {
  conversations: Conversation[];
  raids: Raid[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void | Promise<void>;
  onInvestigateRaid: (reportCode: string) => void;
  onOpenProfile: () => void;
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

function SidebarImpl({
  conversations,
  raids,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onInvestigateRaid,
  onOpenProfile,
}: Props) {
  const [raidsOpen, setRaidsOpen] = useState(true);
  const [convsOpen, setConvsOpen] = useState(true);
  // Feature 010 / FR-006: the conversation awaiting the in-app delete confirmation.
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await onDelete(pendingDelete.id);
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  }

  return (
    <aside className="sidebar">
      <Button onClick={onNew}>+ New chat</Button>
      <Button variant="secondary" onClick={onOpenProfile} title="Edit your profile">
        ⚑ Profile
      </Button>

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
              className={`conversation-item group ${c.id === activeId ? "active" : ""}`}
              onClick={() => onSelect(c.id)}
            >
              <span className="conversation-title">{c.title || "Untitled"}</span>
              <Button
                variant="ghost"
                size="icon"
                className="size-7 shrink-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                aria-label="Delete conversation"
                title="Delete"
                onClick={(e) => {
                  e.stopPropagation();
                  setPendingDelete(c);
                }}
              >
                ✕
              </Button>
            </div>
          ))}
        </div>
      )}

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

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete conversation?"
        description={`"${pendingDelete?.title || "Untitled"}" will be deleted permanently.`}
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </aside>
  );
}

// PERF-010: skip re-rendering while a reply streams (its props don't change per token).
export const Sidebar = memo(SidebarImpl);
