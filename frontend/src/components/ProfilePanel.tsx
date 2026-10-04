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
} from "../api/restClient";
import type { Character, GuideStatus, Guild, Profile, RaidRole } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

const REGIONS = ["US", "EU", "KR", "TW", "CN"];

const STATUS_LABEL: Record<GuideStatus, string> = {
  none: "",
  pending: "guide loading…",
  ready: "guide ready",
  failed: "guide unavailable",
};

function StatusBadge({ status }: { status: GuideStatus }) {
  if (status === "none") return null;
  return <span className={`guide-badge guide-${status}`}>{STATUS_LABEL[status]}</span>;
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
      <select
        aria-label="Raid role"
        value={char.raid_role ?? ""}
        disabled={busy}
        onChange={(e) => onChange((e.target.value || null) as RaidRole | null)}
      >
        {ROLE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
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
      <input
        placeholder="Name"
        value={form.name}
        onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
      />
      <input
        placeholder="Server"
        value={form.server}
        onChange={(e) => setForm((f) => ({ ...f, server: e.target.value }))}
      />
      <select
        value={form.region}
        onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}
      >
        {REGIONS.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <button type="submit" disabled={!canSubmit}>
        {submitLabel}
      </button>
    </form>
  );
}

export function ProfilePanel({ open, onClose }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProfile(await getProfile());
      setErr(null);
    } catch {
      setErr("Could not load your profile.");
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  // Poll while any guide is still resolving so the badges flip to "ready" on their own.
  useEffect(() => {
    if (!open || !profile) return;
    const pending =
      profile.self?.guide_status === "pending" ||
      profile.friends.some((f) => f.guide_status === "pending") ||
      profile.guild?.summary_status === "pending";
    if (!pending) return;
    const t = setTimeout(() => void refresh(), 4000);
    return () => clearTimeout(t);
  }, [open, profile, refresh]);

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

  if (!open) return null;

  const self = profile?.self ?? null;
  const guild: Guild | null = profile?.guild ?? null;

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-label="Profile">
      <div className="profile-panel">
        <header className="profile-header">
          <h2>Your profile</h2>
          <button className="profile-close" onClick={onClose} title="Close">
            ✕
          </button>
        </header>

        {err && <div className="profile-error">{err}</div>}

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
              <StatusBadge status={self.guide_status} />
            </div>
          )}
          <IdentityForm
            initial={
              self ? { name: self.name, server: self.server, region: self.region } : EMPTY
            }
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
              <StatusBadge status={f.guide_status} />
              <button
                className="profile-remove"
                disabled={busy}
                onClick={() => run(() => deleteFriend(f.id))}
                title="Remove friend"
              >
                ✕
              </button>
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
              <StatusBadge status={guild.summary_status} />
              <button
                className="profile-remove"
                disabled={busy}
                onClick={() => run(() => deleteGuild())}
                title="Remove guild"
              >
                ✕
              </button>
            </div>
          )}
          <IdentityForm
            initial={
              guild ? { name: guild.name, server: guild.server, region: guild.region } : EMPTY
            }
            submitLabel={guild ? "Replace guild" : "Set guild"}
            busy={busy}
            onSubmit={(v) => run(() => putGuild(v))}
          />
        </section>
      </div>
    </div>
  );
}
