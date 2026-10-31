import { useEffect, useId, useRef, useState } from "react";
import { ApiError, approveProposal, cancelProposal } from "../api/restClient";
import { notifyProfileChanged, useProfileChanged } from "../lib/profileEvents";
import { classColor, classDisplayName } from "../lib/classColors";
import type { Message, ProfileProposal, ProposalItem, ProposalStatus } from "../types";
import { Alert, AlertDescription } from "./ui/alert";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { ClassAvatar } from "./profile/ClassAvatar";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "./ui/item";
import { Spinner } from "./ui/spinner";

// Feature 031 (sc-207): the in-chat confirmation card for an agent's profile change proposal
// (design: participants-and-confirmation.html #card). Approve applies every valid item, Cancel
// cancels the whole proposal (D4); items that failed validation are shown as skipped.

// The design's labels for the proposal codes; the server's follow-up line uses the same words.
const LABELS: Record<string, string> = {
  duplicate_friend: "already a friend",
  already_friend: "already a friend",
  already_own: "your own character",
  duplicate_character: "your own character",
  character_limit: "character limit reached",
  friend_limit: "friend limit (50) reached",
  invalid_name: "name not valid",
  invalid_realm: "realm unknown, add by hand",
  invalid_region: "region unknown",
  invalid_item: "not valid",
  duplicate_item: "listed twice",
  not_found: "no longer in your profile",
  no_change: "already set",
};

const label = (code: string | null) => LABELS[code ?? ""] ?? "not applied";

// sc-221: items refused for their identity may carry hostile text from a log, so their row
// shows the reason only, never the name, realm or spec (as the server's follow-up line does).
const IDENTITY_REFUSED = new Set(["invalid_name", "invalid_realm", "invalid_region", "invalid_item"]);

// A 409 from approve/cancel is the server's state, shown without another request.
const CONFLICT_STATUS: Record<string, ProposalStatus> = {
  proposal_expired: "expired",
  proposal_cancelled: "cancelled",
  proposal_applied: "applied",
};

const STATUS_BADGE: Record<ProposalStatus, { text: string; variant: "outline" | "success" | "secondary" | "warning" }> = {
  pending: { text: "Pending", variant: "outline" },
  applied: { text: "Applied", variant: "success" },
  cancelled: { text: "Cancelled", variant: "secondary" },
  expired: { text: "Expired", variant: "warning" },
};

const EXPIRED_TEXT = "This proposal expired. Ask Barnaby again.";

function shownStatus(p: ProfileProposal): ProposalStatus {
  return p.status === "pending" && Date.now() >= Date.parse(p.expires_at) ? "expired" : p.status;
}

function actionText(it: ProposalItem): string {
  if (it.action === "add") return "+ Add";
  if (it.action === "remove") return "− Remove";
  return `Role: ${it.previous_raid_role ?? "auto"} → ${it.raid_role ?? "auto"}`;
}

const APPLIED_TEXT = { add: "Added", remove: "Removed", update: "Role set" } as const;

function rowBadge(it: ProposalItem): { text: string; variant: "outline" | "success" | "warning" | "destructive" } {
  if (it.result?.status === "applied") return { text: APPLIED_TEXT[it.action], variant: "success" };
  if (it.result?.status === "failed") return { text: `Failed · ${label(it.result.code)}`, variant: "destructive" };
  if (it.result?.status === "skipped" || !it.validation.ok) {
    return { text: `Skipped · ${label(it.result?.code ?? it.validation.code)}`, variant: "warning" };
  }
  return { text: actionText(it), variant: "outline" };
}

function appliedSummary(p: ProfileProposal): string {
  const count = (pred: (it: ProposalItem) => boolean) => p.items.filter(pred).length;
  const applied = (action: ProposalItem["action"]) => (it: ProposalItem) =>
    it.result?.status === "applied" && it.action === action;
  const parts = [
    [count(applied("add")), "added"],
    [count(applied("remove")), "removed"],
    [count(applied("update")), "role set"],
    [count((it) => it.result?.status === "skipped"), "skipped"],
    [count((it) => it.result?.status === "failed"), "failed"],
  ]
    .filter(([n]) => n)
    .map(([n, what]) => `${n} ${what}`);
  return parts.length ? `Applied: ${parts.join(", ")}` : "Applied.";
}

function appliedTargets(p: ProfileProposal): ("friend" | "own")[] {
  return [...new Set(p.items.filter((it) => it.result?.status === "applied").map((it) => it.target))];
}

function RefusedRow({ item }: { item: ProposalItem }) {
  return (
    <Item role="listitem" variant="outline" size="sm" className="opacity-60">
      <ItemMedia>
        <ClassAvatar char={{ name: "?", class_name: null }} className="size-9" />
      </ItemMedia>
      <ItemContent className="min-w-0">
        <ItemTitle className="flex-wrap">
          Skipped entry
          <span className="font-normal text-muted-foreground">
            · {item.target === "friend" ? "Friends" : "Your characters"}
          </span>
        </ItemTitle>
        {item.validation.message && <ItemDescription>{item.validation.message}</ItemDescription>}
      </ItemContent>
      <ItemActions>
        <Badge variant="warning">{rowBadge(item).text}</Badge>
      </ItemActions>
    </Item>
  );
}

function ItemRow({ item }: { item: ProposalItem }) {
  if (!item.validation.ok && IDENTITY_REFUSED.has(item.validation.code ?? "")) return <RefusedRow item={item} />;
  const badge = rowBadge(item);
  const skipped = badge.variant === "warning";
  const spec = [item.spec, item.class_name && classDisplayName(item.class_name)].filter(Boolean).join(" ");
  const note =
    item.result?.status === "failed"
      ? "Valid when proposed, changed since"
      : !item.validation.ok
        ? item.validation.message
        : null;
  return (
    <Item role="listitem" variant="outline" size="sm" className={skipped ? "opacity-60" : undefined}>
      <ItemMedia>
        <ClassAvatar char={item} className="size-9" />
      </ItemMedia>
      <ItemContent className="min-w-0">
        <ItemTitle className="flex-wrap">
          {item.name}
          <span className="font-normal text-muted-foreground">
            · {item.target === "friend" ? "Friends" : "Your characters"}
          </span>
        </ItemTitle>
        <ItemDescription>
          {item.realm} · {item.region.toUpperCase()}
          {spec && (
            <>
              {" · "}
              <span style={{ color: classColor(item.class_name) ?? undefined }}>{spec}</span>
            </>
          )}
          {item.played_role && ` · played ${item.played_role}`}
          {item.action === "add" && item.raid_role && ` · role: ${item.raid_role}`}
          {note && <span className="block">{note}</span>}
        </ItemDescription>
      </ItemContent>
      <ItemActions>
        <Badge variant={badge.variant}>{badge.text}</Badge>
      </ItemActions>
    </Item>
  );
}

interface Props {
  proposal: ProfileProposal;
  /** The saved follow-up line, to append to the chat it belongs to. */
  onFollowUp?: (conversationId: string, message: Message) => void;
}

export function ProposalCard({ proposal, onFollowUp }: Props) {
  const [current, setCurrent] = useState(proposal);
  const [busy, setBusy] = useState<"approve" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false); // blocks a second click before the re-render lands
  const rootRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // A reload hands over a fresh proposal; another tab's approve arrives as a broadcast.
  useEffect(() => setCurrent(proposal), [proposal]);
  useProfileChanged((change) => {
    if (change.proposal.id === proposal.id) setCurrent(change.proposal);
  });

  const status = shownStatus(current);
  const valid = current.items.filter((it) => it.validation.ok).length;
  const expires = new Date(current.expires_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  const statusText = {
    pending: valid ? `Nothing changes until you approve · Expires ${expires}` : "Nothing to apply",
    applied: appliedSummary(current),
    cancelled: "Cancelled. Your profile is unchanged.",
    expired: EXPIRED_TEXT,
  }[status];

  const decide = async (kind: "approve" | "cancel") => {
    if (busyRef.current) return;
    if (shownStatus(current) === "expired") {
      setCurrent({ ...current, status: "expired" });
      return;
    }
    busyRef.current = true;
    setBusy(kind);
    setError(null);
    try {
      const res = await (kind === "approve" ? approveProposal : cancelProposal)(current.id);
      setCurrent(res.proposal);
      if (res.follow_up) onFollowUp?.(res.proposal.conversation_id, res.follow_up);
      const targets = appliedTargets(res.proposal);
      if (targets.length) notifyProfileChanged({ proposal: res.proposal, targets });
    } catch (e) {
      const conflict = e instanceof ApiError && e.status === 409 ? CONFLICT_STATUS[e.message] : undefined;
      if (conflict) setCurrent({ ...current, status: conflict });
      else setError(kind === "approve" ? "Couldn't apply. Try again." : "Couldn't cancel. Try again.");
    } finally {
      busyRef.current = false;
      setBusy(null);
      rootRef.current?.focus();
    }
  };

  const badge = STATUS_BADGE[status];
  return (
    <Card
      ref={rootRef}
      tabIndex={-1}
      role="group"
      aria-labelledby={titleId}
      className="mt-3 gap-4 bg-background/30 py-4 outline-none"
    >
      <CardHeader className="px-4">
        <CardTitle id={titleId}>Proposed profile changes</CardTitle>
        <CardDescription>{status === "expired" ? "Nothing was changed." : statusText}</CardDescription>
        <CardAction>
          <Badge variant={badge.variant}>{badge.text}</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-4">
        <ItemGroup role="list" className="gap-2">
          {current.items.map((it) => (
            <ItemRow key={it.index} item={it} />
          ))}
        </ItemGroup>
        {status === "expired" && (
          <Alert>
            <AlertDescription>{EXPIRED_TEXT}</AlertDescription>
          </Alert>
        )}
        {error && status === "pending" && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
      {status === "pending" && (
        <CardFooter className="gap-2 px-4">
          <Button size="sm" disabled={!valid || busy !== null} onClick={() => void decide("approve")}>
            {busy === "approve" && <Spinner />}
            Approve {valid}
          </Button>
          <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void decide("cancel")}>
            {busy === "cancel" && <Spinner />}
            Cancel
          </Button>
        </CardFooter>
      )}
      <p aria-live="polite" className="sr-only">
        {status === "pending" ? "" : statusText}
      </p>
    </Card>
  );
}
