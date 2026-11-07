import { memo, useMemo, useState } from "react";
import { LuPin } from "react-icons/lu";
import type { Conversation } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { Button } from "./ui/button";
import { Separator } from "./ui/separator";
import { Toggle } from "./ui/toggle";

interface Props {
  conversations: Conversation[];
  raidCount: number;
  raidsActive: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void | Promise<void>;
  onTogglePin: (id: string, pinned: boolean) => void;
  onOpenRaids: () => void;
  onOpenProfile: () => void;
}

// Feature 019: pinned chats, most recently pinned first (FR-006).
function byPinnedDesc(a: Conversation, b: Conversation): number {
  return Date.parse(b.pinned_at ?? "") - Date.parse(a.pinned_at ?? "");
}

function SidebarImpl({
  conversations,
  raidCount,
  raidsActive,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onTogglePin,
  onOpenRaids,
  onOpenProfile,
}: Props) {
  const [convsOpen, setConvsOpen] = useState(true);
  // Feature 010 / FR-006: the conversation awaiting the in-app delete confirmation.
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Feature 019: the Pinned group sits on top; the rest keep the server's activity order.
  const [pinned, unpinned] = useMemo(
    () => [
      conversations.filter((c) => c.pinned_at).sort(byPinnedDesc),
      conversations.filter((c) => !c.pinned_at),
    ],
    [conversations],
  );

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

  function renderConversation(c: Conversation) {
    const isPinned = Boolean(c.pinned_at);
    const pinLabel = isPinned ? "Unpin chat" : "Pin chat";
    return (
      <div
        key={c.id}
        className={`conversation-item group ${c.id === activeId ? "active" : ""}`}
        onClick={() => onSelect(c.id)}
      >
        <span className="conversation-title">{c.title || "Untitled"}</span>
        {/* FR-004a: keyboard reachable, named, and its pressed state is exposed. */}
        <Toggle
          size="sm"
          pressed={isPinned}
          onPressedChange={(next) => onTogglePin(c.id, next)}
          onClick={(e) => e.stopPropagation()}
          aria-label={pinLabel}
          title={pinLabel}
          className={`size-7 min-w-7 shrink-0 ${
            isPinned ? "" : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          }`}
        >
          <LuPin />
        </Toggle>
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
    );
  }

  return (
    <aside className="sidebar">
      <Button onClick={onNew}>+ New chat</Button>
      <Button variant="secondary" onClick={onOpenProfile} title="Edit your profile">
        ⚑ Profile
      </Button>
      {/* 073: one entry opens the Raids page (a tab per raid); it no longer starts a chat. */}
      <Button
        variant={raidsActive ? "default" : "secondary"}
        onClick={onOpenRaids}
        aria-current={raidsActive ? "page" : undefined}
        title="Your tracked raids"
      >
        ⚔ Raids
        <span className="section-count">{raidCount}</span>
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
          {pinned.length > 0 && (
            <div role="group" aria-label="Pinned chats" className="flex flex-col gap-1">
              <div className="px-2 text-[0.6875rem] uppercase tracking-wider text-muted-foreground">
                Pinned
              </div>
              {pinned.map(renderConversation)}
              {unpinned.length > 0 && <Separator className="my-1" />}
            </div>
          )}
          {unpinned.map(renderConversation)}
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
