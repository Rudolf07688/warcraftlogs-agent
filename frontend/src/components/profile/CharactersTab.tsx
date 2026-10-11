import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  addFriend,
  deleteFriend,
  deleteGuild,
  getProfile,
  putGuild,
  putSelf,
  updateFriend,
} from "../../api/restClient";
import type { Character, GuideStatus, Guild, Profile, RaidRole } from "../../types";
import { ConfirmDialog } from "../ConfirmDialog";
import { StatusAlert } from "../StatusAlert";
import { GUIDE_LABEL_SHORT, GUIDE_TONE, StatusBadge } from "../StatusBadge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";

// Characters tab (feature 008 / US1): self, friends (unlimited), raid roles, and the single
// main guild. Extracted verbatim-in-behavior from the former ProfilePanel modal — same
// endpoints, same friendly duplicate message — restyled for the themed profile page.

const REGIONS = ["US", "EU", "KR", "TW", "CN"];

function GuideBadge({ status }: { status: GuideStatus }) {
  if (status === "none") return null;
  return <StatusBadge tone={GUIDE_TONE[status]}>{GUIDE_LABEL_SHORT[status]}</StatusBadge>;
}

function identityLabel(c: Character): string {
  const spec = [c.class_name, c.active_spec].filter(Boolean).join(" ");
  const base = `${c.name}-${c.server} (${c.region})`;
  return spec ? `${base} — ${spec}` : base;
}

// US4: raid-role picker. "Auto" (empty value) clears the override so the role falls
// back to the spec-inferred default; when auto is selected we annotate the inferred role.
const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Auto" },
  { value: "tank", label: "Tank" },
  { value: "healer", label: "Healer" },
  { value: "dps", label: "DPS" },
];

const ROLE_LABEL: Record<RaidRole, string> = { tank: "Tank", healer: "Healer", dps: "DPS" };

function RoleControl({
  char,
  busy,
  onChange,
}: {
  char: Character;
  busy: boolean;
  onChange: (role: RaidRole | null) => void;
}) {
  const isInferred = char.raid_role == null && char.effective_role != null;
  return (
    <span className="profile-role" title="Raid role">
      <NativeSelect
        size="sm"
        aria-label="Raid role"
        value={char.raid_role ?? ""}
        disabled={busy}
        onChange={(e) => onChange((e.target.value || null) as RaidRole | null)}
      >
        {ROLE_OPTIONS.map((o) => (
          <NativeSelectOption key={o.value} value={o.value}>
            {o.label}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      {isInferred && char.effective_role && (
        <span className="role-inferred" title="Inferred from spec">
          {ROLE_LABEL[char.effective_role]} (inferred)
        </span>
      )}
    </span>
  );
}

interface FormState {
  name: string;
  server: string;
  region: string;
}

const EMPTY: FormState = { name: "", server: "", region: "US" };

function IdentityForm({
  initial,
  submitLabel,
  onSubmit,
  busy,
}: {
  initial: FormState;
  submitLabel: string;
  onSubmit: (v: FormState) => void;
  busy: boolean;
}) {
  const [form, setForm] = useState<FormState>(initial);
  useEffect(() => setForm(initial), [initial.name, initial.server, initial.region]); // eslint-disable-line react-hooks/exhaustive-deps

  const canSubmit = form.name.trim() && form.server.trim() && !busy;
  return (
    <form
      className="profile-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) onSubmit({ ...form, name: form.name.trim(), server: form.server.trim() });
      }}
    >
      <Input
        className="flex-1 min-w-[90px]"
        aria-label="Name"
        placeholder="Name"
        value={form.name}
        onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
      />
      <Input
        className="flex-1 min-w-[90px]"
        aria-label="Server"
        placeholder="Server"
        value={form.server}
        onChange={(e) => setForm((f) => ({ ...f, server: e.target.value }))}
      />
      <NativeSelect
        aria-label="Region"
        value={form.region}
        onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}
      >
        {REGIONS.map((r) => (
          <NativeSelectOption key={r} value={r}>
            {r}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <Button type="submit" disabled={!canSubmit}>
        {submitLabel}
      </Button>
    </form>
  );
}

export function CharactersTab() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Feature 010 / FR-006: the friend or guild awaiting the in-app remove confirmation.
  const [pendingRemove, setPendingRemove] = useState<
    { kind: "friend"; friend: Character } | { kind: "guild"; guild: Guild } | null
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
      profile.self?.guide_status === "pending" ||
      profile.friends.some((f) => f.guide_status === "pending") ||
      profile.guild?.summary_status === "pending";
    if (!pending) return;
    const t = setTimeout(() => void refresh(), 4000);
    return () => clearTimeout(t);
  }, [profile, refresh]);

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
        await refresh();
        setErr(null);
      } catch {
        setErr("That action failed. Check the details and try again.");
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  // Adding a friend has a distinct, expected failure (duplicate) that deserves a
  // friendly message rather than the generic one (US4 / FR-023).
  const addFriendHandler = useCallback(
    async (v: FormState) => {
      setBusy(true);
      try {
        await addFriend(v);
        await refresh();
        setErr(null);
      } catch (e) {
        if (e instanceof ApiError && (e.status === 409 || e.message === "duplicate_friend")) {
          setErr(`${v.name}-${v.server} (${v.region}) is already added.`);
        } else {
          setErr("That action failed. Check the details and try again.");
        }
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const self = profile?.self ?? null;
  const guild: Guild | null = profile?.guild ?? null;

  return (
    <div className="profile-tabpanel">
      {err && <StatusAlert tone="error">{err}</StatusAlert>}

      <section className="profile-section">
        <h3>You</h3>
        {self && (
          <div className="profile-row">
            <span>{identityLabel(self)}</span>
            <RoleControl
              char={self}
              busy={busy}
              onChange={(role) =>
                run(() =>
                  putSelf({
                    name: self.name,
                    server: self.server,
                    region: self.region,
                    raid_role: role,
                  }),
                )
              }
            />
            <GuideBadge status={self.guide_status} />
          </div>
        )}
        <IdentityForm
          initial={self ? { name: self.name, server: self.server, region: self.region } : EMPTY}
          submitLabel={self ? "Update" : "Set self"}
          busy={busy}
          onSubmit={(v) => run(() => putSelf({ ...v, raid_role: self?.raid_role ?? null }))}
        />
      </section>

      <section className="profile-section">
        <h3>Friends</h3>
        {profile?.friends.map((f) => (
          <div className="profile-row" key={f.id}>
            <span>{identityLabel(f)}</span>
            <RoleControl
              char={f}
              busy={busy}
              onChange={(role) => run(() => updateFriend(f.id, role))}
            />
            <GuideBadge status={f.guide_status} />
            <Button
              variant="ghost"
              size="icon"
              className="size-7"
              disabled={busy}
              onClick={() => setPendingRemove({ kind: "friend", friend: f })}
              aria-label="Remove friend"
              title="Remove friend"
            >
              ✕
            </Button>
          </div>
        ))}
        <IdentityForm initial={EMPTY} submitLabel="Add friend" busy={busy} onSubmit={addFriendHandler} />
      </section>

      <section className="profile-section">
        <h3>Main guild</h3>
        {guild && (
          <div className="profile-row">
            <span>
              {guild.name}-{guild.server} ({guild.region})
            </span>
            <GuideBadge status={guild.summary_status} />
            <Button
              variant="ghost"
              size="icon"
              className="size-7"
              disabled={busy}
              onClick={() => setPendingRemove({ kind: "guild", guild })}
              aria-label="Remove guild"
              title="Remove guild"
            >
              ✕
            </Button>
          </div>
        )}
        <IdentityForm
          initial={guild ? { name: guild.name, server: guild.server, region: guild.region } : EMPTY}
          submitLabel={guild ? "Replace guild" : "Set guild"}
          busy={busy}
          onSubmit={(v) => run(() => putGuild(v))}
        />
      </section>

      <ConfirmDialog
        open={pendingRemove !== null}
        title={pendingRemove?.kind === "guild" ? "Remove guild?" : "Remove friend?"}
        description={
          pendingRemove?.kind === "guild"
            ? `${pendingRemove.guild.name}-${pendingRemove.guild.server} (${pendingRemove.guild.region}) will be removed as your main guild.`
            : pendingRemove
              ? `${identityLabel(pendingRemove.friend)} will be removed from your friends.`
              : ""
        }
        confirmLabel="Remove"
        busy={busy}
        onConfirm={async () => {
          const target = pendingRemove;
          if (!target) return;
          await run(() => (target.kind === "guild" ? deleteGuild() : deleteFriend(target.friend.id)));
          setPendingRemove(null);
        }}
        onCancel={() => setPendingRemove(null)}
      />
    </div>
  );
}
