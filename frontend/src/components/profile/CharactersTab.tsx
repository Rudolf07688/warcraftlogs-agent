import { type CSSProperties, useCallback, useEffect, useId, useState } from "react";
import {
  LuCastle,
  LuTrash2,
  LuUser,
  LuUserPlus,
  LuUsers,
} from "react-icons/lu";
import {
  ApiError,
  addFriend,
  addOwnCharacter,
  deleteFriend,
  deleteGuild,
  deleteOwnCharacter,
  getProfile,
  putGuild,
  updateFriend,
  updateOwnCharacter,
} from "../../api/restClient";
import { classColor, classDisplayName, initials } from "../../lib/classColors";
import { cn } from "../../lib/utils";
import type { Character, GuideStatus, Guild, Profile, RaidRole } from "../../types";
import { ConfirmDialog } from "../ConfirmDialog";
import { StatusAlert } from "../StatusAlert";
import { GUIDE_GLYPH, GUIDE_GLYPH_LABEL, GUIDE_LABEL_SHORT, GUIDE_TONE, StatusBadge } from "../StatusBadge";
import { Avatar, AvatarFallback } from "../ui/avatar";
import { Button } from "../ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "../ui/empty";
import { Field, FieldGroup, FieldLabel } from "../ui/field";
import { Input } from "../ui/input";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "../ui/item";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import { Skeleton } from "../ui/skeleton";
import { Spinner } from "../ui/spinner";

// Characters tab (feature 008 / US1): your own characters (feature 012: several, up to the
// server's limit), friends (unlimited), raid roles, and the single main guild. Extracted verbatim-in-behavior from the former ProfilePanel modal — same
// endpoints, same friendly duplicate message. Profile revamp: one card per section, friends
// as a list of items, and a single dialog for setting/editing an identity.

const REGIONS = ["US", "EU", "KR", "TW", "CN"];
const GENERIC_ERROR = "That action failed. Check the details and try again.";

function GuideBadge({ status }: { status: GuideStatus }) {
  if (status === "none") return null;
  return <StatusBadge tone={GUIDE_TONE[status]}>{GUIDE_LABEL_SHORT[status]}</StatusBadge>;
}

// Feature 015: one compact indicator per content type, e.g. "Raid ✓" "M+ –". Characters
// get "ready" whenever a verified guide exists, so the glyph follows the status directly.
const INDICATORS = [
  { key: "raid", short: "Raid", long: "Raid" },
  { key: "mplus", short: "M+", long: "Mythic+" },
] as const;

function GuideIndicators({ char }: { char: Character }) {
  if (!char.class_name || !char.active_spec) return null;
  return (
    <span className="inline-flex gap-1">
      {INDICATORS.map(({ key, short, long }) => {
        const status = char.guides[key];
        const glyph = status === "ready" ? "published" : status;
        const label = `${long} guide: ${GUIDE_GLYPH_LABEL[glyph]}`;
        return (
          <StatusBadge key={key} tone={status === "none" ? "neutral" : GUIDE_TONE[status]} title={label}>
            <span aria-label={label}>
              {short} <span aria-hidden>{GUIDE_GLYPH[glyph]}</span>
            </span>
          </StatusBadge>
        );
      })}
    </span>
  );
}

function realmLabel(it: { server: string; region: string }): string {
  return `${it.server} · ${it.region}`;
}

function specLabel(c: Character): string {
  return [c.active_spec, c.class_name && classDisplayName(c.class_name)].filter(Boolean).join(" ");
}

function identityLabel(c: Character): string {
  const spec = [c.class_name, c.active_spec].filter(Boolean).join(" ");
  const base = `${c.name}-${c.server} (${c.region})`;
  return spec ? `${base} — ${spec}` : base;
}

// A round avatar with the character's initials, ringed and tinted in their class colour.
function ClassAvatar({ char, className }: { char: Character; className?: string }) {
  const color = classColor(char.class_name);
  const style: CSSProperties | undefined = color
    ? { borderColor: color, color, background: `color-mix(in oklch, ${color} 16%, transparent)` }
    : undefined;
  return (
    <Avatar className={cn("border-2 border-border", className)} aria-hidden="true">
      <AvatarFallback className="bg-muted font-display font-semibold text-glow" style={style}>
        {initials(char.name)}
      </AvatarFallback>
    </Avatar>
  );
}

// US4: raid roles. "Auto" (no override) falls back to the spec-inferred default.
const ROLE_LABEL: Record<RaidRole, string> = { tank: "Tank", healer: "Healer", dps: "DPS" };
// Character rows use a compact select; "Auto" shows the inferred role when there is one.
function RoleSelect({
  char,
  busy,
  onChange,
}: {
  char: Character;
  busy: boolean;
  onChange: (role: RaidRole | null) => void;
}) {
  const inferred = char.raid_role == null ? char.effective_role : null;
  return (
    <NativeSelect
      size="sm"
      aria-label="Raid role"
      title="Raid role"
      value={char.raid_role ?? ""}
      disabled={busy}
      onChange={(e) => onChange((e.target.value || null) as RaidRole | null)}
    >
      <NativeSelectOption value="">{inferred ? `Auto · ${ROLE_LABEL[inferred]}` : "Auto"}</NativeSelectOption>
      {(Object.keys(ROLE_LABEL) as RaidRole[]).map((r) => (
        <NativeSelectOption key={r} value={r}>
          {ROLE_LABEL[r]}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}

// One list for your own characters and your friends (feature 012): avatar, name, guide
// status, realm and spec, raid role, and a remove button per character.
function CharacterList({
  chars,
  busy,
  removeLabel,
  onRoleChange,
  onRemove,
}: {
  chars: Character[];
  busy: boolean;
  removeLabel: string;
  onRoleChange: (c: Character, role: RaidRole | null) => void;
  onRemove: (c: Character) => void;
}) {
  return (
    <ItemGroup className="grid gap-3 md:grid-cols-2">
      {chars.map((c) => (
        <Item key={c.id} role="listitem" variant="outline" size="sm" className="bg-background/30">
          <ItemMedia>
            <ClassAvatar char={c} className="size-10" />
          </ItemMedia>
          <ItemContent className="min-w-0">
            <ItemTitle className="flex-wrap">
              {c.name}
              <GuideIndicators char={c} />
            </ItemTitle>
            <ItemDescription className="truncate">
              {realmLabel(c)}
              {specLabel(c) && (
                <>
                  {" · "}
                  <span style={{ color: classColor(c.class_name) ?? undefined }}>{specLabel(c)}</span>
                </>
              )}
            </ItemDescription>
          </ItemContent>
          <ItemActions>
            <RoleSelect char={c} busy={busy} onChange={(role) => onRoleChange(c, role)} />
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground hover:text-destructive"
              disabled={busy}
              onClick={() => onRemove(c)}
              aria-label={removeLabel}
              title={removeLabel}
            >
              <LuTrash2 />
            </Button>
          </ItemActions>
        </Item>
      ))}
    </ItemGroup>
  );
}

interface FormState {
  name: string;
  server: string;
  region: string;
}

const EMPTY: FormState = { name: "", server: "", region: "US" };

type DialogKind = "own" | "friend" | "guild";

// One dialog for adding an own character or a friend, and setting/replacing the guild.
// It stays open (showing the error) until the submit succeeds.
function IdentityDialog({
  open,
  title,
  description,
  submitLabel,
  initial,
  busy,
  error,
  onSubmit,
  onClose,
}: {
  open: boolean;
  title: string;
  description: string;
  submitLabel: string;
  initial: FormState;
  busy: boolean;
  error: string | null;
  onSubmit: (v: FormState) => void;
  onClose: () => void;
}) {
  const id = useId();
  const [form, setForm] = useState<FormState>(initial);
  // Reset the fields each time the dialog opens.
  useEffect(() => {
    if (open) setForm(initial);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const canSubmit = form.name.trim() && form.server.trim() && !busy;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <form
          className="flex flex-col gap-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) onSubmit({ ...form, name: form.name.trim(), server: form.server.trim() });
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          {error && <StatusAlert tone="error">{error}</StatusAlert>}
          <FieldGroup className="grid gap-4 sm:grid-cols-[1fr_1fr_6rem]">
            <Field>
              <FieldLabel htmlFor={`${id}-name`}>Name</FieldLabel>
              <Input
                id={`${id}-name`}
                placeholder="Thrall"
                autoComplete="off"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`${id}-server`}>Server</FieldLabel>
              <Input
                id={`${id}-server`}
                placeholder="Draenor"
                autoComplete="off"
                value={form.server}
                onChange={(e) => setForm((f) => ({ ...f, server: e.target.value }))}
              />
            </Field>
            <Field className="[&_[data-slot=native-select-wrapper]]:w-full">
              <FieldLabel htmlFor={`${id}-region`}>Region</FieldLabel>
              <NativeSelect
                id={`${id}-region`}
                value={form.region}
                onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}
              >
                {REGIONS.map((r) => (
                  <NativeSelectOption key={r} value={r}>
                    {r}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button type="button" variant="secondary" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {busy && <Spinner />}
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CardsSkeleton() {
  return (
    <div className="grid gap-4 lg:grid-cols-3" aria-busy="true" aria-label="Loading your profile">
      <Card className="lg:col-span-2">
        <CardContent className="flex items-center gap-4">
          <Skeleton className="size-16 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-28" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="flex flex-col gap-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
      <Card className="lg:col-span-3">
        <CardContent className="grid gap-3 md:grid-cols-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </CardContent>
      </Card>
    </div>
  );
}

const SECTION_TITLE = "font-display text-base tracking-wide text-glow";

export function CharactersTab() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const [dialogErr, setDialogErr] = useState<string | null>(null);
  // Feature 010 / FR-006: the friend or guild awaiting the in-app remove confirmation.
  const [pendingRemove, setPendingRemove] = useState<
    | { kind: "own"; char: Character }
    | { kind: "friend"; char: Character }
    | { kind: "guild"; guild: Guild }
    | null
  >(null);

  const refresh = useCallback(async () => {
    try {
      setProfile(await getProfile());
      setErr(null);
    } catch {
      setErr("Could not load your profile.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while any guide is still resolving so the badges flip to "ready" on their own.
  useEffect(() => {
    if (!profile) return;
    const pending =
      [...profile.own, ...profile.friends].some(
        (c) => c.guides.raid === "pending" || c.guides.mplus === "pending",
      ) ||
      profile.guild?.summary_status === "pending";
    if (!pending) return;
    const t = setTimeout(() => void refresh(), 4000);
    return () => clearTimeout(t);
  }, [profile, refresh]);

  // Runs a mutation then reloads; resolves to an error message, or null on success.
  const run = useCallback(
    async (fn: () => Promise<unknown>, describeError: (e: unknown) => string = () => GENERIC_ERROR) => {
      setBusy(true);
      try {
        await fn();
        await refresh();
        return null;
      } catch (e) {
        return describeError(e);
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  // Inline actions (role changes, removals) report on the page-level alert.
  const runInline = useCallback(
    async (fn: () => Promise<unknown>) => {
      const msg = await run(fn);
      setErr(msg);
    },
    [run],
  );

  const own = profile?.own ?? [];
  const ownLimit = profile?.own_limit ?? 0;
  const ownFull = own.length >= ownLimit;
  const guild: Guild | null = profile?.guild ?? null;
  const friends = profile?.friends ?? [];

  const openDialog = (kind: DialogKind) => {
    setDialogErr(null);
    setDialog(kind);
  };

  // Adding a character has distinct, expected failures (duplicate, saved in the other list,
  // limit reached) that deserve friendly messages rather than the generic one.
  const describeAddError = (v: FormState) => (e: unknown) => {
    const who = `${v.name}-${v.server} (${v.region})`;
    if (!(e instanceof ApiError)) return GENERIC_ERROR;
    switch (e.message) {
      case "duplicate_character":
      case "duplicate_friend":
        return `${who} is already added.`;
      case "already_friend":
        return `${who} is saved as a friend — remove it there first.`;
      case "already_own":
        return `${who} is one of your characters.`;
      case "character_limit":
        return `You can register up to ${ownLimit} characters.`;
      default:
        return e.status === 409 ? `${who} is already added.` : GENERIC_ERROR;
    }
  };

  const submitDialog = async (v: FormState) => {
    let msg: string | null = null;
    if (dialog === "own") {
      msg = await run(() => addOwnCharacter(v), describeAddError(v));
    } else if (dialog === "guild") {
      msg = await run(() => putGuild(v));
    } else if (dialog === "friend") {
      msg = await run(() => addFriend(v), describeAddError(v));
    }
    setDialogErr(msg);
    if (msg === null) setDialog(null);
  };

  const dialogCopy: Record<DialogKind, { title: string; description: string; submit: string; initial: FormState }> = {
    own: {
      title: "Add your character",
      description:
        "A character you play, as it appears on Warcraft Logs. The agent treats all your characters as you.",
      submit: "Add character",
      initial: EMPTY,
    },
    friend: {
      title: "Add a friend",
      description: "Track a raid-mate's character so you can ask about them by name.",
      submit: "Add friend",
      initial: EMPTY,
    },
    guild: {
      title: guild ? "Replace main guild" : "Set main guild",
      description: "The guild whose raids and roster the agent should know about.",
      submit: guild ? "Replace guild" : "Set guild",
      initial: guild ? { name: guild.name, server: guild.server, region: guild.region } : EMPTY,
    },
  };
  const copy = dialogCopy[dialog ?? "own"];

  if (!profile && !err) return <CardsSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      {err && (
        <StatusAlert tone="error" onDismiss={() => setErr(null)}>
          {err}
        </StatusAlert>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className={SECTION_TITLE}>Your characters</CardTitle>
            <CardDescription>
              {ownFull
                ? `Maximum of ${ownLimit} characters.`
                : "Every character you play. The agent treats all of them as you."}
            </CardDescription>
            {own.length > 0 && (
              <CardAction>
                <Button size="sm" disabled={busy || ownFull} onClick={() => openDialog("own")}>
                  <LuUserPlus />
                  Add character
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent>
            {own.length > 0 ? (
              <CharacterList
                chars={own}
                busy={busy}
                removeLabel="Remove character"
                onRoleChange={(c, role) => void runInline(() => updateOwnCharacter(c.id, role))}
                onRemove={(c) => setPendingRemove({ kind: "own", char: c })}
              />
            ) : (
              <Empty className="border border-dashed p-6 md:p-8">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <LuUser />
                  </EmptyMedia>
                  <EmptyTitle>No characters yet</EmptyTitle>
                  <EmptyDescription>
                    Tell the agent who you play so it can tailor answers and fetch your class guides.
                  </EmptyDescription>
                </EmptyHeader>
                <EmptyContent>
                  <Button onClick={() => openDialog("own")}>
                    <LuUserPlus />
                    Add your character
                  </Button>
                </EmptyContent>
              </Empty>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className={SECTION_TITLE}>Main guild</CardTitle>
            <CardDescription>Your raid team's home.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1">
            {guild ? (
              <div className="flex items-center gap-3">
                <Avatar className="size-12 border-2 border-primary/50" aria-hidden="true">
                  <AvatarFallback className="bg-primary/10 text-glow">
                    <LuCastle className="size-5" />
                  </AvatarFallback>
                </Avatar>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="truncate font-semibold">{guild.name}</span>
                  <span className="text-sm text-muted-foreground">{realmLabel(guild)}</span>
                  <GuideBadge status={guild.summary_status} />
                </div>
              </div>
            ) : (
              <Empty className="border border-dashed p-6">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <LuCastle />
                  </EmptyMedia>
                  <EmptyTitle>No guild set</EmptyTitle>
                </EmptyHeader>
                <EmptyContent>
                  <Button size="sm" onClick={() => openDialog("guild")}>
                    Set guild
                  </Button>
                </EmptyContent>
              </Empty>
            )}
          </CardContent>
          {guild && (
            <CardFooter className="gap-2">
              <Button variant="secondary" size="sm" disabled={busy} onClick={() => openDialog("guild")}>
                Replace
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto size-8 text-muted-foreground hover:text-destructive"
                disabled={busy}
                onClick={() => setPendingRemove({ kind: "guild", guild })}
                aria-label="Remove guild"
                title="Remove guild"
              >
                <LuTrash2 />
              </Button>
            </CardFooter>
          )}
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className={SECTION_TITLE}>Friends</CardTitle>
            <CardDescription>
              {friends.length === 1 ? "1 character" : `${friends.length} characters`} you can ask about by name.
            </CardDescription>
            {friends.length > 0 && (
              <CardAction>
                <Button size="sm" disabled={busy} onClick={() => openDialog("friend")}>
                  <LuUserPlus />
                  Add friend
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent>
            {friends.length > 0 ? (
              <CharacterList
                chars={friends}
                busy={busy}
                removeLabel="Remove friend"
                onRoleChange={(c, role) => void runInline(() => updateFriend(c.id, role))}
                onRemove={(c) => setPendingRemove({ kind: "friend", char: c })}
              />
            ) : (
              <Empty className="border border-dashed p-6 md:p-8">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <LuUsers />
                  </EmptyMedia>
                  <EmptyTitle>No friends yet</EmptyTitle>
                  <EmptyDescription>Add raid-mates to compare logs and ask about them by name.</EmptyDescription>
                </EmptyHeader>
                <EmptyContent>
                  <Button onClick={() => openDialog("friend")}>
                    <LuUserPlus />
                    Add friend
                  </Button>
                </EmptyContent>
              </Empty>
            )}
          </CardContent>
        </Card>
      </div>

      <IdentityDialog
        open={dialog !== null}
        title={copy.title}
        description={copy.description}
        submitLabel={copy.submit}
        initial={copy.initial}
        busy={busy}
        error={dialogErr}
        onSubmit={(v) => void submitDialog(v)}
        onClose={() => setDialog(null)}
      />

      <ConfirmDialog
        open={pendingRemove !== null}
        title={
          pendingRemove?.kind === "guild"
            ? "Remove guild?"
            : pendingRemove?.kind === "own"
              ? "Remove character?"
              : "Remove friend?"
        }
        description={
          pendingRemove?.kind === "guild"
            ? `${pendingRemove.guild.name}-${pendingRemove.guild.server} (${pendingRemove.guild.region}) will be removed as your main guild.`
            : pendingRemove
              ? `${identityLabel(pendingRemove.char)} will be removed from your ${
                  pendingRemove.kind === "own" ? "characters" : "friends"
                }.`
              : ""
        }
        confirmLabel="Remove"
        busy={busy}
        onConfirm={async () => {
          const target = pendingRemove;
          if (!target) return;
          await runInline(() =>
            target.kind === "guild"
              ? deleteGuild()
              : target.kind === "own"
                ? deleteOwnCharacter(target.char.id)
                : deleteFriend(target.char.id),
          );
          setPendingRemove(null);
        }}
        onCancel={() => setPendingRemove(null)}
      />
    </div>
  );
}
